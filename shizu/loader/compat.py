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


import inspect
import logging
import re

from shizu import dispatcher, utils
from shizu.telegram.exceptions import TelegramConnectionError


class TelethonCompatibility:
    """Detect Telethon plugins and maintain their dispatcher and client bindings."""

    def __init__(self, manager):
        self.manager = manager

    @staticmethod
    def detect_source(source_code: str) -> bool:
        """Checks if the module is a Telethon module"""
        telethon_patterns = [
            r"@loader\.tds\b",
            r"async def \w+\(self,\s*message\)",
            r"from \.\.inline\b",
            r'"telethon"',
            r"'telethon'",
            r"from telethon\.tl\.patched",
            r"from telethon\.tl\.types import Message",
            r"from telethon\.tl\.types import.*Message",
            r"(?m)^def register\(cb\)",
            r"(?m)^\s*(?:from|import)\s+(?:telethon|hikkatl)\b",
            r"strings\s*=\s*\{\s*[\"']name[\"']",
        ]

        if re.search(r"^\s*(?:from|import)\s+pyrogram\b", source_code, re.MULTILINE):
            return False

        return any(
            re.search(pattern, source_code, re.IGNORECASE)
            for pattern in telethon_patterns
        )

    async def ready(self) -> bool:
        """Verify Telethon again when the fast check fails and start its dispatcher"""
        manager = self.manager
        tl = getattr(manager._app, "tl", None)
        if not utils.is_tl_configured() or tl in (None, "Not enabled"):
            return False
        if not utils.is_tl_enabled(manager._app):
            try:
                await manager._app.telethon_connections.verify(tl, manager.me.id)
            except (TelegramConnectionError, AttributeError) as error:
                logging.warning("Telethon is unavailable: %s", error)
                return False
        if not utils.is_tl_enabled(manager._app):
            return False
        if manager.telethon_dp is None:
            manager.telethon_dp = dispatcher.TelethonDispatcherManager(tl, manager)
            await manager.telethon_dp.load()
            for module in manager.modules:
                if getattr(module, "m__telethon", False):
                    manager.telethon_dp.register_raw(module)
        return True

    def client(self):
        manager = self.manager
        tl = getattr(manager._app, "tl", None)
        return (
            tl
            if utils.is_tl_enabled(manager._app) and tl not in (None, "Not enabled")
            else manager._app
        )

    def configure_instance(self, instance):
        manager = self.manager
        explicitly_pyrogram = (
            hasattr(instance, "m__telethon") and instance.m__telethon is False
        )

        if instance.name in manager.cmodules:
            instance.m__telethon = False
        elif explicitly_pyrogram:
            instance.m__telethon = False
        elif not hasattr(instance, "m__telethon") or instance.m__telethon is not False:
            is_telethon_detected = False
            for handler in instance.command_handlers.values():
                try:
                    if hasattr(handler, "__func__"):
                        sig = inspect.signature(handler.__func__)
                        params = list(sig.parameters.keys())[1:]
                    else:
                        sig = inspect.signature(handler)
                        params = list(sig.parameters.keys())
                    if "message" in params and "app" not in params:
                        is_telethon_detected = True
                        break
                except (ValueError, TypeError, AttributeError):
                    continue

            if not is_telethon_detected:
                for watcher in instance.watcher_handlers:
                    try:
                        if hasattr(watcher, "__func__"):
                            sig = inspect.signature(watcher.__func__)
                            params = list(sig.parameters.keys())[1:]
                            param_annotations = {
                                name: sig.parameters[name].annotation
                                for name in params
                                if sig.parameters[name].annotation
                                != inspect.Parameter.empty
                            }
                        else:
                            sig = inspect.signature(watcher)
                            params = list(sig.parameters.keys())
                            param_annotations = {
                                name: sig.parameters[name].annotation
                                for name in params
                                if sig.parameters[name].annotation
                                != inspect.Parameter.empty
                            }

                        if (
                            len(params) >= 1
                            and "message" in params
                            and "app" not in params
                        ):
                            if "message" in param_annotations:
                                annotation = param_annotations["message"]
                                annotation_str = str(annotation)
                                if (
                                    "patched" in annotation_str
                                    or "telethon.tl" in annotation_str
                                ):
                                    is_telethon_detected = True
                                    break
                            else:
                                is_telethon_detected = True
                                break
                    except (ValueError, TypeError, AttributeError):
                        continue

            if is_telethon_detected:
                instance.m__telethon = True
