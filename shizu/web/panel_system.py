"""Read-only host metrics and metadata for the authenticated dashboard."""

import asyncio
import os
import platform
import stat
import time
from collections import deque
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import psutil

from shizu import utils
from shizu.security import SecretRedactor


class PanelSystem:
    def __init__(self, db, client, key_path):
        self.db, self.client, self.key_path = db, client, key_path
        self._lock = asyncio.Lock()
        self._cached = None
        self._sampled = 0
        self._history = deque(maxlen=24)

    @staticmethod
    def _read(operation):
        try:
            return operation()
        except (OSError, psutil.Error, NotImplementedError):
            return None

    async def metrics(self):
        async with self._lock:
            if self._cached is None or time.monotonic() - self._sampled >= 2:
                self._cached = await asyncio.to_thread(self._metrics)
                if self._cached["cpu_percent"] is not None:
                    self._history.append(self._cached["cpu_percent"])
                self._cached["history"] = list(self._history)
                self._sampled = time.monotonic()
            return self._cached

    def _metrics(self):
        # A short blocking sample runs in a worker, never in Telegram's event loop.
        cpu = self._read(lambda: psutil.cpu_percent(interval=0.2))
        memory = self._read(psutil.virtual_memory)
        swap = self._read(psutil.swap_memory)
        disk_path = Path(getattr(self.db, "location", ".") or ".").resolve().parent
        disk = self._read(lambda: psutil.disk_usage(str(disk_path)))
        process = self._read(psutil.Process)
        rss = self._read(lambda: process.memory_info().rss) if process else None
        threads = self._read(process.num_threads) if process else None
        boot = self._read(psutil.boot_time)
        return {
            "sampled_at": time.time(),
            "cpu_percent": cpu,
            "cpu_count": self._read(psutil.cpu_count),
            "load_average": self._read(os.getloadavg)
            if hasattr(os, "getloadavg")
            else None,
            "memory": {
                "total": memory.total,
                "used": memory.total - memory.available,
                "available": memory.available,
                "percent": memory.percent,
            }
            if memory
            else None,
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent,
            }
            if disk
            else None,
            "process": {"memory": rss, "threads": threads},
            "swap": {"total": swap.total, "used": swap.used, "percent": swap.percent}
            if swap
            else None,
            "host_uptime": max(0, int(time.time() - boot)) if boot else None,
            "shizu_uptime": utils.uptime(),
        }

    @staticmethod
    def file_info(kind, location):
        item = {"kind": kind, "name": "", "status": "unavailable"}
        if location is None:
            return item
        if str(location) == ":memory:":
            return {**item, "status": "memory"}
        path = Path(location)
        item["name"] = SecretRedactor.text(path.name)
        try:
            info = path.stat()
        except FileNotFoundError:
            return {**item, "status": "missing"}
        except OSError:
            return item
        if not stat.S_ISREG(info.st_mode):
            return item
        return {
            **item,
            "status": "present",
            "bytes": info.st_size,
            "modified": info.st_mtime,
            "mode": f"{stat.S_IMODE(info.st_mode):04o}",
            "private": not bool(info.st_mode & 0o077),
            "readable": os.access(path, os.R_OK),
            "writable": os.access(path, os.W_OK),
        }

    def diagnostics(self):
        packages = {}
        for name in ("kurigram", "aiohttp", "psutil", "cryptography"):
            try:
                packages[name] = version(name)
            except PackageNotFoundError:
                packages[name] = None
        storage = getattr(self.client, "storage", None)
        session_path = getattr(storage, "database", None)
        files = [
            self.file_info("database", getattr(self.db, "location", None)),
            self.file_info("session_file", session_path),
            self.file_info("backup_key", self.key_path),
        ]
        if session_path is not None and str(session_path) != ":memory:":
            for suffix in ("-wal", "-shm", "-journal"):
                item = self.file_info("session_auxiliary", f"{session_path}{suffix}")
                if item["status"] != "missing":
                    files.append(item)
        return {
            "python": platform.python_version(),
            "system": f"{platform.system()} {platform.release()}",
            "architecture": platform.machine(),
            "packages": packages,
            "database_sections": len(self.db),
            "files": files,
        }
