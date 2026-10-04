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
import functools
import logging
import time
from collections import defaultdict, deque

from shizu.health import reporter

logger = logging.getLogger(__name__)


class ApiLimiter:
    """Paces userbot API requests so a busy module cannot get the account flood-banned.
    Requests over a limit wait for their turn instead of failing."""

    GLOBAL = (30, 1)
    CHAT_SENDS = (20, 60)
    BURST = (400, 30)
    PAUSE = 15
    SEND_METHODS = {
        "SendMessage",
        "SendMedia",
        "SendMultiMedia",
        "ForwardMessages",
        "SendInlineBotResult",
    }
    BURST_NOTICE = (
        "🛡 <b>API protection paused Shizu for {} seconds.</b>\n"
        "Something sent {} requests in {} seconds, which risks a flood ban. "
        "Check your modules if this repeats."
    )

    def __init__(self, db):
        self.db = db
        self._global = deque()
        self._burst = deque()
        self._chats = defaultdict(deque)
        self._paused_until = 0.0

    @property
    def enabled(self) -> bool:
        return self.db.get("shizu.api", "protection", True)

    def attach(self, client) -> None:
        original = client.invoke

        @functools.wraps(original)
        async def invoke(query, *args, **kwargs):
            if self.enabled:
                await self.throttle(query)
            return await original(query, *args, **kwargs)

        client.invoke = invoke

    @staticmethod
    def _peer_key(query):
        peer = getattr(query, "to_peer", None) or getattr(query, "peer", None)
        if peer is None:
            return None
        for field in ("channel_id", "chat_id", "user_id"):
            if (value := getattr(peer, field, None)) is not None:
                return value
        return type(peer).__name__

    @staticmethod
    async def _take(times: deque, limit: int, window: float) -> None:
        while True:
            now = time.monotonic()
            while times and now - times[0] >= window:
                times.popleft()
            if len(times) < limit:
                times.append(now)
                return
            await asyncio.sleep(window - (now - times[0]) + 0.01)

    def _check_burst(self) -> None:
        limit, window = self.BURST
        now = time.monotonic()
        self._burst.append(now)
        while self._burst and now - self._burst[0] >= window:
            self._burst.popleft()
        if len(self._burst) > limit and now >= self._paused_until:
            count = len(self._burst)
            self._burst.clear()
            self._paused_until = now + self.PAUSE
            logger.warning(
                "API protection: %s requests in %ss, pausing for %ss",
                count,
                window,
                self.PAUSE,
            )
            reporter.problem(
                "api_burst", self.BURST_NOTICE.format(self.PAUSE, count, window)
            )

    async def throttle(self, query) -> None:
        self._check_burst()
        if (wait := self._paused_until - time.monotonic()) > 0:
            await asyncio.sleep(wait)
        await self._take(self._global, *self.GLOBAL)
        if (
            type(query).__name__ in self.SEND_METHODS
            and (key := self._peer_key(query)) is not None
        ):
            await self._take(self._chats[key], *self.CHAT_SENDS)
