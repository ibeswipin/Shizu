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

"""Handler timings and error reports for module developers"""

import contextlib
import html
import os
import platform
import re
import time
import traceback
from dataclasses import dataclass

from shizu.health import reporter
from shizu.redaction import SecretRedactor


@dataclass
class HandlerStats:
    module: str
    handler: str
    kind: str
    calls: int = 0
    total: float = 0.0
    slowest: float = 0.0
    errors: int = 0


class Profiler:
    """Counts how long each module command and watcher runs and how often it fails"""

    SLOW_WATCHER = 2.0
    SLOW_NOTICE = (
        "🐢 <b>{} is slow</b>\n"
        "The watcher <code>{}</code> took <code>{:.1f}</code> s on one message. "
        "Watchers run on every incoming message, so this slows down the whole userbot."
        "\n\nSee <code>.perf</code> for details."
    )

    def __init__(self):
        self.started = time.time()
        self.stats: dict[tuple, HandlerStats] = {}

    @staticmethod
    def _names(handler) -> tuple[str, str]:
        module = getattr(handler, "__self__", None)
        function = getattr(handler, "__func__", handler)
        return (
            getattr(module, "name", None) or "Shizu",
            getattr(function, "__name__", repr(function)),
        )

    @contextlib.contextmanager
    def measure(self, handler, kind: str):
        start = time.perf_counter()
        failed = False
        try:
            yield
        except Exception:
            failed = True
            raise
        finally:
            self._record(handler, kind, time.perf_counter() - start, failed)

    def _record(self, handler, kind: str, elapsed: float, failed: bool) -> None:
        module, name = self._names(handler)
        key = (module, name, kind)
        stats = self.stats.get(key)
        if stats is None:
            stats = self.stats[key] = HandlerStats(module, name, kind)
        stats.calls += 1
        stats.total += elapsed
        stats.slowest = max(stats.slowest, elapsed)
        stats.errors += failed
        if kind == "watcher" and elapsed >= self.SLOW_WATCHER:
            reporter.problem(
                f"slow:{module}.{name}",
                self.SLOW_NOTICE.format(
                    html.escape(module), html.escape(name), elapsed
                ),
            )

    def top(self, limit: int = 15) -> list[HandlerStats]:
        return sorted(self.stats.values(), key=lambda s: s.total, reverse=True)[
            :limit
        ]

    def reset(self) -> None:
        self.started = time.time()
        self.stats.clear()


class ErrorReports:
    """Error reports the owner can send to the module developer"""

    LIMIT = 50
    TRACE_LIMIT = 3000
    CORE_SUPPORT = "@shizu_talks"
    META = r"#\s*meta\s+{}:\s*(@\w+)"

    def __init__(self):
        self._items: dict[str, tuple[str, str]] = {}
        self._counter = 0

    def support_for(self, module) -> str | None:
        if module is None:
            return None
        if support := getattr(module, "support", None):
            return support
        manager = getattr(module, "all_modules", None)
        if manager and module.name in manager.cmodules:
            return self.CORE_SUPPORT
        source = (
            getattr(manager, "raw_modules", {}).get(type(module).__module__) or ""
        )
        for field in ("support", "developer"):
            if match := re.search(self.META.format(field), source):
                return match.group(1)
        return None

    @staticmethod
    def _scrub(text: str) -> str:
        for path in {os.getcwd(), os.path.expanduser("~")}:
            if len(path) > 1:
                text = text.replace(path, "~")
        return SecretRedactor.text(text)

    @staticmethod
    def _versions() -> str:
        from shizu.version import __version__, branch

        parts = [f"Shizu v{'.'.join(map(str, __version__))} ({branch})"]
        parts.append(f"Python {platform.python_version()} · {platform.system()}")
        for name in ("pyrogram", "telethon", "aiogram"):
            with contextlib.suppress(Exception):
                parts.append(f"{name} {__import__(name).__version__}")
        return "\n".join(parts)

    def create(self, handler, label: str) -> str | None:
        """Store a report of the exception being handled; returns its id"""
        module = getattr(handler, "__self__", None)
        support = self.support_for(module)
        if not support:
            return None
        trace = self._scrub(traceback.format_exc())[-self.TRACE_LIMIT :]
        version = getattr(module, "version", None)
        text = (
            "🐞 <b>Shizu error report</b>\n\n"
            f"<b>Module:</b> {html.escape(module.name)}"
            f"{f' v{html.escape(str(version))}' if version else ''}\n"
            f"<b>Handler:</b> <code>{html.escape(label)}</code>\n"
            f"{html.escape(self._versions())}\n\n"
            f"<pre>{html.escape(trace)}</pre>"
        )
        self._counter += 1
        report_id = str(self._counter)
        self._items[report_id] = (support, text)
        while len(self._items) > self.LIMIT:
            self._items.pop(next(iter(self._items)))
        return report_id

    def get(self, report_id: str) -> tuple[str, str] | None:
        return self._items.get(report_id)

    def pop(self, report_id: str) -> tuple[str, str] | None:
        return self._items.pop(report_id, None)


profiler = Profiler()
reports = ErrorReports()
