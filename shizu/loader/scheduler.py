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
import json
import logging
import secrets
import time

from shizu import utils
from shizu.diagnostics import profiler
from shizu.health import reporter

logger = logging.getLogger(__name__)


class TaskScheduler:
    """One-off module tasks kept in the database, so they survive restarts"""

    SECTION = "shizu.scheduler"
    TICK = 1

    def __init__(self, manager):
        self.manager = manager
        self._runner = None

    @property
    def _tasks(self) -> dict:
        return self.manager._db.get(self.SECTION, "tasks", {})

    def _save(self, tasks: dict) -> None:
        self.manager._db.set(self.SECTION, "tasks", tasks)

    def _module(self, name: str):
        for module in self.manager.modules:
            if module.name == name:
                return module
        return None

    def add(self, module, when, method: str, payload=None) -> str:
        if isinstance(when, datetime.datetime):
            at = when.timestamp()
        elif isinstance(when, datetime.timedelta):
            at = time.time() + when.total_seconds()
        else:
            at = time.time() + float(when)
        if not callable(getattr(module, method, None)):
            raise ValueError(f"{module.name} has no method {method!r}")
        json.dumps(payload)
        task_id = secrets.token_hex(6)
        tasks = dict(self._tasks)
        tasks[task_id] = {
            "module": module.name,
            "method": method,
            "at": at,
            "payload": payload,
        }
        self._save(tasks)
        return task_id

    def cancel(self, module, task_id: str) -> bool:
        tasks = dict(self._tasks)
        if tasks.get(task_id, {}).get("module") != module.name:
            return False
        tasks.pop(task_id)
        self._save(tasks)
        return True

    def cancel_matching(self, module, method: str, payload=None) -> int:
        tasks = dict(self._tasks)
        matching = [
            task_id
            for task_id, task in tasks.items()
            if task["module"] == module.name
            and task["method"] == method
            and task["payload"] == payload
        ]
        for task_id in matching:
            tasks.pop(task_id)
        if matching:
            self._save(tasks)
        return len(matching)

    def of(self, module) -> dict:
        return {
            task_id: task
            for task_id, task in self._tasks.items()
            if task["module"] == module.name
        }

    def start(self) -> None:
        if self._runner is None or self._runner.done():
            self._runner = utils.spawn(self._run())

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.TICK)
            try:
                self._run_due()
            except Exception:
                logger.exception("Scheduler tick failed")

    def _run_due(self) -> None:
        now = time.time()
        due = []
        for task_id, task in self._tasks.items():
            if task["at"] <= now and (module := self._module(task["module"])):
                due.append((task_id, task, module))
        if not due:
            return
        tasks = dict(self._tasks)
        for task_id, *_ in due:
            tasks.pop(task_id, None)
        self._save(tasks)
        for _, task, module in due:
            utils.spawn(self._call(module, task))

    @staticmethod
    async def _call(module, task: dict) -> None:
        handler = getattr(module, task["method"], None)
        if not callable(handler):
            logger.warning("%s has no method %s", module.name, task["method"])
            return
        try:
            with profiler.measure(handler, "task"):
                await handler(task["payload"])
        except Exception as error:
            logger.exception("Scheduled task %s.%s failed", module.name, task["method"])
            reporter.failure(f"{module.name} · task", error, module.name)
