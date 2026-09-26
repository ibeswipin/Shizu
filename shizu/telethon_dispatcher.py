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
import re
import traceback
from typing import TYPE_CHECKING

from telethon import events

from shizu import utils
from shizu.dispatcher import security_manager

if TYPE_CHECKING:
    from shizu.loader import ModulesManager

logger = logging.getLogger(__name__)


def _flag(func, name: str):
    return getattr(getattr(func, "__func__", func), name, None)


def _rules(message, prefixes) -> dict:
    text = message.raw_text or ""
    channel = bool(message.is_channel and not message.is_group)
    mentioned = bool(getattr(message, "mentioned", False))
    return {
        "out": message.out,
        "in": not message.out,
        "only_pm": message.is_private,
        "no_pm": not message.is_private,
        "only_groups": message.is_group,
        "no_groups": not message.is_group,
        "only_channels": channel,
        "no_channels": not channel,
        "only_media": bool(message.media),
        "no_media": not message.media,
        "only_photos": bool(message.photo),
        "no_photos": not message.photo,
        "only_videos": bool(message.video),
        "no_videos": not message.video,
        "only_audios": bool(message.audio or message.voice),
        "no_audios": not (message.audio or message.voice),
        "only_docs": bool(message.document) and not (message.sticker or message.video or message.audio or message.voice or message.gif),
        "no_docs": not message.document,
        "only_stickers": bool(message.sticker),
        "no_stickers": not message.sticker,
        "only_forwards": bool(message.fwd_from),
        "no_forwards": not message.fwd_from,
        "only_reply": bool(message.is_reply),
        "no_reply": not message.is_reply,
        "only_inline": bool(message.via_bot_id),
        "no_inline": not message.via_bot_id,
        "mention": mentioned,
        "no_mention": not mentioned,
        "only_messages": True,
        "editable": bool(message.out and not message.fwd_from),
        "only_commands": any(text.startswith(p) for p in prefixes),
        "no_commands": not any(text.startswith(p) for p in prefixes),
    }


def _values_accept(values: dict, message) -> bool:
    text = message.raw_text or ""
    checks = {
        "startswith": lambda v: text.startswith(v),
        "endswith": lambda v: text.endswith(v),
        "contains": lambda v: v in text,
        "regex": lambda v: re.search(v, text) is not None,
        "from_id": lambda v: message.sender_id == v,
        "chat_id": lambda v: message.chat_id == v,
        "filter": lambda v: bool(v(message)),
    }
    return all(checks[key](value) for key, value in values.items() if key in checks)


def filters_accept(func, message, prefixes, tags_attr: str, values_attr: str) -> bool:
    tags = _flag(func, tags_attr) or ()
    if tags:
        rules = _rules(message, prefixes)
        if not all(rules[tag] for tag in tags if tag in rules):
            return False
    return _values_accept(_flag(func, values_attr) or {}, message)


def watcher_accepts(watcher, message, prefixes) -> bool:
    legacy = {
        "watcher_no_commands": "no_commands",
        "watcher_no_stickers": "no_stickers",
        "watcher_no_docs": "no_docs",
        "watcher_no_audios": "no_audios",
        "watcher_no_videos": "no_videos",
        "watcher_no_photos": "no_photos",
        "watcher_no_forwards": "no_forwards",
    }
    enabled = [tag for attr, tag in legacy.items() if _flag(watcher, attr)]
    if enabled:
        rules = _rules(message, prefixes)
        if not all(rules[tag] for tag in enabled):
            return False
    return filters_accept(watcher, message, prefixes, "watcher_tags", "watcher_values")


class TelethonDispatcherManager:
    def __init__(self, client, modules: "ModulesManager") -> None:
        self.client = client
        self.modules = modules
        self.security = security_manager()
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

        self.client.dispatcher = self
        self.client.add_event_handler(self._on_new, events.NewMessage())
        self.client.add_event_handler(self._handle_command, events.MessageEdited())
        self._loaded = True
        return True

    def register_raw(self, module) -> None:
        registered = []
        for handler in getattr(module, "raw_handlers", None) or ():
            updates = handler.__func__.raw_handler_updates

            async def callback(update, handler=handler):
                try:
                    await handler(update)
                except Exception:
                    logger.exception("Raw handler %s failed", handler.__name__)

            self.client.add_event_handler(callback, events.Raw(types=list(updates) or None))
            registered.append(callback)
        module._raw_callbacks = registered

    def unregister_raw(self, module) -> None:
        for callback in getattr(module, "_raw_callbacks", None) or ():
            self.client.remove_event_handler(callback)
        module._raw_callbacks = []

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

        if not filters_accept(func, message, self.prefixes, "tags", "tag_values"):
            return
        if not await self.security.check(message, func, command, self.client):
            return
        if (
            _flag(func, "ratelimit")
            and not message.out
            and self.security.rate_limited(message.sender_id, command)
        ):
            return

        self.modules.last_commands[message.chat_id] = (command, message)
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
