"""Authenticated database backups; recovery keys never travel with the archive."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from shizu.private_files import PrivateFiles
from shizu.redaction import SecretRedactor


class BackupError(ValueError):
    """A safe, credential-free explanation suitable for the owner."""

    def __init__(self, message: str, code: str = "invalid_structure"):
        super().__init__(message)
        self.code = code


class EncryptedBackup:
    MAGIC = b"SHIZU-BACKUP:1\n"
    MAX_BYTES = 64 * 1024 * 1024

    def __init__(self, key_path: str | Path | None = None):
        self.key_path = (
            Path(
                key_path
                or os.environ.get("SHIZU_BACKUP_KEY_FILE")
                or Path.home() / ".config" / "shizu" / "backup.key"
            )
            .expanduser()
            .absolute()
        )

    def _cipher(self, *, create: bool) -> Fernet:
        try:
            if create and self.key_path.parent == Path.home() / ".config" / "shizu":
                PrivateFiles.directory(self.key_path.parent)
            key = (
                PrivateFiles.create_once(self.key_path, Fernet.generate_key())
                if create
                else PrivateFiles.read(self.key_path)
            ).strip()
            SecretRedactor.remember(key)
            return Fernet(key)
        except FileNotFoundError:
            raise BackupError(
                "Recovery key is missing. Restore the original key file first.",
                code="key_missing",
            ) from None
        except (OSError, ValueError, TypeError):
            raise BackupError(
                "Could not read a valid backup key file.", code="key_invalid"
            ) from None

    @staticmethod
    def _unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BackupError("Duplicate keys in the backup.")
            result[key] = value
        return result

    @staticmethod
    def _invalid_constant(value):
        raise BackupError("Non-finite numbers in the backup.")

    @classmethod
    def _decode_json(cls, data: bytes):
        try:
            return json.loads(
                data.decode("utf-8"),
                object_pairs_hook=cls._unique_object,
                parse_constant=cls._invalid_constant,
            )
        except (UnicodeError, ValueError, RecursionError):
            raise BackupError("Invalid backup structure.") from None

    @staticmethod
    def _validate_database(data, owner_id: int) -> dict:
        if not isinstance(data, dict) or any(
            not isinstance(section, dict) for section in data.values()
        ):
            raise BackupError("The backup must contain database sections.")
        # Database.get is the module API (section, key), not dict.get.
        saved_owner = dict.get(data, "shizu.me", {}).get("me")
        if saved_owner is not None and (
            type(saved_owner) is not int or saved_owner != owner_id
        ):
            raise BackupError(
                "This backup belongs to another Telegram account.", code="wrong_owner"
            )
        try:
            json.dumps(data, allow_nan=False)
        except (ValueError, TypeError, RecursionError):
            raise BackupError(
                "Invalid backup structure or non-finite numbers."
            ) from None
        return data

    def encrypt(self, data: dict, owner_id: int) -> bytes:
        self._validate_database(data, owner_id)
        try:
            payload = json.dumps(
                {
                    "version": 1,
                    "owner_id": owner_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "data": data,
                },
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (ValueError, TypeError, RecursionError):
            raise BackupError(
                "The database cannot be serialized safely.", code="serialization_failed"
            ) from None
        if len(payload) > (self.MAX_BYTES - len(self.MAGIC)) * 3 // 4 - 128:
            raise BackupError(
                "The database is too large for an encrypted backup (64 MiB limit).",
                code="too_large",
            )
        return self.MAGIC + self._cipher(create=True).encrypt(payload)

    def decrypt(
        self, archive: bytes, owner_id: int, *, allow_legacy: bool = False
    ) -> dict:
        if len(archive) > self.MAX_BYTES:
            raise BackupError("The backup exceeds the 64 MiB limit.", code="too_large")
        if not archive.startswith(self.MAGIC):
            if allow_legacy:
                return self._validate_database(self._decode_json(archive), owner_id)
            raise BackupError(
                "Expected an encrypted backup. For an old JSON backup use .restoredb --legacy.",
                code="encrypted_required",
            )
        try:
            payload = self._cipher(create=False).decrypt(archive[len(self.MAGIC) :])
        except InvalidToken:
            raise BackupError(
                "Wrong recovery key or damaged backup. The database was not changed.",
                code="decryption_failed",
            ) from None
        envelope = self._decode_json(payload)
        if (
            not isinstance(envelope, dict)
            or type(envelope.get("version")) is not int
            or envelope["version"] != 1
        ):
            raise BackupError("Unsupported backup version.", code="version_unsupported")
        if (
            type(envelope.get("owner_id")) is not int
            or envelope["owner_id"] != owner_id
        ):
            raise BackupError(
                "This backup belongs to another Telegram account.", code="wrong_owner"
            )
        return self._validate_database(envelope.get("data"), owner_id)
