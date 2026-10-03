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
import html
import sys
import time

from aiogram.types import CallbackQuery
from pyrogram import Client, types

from shizu import loader, utils
from shizu.bot import token_manager

PREFIX = "shizu_panel:"


@loader.module("ShizuPanel", "hikamoru")
class ShizuPanel(loader.Module):
    """Control Shizu from the bot with /panel"""

    strings = {}

    def _text(self):
        prefixes = ", ".join(
            f"<code>{html.escape(p)}</code>"
            for p in self.db.get("shizu.loader", "prefixes", ["."])
        )
        return (
            "⚙️ <b>Shizu control panel</b>\n\n"
            f"Prefix: {prefixes}\n"
            f"Bot: @{self.db.get('shizu.bot', 'username', '')}"
        )

    def _markup(self, *rows):
        return self.bot._generate_markup(
            [[{"text": text, "data": PREFIX + action} for text, action in row] for row in rows]
        )

    def _panel(self):
        return self._markup(
            [("🔄 Restart", "restart"), ("⏹ Stop", "stop")],
            [("✏️ Prefix", "prefix"), ("🤖 Bot token", "token")],
        )

    def _cancel(self):
        return self._markup([("Cancel", "back")])

    async def _set_token(self, token):
        username = await token_manager.check_token(token)
        token_manager.save_token(token, username)
        return username

    @loader.on_bot(
        lambda self, app, m: m.chat.type == "private"
        and m.text == "/panel"
        and self.bot._is_owner(m.from_user.id)
    )
    async def panel_message_handler(self, app, message):
        self.bot.ss(message.from_user.id, False)
        await self.bot.bot.send_message(
            message.chat.id, self._text(), reply_markup=self._panel()
        )

    @loader.on_bot(
        lambda self, app, m: m.chat.type == "private"
        and m.text != "/panel"
        and str(self.bot.gs(m.from_user.id)).startswith(PREFIX)
    )
    async def panel_input_message_handler(self, app, message):
        user, chat = message.from_user.id, message.chat.id
        action = self.bot.gs(user)[len(PREFIX):]
        text = (message.text or "").strip()

        if action == "prefix":
            prefixes = list(dict.fromkeys(text.split()))
            if not prefixes:
                return await self.bot.bot.send_message(
                    chat, "Send at least one prefix.", reply_markup=self._cancel()
                )
            self.db.set("shizu.loader", "prefixes", prefixes)
            self.bot.ss(user, False)
            return await self.bot.bot.send_message(
                chat, "✅ Prefix changed.\n\n" + self._text(), reply_markup=self._panel()
            )

        with contextlib.suppress(Exception):
            await message.delete()
        try:
            username = await self._set_token(text)
        except ValueError as e:
            return await self.bot.bot.send_message(
                chat,
                f"❌ {html.escape(str(e))}\nSend another token or press Cancel.",
                reply_markup=self._cancel(),
            )
        self.bot.ss(user, False)
        await self.bot.bot.send_message(
            chat, f"✅ Token saved. Restarting with @{username}…"
        )
        utils.restart()

    async def panel_callback_handler(self, call: CallbackQuery):
        if not (call.data or "").startswith(PREFIX):
            return
        if not self.bot._is_owner(call.from_user.id):
            return await call.answer("🚫 You are not allowed to press this button!")

        action = call.data[len(PREFIX):]
        self.bot.ss(call.from_user.id, False)
        await call.answer()

        if action == "restart":
            await call.message.edit_text("🔄 <b>Restarting…</b>")
            self.db.set(
                "shizu.updater",
                "restart",
                {
                    "chat": call.message.chat.id,
                    "id": call.message.message_id,
                    "start": time.time(),
                    "type": "restart",
                    "bot": True,
                },
            )
            utils.restart()
        elif action == "stop":
            await call.message.edit_text(
                "⏹ <b>Stop Shizu?</b>\nIt stays offline until you start it again on the server.",
                reply_markup=self._markup([("Yes, stop", "stop_yes"), ("Cancel", "back")]),
            )
        elif action == "stop_yes":
            await call.message.edit_text("⏹ <b>Shizu stopped.</b>")
            sys.exit(0)
        elif action == "prefix":
            self.bot.ss(call.from_user.id, PREFIX + action)
            await call.message.edit_text(
                "✏️ Send the new prefix. For several prefixes, separate them with spaces.",
                reply_markup=self._cancel(),
            )
        elif action == "token":
            self.bot.ss(call.from_user.id, PREFIX + action)
            await call.message.edit_text(
                "🤖 Send the new bot token from @BotFather.\nShizu will restart with the new bot.",
                reply_markup=self._cancel(),
            )
        elif action == "back":
            await call.message.edit_text(self._text(), reply_markup=self._panel())

    @loader.command()
    async def setbot(self, app: Client, message: types.Message):
        """(token) - Change the bot token and restart"""
        token = utils.get_args_raw(message).strip()
        with contextlib.suppress(Exception):
            await message.delete()
        if not token:
            return await app.send_message(message.chat.id, "Usage: <code>setbot (token)</code>")
        try:
            username = await self._set_token(token)
        except ValueError as e:
            return await app.send_message(message.chat.id, f"❌ {html.escape(str(e))}")
        await app.send_message(message.chat.id, f"✅ Token saved. Restarting with @{username}…")
        utils.restart()
