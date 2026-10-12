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

"""Command permissions, secret masking, private storage, and safe startup."""

import asyncio
import contextlib
import html
import io
import logging
import os
import re
import stat
import tempfile
import threading
import time
import traceback
from collections import defaultdict, deque
from collections.abc import Mapping
from pathlib import Path

OWNER = 1 << 0
SUDO = 1 << 1
SUPPORT = 1 << 2
GROUP_OWNER = 1 << 3
GROUP_ADMIN_ADD_ADMINS = 1 << 4
GROUP_ADMIN_CHANGE_INFO = 1 << 5
GROUP_ADMIN_BAN_USERS = 1 << 6
GROUP_ADMIN_DELETE_MESSAGES = 1 << 7
GROUP_ADMIN_PIN_MESSAGES = 1 << 8
GROUP_ADMIN_INVITE_USERS = 1 << 9
GROUP_ADMIN = 1 << 10
GROUP_MEMBER = 1 << 11
PM = 1 << 12
EVERYONE = 1 << 13

GROUP_ADMIN_ANY = (
    GROUP_ADMIN_ADD_ADMINS
    | GROUP_ADMIN_CHANGE_INFO
    | GROUP_ADMIN_BAN_USERS
    | GROUP_ADMIN_DELETE_MESSAGES
    | GROUP_ADMIN_PIN_MESSAGES
    | GROUP_ADMIN_INVITE_USERS
    | GROUP_ADMIN
)
DEFAULT_PERMISSIONS = OWNER | SUDO
ALL = (1 << 14) - 1

FLAGS = {
    "owner": OWNER,
    "sudo": SUDO,
    "support": SUPPORT,
    "group_owner": GROUP_OWNER,
    "group_admin_add_admins": GROUP_ADMIN_ADD_ADMINS,
    "group_admin_change_info": GROUP_ADMIN_CHANGE_INFO,
    "group_admin_ban_users": GROUP_ADMIN_BAN_USERS,
    "group_admin_delete_messages": GROUP_ADMIN_DELETE_MESSAGES,
    "group_admin_pin_messages": GROUP_ADMIN_PIN_MESSAGES,
    "group_admin_invite_users": GROUP_ADMIN_INVITE_USERS,
    "group_admin": GROUP_ADMIN,
    "group_member": GROUP_MEMBER,
    "pm": PM,
    "everyone": EVERYONE,
    "unrestricted": EVERYONE,
    "inline_everyone": EVERYONE,
}

TELETHON_RIGHTS = {
    GROUP_ADMIN_ADD_ADMINS: "add_admins",
    GROUP_ADMIN_CHANGE_INFO: "change_info",
    GROUP_ADMIN_BAN_USERS: "ban_users",
    GROUP_ADMIN_DELETE_MESSAGES: "delete_messages",
    GROUP_ADMIN_PIN_MESSAGES: "pin_messages",
    GROUP_ADMIN_INVITE_USERS: "invite_users",
}
PYROGRAM_RIGHTS = {
    GROUP_ADMIN_ADD_ADMINS: "can_promote_members",
    GROUP_ADMIN_CHANGE_INFO: "can_change_info",
    GROUP_ADMIN_BAN_USERS: "can_restrict_members",
    GROUP_ADMIN_DELETE_MESSAGES: "can_delete_messages",
    GROUP_ADMIN_PIN_MESSAGES: "can_pin_messages",
    GROUP_ADMIN_INVITE_USERS: "can_invite_users",
}

RATELIMIT_CALLS = 3
RATELIMIT_WINDOW = 10


def mask_of(func) -> int:
    """Permission bitmask declared on a command, 0 when none was declared"""
    target = getattr(func, "__func__", func)
    mask = 0
    for flag in getattr(target, "security", ()) or ():
        mask |= FLAGS.get(flag, 0)
    return mask


class SecurityManager:
    """Decides whether a sender may run a command"""

    def __init__(self, db):
        self._db = db
        self._calls = defaultdict(deque)

    @property
    def _me(self) -> int:
        return self._db.get("shizu.me", "me", None)

    @property
    def _owner(self) -> list:
        owners = list(self._db.get("shizu.me", "owners", []))
        if not self._db.get("shizu.owner", "status", False):
            owners = []
        return [self._me, *owners] if self._me else owners

    @property
    def _sudo(self) -> list:
        users = {int(uid) for uid in self._db.get("shizu.permissions", "users", {})}
        users |= {
            int(uid) for uid in self._db.get("shizu.commandgroups", "user_groups", {})
        }
        return sorted(users)

    @property
    def _support(self) -> list:
        return []

    def has_command_access(self, user_id: int, command: str = None) -> bool:
        if user_id in self._owner:
            return True
        if not command:
            return False
        user = str(user_id)
        if command in self._db.get("shizu.permissions", "users", {}).get(user, []):
            return True
        groups = self._db.get("shizu.commandgroups", "groups", {})
        return any(
            command in groups.get(name, [])
            for name in self._db.get("shizu.commandgroups", "user_groups", {}).get(
                user, []
            )
        )

    def rate_limited(self, user_id: int, command: str) -> bool:
        now = time.monotonic()
        calls = self._calls[(user_id, command)]
        while calls and now - calls[0] > RATELIMIT_WINDOW:
            calls.popleft()
        if len(calls) >= RATELIMIT_CALLS:
            return True
        calls.append(now)
        return False

    async def check(self, message, func=None, command: str = None, client=None) -> bool:
        """True when the sender of `message` may run `func` (or a raw bitmask)"""
        info = _message_info(message)
        if info["out"] or (info["user_id"] and info["user_id"] == self._me):
            return True
        user_id = info["user_id"]
        if not user_id:
            return False

        mask = func if isinstance(func, int) else mask_of(func) if func else 0
        if not mask:
            return self.has_command_access(user_id, command)

        if mask & OWNER and user_id in self._owner:
            return True
        if mask & (SUDO | SUPPORT) and self.has_command_access(user_id, command):
            return True
        if mask & EVERYONE:
            return True
        if mask & PM and info["private"]:
            return True
        if info["private"]:
            return False
        if mask & GROUP_MEMBER:
            return True
        if mask & (GROUP_OWNER | GROUP_ADMIN_ANY):
            return await _group_rights_allow(
                mask,
                client or getattr(message, "_client", None),
                info["chat_id"],
                user_id,
            )
        return False


