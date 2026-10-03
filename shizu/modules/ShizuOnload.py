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
import re
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

from shizu import fsm, loader, utils
from shizu.version import __version__, branch


AVATARS_VERSION = 2

SERVICE_CHATS = (
    ("logs", "Shizu-logs", "📫 Shizu logs. Do not delete this group, or the bot will break", "assets/logs.jpg"),
    ("backup", "Shizu-backup", "📫 Shizu backups. Do not delete this group, or the bot will break", "assets/backups.jpg"),
    ("besafe", "Shizu-besafe", "🛡 Shizu BeSafe confirmations. Do not delete this group, or the bot will break", "assets/besafe.jpg"),
)


@loader.module(name="ShizuOnload", author="hikamoru")
class ShizuOnload(loader.Module):
    """Handles Shizu startup events"""

    strings = {}

    async def on_load(self, app: Client):
        with contextlib.suppress(Exception):
            async for _ in app.get_dialogs():
                pass

        for key, *_ in SERVICE_CHATS:
            chat_id = self.db.get("shizu.chat", key)
            if not chat_id:
                continue
            try:
                await app.resolve_peer(chat_id)
            except (ChannelInvalid, ChannelPrivate, PeerIdInvalid):
                logging.warning("Service chat %s (%s) is gone, recreating", key, chat_id)
                self.db.pop("shizu.chat", key)

        if missing := [chat for chat in SERVICE_CHATS if not self.db.get("shizu.chat", chat[0])]:
            logging.info("Trying to create service chats")
            app.me = await app.get_me()
            for key, title, description, _ in missing:
                chat = await utils.create_chat(app, title, description, True, True, True)
                self.db.set("shizu.chat", key, chat.id)
            logging.info("Service chats created")
            utils.restart()

        chats = {key: self.db.get("shizu.chat", key) for key, *_ in SERVICE_CHATS}

        avatars = self.db.get("shizu.chat", "avatars")
        if not isinstance(avatars, dict):
            avatars = {}
        for key, _, _, photo in SERVICE_CHATS:
            if avatars.get(str(chats[key])) == AVATARS_VERSION:
                continue
            try:
                await app.set_chat_photo(chat_id=chats[key], photo=photo)
                avatars[str(chats[key])] = AVATARS_VERSION
            except Exception:
                logging.exception("Could not set the photo of service chat %s", key)
        self.db.set("shizu.chat", "avatars", avatars)

        if self.db.get("shizu.bot", "avatar") != 2:
            try:
                async with fsm.Conversation(app, "@BotFather") as conv:
                    await conv.ask("/cancel")
                    await conv.get_response()
                    await conv.ask("/setuserpic")
                    await conv.get_response()
                    await conv.ask(f"@{self.db.get('shizu.bot', 'username')}")
                    await conv.get_response()
                    await conv.ask_media("assets/bot.jpg", media_type="photo")
                    await conv.get_response()
                self.db.set("shizu.bot", "avatar", 2)
            except Exception:
                logging.exception("Could not update the bot avatar")

        peers = sorted(chats.values())
        if bot_username := self.db.get("shizu.bot", "username"):
            peers.append(f"@{bot_username}")
        if self.db.get("shizu.folder", "peers") != peers:
            try:
                await app.invoke(
                    functions.messages.UpdateDialogFilter(
                        id=250,
                        filter=typ.DialogFilter(
                            id=250,
                            title=typ.TextWithEntities(text="Shizu", entities=[]),
                            include_peers=[await app.resolve_peer(i) for i in peers],
                            pinned_peers=[],
                            exclude_peers=[],
                            emoticon="❤️",
                        ),
                    )
                )
                self.db.set("shizu.folder", "peers", peers)
            except Exception:
                logging.exception("Could not create the Shizu chat folder")

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

            if restarted_text and restart.get("bot"):
                try:
                    await self._bot.edit_message_text(
                        re.sub(r"</?emoji[^>]*>", "", restarted_text),
                        chat_id=restart["chat"],
                        message_id=restart["id"],
                        parse_mode="html",
                    )
                except Exception:
                    logging.exception("Could not edit update message in bot chat")
            elif restarted_text:
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

        commit = utils.get_git_hash()
        build = (
            f' · <a href="https://github.com/ibeswipin/Shizu/commit/{commit}">{commit[:7]}</a>'
            if commit
            else ""
        )
        prefixes = " ".join(
            f"<code>{utils.escape_html(p)}</code>"
            for p in self.db.get("shizu.loader", "prefixes", ["."])
        )
        started_text = (
            "静 <b>Shizu is online</b>\n\n"
            f"<b>Version</b> <code>v{'.'.join(map(str, __version__))}</code> · <code>{branch}</code>{build}\n"
            f"<b>Prefix</b> {prefixes}\n"
            f"<b>Host</b> {utils.get_named_platform()}\n\n"
            f"⚙️ Control panel: /panel in @{self.db.get('shizu.bot', 'username', '')}"
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
