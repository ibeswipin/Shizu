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

from pyrogram import Client, types
from shizu import loader, utils, version


@loader.module("ShizuInfo", "hikamoru")
class InformationMod(loader.Module):
    """Info"""

    strings = {}

    def __init__(self):
        self.config = loader.ModuleConfig(
            "custom_message",
            None,
            lambda: self.strings("custom_msg"),
            "custom_buttons",
            {"text": "🤝 Support", "url": "https://t.me/shizu_talks"},
            lambda: self.strings("custom_button"),
            "photo_url",
            "https://github.com/AmoreForever/shizuassets/blob/master/shizubanner.jpg?raw=true",
            lambda: self.strings("photo_url"),
        )

    def text_(self, me: types.User, username):
        """Get text"""
        mention = f'<a href="tg://user?id={me.id}">{utils.escape_html((utils.get_display_name(me)))}</a>'
        prefix = ", ".join(self.prefix)

        if self.config["custom_message"]:
            return "🐙 Shizu\n" + self.config["custom_message"].format(
                mention=mention,
                version={".".join(map(str, version.__version__))},
                prefix=prefix,
                branch=version.branch,
                platform=utils.get_platform(),
            )

        return self.strings("text").format(
            mention=mention,
            version=".".join(map(str, version.__version__)),
            prefix=prefix,
            branch=version.branch,
            platform=utils.get_platform(),
            username=username,
        )

    @loader.command()
    async def info(self, app: Client, message: types.Message):
        """Info about Shizu"""
        if self.config["custom_buttons"]:
            await message.answer(
                response=self.text_(self.me, (await self.bot.bot.get_me()).username),
                reply_markup=[[self.config["custom_buttons"]]],
                photo=self.config["photo_url"],
            )
        else:
            await message.answer(
                response=self.config["photo_url"],
                photo_=True,
                caption=self.text_(self.me, (await self.bot.bot.get_me()).username),
            )
