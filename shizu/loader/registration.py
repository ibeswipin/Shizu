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


import inspect
import sys
from importlib.machinery import ModuleSpec

from shizu import utils
from shizu.translator import Strings, Translator

from .compat import TelethonCompatibility
from .compiler import ModuleCompiler
from .handlers import HandlerRegistry
from .models import Module


class ModuleRegistrar:
    """Create module instances while preserving collision checks and injected API."""

    def __init__(self, manager):
        self.manager = manager

    def register(
        self,
        module_name: str,
        file_path: str = "",
        spec: ModuleSpec = None,
        is_telethon: bool = False,
    ) -> Module:
        module = ModuleCompiler.execute_module(module_name, file_path, spec)
        instance = None
        handlers = HandlerRegistry(self.manager)
        for value in vars(module).values():
            if not inspect.isclass(value) or not issubclass(value, Module):
                continue
            self.replace_clashing(module, value)
            self.bind_class(value)
            instance = value()
            self.bind_instance(instance, is_telethon)
            handlers.collect(instance)
            TelethonCompatibility(self.manager).configure_instance(instance)
            self.manager.modules.append(instance)
            handlers.register(instance)
        handlers.add_hidden(instance)
        return instance

    def replace_clashing(self, module, value):
        manager = self.manager
        clashing = [
            m
            for m in manager.modules
            if m.__class__.__name__ == value.__name__
            or getattr(m, "name", None) == getattr(value, "name", None)
        ]
        if any(manager.is_core(m) for m in clashing):
            raise ValueError(f"{value.__name__} clashes with a core module")
        for existing in clashing:
            manager.unload_module(existing, True)
        # Replacement teardown must not remove the new module's namespace.
        sys.modules[module.__name__] = module

    def bind_class(self, value):
        manager = self.manager
        value.db = manager._db
        value.all_modules = manager
        value.bot = manager.bot_manager
        value._bot = manager.bot_manager.bot
        value.inline_bot = manager.bot_manager.bot
        value.inline = manager.bot_manager
        value.me = manager.me
        value.tg_id = manager.me.id
        value._tg_id = manager.me.id
        value.app = manager._app
        value._app = manager._app
        value.strings = Strings(
            value, Translator(manager._app, manager._db), manager._db
        )
        value.userbot = "Shizu"
        value.cmodules = manager.cmodules
        value.get_mod = manager.get_module
        value.prefix = manager._db.get("shizu.loader", "prefixes", ["."])
        value.lookup = manager._lookup

        if utils.is_tl_enabled(manager._app):
            value.client = manager._app.tl
            value._client = manager._app.tl
            value.tl = manager._app.tl

    def bind_instance(self, instance, is_telethon):
        manager = self.manager
        if is_telethon:
            instance.m__telethon = True

        instance.reconfmod = manager.config_reconfigure
        instance.shizu = True
        instance.hidden = manager.hidden
        instance.inline = manager.bot_manager

        if utils.is_tl_enabled(manager._app):
            instance.client = manager._app.tl
            instance._client = manager._app.tl
            instance.tl = manager._app.tl
