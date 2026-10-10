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
from shizu.remote import RemoteModuleError
from shizu.translator import Translator

from .compiler import ModuleCompiler
from .dependencies import VALID_PIP_PACKAGES


class ModuleLoader:
    """Review and load third-party source, retrying dependency installation once."""

    def __init__(self, manager):
        self.manager = manager

    async def load(
        self,
        module_source: str,
        origin: str = "<string>",
        did_requirements: bool = False,
    ) -> str:
        """Loads a third-party module"""
        manager = self.manager

        original_source = module_source

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
            module_source = inter.transform(original_source)
        else:
            module_source = original_source

        module_name = f"shizu.modules.{manager.me.id}-{''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))}"
        pattern = re.compile(r"@loader\.module\((.*?)\)\nclass\s+(\w+)\(")

        if match := pattern.search(module_source):
            module_name = f"shizu.modules.{match[2]}"
        else:
            return False

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
        manager.raw_modules[module_name] = original_source
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

        except ImportError:
            logging.exception("Failed to import module %s", module_name)

            if did_requirements:
                await manager.bot_manager.bot.send_message(
                    manager._db.get("shizu.chat", "logs", None),
                    "🚫 Dependencies were installed, but the module still cannot be imported. "
                    "See the application log for details.",
                )
                return False
            try:
                requirements = [
                    x
                    for x in map(
                        str.strip,
                        VALID_PIP_PACKAGES.search(module_source)[1].split(" "),
                    )
                    if x and x[0] not in ("-", "_", ".")
                ]
            except TypeError:
                return False

            await manager.bot_manager.bot.send_message(
                manager._db.get("shizu.chat", "logs", None),
                f"⤵️ <b>Installing packages:</b> <code>{', '.join(requirements)}</code>...",
            )

            try:
                await loader._install_requirements(requirements)
            except (subprocess.CalledProcessError, OSError) as error:
                output = manager._pip_error(error)
                logging.error(
                    "Failed to install module dependencies %s:\n%s",
                    requirements,
                    output,
                )
                await manager.bot_manager.bot.send_message(
                    manager._db.get("shizu.chat", "logs", None),
                    "🚫 <b>Failed to install module dependencies</b> "
                    f"<code>{utils.escape_html(' '.join(requirements))}</code>\n\n"
                    f"<pre>{utils.escape_html(output[-3000:])}</pre>",
                )
                return False

            return await manager.load_module(original_source, origin, True)
        except Exception:
            item = logger_.CustomException.from_exc_info(*sys.exc_info())
            exc = (
                "🚫 <b>Error while loading module</b>"
                "\n\n"
                + "\n".join(item.full_stack.splitlines()[:-1])
                + "\n\n"
                + "😵 "
                + item.full_stack.splitlines()[-1]
            )
            await manager.bot_manager.bot.send_message(
                manager._db.get("shizu.chat", "logs", None), exc, parse_mode="html"
            )
            return False

        if not instance:
            return False

        try:
            manager.config_reconfigure(instance, manager._db)
            if not await manager.send_on_load(
                instance, Translator(manager._app, manager._db)
            ):
                return False
        except Exception:
            logging.exception("Failed to start module %s", instance.name)
            return False

        if remote:
            manager.remote_modules.install(origin, original_source)
        return instance.name
