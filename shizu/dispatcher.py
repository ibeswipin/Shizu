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

import random
import contextlib
import sys
import traceback

import inspect

from types import FunctionType

from pyrogram import Client, filters, types
from pyrogram.handlers import MessageHandler, EditedMessageHandler

from shizu import loader, utils, database, logger as lo


async def check_filters(
    func: FunctionType,
    app: Client,
    message: types.Message,
    command_name: str = None,
) -> bool:
    db = database.db
    if custom_filters := getattr(func, "_filters", None):
        coro = custom_filters(app, message)

        if inspect.iscoroutine(coro):
            coro = await coro

        if not coro:
            return False

    if message.from_user.is_self:
        return True

    user_id = message.sender_chat.id if message.from_user is None else message.from_user.id
    
    if (
        user_id in db.get("shizu.me", "owners", []) and db.get("shizu.owner", "status", False)
    ):
        return True

    if message.outgoing:
        return True

    if command_name:
        perms = db.get("shizu.permissions", "users", {})
        user_id_str = str(user_id)
        if user_id_str in perms and command_name in perms[user_id_str]:
            return True

    return False


class DispatcherManager:
    """Manager of dispatcher"""

    def __init__(self, app: Client, modules: "loader.ModulesManager") -> None:
        self.app = app
        self.modules = modules

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

        if not func:
            return

        if hasattr(func, "__self__"):
            module = func.__self__
            if hasattr(module, "m__telethon") and getattr(module, "m__telethon", False):
                return

        try:
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if len(params) == 2 and 'message' in params and 'app' not in params:
                return
        except (ValueError, TypeError):
            pass

        if not await check_filters(func, app, message, command_lower):
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

    async def _handle_watchers(
        self, app: Client, message: types.Message
    ) -> types.Message:
        if not self.modules or not hasattr(self.modules, "watcher_handlers"):
            return message
        
        watchers = self.modules.watcher_handlers
        if not watchers:
            return message
        
        for watcher in watchers:
            if not watcher:
                continue
            
            if isinstance(watcher, tuple):
                watcher, is_telethon = watcher
                if is_telethon:
                    continue
            
            try:
                if hasattr(watcher, "__self__"):
                    module = watcher.__self__
                    if not hasattr(module, "name"):
                        continue
                    is_telethon_module = getattr(module, "m__telethon", False)
                    if is_telethon_module:
                        continue
                    func = getattr(watcher, "__func__", watcher)
                else:
                    func = watcher
                
                watcher_only_messages = getattr(func, "watcher_only_messages", getattr(watcher, "watcher_only_messages", None))
                if watcher_only_messages is not None and watcher_only_messages:
                    if not message.text and not message.caption:
                        continue
                
                
                watcher_no_commands = getattr(func, "watcher_no_commands", getattr(watcher, "watcher_no_commands", False))
                if watcher_no_commands:
                    prefixes = self.modules._db.get("shizu.loader", "prefixes", ["."])
                    text = message.text or ""
                    if text and any(text.startswith(p) for p in prefixes):
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
                if getattr(func, "watcher_no_forwards", getattr(watcher, "watcher_no_forwards", False)) and (message.forward_from or message.forward_from_chat):
                    continue
                
                try:
                    await watcher(app, message)
                except TypeError as e:
                    error_msg = str(e)
                    if "takes" in error_msg and "positional arguments" in error_msg:
                        try:
                            await watcher(message)
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception:
                continue
        
        return message
