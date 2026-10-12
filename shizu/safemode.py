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

"""Start without third-party modules after several failed starts in a row"""

import asyncio
import contextlib
import logging
import os


class SafeMode:
    """Counts starts that did not get stable and remembers which module was loading"""

    SECTION = "shizu.safemode"
    FAILED_STARTS = 3
    STABLE_AFTER = 60

    def __init__(self, db):
        self.db = db
        self.starts = db.get(self.SECTION, "starts", 0) + 1
        self.forced = bool(db.get(self.SECTION, "forced", False))
        self.active = self.forced or self.starts > self.FAILED_STARTS
        if loading := db.get(self.SECTION, "loading"):
            db.set(self.SECTION, "suspect", loading)
            db.pop(self.SECTION, "loading")
        self.suspect = db.get(self.SECTION, "suspect")
        db.set(self.SECTION, "starts", self.starts)
        if self.active and not self.forced:
            logging.warning(
                "Safe mode: %s failed starts in a row, third-party modules are skipped",
                self.starts - 1,
            )

    @classmethod
    def stopped_cleanly(cls, db) -> None:
        """A planned restart or stop is not a failed start"""
        if db is not None:
            db.pop(cls.SECTION, "starts")

    @contextlib.contextmanager
    def loading(self, origin: str):
        """Remember `origin` until it is loaded, so a crash points at it"""
        self.db.set(self.SECTION, "loading", origin)
        try:
            yield
        finally:
            self.db.pop(self.SECTION, "loading")

    async def watch(self) -> None:
        """Forget the failed starts once Shizu has been running for a while"""
        await asyncio.sleep(self.STABLE_AFTER)
        self.db.set(self.SECTION, "starts", 0)
        if not self.active:
            self.db.pop(self.SECTION, "suspect")

    def leave(self) -> None:
        """Load every module on the next start"""
        for key in ("starts", "forced", "suspect"):
            self.db.pop(self.SECTION, key)

    def remove_suspect(self, manager) -> bool:
        """Delete the module that broke the start; True when something was removed"""
        origin = self.suspect
        if not origin:
            return False
        if manager.remote_modules.is_remote(origin):
            manager.remote_modules.forget(origin)
            manager._db.set(
                "shizu.loader",
                "modules",
                [
                    m
                    for m in manager._db.get("shizu.loader", "modules", [])
                    if m != origin
                ],
            )
        else:
            path = os.path.realpath(origin)
            folder = os.path.realpath(manager._local_modules_path)
            name = os.path.basename(path)[:-3]
            if (
                os.path.dirname(path) != folder
                or not os.path.isfile(path)
                or name in manager.cmodules
            ):
                return False
            os.remove(path)
        self.leave()
        return True
