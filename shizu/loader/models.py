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


import asyncio
from typing import TYPE_CHECKING, Any

from pyrogram import Client

from .decorators import module

if TYPE_CHECKING:
    from .manager import ModulesManager


@module(name="Unknown")
class Module:
    """Module description"""

    name: str
    author: str
    version: int | float

    async def on_load(self, app: Client) -> Any:
        """Called when loading the module"""

    async def client_ready(self, client=None) -> Any:
        """Called once the client is ready; receives the Telethon client for
        Telethon modules and the Pyrogram client otherwise"""

    def get_prefix(self) -> str:
        """First configured command prefix"""
        return self.db.get("shizu.loader", "prefixes", ["."])[0]

    def pointer(self, key: str, default: Any = None, item_type: Any = None):
        """List or dict bound to `key` that is saved on every change"""
        from shizu.pointers import PointerDict, PointerList

        if isinstance(default, dict) or item_type is dict:
            return PointerDict(self.db, self.name, key, default)
        return PointerList(self.db, self.name, key, default)

    def get(self, key: str, default: Any = None) -> Any:
        """Read a value from this module's database section"""
        db = getattr(self, "db", None)
        if db is None:
            return default
        return db.get(self.name, key, default)

    def set(self, key: str, value: Any) -> None:
        """Write a value to this module's database section"""
        db = getattr(self, "db", None)
        if db is None:
            return
        db.set(self.name, key, value)

    def adopt_config(self, old_name: str) -> None:
        """Take over config values saved under this module's former name"""
        old = self.db.get(old_name, "__config__", {})
        for key, value in old.items():
            if key in self.config:
                self.config[key] = value
        if old:
            self.db.pop(old_name, "__config__")

    @property
    def _db(self):
        return getattr(self, "db", None)

    @_db.setter
    def _db(self, value):
        self.db = value

    @property
    def allmodules(self) -> "ModulesManager":
        return getattr(self, "all_modules", None)

    @allmodules.setter
    def allmodules(self, value):
        self.all_modules = value

    async def invoke(
        self,
        command: str,
        args: str = "",
        peer: Any = None,
        message: Any = None,
        edit: bool = False,
    ):
        """Run another command by sending it as an outgoing message; with
        `edit=True` the given message is edited into the command instead"""
        text = f"{self.get_prefix()}{command} {args or ''}".strip()
        client = getattr(self, "client", None) or self.app
        if edit and message is not None:
            return await message.edit(text)
        target = peer
        if target is None and message is not None:
            target = getattr(message, "chat_id", None) or message.chat.id
        if target is None:
            target = "me"
        reply_to = (
            getattr(message, "id", None) if message is not None and not edit else None
        )
        if hasattr(client, "send_message") and hasattr(client, "get_permissions"):
            return await client.send_message(target, text, reply_to=reply_to)
        return await client.send_message(target, text, reply_to_message_id=reply_to)

    async def animate(
        self, message: Any, frames: list, interval: float, *, inline: bool = False
    ):
        """Edit `message` through `frames`, waiting `interval` seconds between them"""
        from shizu import utils

        if interval < 0.1:
            interval = 0.1
        for frame in frames:
            message = await utils.answer(message, frame) or message
            await asyncio.sleep(interval)
        return message

    async def import_lib(
        self,
        url: str,
        *,
        suspend_on_error: bool = False,
    ):
        """Download, review and initialise a shared library, cached per URL"""
        return await self.all_modules.import_library(
            url, suspend_on_error=suspend_on_error
        )

    async def request_join(
        self, peer: Any, reason: str, assure_joined: bool = False
    ) -> bool:
        """Ask the owner through the inline bot whether to join `peer`"""
        return await self.all_modules.request_join(self, peer, reason)


class Library:
    """Shared code loaded with `import_lib`; `init` is awaited once after loading"""

    name: str = None
    developer: str = None
    version: Any = None

    async def init(self):
        """Called once after the library is loaded"""

    def get(self, key: str, default: Any = None) -> Any:
        return self.db.get(self._section, key, default)

    def set(self, key: str, value: Any) -> None:
        self.db.set(self._section, key, value)

    def pointer(self, key: str, default: Any = None, item_type: Any = None):
        from shizu.pointers import PointerDict, PointerList

        if isinstance(default, dict) or item_type is dict:
            return PointerDict(self.db, self._section, key, default)
        return PointerList(self.db, self._section, key, default)

    @property
    def _section(self) -> str:
        return f"__lib__{self.name or type(self).__name__}"

    @property
    def _db(self):
        return getattr(self, "db", None)

    @_db.setter
    def _db(self, value):
        self.db = value


class LoadError(Exception):
    """Raise from `on_load` or `client_ready` to abort loading with a message"""


class SelfUnload(Exception):
    """Raise from `on_load` or `client_ready` to unload the module"""
