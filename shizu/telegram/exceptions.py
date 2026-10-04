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


"""Public errors for Telegram connection handlers; messages contain no secrets."""


class TelegramConnectionError(Exception):
    """Base domain error with a frontend-friendly status."""

    status = "connection_error"


class SessionStorageError(TelegramConnectionError):
    """Encryption configuration or session persistence failed."""

    status = "storage_error"


class PyrogramSessionInvalid(TelegramConnectionError):
    """The primary account needs to sign in again."""

    status = "reauthorization_required"


class TelethonSessionInvalid(TelegramConnectionError):
    """The separate authorization was revoked; reconnect with user consent."""

    status = "reconnect_required"


class LoginTokenError(TelegramConnectionError):
    """A QR token failed even after one fresh-token retry."""

    status = "token_error"


class LoginTimeout(TelegramConnectionError):
    """Telegram did not complete the QR login in time."""

    status = "login_timeout"


class TwoFactorRequired(TelegramConnectionError):
    """A pending login needs the user's cloud password."""

    status = "need_2fa"


class InvalidTwoFactorPassword(TelegramConnectionError):
    """The supplied cloud password was rejected."""

    status = "invalid_password"


class LoginAttemptExpired(TelegramConnectionError):
    """The in-memory password challenge expired or belongs to another process."""

    status = "login_expired"


class TelegramRPCFailure(TelegramConnectionError):
    """A Telegram RPC or transport operation failed."""

    status = "rpc_error"


class TelegramFloodWait(TelegramConnectionError):
    """The caller must wait before trying again."""

    status = "flood_wait"

    def __init__(self, seconds: int):
        self.retry_after = seconds
        super().__init__(f"Telegram asks you to wait {seconds} seconds.")


class AccountMismatch(TelegramConnectionError):
    """The stored or newly authorized client is for a different account."""

    status = "account_mismatch"
