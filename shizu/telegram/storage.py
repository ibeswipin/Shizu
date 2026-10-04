"""Async encrypted session storage. No Telegram .session files are created."""

import asyncio
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from shizu.telegram.exceptions import SessionStorageError


@dataclass(frozen=True)
class TelethonSessionRecord:
    """Persisted row. Only encrypted_session contains session credentials."""

    user_id: int
    encrypted_session: str
    created_at: datetime
    status: str


class SessionStorage:
    """Store Fernet-encrypted strings in a SQLite table, with I/O off the loop."""

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS telethon_sessions (
            user_id INTEGER PRIMARY KEY,
            encrypted_session TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'invalid'))
        )
    """

    def __init__(self, path: str | Path, encryption_key: str | bytes) -> None:
        self.path = Path(path)
        try:
            self._cipher = Fernet(encryption_key)
        except (ValueError, TypeError):
            raise SessionStorageError(
                "SHIZU_SESSION_KEY must be a valid Fernet key."
            ) from None
        self._lock = asyncio.Lock()

    @classmethod
    def from_environment(cls) -> "SessionStorage":
        """Require a stable key supplied by the operator; never generate silently."""
        key = os.environ.get("SHIZU_SESSION_KEY")
        if not key:
            raise SessionStorageError(
                "Set SHIZU_SESSION_KEY to enable encrypted Telethon sessions."
            )
        return cls(
            os.environ.get("SHIZU_TELETHON_DB", "telethon_sessions.sqlite3"), key
        )

    def _execute(self, query: str, parameters: tuple[Any, ...]) -> sqlite3.Row | None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            with connection:
                connection.execute(self.SCHEMA)
                return connection.execute(query, parameters).fetchone()

    async def _run(
        self, query: str, parameters: tuple[Any, ...] = ()
    ) -> sqlite3.Row | None:
        async with self._lock:
            try:
                return await asyncio.to_thread(self._execute, query, parameters)
            except (sqlite3.Error, OSError):
                raise SessionStorageError(
                    "Could not access the encrypted session store."
                ) from None

    async def get(self, user_id: int) -> TelethonSessionRecord | None:
        """Load metadata and ciphertext without exposing a plaintext session."""
        row = await self._run(
            "SELECT * FROM telethon_sessions WHERE user_id = ?", (user_id,)
        )
        if row is None:
            return None
        return TelethonSessionRecord(
            row["user_id"],
            row["encrypted_session"],
            datetime.fromisoformat(row["created_at"]),
            row["status"],
        )

    async def load(self, user_id: int) -> str | None:
        """Decrypt only an active row, refusing a wrong key or damaged ciphertext."""
        row = await self.get(user_id)
        if row is None or row.status != "active":
            return None
        return self.decrypt(row)

    def decrypt(self, record: TelethonSessionRecord) -> str:
        """Decrypt a row for login or explicit logout, including invalid rows."""
        try:
            return self._cipher.decrypt(record.encrypted_session.encode()).decode()
        except (InvalidToken, UnicodeError):
            raise SessionStorageError(
                "The stored session cannot be decrypted with this key."
            ) from None

    async def save(self, user_id: int, session: str) -> None:
        """Replace a user's authorization atomically after successful login."""
        if not session:
            raise SessionStorageError("Cannot save an empty Telethon session.")
        encrypted = self._cipher.encrypt(session.encode()).decode()
        created = datetime.now(timezone.utc).isoformat()
        await self._run(
            "INSERT INTO telethon_sessions VALUES (?, ?, ?, 'active') "
            "ON CONFLICT(user_id) DO UPDATE SET encrypted_session=excluded.encrypted_session, "
            "created_at=excluded.created_at, status='active'",
            (user_id, encrypted, created),
        )

    async def invalidate(self, user_id: int) -> None:
        """Keep the row for diagnostics/logout, but never reuse it for a login."""
        await self._run(
            "UPDATE telethon_sessions SET status='invalid' WHERE user_id=?", (user_id,)
        )

    async def delete(self, user_id: int) -> None:
        """Remove a row only after logout succeeded or revocation was established."""
        await self._run("DELETE FROM telethon_sessions WHERE user_id=?", (user_id,))
