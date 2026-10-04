"""QR bridge using a NEW Telethon authorization; no Pyrogram key conversion."""

import asyncio
import base64
import binascii
import contextlib
import logging
import struct
from typing import Any
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs, urlparse

from pyrogram import Client, errors as pyro_errors
from pyrogram.raw.functions.auth import AcceptLoginToken
from telethon import TelegramClient
from telethon import errors as tl_errors
from telethon.sessions import StringSession
from telethon.network.mtprotosender import MTProtoSender
from telethon.tl.tlobject import TLObject

from shizu.telegram.exceptions import (
    InvalidTwoFactorPassword,
    LoginTimeout,
    LoginTokenError,
    PyrogramSessionInvalid,
    TelegramConnectionError,
    TelegramFloodWait,
    TelegramRPCFailure,
    TelethonSessionInvalid,
    TwoFactorRequired,
)
from shizu.telegram.state import TelethonConnectionState
from shizu.telegram.device import TelegramDeviceProfile

logger = logging.getLogger(__name__)


class TelegramErrorMapper:
    """Translate errors using their public types/IDs; never log request contents."""

    INVALID = {
        "AuthKeyUnregistered",
        "AuthKeyInvalid",
        "AuthKeyDuplicated",
        "SessionRevoked",
        "SessionExpired",
        "UserDeactivated",
        "UserDeactivatedBan",
    }
    TOKENS = {
        "AUTH_TOKEN_EXPIRED",
        "AUTH_TOKEN_INVALID",
        "AUTH_TOKEN_INVALIDX",
        "AUTH_TOKEN_INVALID2",
        "AUTH_TOKEN_ALREADY_ACCEPTED",
        "AUTH_TOKEN_EXCEPTION",
    }

    @classmethod
    def invalid_session(cls, error: BaseException) -> bool:
        return type(error).__name__.removesuffix("Error") in cls.INVALID

    @classmethod
    def token_error(cls, error: BaseException) -> bool:
        return (
            getattr(error, "ID", None) in cls.TOKENS
            or getattr(error, "message", None) in cls.TOKENS
            or type(error).__name__.startswith("AuthToken")
        )

    @classmethod
    def translate(
        cls, error: Exception, *, primary: bool = False
    ) -> TelegramConnectionError:
        """Return a safe domain exception, logging only class names."""
        logger.warning("Telegram connection failed (%s)", type(error).__name__)
        if cls.invalid_session(error):
            if primary:
                return PyrogramSessionInvalid(
                    "Sign in to the primary Telegram account again."
                )
            return TelethonSessionInvalid(
                "Telethon was disconnected in Telegram. Please reconnect."
            )
        if isinstance(error, (pyro_errors.FloodWait, tl_errors.FloodWaitError)):
            return TelegramFloodWait(
                int(getattr(error, "value", getattr(error, "seconds", 0)))
            )
        return TelegramRPCFailure(
            "Telegram could not complete the request. Please try again."
        )


class ManagedTelegramClient(TelegramClient):
    """Mark a saved authorization invalid on revoked-key errors in any RPC call."""

    session_invalidated: Callable[[], Awaitable[None]] | None = None
    _logging_out = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.connection_state = TelethonConnectionState()

    async def disconnect(self) -> None:
        """Closing a connection does not revoke the saved authorization."""
        try:
            await super().disconnect()
        finally:
            self.connection_state.disconnected()

    async def log_out(self) -> bool:
        """Preserve the cause of logout failure instead of Telethon swallowing RPC errors."""
        self._logging_out = True
        try:
            result = await super().log_out()
            if result:
                self.connection_state.invalidated()
            return result
        finally:
            self._logging_out = False

    async def _call(
        self,
        sender: MTProtoSender,
        request: TLObject | list[TLObject],
        ordered: bool = False,
        flood_sleep_threshold: int | None = None,
    ) -> Any:
        try:
            result = await super()._call(sender, request, ordered, flood_sleep_threshold)
        except tl_errors.RPCError as error:
            if (
                isinstance(error, tl_errors.AuthKeyUnregisteredError)
                and self.connection_state.user_id is None
                and self.session_invalidated is None
                and not self._logging_out
            ):
                # connect() probes get_me() before a fresh QR login. Telethon
                # must receive UnauthorizedError itself so get_me() returns
                # None and connection initialization can continue normally.
                raise
            if TelegramErrorMapper.invalid_session(error):
                self.connection_state.invalidated()
                if self.session_invalidated is not None:
                    await self.session_invalidated()
                raise TelegramErrorMapper.translate(error) from None
            if self._logging_out:
                raise TelegramErrorMapper.translate(error) from None
            raise
        except (OSError, asyncio.TimeoutError):
            self.connection_state.unavailable()
            raise
        else:
            self.connection_state.rpc_succeeded()
            return result


