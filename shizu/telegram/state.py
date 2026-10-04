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


"""Runtime state verified against Telegram, independent of the saved preference."""

import time
from enum import Enum
from typing import Any


class TelethonStatus(str, Enum):
    """A transport failure is recoverable; a revoked authorization is not."""

    UNVERIFIED = "unverified"
    READY = "ready"
    UNAVAILABLE = "unavailable"
    DISCONNECTED = "disconnected"
    INVALID = "invalid"


class TelethonConnectionState:
    """Track a client's verified account and subsequent RPC/transport outcomes."""

    def __init__(self) -> None:
        self.status = TelethonStatus.UNVERIFIED
        self.user_id: int | None = None
        self.verified_at: float | None = None

    def authorized(self, user_id: int) -> None:
        """Called only after a fresh get_me() matches the expected account."""
        self.user_id = user_id
        self.verified_at = time.monotonic()
        self.status = TelethonStatus.READY

    def rpc_succeeded(self) -> None:
        """Recover after a network interruption, without trusting a new client."""
        if self.user_id is not None and self.status != TelethonStatus.INVALID:
            self.status = TelethonStatus.READY

    def unavailable(self) -> None:
        if self.status != TelethonStatus.INVALID:
            self.status = TelethonStatus.UNAVAILABLE

    def disconnected(self) -> None:
        if self.status != TelethonStatus.INVALID:
            self.status = TelethonStatus.DISCONNECTED

    def invalidated(self) -> None:
        self.status = TelethonStatus.INVALID

    def ready(self, client: Any) -> bool:
        """Fast local check; fresh server validation is performed by the service."""
        if not client.is_connected():
            self.disconnected()
            return False
        return self.status == TelethonStatus.READY and self.user_id is not None
