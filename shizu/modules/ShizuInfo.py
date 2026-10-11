"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

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

import collections
import html
import logging

from pyrogram import Client, types

from shizu import loader, utils, version
from shizu.telegram.rich import send_direct, send_rich

logger = logging.getLogger(__name__)


@loader.module("ShizuInfo", "hikamoru")
class InformationMod(loader.Module):
    """Info"""

    strings = {}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "custom_message", None, lambda: self.strings("custom_msg")
            ),
            loader.ConfigValue(
                "custom_buttons",
                {"text": "Support", "url": "https://t.me/shizu_talks"},
                lambda: self.strings("custom_button"),
            ),
            loader.ConfigValue(
                "photo_url",
                "https://github.com/ibeswipin/Shizu/raw/refs/heads/beta/assets/shizubanner.jpg",
                lambda: self.strings("photo_url"),
            ),
            loader.ConfigValue(
                "rich",
                False,
                lambda: self.strings("rich"),
                validator=loader.validators.Boolean(),
            ),
        )

    async def text_(self, me: types.User, username):
        """Get text"""
        mention = f'<a href="tg://user?id={me.id}">{utils.escape_html(utils.get_display_name(me))}</a>'
        prefix = ", ".join(self.prefix)

        if self.config["custom_message"]:
            values = {
                **await utils.get_placeholders(),
                "mention": mention,
                "version": ".".join(map(str, version.__version__)),
                "prefix": prefix,
                "branch": version.branch,
                "platform": utils.get_platform(),
            }
            return "🐙 Shizu\n" + self.config["custom_message"].format_map(
                collections.defaultdict(str, values)
            )

        stats = utils.render_table(
            [
                [
                    self.strings("label_version"),
                    ".".join(map(str, version.__version__)),
                ],
                [self.strings("label_branch"), version.branch],
                [self.strings("label_platform"), utils.get_platform()],
                [self.strings("label_prefix"), prefix],
                [self.strings("label_bot"), f"@{username}"],
            ]
        )
        return f"🐙 <b>Shizu</b> — {mention}\n{stats}"

    async def _rich_message(
        self, username: str, fallback_text: str
    ) -> types.InputRichMessage:
        if self.config["custom_message"]:
            content = fallback_text
        else:
            mention = (
                f'<a href="tg://user?id={self.me.id}">'
                f"{utils.escape_html(utils.get_display_name(self.me))}</a>"
            )
            rows = [
                (
                    self.strings("label_version"),
                    ".".join(map(str, version.__version__)),
                ),
                (self.strings("label_branch"), version.branch),
                (
                    self.strings("label_platform"),
                    utils.get_platform().split(" ", 1)[-1],
                ),
                (self.strings("label_prefix"), ", ".join(self.prefix)),
            ]
            cells = "".join(
                f"<tr><td>{utils.escape_html(label)}</td>"
                f"<td>{utils.escape_html(value)}</td></tr>"
                for label, value in rows
            )
            if username:
                username = utils.escape_html(username)
                cells += (
                    f"<tr><td>{utils.escape_html(self.strings('label_bot'))}</td><td>"
                    f'<a href="https://t.me/{username}">@{username}</a></td></tr>'
                )
            content = f"<h2>Shizu — {mention}</h2><table bordered>{cells}</table>"

        markup = f"<blockquote>{content}</blockquote>"
        media = None
        if self.config["photo_url"]:
            markup = (
                '<blockquote><img src="tg://photo?id=banner"/></blockquote>' + markup
            )
            media = [
                types.InputRichMessageMedia(
                    id="banner",
                    media=types.InputMediaPhoto(self.config["photo_url"]),
                )
            ]

        button = self.config["custom_buttons"]
        if button:
            style = button.get("style", "danger")
            if style not in {"primary", "success", "danger"}:
                style = "danger"
            label = self._button_label(button)
            markup += (
                "<tg-button-row>"
                f'<tg-button type="url" style="{style}" '
                f'url="{html.escape(button["url"])}">'
                f"{utils.escape_html(label)}</tg-button>"
                "</tg-button-row>"
            )
        return types.InputRichMessage(html=markup, media=media)

    def _button_label(self, button):
        if button["url"] == "https://t.me/shizu_talks" and button["text"] in {
            "Support",
            "🤝 Support",
        }:
            return self.strings("label_support")
        return button["text"]

    @loader.command(aliases=["ubinfo", "support"])
    async def info(self, app: Client, message: types.Message):
        """Info about Shizu"""
        username = self.db.get("shizu.bot", "username", "")
        text = await self.text_(self.me, username)
        if self.config["rich"]:
            rich_text = text
            button = self.config["custom_buttons"]
            if button:
                text += (
                    f'\n<a href="{html.escape(button["url"])}">'
                    f"{utils.escape_html(self._button_label(button))}</a>"
                )
            try:
                payload = await self._rich_message(username, rich_text)
                return await send_rich(message, payload, text, app=app)
            except Exception:
                logger.warning(
                    "Could not send rich info; using a text card",
                    exc_info=True,
                )
            return await send_direct(app, message, text)

        if self.config["custom_buttons"]:
            await message.answer(
                response=text,
                reply_markup=[[self.config["custom_buttons"]]],
                photo=self.config["photo_url"],
            )
        else:
            await message.answer(
                response=self.config["photo_url"],
                photo_=True,
                caption=text,
            )
