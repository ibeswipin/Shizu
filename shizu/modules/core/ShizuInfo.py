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

# meta banner: https://github.com/ibeswipin/Shizu/raw/refs/heads/beta/assets/banners/ShizuInfo.png

import collections
import html
import logging

from pyrogram import Client, types

from shizu import loader, utils, version
from shizu.telegram.rich import button_label_html, send_direct, send_rich

logger = logging.getLogger(__name__)


@loader.module("ShizuInfo", "hikamoru")
class InformationMod(loader.Module):
    """Info"""

    strings = {}
    ICONS = {
        "label_version": ("5310224206732996002", "⭐"),
        "label_branch": ("5292226786229236118", "🔄"),
        "label_platform": ("5235588635885054955", "🎲"),
        "label_prefix": ("5258023599419171861", "🔧"),
        "label_bot": ("5258196742435787040", "👾"),
    }

    def _label(self, key: str) -> str:
        label = utils.escape_html(self.strings(key))
        if not getattr(self.me, "is_premium", False) or key not in self.ICONS:
            return label
        emoji_id, fallback = self.ICONS[key]
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji> {label}'

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "custom_message",
                None,
                lambda: self.strings("custom_msg"),
                label=lambda: self.strings("cfg_label_custom_message"),
            ),
            loader.ConfigValue(
                "custom_buttons",
                [{"text": "Support", "url": "https://t.me/shizu_talks"}],
                lambda: self.strings("custom_button"),
                validator=loader.validators.Series(validator=loader.validators.Button()),
                label=lambda: self.strings("cfg_label_custom_buttons"),
            ),
            loader.ConfigValue(
                "photo_url",
                "https://github.com/ibeswipin/Shizu/raw/refs/heads/beta/assets/shizubanner.png",
                lambda: self.strings("photo_url"),
                label=lambda: self.strings("cfg_label_photo_url"),
            ),
            loader.ConfigValue(
                "rich",
                False,
                lambda: self.strings("rich"),
                validator=loader.validators.Boolean(),
                label=lambda: self.strings("cfg_label_rich"),
            ),
        )

    async def on_load(self, app: Client):
        previous = "https://github.com/ibeswipin/Shizu/raw/refs/heads/beta/assets/shizubanner.jpg"
        if self.config["photo_url"] == previous:
            self.config["photo_url"] = self.config.getdef("photo_url")
        buttons = self.config["custom_buttons"]
        if isinstance(buttons, dict):
            self.config["custom_buttons"] = [buttons] if buttons else []

    async def text_(self, me: types.User, username, logo: str = "🐙"):
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
                "platform": utils.get_platform(getattr(me, "is_premium", False)),
            }
            return f"{logo} Shizu\n" + self.config["custom_message"].format_map(
                collections.defaultdict(str, values)
            )

        stats = utils.render_table(
            [
                [
                    self.strings("label_version"),
                    ".".join(map(str, version.__version__)),
                ],
                [self.strings("label_branch"), version.branch],
                [
                    self.strings("label_platform"),
                    utils.get_platform(getattr(me, "is_premium", False)),
                ],
                [self.strings("label_prefix"), prefix],
                [self.strings("label_bot"), f"@{username}"],
            ]
        )
        return f"{logo} <b>Shizu</b> — {mention}\n{stats}"

    async def _rich_message(
        self, username: str, fallback_text: str, logo: str = "🐙"
    ) -> types.InputRichMessage:
        if self.config["custom_message"]:
            content = fallback_text
        else:
            mention = (
                f'<a href="tg://user?id={self.me.id}">'
                f"{utils.escape_html(utils.get_display_name(self.me))}</a>"
            )
            rows = [
                ("label_version", ".".join(map(str, version.__version__))),
                ("label_branch", version.branch),
                ("label_platform", utils.get_platform().split(" ", 1)[-1]),
                ("label_prefix", ", ".join(self.prefix)),
            ]
            cells = "".join(
                f"<tr><td>{self._label(key)}</td>"
                f"<td>{utils.escape_html(value)}</td></tr>"
                for key, value in rows
            )
            if username:
                username = utils.escape_html(username)
                cells += (
                    f"<tr><td>{self._label('label_bot')}</td><td>"
                    f'<a href="https://t.me/{username}">@{username}</a></td></tr>'
                )
            content = f"<h2>{logo} Shizu — {mention}</h2><table bordered>{cells}</table>"

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

        for button in self.config["custom_buttons"]:
            style = button.get("style", "danger")
            if style not in {"primary", "success", "danger"}:
                style = "danger"
            markup += (
                "<tg-button-row>"
                f'<tg-button type="url" style="{style}" '
                f'url="{html.escape(button["url"])}">'
                f"{button_label_html({'text': self._button_label(button), 'emoji': button.get('emoji')})}</tg-button>"
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
        from_account = self.config["rich"] or not self.config["custom_buttons"]
        logo = utils.shizu_logo(self.me) if from_account else "🐙"
        text = await self.text_(self.me, username, logo)
        if self.config["rich"]:
            rich_text = text
            for button in self.config["custom_buttons"]:
                text += (
                    f'\n<a href="{html.escape(button["url"])}">'
                    f"{utils.escape_html(self._button_label(button))}</a>"
                )
            try:
                payload = await self._rich_message(username, rich_text, logo)
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
                reply_markup=[
                    [{"text": button["text"], "url": button["url"]}]
                    for button in self.config["custom_buttons"]
                ],
                photo=self.config["photo_url"],
            )
        else:
            await message.answer(
                response=self.config["photo_url"],
                photo_=True,
                caption=text,
            )