class TelethonLoginBridge:
    """Build clients and approve QR tokens through a connected Pyrogram client."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        *,
        device_model: str = TelegramDeviceProfile.device_model,
        app_version: str = TelegramDeviceProfile.app_version,
        system_version: str = TelegramDeviceProfile.system_version,
        timeout: float = 30,
    ) -> None:
        self.api_id, self.api_hash = api_id, api_hash
        self.device_model, self.app_version, self.system_version = (
            device_model,
            app_version,
            system_version,
        )
        self.timeout = timeout

    @property
    def warning(self) -> str:
        """Display this BEFORE the user initiates a separate authorization."""
        return f"Telegram спросит, узнаёте ли вы вход с устройства {self.device_model} — нажмите «Да»."

    def build_client(self, session: str | None = None) -> ManagedTelegramClient:
        """StringSession() creates fresh keys for a new client, entirely in memory."""
        try:
            stored = StringSession(session) if session else StringSession()
        except (ValueError, binascii.Error, struct.error):
            raise TelegramRPCFailure(
                "The stored Telethon session is malformed."
            ) from None
        return ManagedTelegramClient(
            stored,
            self.api_id,
            self.api_hash,
            device_model=self.device_model,
            app_version=self.app_version,
            system_version=self.system_version,
            flood_sleep_threshold=0,
        )

    def extract_token(self, url: str) -> bytes:
        """Validate a tg://login URL and restore missing base64url padding."""
        parsed = urlparse(url)
        tokens = parse_qs(parsed.query).get("token", [])
        if parsed.scheme != "tg" or parsed.netloc != "login" or len(tokens) != 1:
            raise LoginTokenError("Telegram returned an invalid login URL.")
        encoded = tokens[0]
        try:
            token = base64.b64decode(
                encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
            )
        except (ValueError, binascii.Error):
            raise LoginTokenError("Telegram returned an invalid login token.") from None
        if not token:
            raise LoginTokenError("Telegram returned an empty login token.")
        return token

    async def accept_token(self, pyro: Client, token: bytes) -> None:
        """Approve the new authorization from the already authorized primary client."""
        await pyro.invoke(AcceptLoginToken(token=token), sleep_threshold=0)

    async def _attempt(self, client: TelegramClient, pyro: Client) -> None:
        qr = await client.qr_login()
        token = self.extract_token(qr.url)
        # Telethon's wait registers its update listener before its first await.
        waiter = asyncio.create_task(qr.wait(timeout=self.timeout))
        try:
            await asyncio.sleep(0)
            await asyncio.wait_for(self.accept_token(pyro, token), self.timeout)
            await waiter
        finally:
            if not waiter.done():
                waiter.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await waiter

    async def login(self, client: TelegramClient, pyro: Client) -> None:
        """Retry ONLY token errors once; let Telethon handle login-token DC migration."""
        for attempt in range(2):
            try:
                await self._attempt(client, pyro)
                return
            except tl_errors.SessionPasswordNeededError:
                raise TwoFactorRequired("Enter your Telegram cloud password.") from None
            except TypeError:
                raise TelegramRPCFailure(
                    "Telegram returned an unexpected login response. Please reconnect."
                ) from None
            except asyncio.TimeoutError:
                raise LoginTimeout(
                    "Telegram login timed out. Please reconnect."
                ) from None
            except (pyro_errors.RPCError, tl_errors.RPCError) as error:
                if TelegramErrorMapper.token_error(error):
                    if not attempt:
                        continue
                    raise LoginTokenError(
                        "The login token was rejected twice. Please reconnect."
                    ) from None
                raise TelegramErrorMapper.translate(
                    error, primary=isinstance(error, pyro_errors.RPCError)
                ) from None

    async def handle_2fa(self, client: TelegramClient, password: str) -> None:
        """Submit a transient cloud password; never retain or log it."""
        if not password:
            raise InvalidTwoFactorPassword("Enter your Telegram cloud password.")
        try:
            await client.sign_in(password=password)
        except tl_errors.PasswordHashInvalidError:
            raise InvalidTwoFactorPassword(
                "Incorrect Telegram cloud password."
            ) from None
        except tl_errors.RPCError as error:
            raise TelegramErrorMapper.translate(error) from None
