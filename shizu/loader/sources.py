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

import requests

from shizu import health, utils
from shizu.inter import inter
from shizu.remote import RemoteModuleError

from .compiler import ModuleCompiler


class ModuleSources:
    """Read local plugins and resolve pinned remote sources in startup order."""

    def __init__(self, manager):
        self.manager = manager

    async def load_local(self):
        manager = self.manager
        modules_list = sorted(
            filter(
                lambda file_name: (
                    file_name.endswith(".py") and not file_name.startswith("_")
                ),
                os.listdir(manager._local_modules_path),
            )
        )

        deferred = []
        for local_module in modules_list:
            module_name = f"shizu.modules.{local_module[:-3]}"
            file_path = os.path.join(
                os.path.abspath("."), manager._local_modules_path, local_module
            )
            try:
                with open(file_path, encoding="utf-8") as f:
                    source_code = f.read()
            except Exception:
                logging.exception("Failed to read local module %s", local_module)
                continue

            if local_module[:-3] not in manager.cmodules:
                deferred.append((module_name, file_path, source_code))
                continue

            manager._register_local(module_name, file_path, source_code)

        await manager.send_on_loads()

        for module_name, file_path, source_code in deferred:
            if manager.load_guard:
                try:
                    if await manager.load_guard(source_code, file_path) is not True:
                        continue
                except Exception:
                    logging.exception("load_guard failed for %s", file_path)
                    continue
            manager._register_local(module_name, file_path, source_code)

        await manager.send_on_loads()

    async def load_remote(self):
        manager = self.manager
        for custom_module in list(manager._db.get("shizu.loader", "modules", [])):
            try:
                await manager.load_remote_module(custom_module)
            except (RemoteModuleError, requests.exceptions.RequestException, OSError):
                continue

    def register_local(self, module_name: str, file_path: str, source_code: str):
        manager = self.manager
        try:
            if manager._is_telethon_module(source_code):
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
            manager.remote_modules.validate_url(url)
            return await manager.remote_modules.resolve(
                url, headers or manager._remote_headers(url), kind=kind
            )
        except (
            RemoteModuleError,
            requests.exceptions.RequestException,
            OSError,
        ) as error:
            manager._remote_problem(url, error)
            raise
