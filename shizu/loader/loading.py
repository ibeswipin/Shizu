# Shizu Copyright (C) 2023-2026  Ibeswipin

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


import hashlib
import logging
import os
import random
import re
import string
import subprocess
import sys

from shizu import loader, utils
from shizu import logger as logger_
from shizu.inter import inter
from shizu.redaction import SecretRedactor
from shizu.remote import RemoteModuleError
from shizu.translator import Translator

from .compiler import ModuleCompiler
from .dependencies import DependencyInstaller


class ModuleLoader:
    """Review source and retry imports after installing missing dependencies."""

    def __init__(self, manager):
        self.manager = manager

    @staticmethod
    def error_key(source, origin):
        return origin, hashlib.sha256(source.encode()).hexdigest()

    def _fail(self, source, origin, error):
        reason = (
            str(error) if isinstance(error, str) else f"{type(error).__name__}: {error}"
        )
        reason = SecretRedactor.text(reason)[:2000]
        errors = getattr(self.manager, "module_load_errors", None)
        if errors is None:
            errors = self.manager.module_load_errors = {}
        if len(errors) >= 64:
            errors.pop(next(iter(errors)))
        errors[self.error_key(source, origin)] = reason
        logging.error(
            "Failed to load module from %s: %s", SecretRedactor.text(origin), reason
        )
        return False

    async def _notice(self, text):
        try:
            await self.manager.bot_manager.bot.send_message(
                self.manager._db.get("shizu.chat", "logs", None),
                SecretRedactor.text(text),
                parse_mode="html",
            )
        except Exception:
            logging.debug("Could not send module loading notice", exc_info=True)

    async def load(
        self,
        module_source: str,
        origin: str = "<string>",
        did_requirements: bool = False,
    ) -> str:
        """Loads a third-party module"""
        manager = self.manager

        original_source = module_source
        getattr(manager, "module_load_errors", {}).pop(
            self.error_key(original_source, origin), None
        )

        remote = manager.remote_modules.is_remote(origin)
        if remote:
            try:
                manager.remote_modules.check_source(origin, original_source)
            except RemoteModuleError as error:
                manager._remote_problem(origin, error)
                raise

        if manager.load_guard:
            verdict = await manager.load_guard(module_source, origin)
            if verdict is not True:
                return verdict

        if remote:
            manager.remote_modules.remember(origin, original_source)

        is_telethon = manager._is_telethon_module(original_source)

        if is_telethon:
            if not await manager._telethon_ready():
                return "OTL"
            try:
                module_source = inter.transform(original_source)
            except Exception as error:
                return self._fail(original_source, origin, error)
        else:
            module_source = original_source

        module_name = f"shizu.modules.{manager.me.id}-{''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))}"
        pattern = re.compile(
            r"@loader\.module\((.*?)\)\s*(?:@[^\n]+\n\s*)*class\s+(\w+)\(", re.S
        )

        if match := pattern.search(module_source):
            module_name = f"shizu.modules.{match[2]}"
        else:
            return self._fail(
                original_source,
                origin,
                "Module class with @loader.module was not found",
            )

        if match := re.search(r"# ?only: ?(.+)", module_source):
            allowed_accounts = match[1].split(",") if match else []
            if str((await manager._app.get_me()).id) not in allowed_accounts:
                return "NFA"

        if (
            re.search(r"# ?tl-only", module_source)
            and not await manager._telethon_ready()
        ):
            return "OTL"
        if remote:
            manager.remote_modules.check_source(origin, original_source)
        previous_source = manager.raw_modules.get(module_name)
        manager.raw_modules[module_name] = original_source
        await utils.refresh_premium(manager)
        attempted = set()
        for attempt in range(6):
            try:
                spec = ModuleCompiler.source_spec(
                    module_name,
                    module_source,
                    origin,
                    has_location=bool(origin) and os.path.isfile(origin),
                )

                instance = manager.register_instance(
                    module_name, spec=spec, is_telethon=is_telethon
                )
            except utils.PremiumRequired:
                if previous_source is None:
                    manager.raw_modules.pop(module_name, None)
                else:
                    manager.raw_modules[module_name] = previous_source
                return "PREMIUM_REQUIRED"
            except ImportError as error:
                requirements = (
                    []
                    if did_requirements
                    else DependencyInstaller.declared_requirements(original_source)
                )
                if not requirements:
                    requirement = DependencyInstaller.missing_requirement(error)
                    if requirement:
                        requirements = [requirement]
                fresh = {
                    re.split(r"[<>=!~\[ @]", item, maxsplit=1)[0]
                    .lower()
                    .replace("_", "-")
                    for item in requirements
                }
                if not requirements or fresh & attempted or attempt == 5:
                    return self._fail(original_source, origin, error)
                attempted.update(fresh)
                did_requirements = True
                await self._notice(
                    "⤵️ <b>Installing packages:</b> "
                    f"<code>{utils.escape_html(', '.join(requirements))}</code>..."
                )
                try:
                    await loader._install_requirements(requirements)
                except (subprocess.CalledProcessError, OSError) as install_error:
                    output = manager._pip_error(install_error)
                    reason = (
                        f"Could not install {', '.join(requirements)}: {output[-1500:]}"
                    )
                    self._fail(original_source, origin, reason)
                    await self._notice(
                        "🚫 <b>Failed to install module dependencies</b>\n"
                        f"<pre>{utils.escape_html(SecretRedactor.text(reason))}</pre>"
                    )
                    return False
            except Exception as error:
                logging.exception("Failed to load module %s", module_name)
                self._fail(original_source, origin, error)
                item = logger_.CustomException.from_exc_info(*sys.exc_info())
                await self._notice(
                    "🚫 <b>Error while loading module</b>\n\n" + item.full_stack
                )
                return False
            else:
                break

        if not instance:
            return self._fail(
                original_source, origin, "No module instance was registered"
            )

        try:
            manager.config_reconfigure(instance, manager._db)
            if not await manager.send_on_load(
                instance, Translator(manager._app, manager._db)
            ):
                return self._fail(
                    original_source,
                    origin,
                    getattr(instance, "_load_error", None)
                    or "Module startup did not complete",
                )
        except Exception as error:
            logging.exception("Failed to start module %s", instance.name)
            return self._fail(original_source, origin, error)

        if remote:
            manager.remote_modules.install(origin, original_source)
        return instance.name
