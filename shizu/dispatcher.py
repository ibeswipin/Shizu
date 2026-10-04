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

import contextlib
import inspect
import logging
import random
import re
import sys
import traceback
from types import FunctionType

from pyrogram import Client, filters, types
from pyrogram.handlers import MessageHandler, EditedMessageHandler
from telethon import events

from shizu.health import reporter
from shizu.besafe import BeSafe
from shizu import loader, utils, database, logger as lo
from shizu.security import SecurityManager

logger = logging.getLogger(__name__)


class BaseDispatcherManager:
    """Shared access control and handler metadata for both Telegram clients."""

    _security: SecurityManager | None = None

    def __init__(self, client, modules: "loader.ModulesManager") -> None:
        self.client = client
        self.modules = modules
        self.security = self.security_manager()

    @classmethod
    def security_manager(cls) -> SecurityManager:
        """Return the same permissions and rate limits for both dispatchers."""
        if BaseDispatcherManager._security is None:
            BaseDispatcherManager._security = SecurityManager(database.db)
        return BaseDispatcherManager._security

    @classmethod
    def has_access(cls, user_id: int, command_name: str | None = None) -> bool:
        return cls.security_manager().has_command_access(user_id, command_name)

    @property
    def prefixes(self) -> list[str]:
        return self.modules._db.get("shizu.loader", "prefixes", ["."])

    @staticmethod
    def _flag(handler, name: str, default=None):
        function = getattr(handler, "__func__", handler)
        return getattr(function, name, getattr(handler, name, default))

    @staticmethod
    def _is_telethon_handler(handler) -> bool:
        module = getattr(handler, "__self__", None)
        return bool(getattr(module, "m__telethon", False))

    @staticmethod
    def _report_watcher_error(watcher, error: Exception) -> None:
        module = getattr(watcher, "__self__", None)
        name = getattr(module, "name", None)
        logger.exception("Watcher of module %s failed", name or "Shizu")
        reporter.failure(f"{name or 'Shizu'} · watcher", error, name)


class DispatcherManager(BaseDispatcherManager):
    """Dispatch Pyrogram messages to commands and watchers."""

    _WATCHER_MEDIA_FIELDS = {
        "watcher_no_stickers": ("sticker",),
        "watcher_no_docs": ("document",),
        "watcher_no_audios": ("audio",),
        "watcher_no_videos": ("video",),
        "watcher_no_photos": ("photo",),
        "watcher_no_forwards": ("forward_from", "forward_from_chat"),
    }

    def __init__(self, app: Client, modules: "loader.ModulesManager") -> None:
        super().__init__(app, modules)
        self.app = app

    async def _check_filters(
        self,
        handler: FunctionType,
        app: Client,
        message: types.Message,
        command_name: str | None = None,
    ) -> bool:
        """Apply custom filters, permissions and incoming-command rate limits."""
        if custom_filter := self._flag(handler, "_filters"):
            accepted = custom_filter(app, message)
            if inspect.isawaitable(accepted):
                accepted = await accepted
            if not accepted:
                return False

        if not await self.security.check(message, handler, command_name, app):
            return False
        user = message.from_user or message.sender_chat
        if (
            self._flag(handler, "ratelimit")
            and user
            and not (message.outgoing or getattr(message.from_user, "is_self", False))
            and self.security.rate_limited(user.id, command_name)
        ):
            return False
        return True

    async def load(self) -> bool:
        """Loads dispatcher"""
        self.app.add_handler(handler=MessageHandler(self._handle_message, filters.all))
        self.app.add_handler(
            handler=EditedMessageHandler(self._handle_message, filters.all),
            group=random.randint(1, 1000),
        )

        return True

    async def _handle_message(
        self, app: Client, message: types.Message
    ) -> types.Message:
        """Handle message"""
        await self._handle_watchers(app, message)

        prefix, command, args = utils.get_full_command(message)
        if not (command or args):
            return

        command = self.modules.aliases.get(command, command)
        command_lower = command.lower()
        func = self.modules.command_handlers.get(command_lower)

        if not func or not BeSafe.allow_handler(func, message):
            return

        if self._is_telethon_handler(func):
            return

        if not await self._check_filters(func, app, message, command_lower):
            return

        try:
            await func(app, message)
            await app.read_chat_history(message.chat.id)

        except Exception:
            item = lo.CustomException.from_exc_info(*sys.exc_info())
            exc = item.message + "\n\n" + item.full_stack
            trace = traceback.format_exc().replace(
                "Traceback (most recent call last):\n", ""
            )

            with contextlib.suppress(Exception):
                log_message = f"⛳️ <b>Command <code>{prefix}{command}</code> failed with error:</b>\n\n{exc}\n"
                await app.inline_bot.send_animation(
                    app.db.get("shizu.chat", "logs", None),
                    "https://i.gifer.com/LRP3.gif",
                    caption=log_message,
                    parse_mode="HTML",
                )
                answer_message = f"<emoji id=5372892693024218813>🥶</emoji> <b>Command <code>{prefix}{command}</code> failed with error:</b>\n\n<code>{trace}</code>\n"
                await message.answer(answer_message)

        return message

    def _resolve_watcher(self, entry):
        """Unwrap legacy registrations and select Pyrogram handlers."""
        watcher = entry
        if isinstance(entry, tuple):
            watcher, is_telethon = entry
            if is_telethon:
                return None
        if not watcher or self._is_telethon_handler(watcher):
            return None
        module = getattr(watcher, "__self__", None)
        if module is not None and not hasattr(module, "name"):
            return None
        return watcher

    def _watcher_accepts(self, watcher, message: types.Message) -> bool:
        """Apply legacy Pyrogram watcher flags without invoking the handler."""
        if self._flag(watcher, "watcher_only_messages"):
            if not message.text and not message.caption:
                return False
        if self._flag(watcher, "watcher_no_commands"):
            text = message.text or ""
            if any(text.startswith(prefix) for prefix in self.prefixes):
                return False
        for flag, fields in self._WATCHER_MEDIA_FIELDS.items():
            if self._flag(watcher, flag) and any(
                getattr(message, field, None) for field in fields
            ):
                return False
        return True

    @staticmethod
    async def _invoke_watcher(watcher, app: Client, message: types.Message) -> None:
        """Support both signatures without retrying a failing handler."""
        arguments = (app, message)
        try:
            signature = inspect.signature(watcher)
        except (TypeError, ValueError):
            signature = None
        if signature is not None:
            try:
                signature.bind(*arguments)
            except TypeError:
                signature.bind(message)
                arguments = (message,)
        await watcher(*arguments)

    async def _handle_watchers(
        self, app: Client, message: types.Message
    ) -> types.Message:
        """Run matching watchers independently so one failure cannot stop others."""
        watchers = getattr(self.modules, "watcher_handlers", None) or ()
        for entry in list(watchers):
            watcher = None
            try:
                watcher = self._resolve_watcher(entry)
                if watcher is None or not BeSafe.allow_handler(watcher, message):
                    continue
                if self._watcher_accepts(watcher, message):
                    await self._invoke_watcher(watcher, app, message)
            except Exception as error:
                self._report_watcher_error(watcher, error)
        return message


