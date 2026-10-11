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
import logging
import time

from aiogram.types import CallbackQuery
from aiogram.utils.exceptions import BotBlocked, TelegramAPIError, UserDeactivated

from shizu import loader, utils


@loader.module("ShizuFeedback", "hikamoru")
class ShizuFeedback(loader.Module):
    """Lets people write to you through the bot and get your replies"""

    strings = {}
    PREFIX = "shizu_feedback:"
    LINKS_LIMIT = 1000
    FLOOD_COUNT = 10
    FLOOD_WINDOW = 10
    PAGE_SIZE = 20
    COMMANDS = ("/broadcast", "/ban", "/unban", "/users")

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "enabled",
                True,
                lambda m: self.strings("cfg_doc_enabled"),
                validator=loader.validators.Boolean(),
                label=lambda: self.strings("cfg_label_enabled"),
            ),
            loader.ConfigValue(
                "greeting",
                None,
                lambda m: self.strings("cfg_doc_greeting"),
                label=lambda: self.strings("cfg_label_greeting"),
            ),
        )
        self._flood = {}

    def _get(self, key, default):
        return self.db.get("shizu.feedback", key, default)

    def _set(self, key, value):
        self.db.set("shizu.feedback", key, value)

    def _remember(self, key, name, value):
        items = self._get(key, {})
        items[str(name)] = value
        self._set(key, dict(list(items.items())[-self.LINKS_LIMIT :]))

    def _flooding(self, user_id):
        now = time.time()
        hits = [t for t in self._flood.get(user_id, []) if now - t < self.FLOOD_WINDOW]
        hits.append(now)
        self._flood[user_id] = hits
        return len(hits) > self.FLOOD_COUNT

    def _mention(self, user):
        return (
            f'<a href="tg://user?id={user.id}">{utils.escape_html(user.full_name)}</a>'
            f" (<code>{user.id}</code>)"
        )

    def _target(self, message):
        reply = message.reply_to_message
        if not reply:
            return None
        return self._get("links", {}).get(str(reply.message_id))

    @loader.on_bot(
        lambda self, app, m: (
            self.config["enabled"]
            and m.chat.type == "private"
            and not self.bot._is_owner(m.from_user.id)
            and not self.bot.gs(m.from_user.id)
        )
    )
    async def incoming_message_handler(self, app, message):
        user = message.from_user
        banned = self._get("banned", [])
        if user.id in banned:
            return

        if self._flooding(user.id):
            banned.append(user.id)
            self._set("banned", banned)
            await self._bot.send_message(
                self.me.id,
                self.strings("flood_banned").format(self._mention(user)),
                reply_markup=self.bot._generate_markup(
                    [
                        [
                            {
                                "text": self.strings("btn_unban"),
                                "data": f"{self.PREFIX}unban:{user.id}",
                            }
                        ]
                    ]
                ),
            )
            return

        users = self._get("users", {})
        is_new = str(user.id) not in users
        if users.get(str(user.id)) != user.full_name:
            users[str(user.id)] = user.full_name
            self._set("users", users)
        if is_new:
            await self._bot.send_message(
                self.me.id, self.strings("new_user").format(self._mention(user))
            )

        if message.text == "/start":
            await message.answer(self.config["greeting"] or self.strings("greeting"))
            return

        if (message.text or "").startswith("/"):
            return

        forwarded = await message.forward(self.me.id)
        self._remember("links", forwarded.message_id, user.id)
        self._remember(
            "sources", f"{user.id}:{message.message_id}", forwarded.message_id
        )

    @loader.on_bot(
        lambda self, app, m: (
            m.chat.type == "private"
            and m.from_user.id == self.me.id
            and not self.bot.gs(m.from_user.id)
            and (
                ((m.text or "").split() or [""])[0] in self.COMMANDS or self._target(m)
            )
        )
    )
    async def owner_message_handler(self, app, message):
        text = message.text or ""
        command = text.split(maxsplit=1)[0] if text.startswith("/") else None
        target = self._target(message)

        if command == "/broadcast":
            return await self._broadcast(message)

        if command == "/users":
            text, markup = self._page("users", 0)
            return await message.reply(text, reply_markup=markup)

        if command in ("/ban", "/unban"):
            args = text.split(maxsplit=1)[1:]
            if not target and args and args[0].isdigit():
                target = int(args[0])
            if not target:
                return await message.reply(self.strings("no_target"))
            banned = [i for i in self._get("banned", []) if i != target]
            if command == "/ban":
                banned.append(target)
            self._set("banned", banned)
            return await message.reply(
                self.strings("banned" if command == "/ban" else "unbanned").format(
                    target
                )
            )

        if command:
            return

        try:
            copied = await message.copy_to(target)
            self._remember("replies", message.message_id, [target, copied.message_id])
        except (BotBlocked, UserDeactivated):
            await message.reply(self.strings("blocked"))
        except TelegramAPIError as error:
            await message.reply(
                self.strings("send_error").format(utils.escape_html(str(error)))
            )

    async def _broadcast(self, message):
        source = message.reply_to_message
        if not source:
            return await message.reply(self.strings("broadcast_usage"))

        banned = set(self._get("banned", []))
        users = self._get("users", {})
        gone, sent = set(), 0
        status = await message.reply(self.strings("broadcasting").format(len(users)))
        for user_id in list(users):
            if int(user_id) in banned:
                continue
            try:
                await source.copy_to(int(user_id))
                sent += 1
            except (BotBlocked, UserDeactivated):
                gone.add(user_id)
            except TelegramAPIError:
                logging.exception("Broadcast to %s failed", user_id)
            await asyncio.sleep(0.05)
        users = self._get("users", {})
        self._set("users", {k: v for k, v in users.items() if k not in gone})
        await status.edit_text(self.strings("broadcast_done").format(sent, len(gone)))

    def _page(self, kind, page):
        users = self._get("users", {})
        ids = (
            [int(i) for i in users]
            if kind == "users"
            else self._get("banned", [])
        )
        pages = max(1, -(-len(ids) // self.PAGE_SIZE))
        page = min(max(page, 0), pages - 1)
        chunk = ids[page * self.PAGE_SIZE : (page + 1) * self.PAGE_SIZE]
        lines = [
            f'▫️ <a href="tg://user?id={i}">'
            f"{utils.escape_html(users.get(str(i), str(i)))}</a> (<code>{i}</code>)"
            for i in chunk
        ]
        text = self.strings(f"{kind}_title").format(len(ids)) + "\n\n"
        text += "\n".join(lines) or self.strings("empty")
        if pages > 1:
            text += f"\n\n{page + 1}/{pages}"

        tabs = [
            {
                "text": self.strings(f"btn_{tab}"),
                "data": f"{self.PREFIX}list:{tab}:0",
            }
            for tab in ("users", "banned")
        ]
        nav = [
            {"text": label, "data": f"{self.PREFIX}list:{kind}:{target}"}
            for label, target in (("◀️", page - 1), ("▶️", page + 1))
            if 0 <= target < pages
        ]
        return text, self.bot._generate_markup([tabs, nav] if nav else [tabs])

    async def aiogram_edited_watcher(self, message):
        if message.chat.type != "private":
            return
        user_id = message.from_user.id

        if user_id == self.me.id:
            reply = self._get("replies", {}).get(str(message.message_id))
            if reply:
                await self._sync_edit(message, *reply)
            return

        if not self.config["enabled"] or user_id in self._get("banned", []):
            return
        forwarded = self._get("sources", {}).get(f"{user_id}:{message.message_id}")
        if not forwarded:
            return
        with contextlib.suppress(TelegramAPIError):
            copied = await message.copy_to(
                self.me.id,
                reply_to_message_id=forwarded,
                allow_sending_without_reply=True,
            )
            self._remember("links", copied.message_id, user_id)

    async def _sync_edit(self, message, chat_id, message_id):
        with contextlib.suppress(TelegramAPIError):
            if message.text:
                await self._bot.edit_message_text(
                    message.html_text, chat_id, message_id
                )
            elif message.caption is not None:
                await self._bot.edit_message_caption(
                    chat_id, message_id, caption=message.html_text
                )

    async def feedback_callback_handler(self, call: CallbackQuery):
        if not (call.data or "").startswith(self.PREFIX):
            return
        if not self.bot._is_owner(call.from_user.id):
            return await call.answer(self.strings("not_allowed"))
        action, _, payload = call.data[len(self.PREFIX) :].partition(":")
        if action == "list":
            kind, _, page = payload.partition(":")
            text, markup = self._page(kind, int(page or 0))
            await call.answer()
            with contextlib.suppress(TelegramAPIError):
                await call.message.edit_text(text, reply_markup=markup)
            return
        user_id = payload
        if action != "unban" or not user_id.isdigit():
            return
        self._set("banned", [i for i in self._get("banned", []) if i != int(user_id)])
        self._flood.pop(int(user_id), None)
        await call.answer(self.strings("unbanned").format(user_id))
        with contextlib.suppress(TelegramAPIError):
            await call.message.edit_reply_markup(None)
