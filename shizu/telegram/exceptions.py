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
