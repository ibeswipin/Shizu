"""
    █ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
    █▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

    Copyright 2022 t.me/hikariatama
    Licensed under the GNU GPLv3
"""

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


from pyrogram import Client
from .. import loader, utils


@loader.module("ShizuStart", "hikamoru")
class ShizuStart(loader.Module):
    """
    Module doesn't do anything just for notification that Shizu started first time
    """

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
▫️ If you're searching for modules by name, give <code>.aelis (ModuleName)</code> a shot.
▫️ Explore available languages with <code>.langs</code>, and switch your language with <code>.setlang (lang)</code>.

📢 Stay tuned for exciting updates in our channel. Join us at @shizuhub to be the first to know about our latest features.

    """

    START_TEXT = (
        "🌘 <b><a href='https://github.com/AmoreForever/Shizu'>Shizu Userbot</a></b>\n\n\n"
        "💫 A userbot can be characterized as a <b>third-party software application</b> that engages with the Telegram API in order to execute <b>automated operations on behalf of an end user</b>. These userbots possess the capability to streamline a variety of tasks, encompassing activities such as <b>dispatching messages, enrolling in channels, retrieving media files, and more</b>.\n\n"
        "😎 Diverging from conventional Telegram bots, <b>userbots operate within the confines of a user's account</b> rather than within a dedicated bot account. This particular distinction empowers userbots with enhanced accessibility to a broader spectrum of functionalities and a heightened degree of flexibility in executing actions.\n\n"
    )

    strings = {}
    def __init__(self):
        self.config = loader.ModuleConfig(
            "status",
            True,
            lambda m: self.strings("cfg_doc_enable_start_text"),
            "custom text",
            None,
            lambda m: self.strings("cfg_doc_start_text"),
        )

    async def on_load(self, app: Client):
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
        if not self.db.get("shizu.me", "notified", None):
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
