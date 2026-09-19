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

import contextlib
import time
import logging

from pyrogram import Client, enums
from pyrogram.raw import functions, types as typ
from pyrogram.errors import (
    MessageIdInvalid,
    BadRequest,
    ChannelInvalid,
    ChannelPrivate,
    PeerIdInvalid,
)

from aiogram.utils.exceptions import ChatNotFound

from shizu import loader, utils
from shizu.version import __version__, branch


@loader.module(name="ShizuOnload", author="hikamoru")
class ShizuOnload(loader.Module):
    """This module for shizu onload events"""

    strings = {}

    async def on_load(self, app: Client):
        with contextlib.suppress(Exception):
            async for _ in app.get_dialogs():
                pass

        for key in ("logs", "backup"):
            chat_id = self.db.get("shizu.chat", key)
            if not chat_id:
                continue
            try:
                await app.resolve_peer(chat_id)
            except (ChannelInvalid, ChannelPrivate, PeerIdInvalid):
                logging.warning("Service chat %s (%s) is gone, recreating", key, chat_id)
                self.db.pop("shizu.chat", key)

        logs_id = self.db.get("shizu.chat", "logs")
        backup_id = self.db.get("shizu.chat", "backup")

        if not logs_id or not backup_id:
            logging.info("Trying to create service chats")
            app.me = await app.get_me()
            folder_id = 250

            if not logs_id:
                logs_id = (
                    await utils.create_chat(
                        app,
                        "Shizu-logs",
                        "📫 Shizu-logs do not delete this group, otherwise bot will be broken",
                        True,
                        True,
                        True,
                    )
                ).id
                self.db.set("shizu.chat", "logs", logs_id)

            if not backup_id:
                backup_id = (
                    await utils.create_chat(
                        app,
                        "Shizu-backup",
                        "📫 Backup-logs do not delete this group, otherwise bot will be broken",
                        True,
                        True,
                        True,
                    )
                ).id
                self.db.set("shizu.chat", "backup", backup_id)

            with contextlib.suppress(Exception):
                await app.set_chat_photo(chat_id=logs_id, photo="assets/logs.jpg")

            with contextlib.suppress(Exception):
                await app.set_chat_photo(chat_id=backup_id, photo="assets/backups.jpg")

            if not self.db.get("shizu.folder", "folder"):
                with contextlib.suppress(Exception):
                    await app.invoke(
                        functions.messages.UpdateDialogFilter(
                            id=folder_id,
                            filter=typ.DialogFilter(
                                id=folder_id,
                                title="Shizu",
                                include_peers=[
                                    await app.resolve_peer(logs_id),
                                    await app.resolve_peer(backup_id),
                                ],
                                pinned_peers=[],
                                exclude_peers=[],
                                emoticon="❤️",
                            ),
                        )
                    )
                    self.db.set("shizu.folder", "folder", True)

            logging.info("Service chats created")
            utils.restart()

        if restart := self.db.get("shizu.updater", "restart"):
            restarted_text = None
            
            if restart["type"] == "restart":
                start_time = restart.get("start")
                if isinstance(start_time, str):
                    start_time = float(start_time)
                elapsed = round(time.time() - start_time)
                restarted_text = self.strings("start_r").format(elapsed)

            elif restart["type"] == "update":
                start_time = restart.get("start")
                if isinstance(start_time, str):
                    start_time = float(start_time)
                elapsed = round(time.time() - start_time)
                restarted_text = self.strings("start_u").format(elapsed)

            if restarted_text:
                try:
                    try:
                        await app.edit_message_caption(
                            restart["chat"],
                            restart["id"],
                            caption=restarted_text,
                            parse_mode=enums.ParseMode.HTML,
                        )
                    except (BadRequest, MessageIdInvalid):
                        await app.edit_message_text(
                            restart["chat"],
                            restart["id"],
                            restarted_text,
                            parse_mode=enums.ParseMode.HTML,
                        )
                except Exception:
                    logging.exception("Could not edit restart message, sending a new one")
                    with contextlib.suppress(Exception):
                        await app.send_message(
                            restart["chat"],
                            restarted_text,
                            parse_mode=enums.ParseMode.HTML,
                        )

            self.db.pop("shizu.updater", "restart")

        started_text = (
            f"🐙 <b>Your <u>Shizu</u> started</b> <code>v{'.'.join(map(str, __version__))}</code>\n\n"
            f"🌳 <b>Branch:</b> <code>{branch}</code>\n"
        )
        try:
            await self._bot.send_photo(
                chat_id=self.db.get("shizu.chat", "logs", None),
                photo=open("assets/Shizu.jpg", "rb"),
                caption=started_text,
                parse_mode="html",
            )
        except ChatNotFound:
            await utils.invite_bot(app, self.db.get("shizu.chat", "logs", None))
            await self._bot.send_photo(
                chat_id=self.db.get("shizu.chat", "logs", None),
                photo=open("assets/Shizu.jpg", "rb"),
                caption=started_text,
                parse_mode="html",
            )
        except Exception:
            pass
