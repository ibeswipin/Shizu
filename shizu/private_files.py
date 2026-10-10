"""Private local files without changing permissions on shared parent directories."""

import contextlib
import io
import os
import stat
import tempfile
from pathlib import Path


class PrivateFiles:
    @staticmethod
    def restrict_process() -> None:
        os.umask(0o077)

    @classmethod
    def directory(cls, path: str | Path) -> None:
        cls.restrict_process()
        path = Path(path)
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            if not stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("Private storage must be a directory.")
            os.fchmod(fd, 0o700)
        finally:
            os.close(fd)

    @staticmethod
    def _open(path: Path, flags: int) -> int:
        fd = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("Private storage must be a regular file.")
            os.fchmod(fd, 0o600)
        except BaseException:
            os.close(fd)
            raise
        return fd

    @classmethod
    def secure_existing(cls, path: str | Path) -> None:
        try:
            fd = cls._open(Path(path), os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        except FileNotFoundError:
            return
        os.close(fd)

    @classmethod
    def secure_sqlite(cls, path: str | Path) -> None:
        cls.restrict_process()
        if str(path) == ":memory:":
            return
        for suffix in ("", "-journal", "-wal", "-shm"):
            cls.secure_existing(f"{path}{suffix}")

    @classmethod
    def read(cls, path: str | Path) -> bytes:
        fd = cls._open(Path(path), os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as file:
            return file.read()

    @classmethod
    def _temporary(cls, path: Path, data: bytes) -> Path:
        cls.restrict_process()
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        tmp = Path(name)
        try:
            with os.fdopen(fd, "wb") as file:
                os.fchmod(file.fileno(), 0o600)
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return tmp

    @classmethod
    def write(cls, path: str | Path, data: bytes) -> None:
        path = Path(path)
        cls.secure_existing(path)
        tmp = cls._temporary(path, data)
        try:
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    @classmethod
    def create_once(cls, path: str | Path, data: bytes) -> bytes:
        """Publish a complete key atomically; concurrent creators reuse the winner."""
        path = Path(path)
        try:
            return cls.read(path)
        except FileNotFoundError:
            pass
        tmp = cls._temporary(path, data)
        try:
            with contextlib.suppress(FileExistsError):
                os.link(tmp, path)
            return cls.read(path)
        finally:
            tmp.unlink(missing_ok=True)

    @classmethod
    def write_config(cls, path, config) -> None:
        text = io.StringIO()
        config.write(text)
        cls.write(path, text.getvalue().encode("utf-8"))
