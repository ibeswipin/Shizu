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


@loader.module(name="ShizuOnload", author="hikamoru")
class ShizuOnload(loader.Module):
    """Handles Shizu startup events"""

    strings = {}

    AVATARS_VERSION = 2

    SERVICE_CHATS = (
        ("logs", "Shizu-logs", "📫 Shizu logs. Do not delete this group, or the bot will break", "assets/logs.jpg"),
        ("backup", "Shizu-backup", "📫 Shizu backups. Do not delete this group, or the bot will break", "assets/backups.jpg"),
        ("besafe", "Shizu-besafe", "🛡 Shizu BeSafe confirmations. Do not delete this group, or the bot will break", "assets/besafe.jpg"),
    )

    text = """
    👋 Hey there! Congratulations on installing the <u>Shizu userbot</u>. Need a hand with anything?

❓ Don't hesitate to reach out to our support chat if you have questions. We're here to assist everyone. @shizu_talks   

🔒 Plus, we've beefed up security to protect against <b>Account Deletion</b>.

💁‍♀️ Let's get you started quickly:

▫️ Just enter <code>.help</code> to see all available modules.
▫️ If you need help with a specific module, try <code>.help (ModuleName/command)</code>.
▫️ Want to grab a module from a link? Easy, just use <code>.dlmod (link)</code>.
▫️ To install a module from a file, reply with <code>.loadmod</code> to the file.
▫️ Deactivate a specific module by using <code>.unloadmod (ModuleName)</code>.
▫️ Explore available languages with <code>.langs</code>, and switch your language with <code>.setlang (lang)</code>.

📢 Stay tuned for exciting updates in our channel. Join us at @shizuhub to be the first to know about our latest features.

    """

    START_TEXT = (
        "🌘 <b><a href='https://github.com/AmoreForever/Shizu'>Shizu Userbot</a></b>\n\n\n"
        "💫 A userbot can be characterized as a <b>third-party software application</b> that engages with the Telegram API in order to execute <b>automated operations on behalf of an end user</b>. These userbots possess the capability to streamline a variety of tasks, encompassing activities such as <b>dispatching messages, enrolling in channels, retrieving media files, and more</b>.\n\n"
        "😎 Diverging from conventional Telegram bots, <b>userbots operate within the confines of a user's account</b> rather than within a dedicated bot account. This particular distinction empowers userbots with enhanced accessibility to a broader spectrum of functionalities and a heightened degree of flexibility in executing actions.\n\n"
    )

    def __init__(self):
        self.config = loader.ModuleConfig(
            "status",
            True,
            lambda m: self.strings("cfg_doc_enable_start_text"),
            "custom text",
            None,
            lambda m: self.strings("cfg_doc_start_text"),
        )

    async def _greet(self):
        if self.db.get("shizu.me", "notified", None):
            return
        mymakr = self.bot._generate_markup(
            [
                [
                    {
                        "text": "📢 Channel",
                        "url": "https://t.me/shizuhub",
                    },
                    {
                        "text": "👥 Support",
                        "url": "https://t.me/shizu_talks",
                    },
                ]
            ]
        )
        await self._bot.send_animation(
            self.me.id,
            "https://i.gifer.com/Qipy.gif",
            caption=self.text,
            reply_markup=mymakr,
        )
        self.db.set("shizu.me", "notified", True)

    @loader.on_bot(lambda self, app, m: m.text == "/start" and m.chat.type == "private")
    async def start_message_handler(self, app, message):
        markup = self.bot._generate_markup(
            [
                [
                    {
                        "text": "🐈‍⬛ Source",
                        "url": "https://github.com/AmoreForever/Shizu",
                    },
                    {
                        "text": "🪭 Chief Developer",
                        "url": "https://t.me/hikamoru",
                    },
                ],
                [
                    {
                        "text": "👥 Support",
                        "url": "https://t.me/shizu_talks",
                    },
                ],
            ]
        )

        if self.config["status"]:
            text = self.config["custom text"] or self.START_TEXT
            await self.bot.bot.send_message(message.chat.id, text, reply_markup=markup)

    async def on_load(self, app: Client):
        self.adopt_config("ShizuStart")
        try:
            await self._greet()
        except Exception:
            logging.exception("Could not send the welcome message")

        with contextlib.suppress(Exception):
            async for _ in app.get_dialogs():
                pass

        for key, *_ in self.SERVICE_CHATS:
            chat_id = self.db.get("shizu.chat", key)
            if not chat_id:
                continue
            try:
                await app.resolve_peer(chat_id)
            except (ChannelInvalid, ChannelPrivate, PeerIdInvalid):
                logging.warning("Service chat %s (%s) is gone, recreating", key, chat_id)
                self.db.pop("shizu.chat", key)

        if missing := [chat for chat in self.SERVICE_CHATS if not self.db.get("shizu.chat", chat[0])]:
            logging.info("Trying to create service chats")
            app.me = await app.get_me()
            for key, title, description, _ in missing:
                chat = await utils.create_chat(app, title, description, True, True, True)
                self.db.set("shizu.chat", key, chat.id)
            logging.info("Service chats created")
            utils.restart()

        chats = {key: self.db.get("shizu.chat", key) for key, *_ in self.SERVICE_CHATS}

        for key, chat_id in chats.items():
            try:
                await utils.ensure_bot_in_chat(app, chat_id)
            except Exception:
                logging.exception("Could not add the bot to service chat %s", key)

        avatars = self.db.get("shizu.chat", "avatars")
        if not isinstance(avatars, dict):
            avatars = {}
        for key, _, _, photo in self.SERVICE_CHATS:
            if avatars.get(str(chats[key])) == self.AVATARS_VERSION:
                continue
            try:
                await app.set_chat_photo(chat_id=chats[key], photo=photo)
                avatars[str(chats[key])] = self.AVATARS_VERSION
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
