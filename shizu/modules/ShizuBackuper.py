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
import os
import time
from datetime import datetime

from pyrogram import Client, enums, types

from shizu import loader, utils
from shizu.backups import BackupError, EncryptedBackup

LOADED_MODULES_DIR = os.path.join(os.getcwd(), "shizu/modules")


@loader.module(name="ShizuBackuper", author="hikamoru")
class BackupMod(loader.Module):
    """Back up modules and the entire userbot"""

    strings = {}

    def __init__(self):
        self.backups = EncryptedBackup()
        self.config = loader.ModuleConfig(
            "auto_backup",
            True,
            lambda m: self.strings("cfg_auto_backup"),
            "backup_time",
            "03:00",
            lambda m: self.strings("cfg_backup_time"),
        )

    async def _send_backup(self, app: Client, caption_key: str = "backup") -> None:
        txt = io.BytesIO(self.backups.encrypt(self.db, self.me.id))
        txt.name = f"shizu-{datetime.now().strftime('%d-%m-%Y-%H-%M')}.shizu-backup"
        chat = self.db.get("shizu.chat", "backup")
        await utils.ensure_bot_in_chat(app, chat)
        await app.inline_bot.send_document(
            chat,
            document=txt,
            caption=self.strings(caption_key).format(
                datetime.now().strftime("%d-%m-%Y %H:%M")
            )
            + "\n\n"
            + self._key_info(),
        )

    def _key_info(self) -> str:
        return self.strings("key_info").format(
            utils.escape_html(str(self.backups.key_path))
        )

    async def _account_owner(self, message) -> bool:
        if getattr(message.from_user, "id", None) == self.me.id or (
            not message.from_user and message.outgoing
        ):
            return True
        await message.answer(self.strings("owner_only"))
        return False

    async def _error(self, message, key: str) -> None:
        await message.answer(
            self.strings("backup_error").format(utils.escape_html(self.strings(key)))
        )

    @loader.loop(time="backup_time", autostart=True)
    async def auto_backup_loop(self):
        """Daily database backup to the backups chat"""
        if self.config["auto_backup"]:
            await self._send_backup(self.app, "auto_backup")

    @loader.command()
    async def backupdb(self, app: Client, message: types.Message):
        """Create a database backup [sent to the backups chat]"""
        if not await self._account_owner(message):
            return
        try:
            await self._send_backup(app)
        except BackupError as error:
            return await self._error(message, error.code)
        await message.answer(self.strings("done"))

    @loader.command()
    async def backupkey(self, app: Client, message: types.Message):
        """Show the recovery key file path; its contents are never sent to Telegram"""
        if await self._account_owner(message):
            await message.answer(self._key_info())

    @loader.command()
    async def autobackup(self, app: Client, message: types.Message):
        """Turn the daily backup on or off. Set its time with .config ShizuBackuper"""
        if not await self._account_owner(message):
            return
        self.config["auto_backup"] = not self.config["auto_backup"]
        text = self.strings("enabled" if self.config["auto_backup"] else "disabled")
        if self.config["auto_backup"]:
            text += self.strings("at_time").format(
                utils.escape_html(str(self.config["backup_time"]))
            )
        await message.answer(text)

    @loader.command()
    async def restoredb(self, app: Client, message: types.Message):
        """Reply to an encrypted backup to restore; --legacy permits an old JSON file"""
        if not await self._account_owner(message):
            return
        reply = message.reply_to_message
        if not reply or not reply.document:
            return await message.answer(self.strings("invalid"))

        args = str(utils.get_args_raw(message) or "").strip()
        if args not in ("", "--legacy"):
            return await message.answer(self.strings("invalid"))
        await message.answer(self.strings("restoring"))
        try:
            if (reply.document.file_size or 0) > self.backups.MAX_BYTES:
                return await self._error(message, "too_large")
            archive = bytearray()
            async for chunk in app.stream_media(reply.document):
                if len(archive) + len(chunk) > self.backups.MAX_BYTES:
                    return await self._error(message, "too_large")
                archive.extend(chunk)
            decoded = self.backups.decrypt(
                bytes(archive), self.me.id, allow_legacy=args == "--legacy"
            )
            self.db.replace(decoded)
        except BackupError as error:
            return await self._error(message, error.code)
        except OSError:
            return await self._error(message, "write_failed")

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
