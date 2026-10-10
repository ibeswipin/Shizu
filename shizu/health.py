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
import logging
import time
from collections import defaultdict, deque

from shizu import database, utils
from shizu.redaction import SecretRedactor

logger = logging.getLogger(__name__)


class Reporter:
    """Tells the owner about problems that need attention, at most once per problem per hour"""

    THRESHOLD = 5
    WINDOW = 600
    MUTE = 3600

    SESSION_ENDED = (
        "🔑 <b>Telegram ended the Shizu session.</b>\n"
        "The userbot is offline until you log in again."
    )
    LOGIN_WEB = "\n\nLog in here: {}"
    LOGIN_CONSOLE = "\n\nLog in on the server: <code>bash install.sh</code> or <code>python -m shizu</code>."
    BOT_TOKEN = (
        "🤖 <b>The bot token stopped working.</b>\n"
        "{}\n\nSet a new token: <code>.setbot &lt;token&gt;</code>"
    )
    FAILING = (
        "⚠️ <b>{} keeps failing</b>\n"
        "{} errors in the last {} minutes. The last one:\n<code>{}</code>"
        "{}"
    )
    UNLOAD_HINT = (
        "\n\nIf it is a module you do not need, unload it: <code>.unloadmod {}</code>"
    )

    def __init__(self):
        self.app = None
        self.bot = None
        self._failures = defaultdict(deque)
        self._sent = {}

    def bind(self, app, bot) -> None:
        self.app, self.bot = app, bot

    @staticmethod
    def _chat():
        return database.db.get("shizu.chat", "logs", None)

    def _due(self, key: str) -> bool:
        now = time.monotonic()
        if now - self._sent.get(key, -self.MUTE) < self.MUTE:
            return False
        self._sent[key] = now
        return True

    def failure(self, source: str, error: BaseException, module: str = None) -> None:
        """Count an error of `source`; report once it keeps happening"""
        now = time.monotonic()
        times = self._failures[source]
        times.append(now)
        while times and now - times[0] > self.WINDOW:
            times.popleft()
        if len(times) < self.THRESHOLD:
            return
        count = len(times)
        times.clear()
        text = self.FAILING.format(
            html.escape(source),
            count,
            self.WINDOW // 60,
            html.escape(SecretRedactor.text(f"{type(error).__name__}: {error}"))[:500],
            self.UNLOAD_HINT.format(html.escape(module)) if module else "",
        )
        self.problem(f"failing:{source}", text)

    def problem(self, key: str, text: str) -> None:
        """Send `text` in the background unless this problem was reported within the last hour"""
        if not self._due(key):
            return
        with contextlib.suppress(RuntimeError):
            utils.spawn(self.send(text))

    async def send(self, text: str, prefer_userbot: bool = False) -> bool:
        """Logs chat through the bot, falling back to the userbot (or the other way round)"""
        text = SecretRedactor.text(text)
        chat = self._chat()
        senders = [self._via_bot, self._via_userbot]
        if prefer_userbot:
            senders.reverse()
        for sender in senders:
            try:
                if await sender(chat, text):
                    return True
            except Exception:
                logger.debug(
                    "Problem notice via %s failed", sender.__name__, exc_info=True
                )
        logger.error("Could not deliver a problem notice: %s", text)
        return False

    async def _via_bot(self, chat, text: str) -> bool:
        if not self.bot or not chat:
            return False
        await self.bot.send_message(
            chat, text, parse_mode="html", disable_web_page_preview=True
        )
        return True

    async def _via_userbot(self, chat, text: str) -> bool:
        if not self.app:
            return False
        await self.app.send_message(chat or "me", text, disable_web_page_preview=True)
        return True

    @classmethod
    async def notify_owner_by_token(cls, text: str, key: str) -> bool:
        """Message the owner from the bot when the userbot itself cannot run; once an hour per `key`, across restarts"""
        text = SecretRedactor.text(text)
        token = database.db.get("shizu.bot", "token", None)
        owner = database.db.get("shizu.me", "me", None)
        if not token or not owner:
            return False
        if time.time() - database.db.get("shizu.health", key, 0) < cls.MUTE:
            return False
        database.db.set("shizu.health", key, time.time())
        from aiogram import Bot

        bot = Bot(token=token)
        try:
            await bot.send_message(
                owner, text, parse_mode="html", disable_web_page_preview=True
            )
            return True
        except Exception:
            logger.warning("Could not notify the owner through the bot", exc_info=True)
            return False
        finally:
            await (await bot.get_session()).close()


reporter = Reporter()
