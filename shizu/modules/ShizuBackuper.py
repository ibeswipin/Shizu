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

import os
import io
import json
import time

from datetime import datetime
from pyrogram import Client, types, enums

from .. import loader, utils


LOADED_MODULES_DIR = os.path.join(os.getcwd(), "shizu/modules")


@loader.module(name="ShizuBackuper", author="hikamoru")
class BackupMod(loader.Module):
    """With this module you can make backups of mods and the entire userbot"""

    strings = {}

    @loader.command()
    async def backupdb(self, app: Client, message: types.Message):
        """Create database backup [will be sent in backups chat]"""
        txt = io.BytesIO(json.dumps(self.db).encode("utf-8"))
        txt.name = f"shizu-{datetime.now().strftime('%d-%m-%Y-%H-%M')}.json"
        await app.inline_bot.send_document(
            app.db.get("shizu.chat", "backup"),
            document=txt,
            caption=self.strings("backup").format(
                datetime.now().strftime("%d-%m-%Y %H:%M")
            ),
        )
        await message.answer(self.strings("done"))

    @loader.command()
    async def restoredb(self, app: Client, message: types.Message):
        """Easy restore database"""
        reply = message.reply_to_message
        if not reply or not reply.document:
            return await message.answer(self.strings("invalid"))

        await message.answer(self.strings("restoring"))
        file = await app.download_media(reply.document)
        decoded_text = json.loads(io.open(file, "r", encoding="utf-8").read())

        if not file.endswith(".json"):
            return await message.answer(self.strings("invalid"))

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
