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
