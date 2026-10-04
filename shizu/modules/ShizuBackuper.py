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

import io
import json
import os
import time
from datetime import datetime

from pyrogram import Client, enums, types

from shizu import loader, utils

LOADED_MODULES_DIR = os.path.join(os.getcwd(), "shizu/modules")


@loader.module(name="ShizuBackuper", author="hikamoru")
class BackupMod(loader.Module):
    """Back up modules and the entire userbot"""

    strings = {}

    def __init__(self):
        self.config = loader.ModuleConfig(
            "auto_backup",
            True,
            lambda m: self.strings("cfg_auto_backup"),
            "backup_time",
            "03:00",
            lambda m: self.strings("cfg_backup_time"),
        )

    async def _send_backup(self, app: Client, caption_key: str = "backup") -> None:
        txt = io.BytesIO(json.dumps(self.db).encode("utf-8"))
        txt.name = f"shizu-{datetime.now().strftime('%d-%m-%Y-%H-%M')}.json"
        chat = self.db.get("shizu.chat", "backup")
        await utils.ensure_bot_in_chat(app, chat)
        await app.inline_bot.send_document(
            chat,
            document=txt,
            caption=self.strings(caption_key).format(
                datetime.now().strftime("%d-%m-%Y %H:%M")
            ),
        )

    @loader.loop(time="backup_time", autostart=True)
    async def auto_backup_loop(self):
        """Daily database backup to the backups chat"""
        if self.config["auto_backup"]:
            await self._send_backup(self.app, "auto_backup")

    @loader.command()
    async def backupdb(self, app: Client, message: types.Message):
        """Create a database backup [sent to the backups chat]"""
        await self._send_backup(app)
        await message.answer(self.strings("done"))

    @loader.command()
    async def autobackup(self, app: Client, message: types.Message):
        """Turn the daily backup on or off. Set its time with .config ShizuBackuper"""
        self.config["auto_backup"] = not self.config["auto_backup"]
        text = self.strings("enabled" if self.config["auto_backup"] else "disabled")
        if self.config["auto_backup"]:
            text += self.strings("at_time").format(
                utils.escape_html(str(self.config["backup_time"]))
            )
        await message.answer(text)

    @loader.command()
    async def restoredb(self, app: Client, message: types.Message):
        """Restore the database from a backup"""
        reply = message.reply_to_message
        if not reply or not reply.document:
            return await message.answer(self.strings("invalid"))

        await message.answer(self.strings("restoring"))
        file = await app.download_media(reply.document)
        if not file.endswith(".json"):
            return await message.answer(self.strings("invalid"))

        with open(file, encoding="utf-8") as f:
            decoded_text = json.load(f)

        self.db.reset()

        self.db.update(**decoded_text)

        self.db.save()

        await app.send_message(
            message.chat.id,
            self.strings("loaded"),
        )

        ms = await message.answer(self.strings("restart"))

        self.db.set(
            "shizu.updater",
            "restart",
            {
                "chat": (
                    message.chat.username
                    if message.chat.type == enums.ChatType.BOT
                    else message.chat.id
                ),
                "id": ms.id,
                "start": time.time(),
                "type": "restart",
            },
        )

        utils.restart()
