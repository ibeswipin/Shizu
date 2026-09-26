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
import traceback
from typing import TYPE_CHECKING

from telethon import events

from shizu import utils
from shizu.dispatcher import has_access

if TYPE_CHECKING:
    from shizu.loader import ModulesManager

logger = logging.getLogger(__name__)


def _flag(watcher, name: str):
    return getattr(getattr(watcher, "__func__", watcher), name, None)


def watcher_accepts(watcher, message, prefixes) -> bool:
    text = message.raw_text or ""
    if _flag(watcher, "watcher_no_commands") and any(
        text.startswith(p) for p in prefixes
    ):
        return False
    checks = {
        "watcher_no_stickers": message.sticker,
        "watcher_no_docs": message.document,
        "watcher_no_audios": message.audio,
        "watcher_no_videos": message.video,
        "watcher_no_photos": message.photo,
        "watcher_no_forwards": message.fwd_from,
    }
    if any(_flag(watcher, name) and value for name, value in checks.items()):
        return False
    tags = _flag(watcher, "watcher_tags") or ()
    rules = {
        "out": message.out,
        "in": not message.out,
        "only_pm": message.is_private,
        "no_pm": not message.is_private,
        "only_groups": message.is_group,
        "no_groups": not message.is_group,
        "only_channels": message.is_channel and not message.is_group,
        "no_channels": not (message.is_channel and not message.is_group),
        "only_media": bool(message.media),
        "no_media": not message.media,
    }
    return all(rules[tag] for tag in tags if tag in rules)


class TelethonDispatcherManager:
    def __init__(self, client, modules: "ModulesManager") -> None:
        self.client = client
        self.modules = modules
        self._loaded = False

    @property
    def prefixes(self) -> list:
        return self.modules._db.get("shizu.loader", "prefixes", ["."])

    async def load(self) -> bool:
        if self._loaded:
            return True
        if not self.client.is_connected():
            try:
                await self.client.connect()
            except Exception:
                logger.exception("Telethon client failed to connect")
                return False

        self.client.add_event_handler(self._on_new, events.NewMessage())
        self.client.add_event_handler(self._handle_command, events.MessageEdited())
        self._loaded = True
        return True

    async def _on_new(self, event):
        await self._handle_watchers(event.message)
        await self._handle_command(event)

    def _parse(self, text: str):
        for prefix in sorted(self.prefixes, key=len, reverse=True):
            if text.startswith(prefix):
                command, *_ = text[len(prefix) :].split(maxsplit=1) or [""]
                return prefix, command.lower()
        return None, None

    async def _handle_command(self, event):
        message = event.message
        prefix, command = self._parse(message.raw_text or "")
        if not command:
            return

        command = self.modules.aliases.get(command, command).lower()
        func = self.modules.command_handlers.get(command)
        module = getattr(func, "__self__", None)
        if not func or not getattr(module, "m__telethon", False):
            return

        if not message.out and not has_access(
            self.modules._db, message.sender_id, command
        ):
            return

        try:
            await func(message)
        except Exception:
            logger.exception("Command %s%s failed", prefix, command)
            trace = utils.escape_html(traceback.format_exc(limit=-5))
            try:
                await utils.answer(
                    message,
                    f"🥶 <b>Command <code>{utils.escape_html(prefix + command)}</code>"
                    f" failed with error:</b>\n\n<code>{trace}</code>",
                )
            except Exception:
                pass

    async def _handle_watchers(self, message):
        prefixes = self.prefixes
        for module in list(self.modules.modules):
            if not getattr(module, "m__telethon", False):
                continue
            for watcher in getattr(module, "watcher_handlers", None) or ():
                if not watcher_accepts(watcher, message, prefixes):
                    continue
                try:
                    await watcher(message)
                except Exception:
                    logger.exception("Watcher of module %s failed", module.name)