class TelethonDispatcherManager(BaseDispatcherManager):
    """Dispatch Telethon commands, watchers and raw updates."""

    def __init__(self, client, modules: "loader.ModulesManager") -> None:
        super().__init__(client, modules)
        self._loaded = False

    def _rules(self, message, prefixes) -> dict:
        """Translate Telethon message properties into supported filter tags."""
        text = message.raw_text or ""
        channel = bool(message.is_channel and not message.is_group)
        mentioned = bool(getattr(message, "mentioned", False))
        audio = bool(message.audio or message.voice)
        document = bool(message.document) and not any(
            (message.sticker, message.video, audio, message.gif)
        )
        command = any(text.startswith(prefix) for prefix in prefixes)
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
            "only_audios": audio,
            "no_audios": not audio,
            "only_docs": document,
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
            "only_commands": command,
            "no_commands": not command,
        }

    def _values_accept(self, values: dict, message) -> bool:
        """Check text patterns, sender/chat restrictions and custom predicates."""
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

    def _filters_accept(
        self, func, message, prefixes, tags_attr: str, values_attr: str
    ) -> bool:
        """Require every declared tag and value filter to match."""
        tags = self._flag(func, tags_attr) or ()
        if tags:
            rules = self._rules(message, prefixes)
            if not all(rules[tag] for tag in tags if tag in rules):
                return False
        return self._values_accept(self._flag(func, values_attr) or {}, message)

    def _watcher_accepts(self, watcher, message, prefixes) -> bool:
        """Combine legacy watcher flags with tag and value filters."""
        legacy = {
            "watcher_no_commands": "no_commands",
            "watcher_no_stickers": "no_stickers",
            "watcher_no_docs": "no_docs",
            "watcher_no_audios": "no_audios",
            "watcher_no_videos": "no_videos",
            "watcher_no_photos": "no_photos",
            "watcher_no_forwards": "no_forwards",
        }
        enabled = [tag for attr, tag in legacy.items() if self._flag(watcher, attr)]
        if enabled:
            rules = self._rules(message, prefixes)
            if not all(rules[tag] for tag in enabled):
                return False
        return self._filters_accept(
            watcher, message, prefixes, "watcher_tags", "watcher_values"
        )

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
                    if BeSafe.allow_handler(handler, update):
                        await handler(update)
                except Exception:
                    logger.exception("Raw handler %s failed", handler.__name__)

            self.client.add_event_handler(
                callback, events.Raw(types=list(updates) or None)
            )
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
        if (
            not func
            or not BeSafe.allow_handler(func, message)
            or not getattr(module, "m__telethon", False)
        ):
            return

        if not self._filters_accept(func, message, self.prefixes, "tags", "tag_values"):
            return
        if not await self.security.check(message, func, command, self.client):
            return
        if (
            self._flag(func, "ratelimit")
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
                if not BeSafe.allow_handler(watcher, message):
                    continue
                if not self._watcher_accepts(watcher, message, prefixes):
                    continue
                try:
                    await watcher(message)
                except Exception as error:
                    self._report_watcher_error(watcher, error)
