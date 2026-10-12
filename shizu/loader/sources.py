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
from pathlib import PurePosixPath

import requests

from shizu import health, utils
from shizu.inter import inter
from shizu.integrity import IntegrityError, runtime
from shizu.remote import RemoteModuleError

from .compiler import ModuleCompiler
from .provenance import CORE_MODULES_PATH, is_core_source
from .storage import migrate_legacy_modules


class ModuleSources:
    """Read local plugins and resolve pinned remote sources in startup order."""

    def __init__(self, manager):
        self.manager = manager

    async def load_local(self):
        manager = self.manager
        release = runtime.get_release()
        release.verify_tree()
        # Load the bundled directory before any reviewed third-party code.
        for relative in sorted(release.files):
            entry = PurePosixPath(relative)
            if (
                not relative.startswith("shizu/modules/core/")
                or len(entry.parts) != 4
                or entry.name.startswith("_")
            ):
                continue
            path = CORE_MODULES_PATH / entry.name
            source_code = release.read(relative).decode("utf-8")
            manager._register_local(f"shizu.modules.{path.stem}", str(path), source_code)

        reserved_names = {
            PurePosixPath(relative).name
            for relative in release.files
            if relative.startswith("shizu/modules/core/")
        }
        migrate_legacy_modules(
            CORE_MODULES_PATH.parent, manager._local_modules_path, reserved_names
        )
        deferred = []
        for local_module in sorted(os.listdir(manager._local_modules_path)):
            if not local_module.endswith(".py") or local_module.startswith("_"):
                continue
            module_name = f"shizu.modules.{local_module[:-3]}"
            file_path = os.path.abspath(
                os.path.join(manager._local_modules_path, local_module)
            )
            try:
                with open(file_path, encoding="utf-8") as f:
                    source_code = f.read()
            except Exception:
                logging.exception("Failed to read local module %s", local_module)
                continue
            deferred.append((module_name, file_path, source_code))

        await manager.send_on_loads()

        if manager.safe_mode.active:
            deferred = []

        for module_name, file_path, source_code in deferred:
            if manager.load_guard:
                try:
                    if await manager.load_guard(source_code, file_path) is not True:
                        continue
                except Exception:
                    logging.exception("load_guard failed for %s", file_path)
                    continue
            with manager.safe_mode.loading(file_path):
                manager._register_local(module_name, file_path, source_code)

        await manager.send_on_loads()

    async def load_remote(self):
        manager = self.manager
        for custom_module in list(manager._db.get("shizu.loader", "modules", [])):
            try:
                with manager.safe_mode.loading(custom_module):
                    await manager.load_remote_module(custom_module)
            except (RemoteModuleError, requests.exceptions.RequestException, OSError):
                continue

    def register_local(self, module_name: str, file_path: str, source_code: str):
        manager = self.manager
        try:
            if not is_core_source(module_name, file_path) and manager._is_telethon_module(
                source_code
            ):
                if not utils.is_tl_enabled(manager._app):
                    return
                spec = ModuleCompiler.source_spec(
                    module_name,
                    inter.transform(source_code),
                    file_path,
                    has_location=True,
                )
                manager.register_instance(module_name, spec=spec, is_telethon=True)
            else:
                manager.register_instance(module_name, file_path)
        except IntegrityError:
            raise
        except utils.PremiumRequired:
            logging.info("Skipped Premium module %s", file_path)
        except Exception:
            logging.exception("Failed to load local module %s", file_path)

    def headers(self, url: str) -> dict | None:
        manager = self.manager
        module = manager.find_module_strict("ShizuLoader")
        return module._remote_headers(url) if module else None

    def report_problem(self, url: str, error: Exception):
        logging.error("Remote code blocked for %s: %s", url, error)
        health.reporter.problem(
            f"remote_source:{url}",
            "🛡 <b>Remote code was not loaded</b>\n"
            f"<code>{utils.escape_html(url)}</code>\n\n"
            f"{utils.escape_html(str(error))}",
        )

    async def resolve(self, url: str, headers=None, *, kind="module"):
        manager = self.manager
        try:
            url = manager.remote_modules.source_url(url)
            return await manager.remote_modules.resolve(
                url,
                headers
                or manager._remote_headers(manager.remote_modules.normalize_url(url)),
                kind=kind,
            )
        except (
            RemoteModuleError,
            requests.exceptions.RequestException,
            OSError,
        ) as error:
            manager._remote_problem(url, error)
            raise
