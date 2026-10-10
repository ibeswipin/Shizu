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

import asyncio
import contextlib
import html
import sys
import time

from aiogram.types import CallbackQuery
from pyrogram import Client, types

from shizu import loader, utils
from shizu.bot.token_manager import TokenManager


@loader.module("ShizuPanel", "hikamoru")
class ShizuPanel(loader.Module):
    """Control Shizu from the bot with /panel"""

    strings = {}
    PREFIX = "shizu_panel:"

    def __init__(self):
        self.dashboard = None
        self._web_lock = asyncio.Lock()

    async def on_unload(self):
        async with self._web_lock:
            if self.dashboard:
                await self.dashboard.stop()

    async def _web_link(self):
        from shizu.web.panel import DashboardServer

        async with self._web_lock:
            if not self.dashboard or not self.dashboard.runner:
                self.dashboard = DashboardServer(self)
                await self.dashboard.start()
                self.app.web_panel = self.dashboard
            text = self.strings("web_link").format(
                html.escape(self.dashboard.invitation())
            )
            if not self.dashboard.url.startswith("https://"):
                text += "\n\n" + self.strings("web_local")
            return text

    @loader.command()
    async def web(self, app: Client, message: types.Message):
        """Open the browser dashboard; web stop closes it and revokes browser sessions"""
        if getattr(message.from_user, "id", None) != self.me.id and not (
            not message.from_user and message.outgoing
        ):
            return await message.answer(self.strings("web_owner_only"))
        if str(utils.get_args_raw(message) or "").strip() == "stop":
            async with self._web_lock:
                if self.dashboard:
                    await self.dashboard.stop()
            return await message.answer(self.strings("web_stopped"))
        try:
            text = await self._web_link()
        except (OSError, ValueError):
            return await message.answer(self.strings("web_start_failed"))
        if message.chat.id == self.me.id:
            return await message.answer(text, disable_web_page_preview=True)
        await app.send_message(self.me.id, text, disable_web_page_preview=True)
        await message.answer(self.strings("web_sent"))

    @loader.callback_handler()
    async def web_callback_handler(self, call: CallbackQuery):
        from shizu.web.panel import DashboardServer

        if not (call.data or "").startswith(DashboardServer.CALLBACK_PREFIX):
            return
        if call.from_user.id != self.me.id:
            return await call.answer(self.strings("web_owner_only"), show_alert=True)
        parts = call.data[len(DashboardServer.CALLBACK_PREFIX) :].split(":")
        if len(parts) != 2 or parts[1] not in ("allow", "deny"):
            return await call.answer(self.strings("web_expired"), show_alert=True)
        if not self.dashboard or not self.dashboard.auth.decide(
            parts[0], call.from_user.id, parts[1] == "allow"
        ):
            return await call.answer(self.strings("web_expired"), show_alert=True)
        await call.answer()
        await call.message.edit_text(
            self.strings("web_allowed" if parts[1] == "allow" else "web_denied")
        )

    def _text(self):
        prefixes = ", ".join(
            f"<code>{html.escape(p)}</code>"
            for p in self.db.get("shizu.loader", "prefixes", ["."])
        )
        return self.strings("panel_text").format(
            prefixes, html.escape(self.db.get("shizu.bot", "username", ""))
        )

    def _markup(self, *rows):
        return self.bot._generate_markup(
            [
                [{"text": text, "data": self.PREFIX + action} for text, action in row]
                for row in rows
            ]
        )

    def _panel(self):
        return self._markup(
            [
                (self.strings("btn_restart"), "restart"),
                (self.strings("btn_stop"), "stop"),
            ],
            [
                (self.strings("btn_prefix"), "prefix"),
                (self.strings("btn_token"), "token"),
            ],
            [(self.strings("btn_web"), "web")],
        )

    def _cancel(self):
        return self._markup([(self.strings("btn_cancel"), "back")])

    async def _set_token(self, token):
        username = await TokenManager.check_token(token)
        TokenManager.save_token(token, username)
        return username

    @loader.on_bot(
        lambda self, app, m: (
            m.chat.type == "private"
            and m.text == "/panel"
            and self.bot._is_owner(m.from_user.id)
        )
    )
    async def panel_message_handler(self, app, message):
        self.bot.ss(message.from_user.id, False)
        await self.bot.bot.send_message(
            message.chat.id, self._text(), reply_markup=self._panel()
        )

    @loader.on_bot(
        lambda self, app, m: (
            m.chat.type == "private"
            and m.text != "/panel"
            and str(self.bot.gs(m.from_user.id)).startswith(self.PREFIX)
        )
    )
    async def panel_input_message_handler(self, app, message):
        user, chat = message.from_user.id, message.chat.id
        action = self.bot.gs(user)[len(self.PREFIX) :]
        text = (message.text or "").strip()

        if action == "prefix":
            prefixes = list(dict.fromkeys(text.split()))
            if not prefixes:
                return await self.bot.bot.send_message(
                    chat, self.strings("prefix_empty"), reply_markup=self._cancel()
                )
            self.db.set("shizu.loader", "prefixes", prefixes)
            self.bot.ss(user, False)
            return await self.bot.bot.send_message(
                chat,
                self.strings("prefix_saved") + "\n\n" + self._text(),
                reply_markup=self._panel(),
            )

        with contextlib.suppress(Exception):
            await message.delete()
        try:
            username = await self._set_token(text)
        except ValueError as e:
            return await self.bot.bot.send_message(
                chat,
                self.strings("token_error").format(html.escape(str(e))),
                reply_markup=self._cancel(),
            )
        self.bot.ss(user, False)
        await self.bot.bot.send_message(
            chat, self.strings("token_saved").format(username)
        )
        utils.restart()

    async def panel_callback_handler(self, call: CallbackQuery):
        if not (call.data or "").startswith(self.PREFIX):
            return
        if not self.bot._is_owner(call.from_user.id):
            return await call.answer(self.strings("not_allowed"))

        action = call.data[len(self.PREFIX) :]
        if action == "web" and call.from_user.id != self.me.id:
            return await call.answer(self.strings("web_owner_only"), show_alert=True)
        self.bot.ss(call.from_user.id, False)
        await call.answer()

        if action == "web":
            try:
                text = await self._web_link()
            except (OSError, ValueError):
                text = self.strings("web_start_failed")
            await self.bot.bot.send_message(
                self.me.id, text, disable_web_page_preview=True
            )
        elif action == "restart":
            if self.dashboard:
                await self.dashboard.stop()
            await call.message.edit_text(self.strings("restarting"))
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
                self.strings("stop_confirm"),
                reply_markup=self._markup(
                    [
                        (self.strings("btn_stop_yes"), "stop_yes"),
                        (self.strings("btn_cancel"), "back"),
                    ]
                ),
            )
        elif action == "stop_yes":
            if self.dashboard:
                await self.dashboard.stop()
            await call.message.edit_text(self.strings("stopped"))
            sys.exit(0)
        elif action == "prefix":
            self.bot.ss(call.from_user.id, self.PREFIX + action)
            await call.message.edit_text(
                self.strings("prefix_prompt"),
                reply_markup=self._cancel(),
            )
        elif action == "token":
            self.bot.ss(call.from_user.id, self.PREFIX + action)
            await call.message.edit_text(
                self.strings("token_prompt"),
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
            return await app.send_message(message.chat.id, self.strings("token_usage"))
        try:
            username = await self._set_token(token)
        except ValueError as e:
            return await app.send_message(message.chat.id, f"❌ {html.escape(str(e))}")
        await app.send_message(
            message.chat.id, self.strings("token_saved").format(username)
        )
        utils.restart()
