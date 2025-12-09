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
import logging
import sys
import traceback

import inspect

from types import FunctionType

from pyrogram import Client, filters, types, raw
from pyrogram.handlers import MessageHandler, EditedMessageHandler

from shizu import loader, utils, database, logger as lo

logger = logging.getLogger(__name__)


async def check_filters(
    func: FunctionType,
    app: Client,
    message: types.Message,
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

    if (
        message.sender_chat.id if message.from_user is None else message.from_user.id
    ) in db.get("shizu.me", "owners", []) and db.get("shizu.owner", "status", False):
        return True

    return bool(message.outgoing)


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
        func = self.modules.command_handlers.get(command.lower())

        if not func:
            return

        try:
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if len(params) == 2 and 'message' in params and 'app' not in params:
                return
        except (ValueError, TypeError):
            pass

        if not await check_filters(func, app, message):
            return

        try:
            await func(app, message)
            await app.read_chat_history(message.chat.id)

        except Exception:
            logging.exception("Error while executing command %s", command)
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
        if not self.modules.watcher_handlers:
            return message
            
        for watcher_item in self.modules.watcher_handlers:
            if isinstance(watcher_item, tuple):
                watcher, is_telethon = watcher_item
                if is_telethon:
                    continue  
            else:
                watcher = watcher_item
            
            # Check watcher filters
            if hasattr(watcher, "is_watcher"):
                # Check only_messages
                if getattr(watcher, "watcher_only_messages", True):
                    if not message.text and not message.caption:
                        continue
                
                # Check no_commands
                if getattr(watcher, "watcher_no_commands", False):
                    prefixes = self.modules._db.get("shizu.loader", "prefixes", ["."])
                    if message.text and message.text.startswith(tuple(prefixes)):
                        continue
                
                # Check no_stickers
                if getattr(watcher, "watcher_no_stickers", False):
                    if message.sticker:
                        continue
                
                # Check no_docs
                if getattr(watcher, "watcher_no_docs", False):
                    if message.document:
                        continue
                
                # Check no_audios
                if getattr(watcher, "watcher_no_audios", False):
                    if message.audio:
                        continue
                
                # Check no_videos
                if getattr(watcher, "watcher_no_videos", False):
                    if message.video:
                        continue
                
                # Check no_photos
                if getattr(watcher, "watcher_no_photos", False):
                    if message.photo:
                        continue
                
                # Check no_forwards
                if getattr(watcher, "watcher_no_forwards", False):
                    if message.forward_from or message.forward_from_chat:
                        continue
            
            try:
                sig = inspect.signature(watcher)
                params = list(sig.parameters.keys())
                # Skip Telethon watchers (they have only 'message' parameter)
                if len(params) == 1 and 'message' in params:
                    continue
                # Skip if has 'message' but no 'app' (Telethon style)
                if len(params) == 2 and 'message' in params and 'app' not in params:
                    continue
            except (ValueError, TypeError):
                pass
            
            try:
                # Try calling with (app, message) for Pyrogram watchers
                await watcher(app, message)
            except TypeError as error:
                error_msg = str(error)
                if "takes" in error_msg and "positional arguments" in error_msg:
                    logging.debug(f"Skipping watcher due to signature mismatch: {error_msg}")
                    continue
                logging.exception(f"Error in watcher {watcher.__name__}: {error}")
            except Exception as error:
                logging.exception(f"Error in watcher {watcher.__name__}: {error}")

        return message
