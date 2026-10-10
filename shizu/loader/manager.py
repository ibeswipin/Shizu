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


import functools
import logging
from importlib.machinery import ModuleSpec
from types import FunctionType
from typing import Any

from pyrogram import Client, types

from shizu import bot, database, dispatcher, extrapatchs, health, loader, utils
from shizu import logger as logger_
from shizu.remote import RemoteModuleRegistry
from shizu.telegram.exceptions import TelegramConnectionError
from shizu.translator import Translator

from .compat import TelethonCompatibility
from .config import ModuleConfiguration
from .dependencies import DependencyInstaller
from .libraries import LibraryLoader
from .lifecycle import ModuleLifecycle
from .loading import ModuleLoader
from .models import Library, Module
from .registration import ModuleRegistrar
from .sources import ModuleSources


class ModulesManager:
    """Public module manager coordinating loader services and shared registries."""

    def __init__(self, app: Client, db: database.Database, me: types.User) -> None:
        self.modules: list[Module] = []
        self.watcher_handlers: list[FunctionType] = []

        self.command_handlers: dict[str, FunctionType] = {}
        self.message_handlers: dict[str, FunctionType] = {}
        self.inline_handlers: dict[str, FunctionType] = {}
        self.callback_handlers: dict[str, FunctionType] = {}

        self._local_modules_path: str = "./shizu/modules"

        self._app = app
        self._client = app

        self._db = db
        self.remote_modules = RemoteModuleRegistry(db)
        self.me = me

        self.aliases = self._db.get("shizu.loader", "aliases", {})

        self.dp: dispatcher.DispatcherManager = None
        self.bot_manager: bot.BotManager = None
        self.telethon_dp = None
        self.load_guard = None
        loader._db, loader._manager = db, self
        self.last_commands: dict[int, tuple] = {}
        self._libraries: dict[str, Library] = {}
        self.raw_modules: dict[str, str] = {}
        self._join_requests: dict[str, tuple] = {}

        self.root_module: Module = None
        self.cmodules = [
            "ShizuBackuper",
            "ShizuHelp",
            "ShizuLoader",
            "ShizuTerminal",
            "ShizuTester",
            "ShizuUpdater",
            "ShizuEval",
            "ShizuInfo",
            "ShizuConfig",
            "ShizuLanguages",
            "ShizuSettings",
            "ShizuOnload",
            "ShizuPermissions",
            "ShizuSystemd",
            "ShizuBeSafe",
            "ShizuPanel",
        ]
        self.hidden = []
        app.db = db

    @staticmethod
    def _pip_error(error: Exception) -> str:
        """pip's own error output, or the exception text when there is none"""
        return DependencyInstaller.error_output(error)

    def _is_telethon_module(self, source_code: str) -> bool:
        """Checks if the module is a Telethon module"""
        return TelethonCompatibility.detect_source(source_code)

    async def load(self, app: Client) -> bool:
        """Loads the module manager"""
        self.dp = dispatcher.DispatcherManager(app, self)
        await self.dp.load()

        self.bot_manager = bot.BotManager(app, self._db, self)
        await self.bot_manager.load()

        for handler in logging.getLogger().handlers:
            if isinstance(handler, logger_.Telegramhandler):
                handler.manager = self.bot_manager

        extrapatchs.MessageMagic(types.Message, app)

        if utils.is_tl_enabled(app):
            try:
                await app.telethon_connections.verify(app.tl, self.me.id)
            except TelegramConnectionError as error:
                logging.warning("Telethon dispatcher unavailable: %s", error.status)
            else:
                self.telethon_dp = dispatcher.TelethonDispatcherManager(app.tl, self)
                await self.telethon_dp.load()

        try:
            app.inline_bot = self.bot_manager.bot
            app.bot = self.bot_manager.bot
        except Exception:
            pass
        health.reporter.bind(app, getattr(self.bot_manager, "bot", None))

        sources = ModuleSources(self)
        await sources.load_local()
        await sources.load_remote()
        return True

    def _register_local(self, module_name: str, file_path: str, source_code: str):
        return ModuleSources(self).register_local(module_name, file_path, source_code)

    def register_instance(
        self,
        module_name: str,
        file_path: str = "",
        spec: ModuleSpec = None,
        is_telethon: bool = False,
    ) -> Module:
        """Registers the module"""
        return ModuleRegistrar(self).register(module_name, file_path, spec, is_telethon)

    def _lookup(self, modname: str):
        return next(
            (mod for mod in self.modules if mod.name.lower() == modname.lower()),
            False,
        )

    async def load_module(
        self,
        module_source: str,
        origin: str = "<string>",
        did_requirements: bool = False,
    ) -> str:
        """Loads a third-party module"""
        return await ModuleLoader(self).load(module_source, origin, did_requirements)

    def _remote_headers(self, url: str) -> dict | None:
        return ModuleSources(self).headers(url)

    def _remote_problem(self, url: str, error: Exception):
        return ModuleSources(self).report_problem(url, error)

    async def _remote_source(self, url: str, headers=None, *, kind="module"):
        return await ModuleSources(self).resolve(url, headers, kind=kind)

    async def load_remote_module(self, url: str, headers: dict | None = None):
        item = await self._remote_source(url, headers)
        return await self.load_module(item.source, item.url)

    async def review_remote_library(self, source: str, url: str):
        return await LibraryLoader(self).review(source, url)

    async def _telethon_ready(self) -> bool:
        """Verify Telethon again when the fast check fails and start its dispatcher"""
        return await TelethonCompatibility(self).ready()

    async def send_on_loads(self) -> bool:
        """Sends commands to execute the function"""
        return await ModuleLifecycle(self).start_all()

    @staticmethod
    def config_reconfigure(module: Module, db):
        """Reconfigures the module"""
        return ModuleConfiguration.configure(module, db)

    async def send_on_load(self, module: Module, translator: Translator) -> bool:
        """Used to perform the function after loading the module"""
        return await ModuleLifecycle(self).start(module, translator)

    @property
    def commands(self) -> dict[str, FunctionType]:
        return self.command_handlers

    @property
    def security(self):
        return dispatcher.DispatcherManager.security_manager()

    def dispatch(self, command: str) -> tuple:
        """Resolve an alias and return `(command, handler)`; handler is None when unknown"""
        command = command.lower()
        command = self.aliases.get(command, command).lower()
        return command, self.command_handlers.get(command)

    def last_command(self, message) -> tuple | None:
        chat_id = getattr(message, "chat_id", None) or getattr(
            getattr(message, "chat", None), "id", None
        )
        return self.last_commands.get(chat_id)

    def log(
        self,
        type_: str,
        *,
        group: Any = None,
        affected_uids: Any = None,
        data: Any = None,
    ):
        """Record an action performed by a module in the Shizu log"""
        details = ", ".join(
            f"{key}={value}"
            for key, value in (
                ("group", group),
                ("users", affected_uids),
                ("data", data),
            )
            if value is not None
        )
        logging.getLogger("shizu.actions").info(
            "%s%s", type_, f" ({details})" if details else ""
        )

    async def check_security(self, message, func) -> bool:
        """Whether the sender of `message` may run `func` (a handler or a permission bitmask)"""
        command = None
        if not isinstance(func, int):
            command = next(
                (
                    name
                    for name, handler in self.command_handlers.items()
                    if handler == func
                ),
                None,
            )
        return await self.security.check(
            message, func, command, getattr(self._app, "tl", None)
        )

    def _module_client(self):
        return TelethonCompatibility(self).client()

    async def import_library(
        self, url: str, *, suspend_on_error: bool = False
    ) -> "Library":
        """Load a shared library from `url` once; later calls return the same instance"""
        return await LibraryLoader(self).load(url, suspend_on_error=suspend_on_error)

    async def _exec_library(
        self, url: str, code: str, source: str, retried: bool = False
    ) -> "Library":
        return await LibraryLoader(self).execute(url, code, source, retried)

    async def request_join(self, module: Module, peer: Any, reason: str) -> bool:
        """Ask the owner in the bot chat whether to join `peer`; True if already a member"""
        client = self._module_client()
        try:
            if hasattr(client, "get_permissions"):
                await client.get_permissions(peer, "me")
            else:
                await client.get_chat_member(peer, "me")
            return True
        except Exception:
            pass

        key = f"{getattr(module, 'name', '?')}:{peer}"
        if key in self._db.get("shizu.loader", "declined_joins", []):
            return False

        token = utils.rand(16)
        self._join_requests[token] = (client, peer, key)

        async def decide(join: bool, call):
            if call.from_user.id != self.me.id:
                return await call.answer("🚫", show_alert=True)
            request = self._join_requests.pop(token, None)
            if not request:
                return await call.answer()
            join_client, join_peer, join_key = request
            if join:
                try:
                    if hasattr(join_client, "get_permissions"):
                        from telethon.tl.functions.channels import JoinChannelRequest

                        await join_client(JoinChannelRequest(join_peer))
                    else:
                        await join_client.join_chat(join_peer)
                    text = f"✅ Joined <code>{utils.escape_html(str(join_peer))}</code>"
                except Exception as error:
                    text = f"❌ Could not join: <code>{utils.escape_html(str(error))}</code>"
            else:
                declined = self._db.get("shizu.loader", "declined_joins", [])
                self._db.set("shizu.loader", "declined_joins", declined + [join_key])
                text = "❌ Declined"
            await call.message.edit_text(text)

        markup = self.bot_manager._generate_markup(
            [
                [
                    {"text": "✅ Join", "callback": functools.partial(decide, True)},
                    {
                        "text": "❌ Decline",
                        "callback": functools.partial(decide, False),
                    },
                ]
            ]
        )
        await self.bot_manager.bot.send_message(
            self.me.id,
            f"📨 <b>{utils.escape_html(getattr(module, 'name', 'Module'))}</b> asks to join "
            f"<code>{utils.escape_html(str(peer))}</code>\n\n<i>{utils.escape_html(reason)}</i>",
            reply_markup=markup,
        )
        return False

    async def call_hook(self, module: Module, hook: str):
        return await ModuleLifecycle(self).call_hook(module, hook)

    def find_module_strict(self, name: str) -> Module | None:
        name = (name or "").strip().lower()
        if not name:
            return None
        for module in self.modules:
            if module.name.lower() == name:
                return module
        handler = self.command_handlers.get(self.aliases.get(name, name))
        return getattr(handler, "__self__", None)

    def is_core(self, module: Module) -> bool:
        return module.name in self.cmodules

    def unload_module(self, module_name=None, is_replace: bool = False) -> str:
        """Unloads the loaded (if loaded) module"""
        return ModuleLifecycle(self).unload(module_name, is_replace)

    def get_module(
        self, name: str, by_commands_too: bool = False, _=None
    ) -> Module | None:
        """Exact module name, exact command or alias, then the closest partial match"""
        name = name.lower().strip()
        if not name:
            return None

        for module in self.modules:
            if module.name.lower() == name:
                return module

        if by_commands_too:
            command = self.aliases.get(name, name).lower()
            if module := getattr(self.command_handlers.get(command), "__self__", None):
                return module

        partial = [module for module in self.modules if name in module.name.lower()]
        if partial:
            return min(partial, key=lambda module: len(module.name))

        if by_commands_too:
            commands = sorted(
                (
                    command
                    for command in self.command_handlers
                    if name in command.lower()
                ),
                key=len,
            )
            for command in commands:
                if module := getattr(self.command_handlers[command], "__self__", None):
                    return module

        return None
