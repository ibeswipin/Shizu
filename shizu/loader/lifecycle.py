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


import contextlib
import inspect
import logging
import os
import re
import sys
import typing

from shizu import utils
from shizu.translator import Strings, Translator
from shizu.types import InfiniteLoop

from .handlers import HandlerRegistry
from .models import LoadError, Module, SelfUnload


def _hook_args(func, available: tuple) -> tuple:
    """Positional arguments `func` accepts, taken from `available` in order"""
    try:
        params = inspect.signature(func).parameters.values()
    except (ValueError, TypeError):
        return ()
    if any(p.kind is p.VAR_POSITIONAL for p in params):
        return available
    positional = [
        p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    return available[: len(positional)]


def iter_attrs(obj: typing.Any, /) -> list[tuple[str, typing.Any]]:
    """
    Returns list of attributes of object
    :param obj: Object to iterate over
    :return: List of attributes and their values

    taken from: https://github.com/hikariatama/Hikka/blob/master/hikka/loader.py
    """
    return ((attr, getattr(obj, attr)) for attr in dir(obj))


class ModuleLifecycle:
    """Run load and unload hooks and manage module loops."""

    def __init__(self, manager):
        self.manager = manager

    async def start_all(self) -> bool:
        """Sends commands to execute the function"""
        manager = self.manager
        for module in list(manager.modules):
            manager.config_reconfigure(module, manager._db)
            await manager.send_on_load(module, Translator(manager._app, manager._db))

    async def start(self, module: Module, translator: Translator) -> bool:
        """Used to perform the function after loading the module"""
        manager = self.manager
        if hasattr(module, "_client_ready_called") and module._client_ready_called:
            return True

        client = manager._app
        if getattr(module, "m__telethon", False):
            if not utils.is_tl_enabled(manager._app):
                return False
            client = manager._app.tl
            if getattr(module, "client", None) is None:
                module._client = module.client = module.tl = client

        for _, method in iter_attrs(module):
            if hasattr(method, "strings"):
                method.strings = Strings(method, translator, manager._db)
                method.translator = translator

        for _, method in iter_attrs(module):
            if isinstance(method, InfiniteLoop):
                method.module_instance = module

                if method.autostart:
                    method.start()

        module._client_ready_called = True

        for hook, args in (
            (module.on_load, (manager._app,)),
            (module.client_ready, (client, manager._db)),
        ):
            try:
                await hook(*_hook_args(hook, args))
            except (LoadError, SelfUnload) as error:
                reason = str(error) or type(error).__name__
                logging.error("Module %s was unloaded: %s", module.name, reason)
                module._load_error = reason
                with contextlib.suppress(Exception):
                    manager.unload_module(module, True)
                return False
            except Exception:
                logging.exception("%s failed in module %s", hook.__name__, module.name)

        added = {
            re.sub(r"_?cmd$", "", name).lower(): value
            for name, value in vars(module).items()
            if name.endswith("cmd") and callable(value)
        }
        module.command_handlers.update(added)
        manager.command_handlers.update(added)

        return True

    async def call_hook(self, module: Module, hook: str):
        manager = self.manager
        func = getattr(module, hook, None)
        if not callable(func):
            return
        try:
            client = getattr(module, "client", None) or manager._app
            await func(*_hook_args(func, (client, manager._db)))
        except Exception:
            logging.exception(
                "%s failed in module %s", hook, getattr(module, "name", module)
            )

    def unload(self, module_name=None, is_replace: bool = False) -> str:
        """Unloads the loaded (if loaded) module"""
        manager = self.manager
        if is_replace:
            module = module_name
        else:
            module = manager.find_module_strict(module_name)
            if not module or manager.is_core(module):
                return False

            with contextlib.suppress(TypeError, OSError):
                path = inspect.getfile(module.__class__)
                if os.path.isfile(path):
                    os.remove(path)

            spec = getattr(inspect.getmodule(module), "__spec__", None)
            if spec and spec.origin != "<string>":
                if manager.remote_modules.is_remote(spec.origin):
                    manager.remote_modules.forget(spec.origin)
                manager._db.set(
                    "shizu.loader",
                    "modules",
                    [
                        m
                        for m in manager._db.get("shizu.loader", "modules", [])
                        if m != spec.origin
                    ],
                )

        HandlerRegistry(manager).remove(module)

        if callable(getattr(module, "on_unload", None)):
            utils.spawn(manager.call_hook(module, "on_unload"))

        for attr in vars(type(module)).values():
            if (
                isinstance(attr, InfiniteLoop)
                and attr.module_instance is module
                and attr._task
            ):
                utils.spawn(attr.stop())

        module_module = inspect.getmodule(module)
        if module_module and module_module.__name__ in sys.modules:
            del sys.modules[module_module.__name__]

        return module.name
