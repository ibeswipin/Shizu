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
import datetime
import re

from types import FunctionType
from typing import Any, Dict, List, Union
from logging import getLogger

from pyrogram import Client, types

from shizu import database
from shizu.health import reporter

logger = getLogger(__name__)


class Module:
    """Base class for modules"""

    name: str
    author: str
    version: Union[int, float]

    async def on_load(self, app: Client) -> Any:
        """called when loading the module"""


class ModulesManager:
    """Manager of modules"""

    def __init__(self) -> None:
        self.modules: List[Module]
        self.watcher_handlers: List[FunctionType]

        self.command_handlers: Dict[str, FunctionType]
        self.message_handlers: Dict[str, FunctionType]
        self.inline_handlers: Dict[str, FunctionType]
        self.callback_handlers: Dict[str, FunctionType]

        self._local_modules_path: str
        self.me: types.User
        self._db: database.Database

        self.aliases: Dict[str, str]

        self.dp
        self.bot_manager


class StopLoop(Exception):
    """Stops the loop, in which is raised"""


class InfiniteLoop:
    _task = None
    status = False

    TIME_RE = re.compile(r"([01]?\d|2[0-3]):[0-5]\d")
    TIME_TICK = 20
    FALLBACK_INTERVAL = 60

    @classmethod
    def parse_times(cls, value) -> set:
        """"09:00", "9:00, 21:30" or ["09:00", "21:30"] -> {"09:00", "21:30"}"""
        items = value.replace(",", " ").split() if isinstance(value, str) else list(value)
        times = set()
        for item in items:
            item = str(item).strip()
            if not cls.TIME_RE.fullmatch(item):
                raise ValueError(f"invalid time {item!r}, use HH:MM")
            hours, minutes = item.split(":")
            times.add(f"{int(hours):02d}:{minutes}")
        if not times:
            raise ValueError("no time given, use HH:MM")
        return times

    @staticmethod
    def is_time_literal(value) -> bool:
        return not isinstance(value, str) or ":" in value or not value.strip()

    # piece of code: https://github.com/hikariatama/Hikka/blob/ce1f24f03313f8500de671815dde065fc8d86897/hikka/loader.py#L138
    def __init__(
        self,
        func: FunctionType,
        interval: Union[int, str, None],
        autostart: bool,
        wait_before: bool,
        time: Union[str, List[str], None] = None,
    ):
        name = getattr(func, "__qualname__", func)
        if (interval is None) == (time is None):
            raise ValueError(
                f"{name}: loader.loop needs either interval= (seconds or a config key) "
                "or time= (\"HH:MM\", a list of them, or a config key), not both"
            )
        if isinstance(interval, bool) or (
            interval is not None and not isinstance(interval, str) and (not isinstance(interval, int) or interval <= 0)
        ):
            raise ValueError(f"{name}: loop interval must be a positive number of seconds or a config key")
        if time is not None and self.is_time_literal(time):
            self.parse_times(time)
        self.func = func
        self.interval = interval
        self.time = time
        self.autostart = autostart
        self._wait_before = wait_before
        self.module_instance = None
        self._task = None
        self._wait_for_stop = asyncio.Event()
        self._last_problem = None

    def _problem(self, text: str) -> None:
        if text != self._last_problem:
            self._last_problem = text
            logger.error("Loop %s: %s", getattr(self.func, "__qualname__", self.func), text)

    def _config(self, key: str):
        config = getattr(self.module_instance, "config", None)
        if config is None or key not in config:
            raise ValueError(f"config has no key {key!r}")
        return config[key]

    def current_interval(self) -> int:
        try:
            value = self._config(self.interval) if isinstance(self.interval, str) else self.interval
            value = int(value)
            if value <= 0:
                raise ValueError
        except (TypeError, ValueError) as e:
            self._problem(f"invalid interval ({e or 'must be a positive number'}), using {self.FALLBACK_INTERVAL} s")
            return self.FALLBACK_INTERVAL
        self._last_problem = None
        return value

    def current_times(self) -> set:
        try:
            value = self.time if self.is_time_literal(self.time) else self._config(self.time)
            times = self.parse_times(value)
        except (TypeError, ValueError) as e:
            self._problem(f"{e}; the loop is paused until it is fixed")
            return set()
        self._last_problem = None
        return times

    def _stop(self, *args, **kwargs):
        self._wait_for_stop.set()

    async def stop(self, *args, **kwargs) -> bool:
        if self._task:
            logger.info("Stopped loop for method %s", self.func)
            self._wait_for_stop = asyncio.Event()
            self.status = False
            task, self._task = self._task, None
            task.add_done_callback(self._stop)
            task.cancel()
            return await self._wait_for_stop.wait()

        logger.info("Loop is not running")
        return True

    def start(self, *args, **kwargs):
        if not self._task:
            self._task = asyncio.ensure_future(self.actual_loop(*args, **kwargs))
        else:
            logger.info("Attempted to start already running loop")

    async def _run(self, *args, **kwargs) -> bool:
        try:
            await self.func(self.module_instance, *args, **kwargs)
        except StopLoop:
            return False
        except Exception as error:
            logger.exception("Error running loop!")
            module = getattr(self.module_instance, "name", None)
            reporter.failure(f"{module or 'Shizu'} · {self.func.__name__}", error, module)
        return True

    async def actual_loop(self, *args, **kwargs):
        self.status = True
        fired = None

        while self.status:
            if self.time is not None:
                now = datetime.datetime.now()
                stamp = now.strftime("%Y-%m-%d %H:%M")
                if stamp != fired and now.strftime("%H:%M") in self.current_times():
                    fired = stamp
                    if not await self._run(*args, **kwargs):
                        break
                await asyncio.sleep(self.TIME_TICK)
                continue

            if self._wait_before:
                await asyncio.sleep(self.current_interval())
            if not await self._run(*args, **kwargs):
                break
            if not self._wait_before:
                await asyncio.sleep(self.current_interval())

        self._wait_for_stop.set()

        self.status = False

    def __del__(self):
        if self._task and not self._task.done():
            self._task.cancel()
