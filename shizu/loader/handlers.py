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
import re
from types import FunctionType

from shizu import loader

from .models import Module


def get_command_handlers(instance: Module) -> dict[str, FunctionType]:
    """Returns a dictionary of command names with their corresponding functions"""

    return {
        re.sub(r"_?cmd$", "", method_name).lower(): method
        for method_name, method in inspect.getmembers(instance, inspect.ismethod)
        if hasattr(method, "is_command") or method_name.endswith("cmd")
    }


def get_watcher_handlers(instance: Module) -> list[FunctionType]:
    """Returns a list of watchers bound to the instance"""
    watchers = []

    for attr_name in dir(instance):
        if attr_name.startswith("_"):
            continue

        try:
            attr = getattr(instance, attr_name, None)
            if not attr or not callable(attr):
                continue

            is_watcher_by_name = "watcher" in attr_name.lower()

            func_for_check = attr
            if inspect.ismethod(attr):
                func_for_check = getattr(attr, "__func__", attr)
            elif callable(attr) and not inspect.isfunction(attr):
                func_for_check = getattr(attr, "__func__", attr)

            is_watcher_decorated = getattr(func_for_check, "is_watcher", False)

            if is_watcher_by_name or is_watcher_decorated:
                if inspect.ismethod(attr):
                    watchers.append(attr)
                elif inspect.isfunction(attr):
                    import types

                    bound_method = types.MethodType(attr, instance)
                    watchers.append(bound_method)
                elif callable(attr):
                    watchers.append(attr)
        except Exception:
            continue

    return watchers


def get_message_handlers(instance: Module) -> dict[str, FunctionType]:
    """Returns a dictionary of names with message handler functions"""
    return {
        method_name[:-16].lower(): getattr(instance, method_name)
        for method_name in dir(instance)
        if (
            callable(getattr(instance, method_name))
            and len(method_name) > 16
            and method_name.endswith("_message_handler")
        )
    }


def _decorated(instance: Module, flag: str) -> dict[str, FunctionType]:
    return {
        getattr(method.__func__, flag + "_name", None) or name.lower(): method
        for name, method in inspect.getmembers(instance, inspect.ismethod)
        if getattr(method.__func__, flag, False)
    }


def get_callback_handlers(instance: Module) -> dict[str, FunctionType]:
    """Returns a dictionary of names with callback handler functions"""
    return {
        **{
            method_name[:-17].lower(): getattr(instance, method_name)
            for method_name in dir(instance)
            if (
                callable(getattr(instance, method_name))
                and len(method_name) > 17
                and method_name.endswith("_callback_handler")
            )
        },
        **_decorated(instance, "is_callback_handler"),
    }


def get_inline_handlers(instance: Module) -> dict[str, FunctionType]:
    """Returns a dictionary of names with inline handler functions"""
    instance_methods = dir(instance)

    return {
        **{
            method_name[:-15].lower(): method
            for method_name in instance_methods
            if (
                callable(method := getattr(instance, method_name))
                and method_name[-15:] == "_inline_handler"
            )
        },
        **_decorated(instance, "is_inline_handler"),
    }


def get_raw_handlers(instance: Module) -> list[FunctionType]:
    """Methods decorated with `raw_handler`"""
    return [
        method
        for _, method in inspect.getmembers(instance, inspect.ismethod)
        if getattr(method.__func__, "raw_handler_updates", None) is not None
    ]


class HandlerRegistry:
    """Collect handlers and keep the manager registries in sync with module lifetime."""

    def __init__(self, manager):
        self.manager = manager

    def collect(self, instance):
        instance.raw_handlers = loader.get_raw_handlers(instance)
        instance.command_handlers = loader.get_command_handlers(instance)
        instance.watcher_handlers = loader.get_watcher_handlers(instance)
        instance.message_handlers = loader.get_message_handlers(instance)
        instance.callback_handlers = loader.get_callback_handlers(instance)
        instance.inline_handlers = loader.get_inline_handlers(instance)

    def register(self, instance):
        manager = self.manager
        if manager.telethon_dp and getattr(instance, "m__telethon", False):
            manager.telethon_dp.register_raw(instance)

        is_telethon_module = getattr(instance, "m__telethon", False)
        if not is_telethon_module:
            manager.command_handlers.update(instance.command_handlers)
            if instance.watcher_handlers:
                manager.watcher_handlers.extend(instance.watcher_handlers)
            manager.message_handlers.update(instance.message_handlers)
            manager.callback_handlers.update(instance.callback_handlers)
            manager.inline_handlers.update(instance.inline_handlers)
        else:
            manager.command_handlers.update(instance.command_handlers)

    def remove(self, module):
        manager = self.manager

        def owned(handler) -> bool:
            return getattr(handler, "__self__", None) is module

        if module in manager.modules:
            manager.modules.remove(module)
        manager.watcher_handlers[:] = [
            w for w in manager.watcher_handlers if not owned(w)
        ]
        for registry in (
            manager.command_handlers,
            manager.message_handlers,
            manager.inline_handlers,
            manager.callback_handlers,
        ):
            for key in [k for k, v in registry.items() if owned(v)]:
                del registry[key]

        if manager.telethon_dp:
            manager.telethon_dp.unregister_raw(module)

    def add_hidden(self, instance):
        for name, func in instance.command_handlers.copy().items():
            if getattr(func, "is_hidden", ""):
                self.manager.hidden.append(name)