def _message_info(message) -> dict:
    if hasattr(message, "sender_id") and hasattr(message, "is_private"):
        return {
            "out": bool(message.out),
            "user_id": message.sender_id,
            "private": bool(message.is_private),
            "chat_id": message.chat_id,
        }
    user = getattr(message, "from_user", None) or getattr(message, "sender_chat", None)
    chat = getattr(message, "chat", None)
    chat_type = getattr(getattr(chat, "type", None), "name", "")
    return {
        "out": bool(getattr(message, "outgoing", False))
        or bool(getattr(user, "is_self", False)),
        "user_id": getattr(user, "id", None),
        "private": chat_type in ("PRIVATE", "BOT"),
        "chat_id": getattr(chat, "id", None),
    }


async def _group_rights_allow(mask: int, client, chat_id, user_id) -> bool:
    if client is None or chat_id is None:
        return False
    try:
        if hasattr(client, "get_permissions"):
            perms = await client.get_permissions(chat_id, user_id)
            if perms.is_creator:
                return True
            if not perms.is_admin:
                return False
            if mask & GROUP_ADMIN:
                return True
            return any(
                mask & bit and getattr(perms, right, False)
                for bit, right in TELETHON_RIGHTS.items()
            )
        member = await client.get_chat_member(chat_id, user_id)
        status = getattr(member.status, "name", "")
        if status == "OWNER":
            return True
        if status != "ADMINISTRATOR":
            return False
        if mask & GROUP_ADMIN:
            return True
        privileges = member.privileges
        return any(
            mask & bit and getattr(privileges, right, False)
            for bit, right in PYROGRAM_RIGHTS.items()
        )
    except Exception:
        return False


class SecretRedactor:
    MASK = "[REDACTED]"
    _secrets = set()
    _lock = threading.RLock()
    _key = re.compile(
        r"(?:token|password|passwd|secret|api_hash|auth_key|session_string|"
        r"encryption_key|phone_code(?:_hash)?)",
        re.I,
    )
    _bot = re.compile(r"\b\d{5,}:[A-Za-z0-9_-]{30,}")
    _session = re.compile(r"(?<![\w-])[A-Za-z0-9_-]{200,}={0,2}(?![\w-])")
    _labelled = re.compile(
        r"(?P<label>(?:[\"']|&quot;|&#(?:x27|39);)?(?:[\w.-]*(?:token|password|passwd|secret|api_hash|"
        r"auth_key|session_string|encryption_key|phone_code(?:_hash)?))"
        r"(?:[\"']|&quot;|&#(?:x27|39);)?\s*[:=]\s*)"
        r"(?:\[REDACTED\]|&quot;[^\n]*?&quot;|&#(?:x27|39);[^\n]*?&#(?:x27|39);|"
        r"\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|"
        r"(?:&(?:\w+|#\d+|#x[\da-f]+);|[^\s,;<>}\]\"'])+)",
        re.I,
    )

    @classmethod
    def remember(cls, value) -> None:
        if isinstance(value, bytes):
            cls.remember(value.hex())
            cls.remember(repr(value))
            try:
                value = value.decode("utf-8")
            except UnicodeError:
                return
        if isinstance(value, str) and len(value) >= 8:
            with cls._lock:
                cls._secrets.add(value)

    @classmethod
    def remember_mapping(cls, value) -> None:
        pending, seen = [value], set()
        while pending:
            item = pending.pop()
            if not isinstance(item, (Mapping, list, tuple)) or id(item) in seen:
                continue
            seen.add(id(item))
            if isinstance(item, Mapping):
                for key, child in item.items():
                    if cls._key.search(str(key)):
                        cls.remember(child)
                    pending.append(child)
            else:
                pending.extend(item)

    @classmethod
    def text(cls, value) -> str:
        text = str(value)
        with cls._lock:
            secrets = sorted(cls._secrets, key=len, reverse=True)
        for secret in secrets:
            for variant in (secret, html.escape(secret)):
                text = text.replace(variant, cls.MASK)
        text = cls._bot.sub(cls.MASK, text)
        text = cls._session.sub(cls.MASK, text)
        return cls._labelled.sub(lambda m: m["label"] + cls.MASK, text)

    @classmethod
    def loguru_record(cls, record) -> None:
        text = record["message"]
        if exception := record["exception"]:
            text += "\n" + "".join(traceback.format_exception(*exception))
            record["exception"] = None
        record["message"] = cls.text(text)
        record["extra"] = {
            key: cls.MASK if cls._key.search(str(key)) else cls.text(value)
            for key, value in record["extra"].items()
        }


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
            if (
                os.path.dirname(path) != folder
                or not os.path.isfile(path)
            ):
                return False
            os.remove(path)
        self.leave()
        return True
