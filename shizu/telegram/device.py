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


"""Consistent connection metadata for Pyrogram and Telethon."""

import configparser
import platform
from dataclasses import dataclass

from shizu.version import __version__


@dataclass(frozen=True)
class TelegramDeviceProfile:
    """Visible device details; these labels do not change the API app or IP."""

    device_model: str = "Shizu"
    system_version: str = platform.system() or "Unknown"
    app_version: str = ".".join(map(str, __version__))

    @classmethod
    def from_config(
        cls, config: configparser.ConfigParser | None = None
    ) -> "TelegramDeviceProfile":
        """Read shared labels from [pyrogram], preserving configured device names."""
        if config is None:
            config = configparser.ConfigParser()
            config.read("config.ini")
        defaults = cls()
        options = {}
        for name, fallback in defaults.client_options().items():
            options[name] = (
                config.get("pyrogram", name, fallback=fallback).strip() or fallback
            )
        return cls(**options)

    def client_options(self) -> dict[str, str]:
        """Constructor options supported by both client libraries."""
        return {
            "device_model": self.device_model,
            "system_version": self.system_version,
            "app_version": self.app_version,
        }
