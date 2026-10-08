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


"""Connection lifecycle for endpoints, setup handlers and the running userbot."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from pyrogram import Client
from pyrogram import errors as pyro_errors
from telethon import errors as tl_errors
from telethon.sessions import StringSession

from shizu.telegram.bridge import (
    ManagedTelegramClient,
    TelegramErrorMapper,
    TelethonLoginBridge,
)
from shizu.telegram.device import TelegramDeviceProfile
from shizu.telegram.exceptions import (
    AccountMismatch,
    InvalidTwoFactorPassword,
    LoginAttemptExpired,
    PyrogramSessionInvalid,
    SessionStorageError,
    TelegramConnectionError,
    TelegramFloodWait,
    TelegramRPCFailure,
    TelethonSessionInvalid,
    TwoFactorRequired,
)
from shizu.telegram.storage import SessionStorage

logger = logging.getLogger(__name__)


@dataclass
class ConnectionResult:
    """Public status plus an internal client; never serialize the client or session."""

    status: str
    warning: str
    client: ManagedTelegramClient | None = field(default=None, repr=False)


@dataclass
class PendingLogin:
    """Temporary client waiting for 2FA, retained only in process memory."""

    client: ManagedTelegramClient = field(repr=False)
    expires_at: float
    timer: asyncio.Task | None = field(default=None, repr=False)


class TelegramConnectionService:
    """Reuse a valid encrypted session or perform the explicit, consented QR bridge."""

    def __init__(
        self,
        bridge: TelethonLoginBridge,
        storage: SessionStorage,
        *,
        password_timeout: float = 180,
        on_invalid: Callable[[int], Awaitable[None]] | None = None,
    ) -> None:
        self.bridge, self.storage = bridge, storage
        self.password_timeout, self.on_invalid = password_timeout, on_invalid
        self._pending: dict[int, PendingLogin] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    @classmethod
    def from_environment(
        cls, api_id: int, api_hash: str, **kwargs: Any
    ) -> "TelegramConnectionService":
        """Use the same configured device profile as the primary client."""
        bridge = TelethonLoginBridge(
            int(api_id),
            api_hash,
            **TelegramDeviceProfile.from_config().client_options(),
        )
        return cls(bridge, SessionStorage.from_environment(), **kwargs)

    def _lock(self, user_id: int) -> asyncio.Lock:
        return self._locks.setdefault(user_id, asyncio.Lock())

    def prepare(self) -> ConnectionResult:
        """Return the notice before any QR token is created or accepted."""
        return ConnectionResult("ready", self.bridge.warning)

    async def _invalidate(self, user_id: int) -> None:
        await self.storage.invalidate(user_id)
        if self.on_invalid:
            await self.on_invalid(user_id)

    def _monitor(self, client: ManagedTelegramClient, user_id: int) -> None:
        async def invalidated() -> None:
            await self._invalidate(user_id)

        client.session_invalidated = invalidated

    async def _check_account(self, client: ManagedTelegramClient, user_id: int) -> None:
        me = await client.get_me()
        if me is None:
            client.connection_state.invalidated()
            raise TelethonSessionInvalid(
                "Telethon authorization is no longer valid. Please reconnect."
            )
        if me.id != user_id:
            client.connection_state.invalidated()
            raise AccountMismatch(
                "Telethon session belongs to another account. Please reconnect."
            )
        client.connection_state.authorized(user_id)
        client.hikka_me = me

    async def verify(
        self, client: ManagedTelegramClient, user_id: int, *, timeout: float = 10
    ) -> None:
        """Refresh the live account check; network errors never revoke a session."""
        async with self._lock(user_id):
            try:
                if not client.is_connected():
                    await asyncio.wait_for(client.connect(), timeout)
                await asyncio.wait_for(self._check_account(client, user_id), timeout)
            except (TelethonSessionInvalid, AccountMismatch):
                client.connection_state.invalidated()
                await self._invalidate(user_id)
                raise
            except (asyncio.TimeoutError, tl_errors.RPCError, OSError) as error:
                if TelegramErrorMapper.invalid_session(error):
                    client.connection_state.invalidated()
                    await self._invalidate(user_id)
                else:
                    client.connection_state.unavailable()
                raise TelegramErrorMapper.translate(error) from None

    async def _restore(self, user_id: int) -> ManagedTelegramClient:
        session = await self.storage.load(user_id)
        if not session:
            raise TelethonSessionInvalid(
                "Connect Telethon to create a separate authorization."
            )
        client = self.bridge.build_client(session)
        self._monitor(client, user_id)
        try:
            await client.connect()
            await self._check_account(client, user_id)
            return client
        except (TelethonSessionInvalid, AccountMismatch):
            try:
                await self._invalidate(user_id)
            finally:
                await client.disconnect()
            raise
        except (asyncio.TimeoutError, tl_errors.RPCError, OSError) as error:
            await client.disconnect()
            raise TelegramErrorMapper.translate(error) from None
        except BaseException:
            await client.disconnect()
            raise

    async def restore(self, user_id: int) -> ManagedTelegramClient:
        """Startup restore only: never silently create a new Telegram authorization."""
        async with self._lock(user_id):
            return await self._restore(user_id)

    async def _save(
        self, client: ManagedTelegramClient, user_id: int
    ) -> ConnectionResult:
        await self._check_account(client, user_id)
        try:
            await self.storage.save(user_id, StringSession.save(client.session))
        except SessionStorageError:
            # Do not leave an untracked authorized device if persistence fails.
            try:
                revoked = await client.log_out()
            except (
                asyncio.TimeoutError,
                TelegramConnectionError,
                tl_errors.RPCError,
                OSError,
            ):
                revoked = False
            if not revoked:
                logger.warning(
                    "Could not revoke unsaved Telethon authorization; remove the Shizu device in Telegram"
                )
            raise
        self._monitor(client, user_id)
        return ConnectionResult("connected", self.bridge.warning, client)

    async def _expire(self, user_id: int, pending: PendingLogin) -> None:
        await asyncio.sleep(self.password_timeout)
        async with self._lock(user_id):
            if self._pending.get(user_id) is pending:
                self._pending.pop(user_id)
                await pending.client.disconnect()

    def _forget_pending(self, user_id: int) -> None:
        pending = self._pending.pop(user_id, None)
        if pending and pending.timer and pending.timer is not asyncio.current_task():
            pending.timer.cancel()

    async def _password(self, user_id: int, password: str) -> ConnectionResult:
        pending = self._pending.get(user_id)
        if not pending or time.monotonic() >= pending.expires_at:
            if pending:
                self._forget_pending(user_id)
                await pending.client.disconnect()
            raise LoginAttemptExpired(
                "The password step expired. Start connecting again."
            )
        try:
            await self.bridge.handle_2fa(pending.client, password)
            result = await self._save(pending.client, user_id)
        except (InvalidTwoFactorPassword, TelegramFloodWait):
            raise
        except (asyncio.TimeoutError, tl_errors.RPCError, OSError) as error:
            self._forget_pending(user_id)
            await pending.client.disconnect()
            raise TelegramErrorMapper.translate(error) from None
        except BaseException:
            self._forget_pending(user_id)
            await pending.client.disconnect()
            raise
        self._forget_pending(user_id)
        return result

    async def primary_user_id(self, pyro: Client) -> int:
        """Identify the primary account while mapping revoked-session errors."""
        try:
            owner = await pyro.get_me()
        except (asyncio.TimeoutError, pyro_errors.RPCError, OSError) as error:
            raise TelegramErrorMapper.translate(error, primary=True) from None
        if owner is None:
            raise PyrogramSessionInvalid(
                "Sign in to the primary Telegram account again."
            )
        return owner.id

    async def connect(
        self, pyro: Client, user_id: int, *, password: str | None = None
    ) -> ConnectionResult:
        """Called after prepare/consent. A password resumes the same in-memory login."""
        async with self._lock(user_id):
            if await self.primary_user_id(pyro) != user_id:
                raise AccountMismatch("Primary session belongs to another account.")
            if password is not None:
                return await self._password(user_id, password)
            if user_id in self._pending:
                return ConnectionResult("need_2fa", self.bridge.warning)
            try:
                client = await self._restore(user_id)
            except TelethonSessionInvalid:
                pass
            else:
                return ConnectionResult("connected", self.bridge.warning, client)
            client = self.bridge.build_client()
            keep_client = False
            try:
                await client.connect()
                await self.bridge.login(client, pyro)
                result = await self._save(client, user_id)
                keep_client = True
                return result
            except TwoFactorRequired:
                pending = PendingLogin(client, time.monotonic() + self.password_timeout)
                self._pending[user_id] = pending
                pending.timer = asyncio.create_task(self._expire(user_id, pending))
                keep_client = True
                return ConnectionResult("need_2fa", self.bridge.warning)
            except (asyncio.TimeoutError, tl_errors.RPCError, OSError) as error:
                raise TelegramErrorMapper.translate(error) from None
            finally:
                if not keep_client:
                    await client.disconnect()

    @asynccontextmanager
    async def client_context(
        self, user_id: int
    ) -> AsyncIterator[ManagedTelegramClient]:
        """Use a saved session for a scoped operation and always close its connection."""
        client = await self.restore(user_id)
        try:
            yield client
        except tl_errors.RPCError as error:
            raise TelegramErrorMapper.translate(error) from None
        finally:
            await client.disconnect()

    async def cancel(self, user_id: int) -> None:
        """Cancel an unfinished password challenge without affecting a saved login."""
        async with self._lock(user_id):
            pending = self._pending.get(user_id)
            self._forget_pending(user_id)
            if pending:
                await pending.client.disconnect()

    async def close(self) -> None:
        """Shutdown hook: dispose of every unfinished login and its expiry timer."""
        timers = [pending.timer for pending in self._pending.values() if pending.timer]
        for user_id in list(self._pending):
            await self.cancel(user_id)
        if timers:
            await asyncio.gather(*timers, return_exceptions=True)


class TelegramDisconnectService:
    """Revoke the separate authorization remotely before deleting local ciphertext."""

    def __init__(self, connections: TelegramConnectionService) -> None:
        self.connections = connections

    async def disconnect(
        self, user_id: int, *, client: ManagedTelegramClient | None = None
    ) -> None:
        """Revoke a live client or a stored session; retain the row on logout failure."""
        await self.connections.cancel(user_id)
        async with self.connections._lock(user_id):
            row = await self.connections.storage.get(user_id)
            if row is None and client is None:
                return
            if client is None:
                client = self.connections.bridge.build_client(
                    self.connections.storage.decrypt(row)
                )
            self.connections._monitor(client, user_id)
            try:
                await client.connect()
                try:
                    await self.connections._check_account(client, user_id)
                    if not await client.log_out():
                        raise TelegramRPCFailure(
                            "Telegram did not confirm logout. Please try again."
                        )
                except TelethonSessionInvalid:
                    # Telegram has already revoked this authorization.
                    pass
                except tl_errors.RPCError as error:
                    if not TelegramErrorMapper.invalid_session(error):
                        raise TelegramErrorMapper.translate(error) from None
                await self.connections.storage.delete(user_id)
            except (asyncio.TimeoutError, OSError) as error:
                raise TelegramErrorMapper.translate(error) from None
            finally:
                await client.disconnect()
