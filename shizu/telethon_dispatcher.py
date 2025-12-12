# Shizu Copyright (C) 2023-2024  AmoreForever

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

from telethon import events
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shizu.loader import ModulesManager


class TelethonDispatcherManager:
    def __init__(self, client, modules: "ModulesManager") -> None:
        self.client = client
        self.modules = modules
        self._watcher_handler = None

    async def load(self) -> bool:
        if not self.client or not hasattr(self.client, "is_connected"):
            return False

        if not self.client.is_connected():
            try:
                await self.client.connect()
            except Exception:
                return False

        if not hasattr(self.client, '_event_builders'):
            self.client._event_builders = []

        async def handle_all_messages(event):
            await self._handle_watchers(event)

        self.client.add_event_handler(
            handle_all_messages,
            events.NewMessage()
        )
        self._watcher_handler = handle_all_messages
        return True

    async def _handle_watchers(self, event):
        if not self.modules or not self.modules.modules:
            return

        for module in self.modules.modules:
            if not hasattr(module, "m__telethon") or not module.m__telethon:
                continue

            if not hasattr(module, "watcher_handlers") or not module.watcher_handlers:
                continue
            
            module_name = getattr(module, "name", "unknown")

            message = event.message
            if not message:
                continue

            for watcher in module.watcher_handlers:
                try:
                    if not callable(watcher):
                        continue

                    func = watcher
                    if hasattr(watcher, "__func__"):
                        func = watcher.__func__
                    
                    watcher_only_messages = getattr(func, "watcher_only_messages", getattr(watcher, "watcher_only_messages", None))
                    if watcher_only_messages is not None and watcher_only_messages:
                        if not message.text and not message.raw_text:
                            continue

                    if getattr(func, "watcher_no_commands", getattr(watcher, "watcher_no_commands", False)):
                        prefixes = self.modules._db.get("shizu.loader", "prefixes", [".", "/"])
                        text = message.text or message.raw_text or ""
                        if text and any(text.startswith(prefix) for prefix in prefixes):
                            continue

                    if getattr(func, "watcher_no_stickers", getattr(watcher, "watcher_no_stickers", False)) and message.sticker:
                        continue
                    if getattr(func, "watcher_no_docs", getattr(watcher, "watcher_no_docs", False)) and message.document:
                        continue
                    if getattr(func, "watcher_no_audios", getattr(watcher, "watcher_no_audios", False)) and message.audio:
                        continue
                    if getattr(func, "watcher_no_videos", getattr(watcher, "watcher_no_videos", False)) and message.video:
                        continue
                    if getattr(func, "watcher_no_photos", getattr(watcher, "watcher_no_photos", False)) and message.photo:
                        continue
                    if getattr(func, "watcher_no_forwards", getattr(watcher, "watcher_no_forwards", False)) and message.fwd_from:
                        continue

                    try:
                        await watcher(message)
                    except Exception as e:
                        pass

                except Exception:
                    continue
