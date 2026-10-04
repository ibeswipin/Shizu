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


"""Authenticated aiohttp handlers for the optional Telethon setup step."""

import logging
from typing import Any
from urllib.parse import urlparse

from aiohttp import web

from shizu import database
from shizu.telegram.exceptions import SessionStorageError, TelegramConnectionError
from shizu.telegram.services import TelegramConnectionService, TelegramDisconnectService

logger = logging.getLogger(__name__)


class TelethonSetupController:
    """Only the browser which completed the primary login can authorize Telethon."""

    def __init__(self, setup: Any) -> None:
        self.setup = setup
        self.connections: TelegramConnectionService | None = None
        self.prepared = False

    def _authorize(self, request: web.Request) -> None:
        owner = getattr(self.setup, "setup_owner", None)
        if (
            not self.setup.authenticated
            or not owner
            or request.cookies.get("shizu_setup") != owner
        ):
            raise web.HTTPUnauthorized()
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc != request.host:
            raise web.HTTPForbidden()
        if self.setup.clients_set.is_set():
            raise web.HTTPConflict()

    def _service(self) -> TelegramConnectionService:
        if self.connections is None:
            self.connections = TelegramConnectionService.from_environment(
                self.setup.client.api_id, self.setup.client.api_hash
            )
        return self.connections

    def _error(self, error: TelegramConnectionError) -> web.Response:
        message = (
            "Telethon is unavailable on this server. You can continue without it."
            if isinstance(error, SessionStorageError)
            else str(error)
        )
        data = {"status": error.status, "error": message}
        if hasattr(error, "retry_after"):
            data["retry_after"] = error.retry_after
        return web.json_response(data, status=400)

    async def prepare(self, request: web.Request) -> web.Response:
        """Return the device confirmation notice before launching the bridge."""
        self._authorize(request)
        try:
            result = self._service().prepare()
        except TelegramConnectionError as error:
            return self._error(error)
        self.prepared = True
        return web.json_response({"status": result.status, "warning": result.warning})

    async def connect(self, request: web.Request) -> web.Response:
        """Start login or resume 2FA. User identity comes from the primary session."""
        self._authorize(request)
        if not self.prepared:
            return web.json_response(
                {"error": "Review the device confirmation notice first."}, status=409
            )
        password = (await request.text()) or None
        try:
            user_id = await self._service().primary_user_id(self.setup.client)
            result = await self._service().connect(
                self.setup.client, user_id, password=password
            )
            if result.status == "connected":
                try:
                    database.db.set("shizu.telethon", "enabled", True)
                    database.db.set("shizu.telethon", "status", "active")
                    self.setup.telethon_choice = True
                finally:
                    await result.client.disconnect()
            return web.json_response({"status": result.status})
        except TelegramConnectionError as error:
            return self._error(error)
        except Exception as error:
            # Setup exception loggers may include locals: never pass a traceback
            # from a boundary that handles passwords.
            logger.warning("Telethon setup failed (%s)", type(error).__name__)
            return web.json_response(
                {
                    "status": "connection_error",
                    "error": "Could not connect Telethon. Please try again.",
                },
                status=500,
            )
        finally:
            password = None

    async def skip(self, request: web.Request) -> web.Response:
        """Continue initial setup with Pyrogram only; discard any pending 2FA step."""
        self._authorize(request)
        try:
            if self.connections:
                await self.connections.cancel(
                    await self._service().primary_user_id(self.setup.client)
                )
        except TelegramConnectionError as error:
            return self._error(error)
        self.setup.telethon_choice = False
        database.db.set("shizu.telethon", "enabled", False)
        return web.json_response({"status": "skipped"})

    async def disconnect(self, request: web.Request) -> web.Response:
        """Explicitly terminate the separate authorization in Telegram and storage."""
        self._authorize(request)
        try:
            await TelegramDisconnectService(self._service()).disconnect(
                await self._service().primary_user_id(self.setup.client)
            )
        except TelegramConnectionError as error:
            return self._error(error)
        database.db.set("shizu.telethon", "enabled", False)
        database.db.set("shizu.telethon", "status", "disabled")
        self.setup.telethon_choice = False
        return web.json_response({"status": "disconnected"})

    async def close(self, app: web.Application | None = None) -> None:
        """Close pending client connections when the aiohttp application stops."""
        if self.connections:
            await self.connections.close()
