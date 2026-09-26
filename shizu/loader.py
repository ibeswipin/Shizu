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
import copy
import functools
import inspect
import asyncio
import logging
import os
import random
import re
import string
import subprocess
import sys
import typing
from urllib.parse import urlparse
from importlib.abc import SourceLoader
from importlib.machinery import ModuleSpec
from importlib.util import module_from_spec, spec_from_file_location
from types import FunctionType
from typing import Any, Dict, List, Union

import requests
from pyrogram import Client, filters, types

from shizu import bot, database, dispatcher, utils, logger as logger_, extrapatchs
from shizu.types import InfiniteLoop, StopLoop
from shizu.translator import Strings, Translator
from shizu.inter import inter

VALID_URL = r"[-[\]_.~:/?#@!$&'()*+,;%<=>a-zA-Z0-9]+"
VALID_PIP_PACKAGES = re.compile(
    r"^\s*# requi(?:red|res):(?: ?)((?:{url} )*(?:{url}))\s*$".format(url=VALID_URL),
    re.MULTILINE,
)


def module(
    name: str, author: Union[str, None] = None, version: Union[int, float, None] = None
) -> FunctionType:
    """Processes the module class

    Parameters:
    name (`str"):
        Module name

    author (`str", optional):
        Author of the module

    version (`int` | `float", optional):
        Module version"""

    def decorator(instance: "Module"):
        """Decorator for processing module class"""
        instance.name = name
        instance.author = author
        instance.version = version
        return instance

    return decorator


def tds(*args, **kwargs):
    """Сompatibility function for Telethon modules"""
    return module(*args, **kwargs)


@module(name="Unknown")
class Module:
    """Module description"""

    name: str
    author: str
    version: Union[int, float]

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
        reply_to = getattr(message, "id", None) if message is not None and not edit else None
        if hasattr(client, "send_message") and hasattr(client, "get_permissions"):
            return await client.send_message(target, text, reply_to=reply_to)
        return await client.send_message(target, text, reply_to_message_id=reply_to)

    async def animate(self, message: Any, frames: list, interval: float, *, inline: bool = False):
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

    async def request_join(self, peer: Any, reason: str, assure_joined: bool = False) -> bool:
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


class StringLoader(SourceLoader):
    """Loads the module from the line"""

    def __init__(self, data: str, origin: str) -> None:
        self.data = data.encode("utf-8")
        self.origin = origin

    def get_code(self, full_name: str) -> Union[Any, None]:
        if source := self.get_source(full_name):
            return compile(source, self.origin, "exec", dont_inherit=True)
        return None

    def get_filename(self, _: str) -> str:
        return self.origin

    def get_data(self, _: str) -> str:
        return self.data


def _hook_args(func, available: tuple) -> tuple:
    """Positional arguments `func` accepts, taken from `available` in order"""
    try:
        params = inspect.signature(func).parameters.values()
    except (ValueError, TypeError):
        return ()
    if any(p.kind is p.VAR_POSITIONAL for p in params):
        return available
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return available[: len(positional)]


def get_command_handlers(instance: Module) -> Dict[str, FunctionType]:
    """Returns a dictionary of command names with their corresponding functions"""

    return {
        re.sub(r"_?cmd$", "", method_name).lower(): method
        for method_name, method in inspect.getmembers(instance, inspect.ismethod)
        if hasattr(method, "is_command") or method_name.endswith("cmd")
    }


def watcher(
    *tags: str,
    only_messages: bool = True,
    no_commands: bool = False,
    no_stickers: bool = False,
    no_docs: bool = False,
    no_audios: bool = False,
    no_videos: bool = False,
    no_photos: bool = False,
    no_forwards: bool = False,
    **kwargs: Any,
) -> FunctionType:
    """Watcher decorator with filtering options

    Parameters:
    only_messages (`bool`): Only process text messages (default: True)
    no_commands (`bool`): Skip messages that are commands (default: False)
    no_stickers (`bool`): Skip sticker messages (default: False)
    no_docs (`bool`): Skip document messages (default: False)
    no_audios (`bool`): Skip audio messages (default: False)
    no_videos (`bool`): Skip video messages (default: False)
    no_photos (`bool`): Skip photo messages (default: False)
    no_forwards (`bool`): Skip forwarded messages (default: False)

    Positional string tags (`"out"`, `"only_pm"`, `"no_media"`, ...) and
    keyword filters (`startswith=`, `contains=`, `regex=`, `from_id=`,
    `chat_id=`, `filter=`) narrow down which messages reach the watcher
    """

    flags = {tag for tag in tags if isinstance(tag, str)}
    flags |= {key for key, value in kwargs.items() if value is True}
    values = {key: value for key, value in kwargs.items() if not isinstance(value, bool)}
    if flags:
        only_messages = "only_messages" in flags
        no_commands = no_commands or "no_commands" in flags

    def decorator(func):
        func.is_watcher = True
        func.watcher_tags = flags
        func.watcher_values = values
        func.watcher_only_messages = only_messages
        func.watcher_no_commands = no_commands
        func.watcher_no_stickers = no_stickers
        func.watcher_no_docs = no_docs
        func.watcher_no_audios = no_audios
        func.watcher_no_videos = no_videos
        func.watcher_no_photos = no_photos
        func.watcher_no_forwards = no_forwards
        return func

    return decorator


def get_watcher_handlers(instance: Module) -> List[FunctionType]:
    """Returns a list of watchers bound to the instance"""
    watchers = []

    for attr_name in dir(instance):
        module_name = getattr(instance, "name", "unknown")
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
            elif hasattr(attr, "__call__") and not inspect.isfunction(attr):
                func_for_check = getattr(attr, "__func__", attr)

            is_watcher_decorated = getattr(func_for_check, "is_watcher", False)

            if is_watcher_by_name or is_watcher_decorated:
                if inspect.ismethod(attr):
                    watchers.append(attr)
                elif inspect.isfunction(attr):
                    import types

                    bound_method = types.MethodType(attr, instance)
                    watchers.append(bound_method)
                elif hasattr(attr, "__call__"):
                    watchers.append(attr)
        except Exception:
            continue

    return watchers


def get_message_handlers(instance: Module) -> Dict[str, FunctionType]:
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


def _decorated(instance: Module, flag: str) -> Dict[str, FunctionType]:
    return {
        getattr(method.__func__, flag + "_name", None) or name.lower(): method
        for name, method in inspect.getmembers(instance, inspect.ismethod)
        if getattr(method.__func__, flag, False)
    }


def get_callback_handlers(instance: Module) -> Dict[str, FunctionType]:
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


def get_inline_handlers(instance: Module) -> Dict[str, FunctionType]:
    """Returns a dictionary of names with inline handler functions"""
    instance_methods = dir(instance)

    return {
        **{
            method_name[:-15].lower(): method
            for method_name in instance_methods
            if (
                callable((method := getattr(instance, method_name)))
                and method_name[-15:] == "_inline_handler"
            )
        },
        **_decorated(instance, "is_inline_handler"),
    }


def get_raw_handlers(instance: Module) -> List[FunctionType]:
    """Methods decorated with `raw_handler`"""
    return [
        method
        for _, method in inspect.getmembers(instance, inspect.ismethod)
        if getattr(method.__func__, "raw_handler_updates", None) is not None
    ]


def on(custom_filters):
    """Creates a filter for the command"""

    def decorator(func):
        """Decorator for handling the command"""
        func._filters = (
            custom_filters
            if custom_filters.__module__ == "pyrogram.filters"
            else filters.create(custom_filters)
        )
        return func

    return decorator


def loop(
    interval: int = 5,
    autostart: typing.Optional[bool] = False,
    wait_before: typing.Optional[bool] = False,
) -> FunctionType:
    """
    Create new infinite loop from class method
    :param interval: Loop iterations delay
    :param autostart: Start loop once module is loaded
    :param wait_before: Insert delay before actual iteration, rather than after
    :attr status: Boolean, describing whether the loop is running
    """

    def wrapped(func):
        return InfiniteLoop(func, interval, autostart, wait_before)

    return wrapped


def iter_attrs(obj: typing.Any, /) -> typing.List[typing.Tuple[str, typing.Any]]:
    """
    Returns list of attributes of object
    :param obj: Object to iterate over
    :return: List of attributes and their values

    taken from: https://github.com/hikariatama/Hikka/blob/master/hikka/loader.py
    """
    return ((attr, getattr(obj, attr)) for attr in dir(obj))


def command(aliases: list = None, hidden: bool = False, **kwargs: Any) -> FunctionType:
    """Command decorator with support for documentation parameters"""

    def decorator(func):
        if hidden:
            func.is_hidden = True

        if aliases:
            list_ = database.db.get(__name__, "aliases", {})

            for alias in aliases:
                list_[alias] = func.__name__

            database.db.set(__name__, "aliases", list_)

        for key, value in kwargs.items():
            if key.endswith("_doc"):
                setattr(func, key, value)

        func.is_command = True
        return func

    return decorator


SECURITY_FLAGS = (
    "owner",
    "sudo",
    "support",
    "unrestricted",
    "inline_everyone",
    "pm",
    "group_owner",
    "group_admin",
    "group_admin_add_admins",
    "group_admin_change_info",
    "group_admin_ban_users",
    "group_admin_delete_messages",
    "group_admin_pin_messages",
    "group_admin_invite_users",
    "group_member",
    "everyone",
)


def _security_flag(flag: str):
    def decorator(func):
        func.security = getattr(func, "security", set()) | {flag}
        return func

    decorator.__name__ = flag
    return decorator


for _flag in SECURITY_FLAGS:
    globals()[_flag] = _security_flag(_flag)


def inline_handler(name: str = None, **kwargs):
    """Register a method as an inline command of the bot (`@bot name args`)"""

    def decorator(func):
        func.is_inline_handler = True
        label = name if isinstance(name, str) else None
        func.is_inline_handler_name = (label or func.__name__.removesuffix("_inline_handler")).lower()
        return func

    return decorator(name) if callable(name) else decorator


def callback_handler(name: str = None, **kwargs):
    """Register a method that receives every button press of the bot"""

    def decorator(func):
        func.is_callback_handler = True
        label = name if isinstance(name, str) else None
        func.is_callback_handler_name = (label or func.__name__.removesuffix("_callback_handler")).lower()
        return func

    return decorator(name) if callable(name) else decorator


def raw_handler(*updates):
    """Receive raw Telethon updates of the given types (all updates when empty)"""

    def decorator(func):
        func.raw_handler_updates = tuple(updates)
        return func

    return decorator


_db = None
_manager = None


async def download_and_install(url: str, message: Any = None) -> bool:
    """Download a module from `url`, load it and keep it installed across restarts"""
    if _manager is None:
        return False
    response = await utils.run_sync(requests.get, url, timeout=30)
    if response.status_code != 200:
        return False
    name = await _manager.load_module(response.text, response.url)
    if not isinstance(name, str) or name in ("NFA", "OTL", "PENDING", "DENIED"):
        return False
    modules = _db.get("shizu.loader", "modules", [])
    if url not in modules:
        _db.set("shizu.loader", "modules", modules + [url])
    if module := _manager.find_module_strict(name):
        await _manager.call_hook(module, "on_dlmod")
    return True


def ratelimit(func):
    """Limit how often users other than the owner may call the command"""
    func.ratelimit = True
    return func


def tag(*tags: str, **kwargs):
    """Only run the command for messages matching the given tags and filters"""

    def decorator(func):
        func.tags = set(tags) | {key for key, value in kwargs.items() if value is True}
        func.tag_values = {
            key: value for key, value in kwargs.items() if not isinstance(value, bool)
        }
        return func

    return decorator


class LoadError(Exception):
    """Raise from `on_load` or `client_ready` to abort loading with a message"""


class SelfUnload(Exception):
    """Raise from `on_load` or `client_ready` to unload the module"""


def on_bot(custom_filters):
    """Creates a filter for bot command"""
    return lambda func: setattr(func, "_filters", custom_filters) or func


class ConfigValue:
    """Config value descriptor for ModuleConfig compatibility"""

    def __init__(self, key, default, doc=None, validator=None):
        self.key = key
        self.default = default
        self.doc = doc
        self.validator = validator

    def validate(self, value):
        """Validate value using validator if present"""
        if self.validator:
            return self.validator.validate(value)
        return value


class Validators:
    """Validators for ConfigValue"""

    class Integer:
        def __init__(self, minimum=None, maximum=None):
            self.minimum = minimum
            self.maximum = maximum

        def validate(self, value):
            try:
                value = int(value)
                if self.minimum is not None and value < self.minimum:
                    raise ValueError(f"Value must be >= {self.minimum}")
                if self.maximum is not None and value > self.maximum:
                    raise ValueError(f"Value must be <= {self.maximum}")
                return value
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid integer value: {e}")

    class ValidationError(ValueError):
        """Raised by validators when a config value is rejected"""

    class RegExp:
        def __init__(self, pattern, description=None, flags=0):
            self.pattern = re.compile(pattern, flags)
            self.description = description

        def validate(self, value):
            if not self.pattern.match(str(value)):
                raise ValueError(
                    self.description or f"Value does not match pattern: {self.pattern.pattern}"
                )
            return value

    class Series:
        def __init__(self, *args, validator=None, min_len=None, max_len=None, fixed_len=None):
            if validator is not None:
                self.validators = (validator,)
            else:
                self.validators = args
            self.min_len = min_len
            self.max_len = max_len
            self.fixed_len = fixed_len

        def _check_length(self, value: list) -> list:
            if self.fixed_len is not None and len(value) != self.fixed_len:
                raise ValueError(f"List must contain exactly {self.fixed_len} items")
            if self.min_len is not None and len(value) < self.min_len:
                raise ValueError(f"List must contain at least {self.min_len} items")
            if self.max_len is not None and len(value) > self.max_len:
                raise ValueError(f"List must contain at most {self.max_len} items")
            return value

        def validate(self, value):
            if not isinstance(value, (list, tuple)):
                if isinstance(value, str):
                    try:
                        import json

                        value = json.loads(value)

                        if not isinstance(value, list):
                            value = [value]
                    except (json.JSONDecodeError, ValueError):
                        value = [v.strip() for v in value.split(",") if v.strip()]
                else:
                    value = [str(value)] if value is not None else []

            if isinstance(value, tuple):
                value = list(value)

            if not self.validators:
                return self._check_length([str(v) for v in value])

            validated_list = []
            for v in value:
                for validator in self.validators:
                    v = validator.validate(v)
                validated_list.append(v)

            return self._check_length(validated_list)

    class Boolean:
        def validate(self, value):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)

    class NoneType:
        def validate(self, value):
            if value is None:
                return None
            raise ValueError("Value must be None")

    class String:
        def __init__(self, length=None, min_len=None, max_len=None):
            self.length = length
            self.min_len = min_len
            self.max_len = max_len

        def validate(self, value):
            value = str(value)
            if self.length is not None and len(value) != self.length:
                raise ValueError(f"Text must be exactly {self.length} characters long")
            if self.min_len is not None and len(value) < self.min_len:
                raise ValueError(f"Text must be at least {self.min_len} characters long")
            if self.max_len is not None and len(value) > self.max_len:
                raise ValueError(f"Text must be at most {self.max_len} characters long")
            return value

    class TelegramID:
        def validate(self, value):
            try:
                value = int(str(value).strip())
            except (TypeError, ValueError):
                raise ValueError("Value must be a Telegram ID (a number)")
            if not -(10**15) < value < 10**15 or value == 0:
                raise ValueError("Value is not a valid Telegram ID")
            return value

    class EntityLike:
        def validate(self, value):
            value = str(value).strip()
            if re.fullmatch(r"-?\d+", value):
                return int(value)
            if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,31}", value) or value.startswith(("https://t.me/", "t.me/")):
                return value
            raise ValueError("Value must be an ID, @username or t.me link")

    class Emoji:
        def __init__(self, length=None, min_len=None, max_len=None):
            self.length, self.min_len, self.max_len = length, min_len, max_len

        def validate(self, value):
            value = str(value)
            if any(ch.isalnum() for ch in value):
                raise ValueError("Value must contain only emoji")
            count = len([ch for ch in value if not ch.isspace() and ord(ch) not in (0x200D, 0xFE0F)])
            if self.length is not None and count != self.length:
                raise ValueError(f"Value must contain exactly {self.length} emoji")
            if self.min_len is not None and count < self.min_len:
                raise ValueError(f"Value must contain at least {self.min_len} emoji")
            if self.max_len is not None and count > self.max_len:
                raise ValueError(f"Value must contain at most {self.max_len} emoji")
            return value

    class Link:
        def validate(self, value):
            value = str(value).strip()
            if not value:
                raise ValueError("Link cannot be empty")

            original_value = value
            if not value.startswith(("http://", "https://")):
                value = "https://" + value

            parsed = urlparse(value)

            if parsed.scheme not in ("http", "https"):
                raise ValueError(
                    f"Invalid link scheme. Only http:// and https:// are allowed: {original_value}"
                )

            if not parsed.netloc:
                raise ValueError(
                    f"Invalid link format. Missing domain: {original_value}"
                )

            netloc = parsed.netloc.split(":")[0]
            is_valid_domain = (
                "." in netloc
                or netloc.lower() == "localhost"
                or re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", netloc)
            )

            if not is_valid_domain:
                raise ValueError(
                    f"Invalid link format. Invalid domain: {original_value}"
                )

            return value

    class Float:
        def __init__(self, minimum=None, maximum=None):
            self.minimum = minimum
            self.maximum = maximum

        def validate(self, value):
            try:
                value = float(value)
                if self.minimum is not None and value < self.minimum:
                    raise ValueError(f"Value must be >= {self.minimum}")
                if self.maximum is not None and value > self.maximum:
                    raise ValueError(f"Value must be <= {self.maximum}")
                return value
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid float value: {e}")

    class Hidden:
        def __init__(self, validator=None):
            self.validator = validator

        def validate(self, value):
            return self.validator.validate(value) if self.validator else value

    class Choice:
        def __init__(self, possible_values):
            self.possible_values = list(possible_values)

        def validate(self, value):
            for possible in self.possible_values:
                if value == possible or str(value) == str(possible):
                    return possible
            raise ValueError(
                f"Value must be one of: {', '.join(map(str, self.possible_values))}"
            )

    class MultiChoice:
        def __init__(self, possible_values):
            self.possible_values = list(possible_values)

        def validate(self, value):
            if isinstance(value, str):
                value = [v.strip() for v in value.split(",") if v.strip()]
            result = []
            for item in value or []:
                match = next((p for p in self.possible_values if item == p or str(item) == str(p)), None)
                if match is None:
                    raise ValueError(f"{item} is not one of: {', '.join(map(str, self.possible_values))}")
                if match not in result:
                    result.append(match)
            return result

    class Union:
        def __init__(self, *validators, validator=None):
            if validator is not None:
                self.validators = (validator,)
            else:
                self.validators = validators

        def validate(self, value):
            if not self.validators:
                return value

            errors = []
            for validator in self.validators:
                try:
                    return validator.validate(value)
                except ValueError as e:
                    errors.append(str(e))
                    continue

            raise ValueError(
                f"Value does not match any of the validators: {', '.join(errors)}"
            )


validators = Validators()


class ModuleConfig(dict):
    """Like a dict but contains doc for each key"""

    def __init__(self, *entries):
        keys = []
        values = []
        defaults = []
        docstrings = []
        self._config_values = {}

        if entries and isinstance(entries[0], ConfigValue):
            for entry in entries:
                if isinstance(entry, ConfigValue):
                    keys.append(entry.key)
                    defaults.append(entry.default)
                    values.append(entry.default)
                    docstrings.append(entry.doc)
                    self._config_values[entry.key] = entry
        else:
            for i, entry in enumerate(entries):
                if i % 3 == 0:
                    keys.append(entry)
                elif i % 3 == 1:
                    values.append(entry)
                    defaults.append(entry)
                else:
                    docstrings.append(entry)

        super().__init__(zip(keys, values) if keys else {})
        self._docstrings = dict(zip(keys, docstrings)) if keys else {}
        self._defaults = (
            {key: copy.deepcopy(value) for key, value in zip(keys, defaults)}
            if keys
            else {}
        )

    def getdoc(self, key, message=None):
        """Get the documentation by key"""
        ret = self._docstrings.get(key)
        if ret is None:
            return "No description"
        if callable(ret):
            try:
                ret = ret(message)
            except TypeError:
                ret = ret()

        return ret or "No description"

    def getdef(self, key):
        """Get the default value by key"""
        return copy.deepcopy(self._defaults.get(key))


class ModulesManager:
    """Module Manager"""

    def __init__(self, app: Client, db: database.Database, me: types.User) -> None:
        self.modules: List[Module] = []
        self.watcher_handlers: List[FunctionType] = []

        self.command_handlers: Dict[str, FunctionType] = {}
        self.message_handlers: Dict[str, FunctionType] = {}
        self.inline_handlers: Dict[str, FunctionType] = {}
        self.callback_handlers: Dict[str, FunctionType] = {}

        self._local_modules_path: str = "./shizu/modules"

        self._app = app
        self._client = app

        self._db = db
        self.me = me

        self.aliases = self._db.get(__name__, "aliases", {})

        self.dp: dispatcher.DispatcherManager = None
        self.bot_manager: bot.BotManager = None
        self.telethon_dp = None
        self.load_guard = None
        global _db, _manager
        _db, _manager = db, self
        self.last_commands: Dict[int, tuple] = {}
        self._libraries: Dict[str, "Library"] = {}
        self._join_requests: Dict[str, tuple] = {}

        self.root_module: Module = None
        self.cmodules = [
            "ShizuBackuper",
            "ShizuHelp",
            "ShizuLoader",
            "ShizuTerminal",
            "ShizuTester",
            "ShizuUpdater",
            "ShizuEval",
            "ShizuModulesHelper",
            "ShizuStart",
            "ShizuInfo",
            "ShizuConfig",
            "ShizuLanguages",
            "ShizuSettings",
            "ShizuOwner",
            "ShizuOnload",
            "ShizuUpdateNotifier",
            "ShizuPermissions",
            "ShizuSystemd",
            "ShizuBeSafe",
        ]
        self.hidden = []
        app.db = db

    def _is_telethon_module(self, source_code: str) -> bool:
        """Checks if the module is a Telethon module"""
        telethon_patterns = [
            r"@loader\.tds\b",
            r"async def \w+\(self,\s*message\)",
            r"from \.\.inline\b",
            r'"telethon"',
            r"'telethon'",
            r"from telethon\.tl\.patched",
            r"from telethon\.tl\.types import Message",
            r"from telethon\.tl\.types import.*Message",
            r"(?m)^def register\(cb\)",
            r"(?m)^\s*(?:from|import)\s+(?:telethon|hikkatl)\b",
            r"strings\s*=\s*\{\s*[\"']name[\"']",
        ]

        if re.search(r"^\s*(?:from|import)\s+pyrogram\b", source_code, re.MULTILINE):
            return False

        return any(
            re.search(pattern, source_code, re.IGNORECASE)
            for pattern in telethon_patterns
        )

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

        if utils.is_tl_enabled() and hasattr(app, "tl") and app.tl != "Not enabled":
            from shizu.telethon_dispatcher import TelethonDispatcherManager

            await app.tl.connect() if not app.tl.is_connected() else None
            self.telethon_dp = TelethonDispatcherManager(app.tl, self)
            await self.telethon_dp.load()

        try:
            app.inline_bot = self.bot_manager.bot
            app.bot = self.bot_manager.bot
        except Exception:
            pass

        modules_list = sorted(
            filter(
                lambda file_name: file_name.endswith(".py")
                and not file_name.startswith("_"),
                os.listdir(self._local_modules_path),
            )
        )

        deferred = []
        for local_module in modules_list:
            module_name = f"shizu.modules.{local_module[:-3]}"
            file_path = os.path.join(
                os.path.abspath("."), self._local_modules_path, local_module
            )
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    source_code = f.read()
            except Exception:
                logging.exception("Failed to read local module %s", local_module)
                continue

            if local_module[:-3] not in self.cmodules:
                deferred.append((module_name, file_path, source_code))
                continue

            self._register_local(module_name, file_path, source_code)

        await self.send_on_loads()

        for module_name, file_path, source_code in deferred:
            if self.load_guard:
                try:
                    if await self.load_guard(source_code, file_path) is not True:
                        continue
                except Exception:
                    logging.exception("load_guard failed for %s", file_path)
                    continue
            self._register_local(module_name, file_path, source_code)

        await self.send_on_loads()

        for custom_module in self._db.get(__name__, "modules", []):
            try:
                r = await utils.run_sync(requests.get, custom_module)
                await self.load_module(r.text, r.url)
            except requests.exceptions.RequestException:
                pass

        return True

    def _register_local(self, module_name: str, file_path: str, source_code: str):
        try:
            if self._is_telethon_module(source_code):
                if not utils.is_tl_enabled():
                    return
                spec = ModuleSpec(
                    module_name,
                    StringLoader(inter.transform(source_code), file_path),
                    origin=file_path,
                )
                spec.has_location = True
                self.register_instance(module_name, spec=spec, is_telethon=True)
            else:
                self.register_instance(module_name, file_path)
        except Exception:
            logging.exception("Failed to load local module %s", file_path)

    def register_instance(
        self,
        module_name: str,
        file_path: str = "",
        spec: ModuleSpec = None,
        is_telethon: bool = False,
    ) -> Module:
        """Registers the module"""
        spec = spec or spec_from_file_location(module_name, file_path)

        module = module_from_spec(spec)

        sys.modules[module.__name__] = module

        spec.loader.exec_module(module)

        instance = None

        for key, value in vars(module).items():
            if not inspect.isclass(value) or not issubclass(value, Module):
                continue

            clashing = [
                m
                for m in self.modules
                if m.__class__.__name__ == value.__name__
                or getattr(m, "name", None) == getattr(value, "name", None)
            ]
            if any(self.is_core(m) for m in clashing):
                raise ValueError(f"{value.__name__} clashes with a core module")
            for module in clashing:
                self.unload_module(module, True)

            value.db = self._db
            value.all_modules = self
            value.bot = self.bot_manager
            value._bot = self.bot_manager.bot
            value.inline_bot = self.bot_manager.bot
            value.inline = self.bot_manager
            value.me = self.me
            value.tg_id = self.me.id
            value._tg_id = self.me.id
            value.app = self._app
            value._app = self._app
            value.strings = Strings(value, Translator(self._app, self._db), self._db)
            value.userbot = "Shizu"
            value.cmodules = self.cmodules
            value.get_mod = self.get_module
            value.prefix = self._db.get("shizu.loader", "prefixes", ["."])
            value.lookup = self._lookup

            if (
                utils.is_tl_enabled()
                and hasattr(self._app, "tl")
                and self._app.tl != "Not enabled"
            ):
                value.client = self._app.tl
                value._client = self._app.tl
                value.tl = self._app.tl

            instance = value()

            if is_telethon:
                instance.m__telethon = True

            instance.reconfmod = self.config_reconfigure
            instance.shizu = True
            instance.hidden = self.hidden
            instance.inline = self.bot_manager

            if (
                utils.is_tl_enabled()
                and hasattr(self._app, "tl")
                and self._app.tl != "Not enabled"
            ):
                instance.client = self._app.tl
                instance._client = self._app.tl
                instance.tl = self._app.tl

            instance.raw_handlers = get_raw_handlers(instance)
            instance.command_handlers = get_command_handlers(instance)
            instance.watcher_handlers = get_watcher_handlers(instance)
            instance.message_handlers = get_message_handlers(instance)
            instance.callback_handlers = get_callback_handlers(instance)
            instance.inline_handlers = get_inline_handlers(instance)

            explicitly_pyrogram = (
                hasattr(instance, "m__telethon") and instance.m__telethon is False
            )

            if instance.name in self.cmodules:
                instance.m__telethon = False
            elif explicitly_pyrogram:
                instance.m__telethon = False
            elif (
                not hasattr(instance, "m__telethon")
                or instance.m__telethon is not False
            ):
                is_telethon_detected = False
                for handler in instance.command_handlers.values():
                    try:
                        if hasattr(handler, "__func__"):
                            sig = inspect.signature(handler.__func__)
                            params = list(sig.parameters.keys())[1:]
                        else:
                            sig = inspect.signature(handler)
                            params = list(sig.parameters.keys())
                        if "message" in params and "app" not in params:
                            is_telethon_detected = True
                            break
                    except (ValueError, TypeError, AttributeError):
                        continue

                if not is_telethon_detected:
                    for watcher in instance.watcher_handlers:
                        try:
                            if hasattr(watcher, "__func__"):
                                sig = inspect.signature(watcher.__func__)
                                params = list(sig.parameters.keys())[1:]
                                param_annotations = {
                                    name: sig.parameters[name].annotation
                                    for name in params
                                    if sig.parameters[name].annotation
                                    != inspect.Parameter.empty
                                }
                            else:
                                sig = inspect.signature(watcher)
                                params = list(sig.parameters.keys())
                                param_annotations = {
                                    name: sig.parameters[name].annotation
                                    for name in params
                                    if sig.parameters[name].annotation
                                    != inspect.Parameter.empty
                                }

                            if (
                                len(params) >= 1
                                and "message" in params
                                and "app" not in params
                            ):
                                if "message" in param_annotations:
                                    annotation = param_annotations["message"]
                                    annotation_str = str(annotation)
                                    if (
                                        "patched" in annotation_str
                                        or "telethon.tl" in annotation_str
                                    ):
                                        is_telethon_detected = True
                                        break
                                else:
                                    is_telethon_detected = True
                                    break
                        except (ValueError, TypeError, AttributeError):
                            continue

                if is_telethon_detected:
                    instance.m__telethon = True

            self.modules.append(instance)
            if self.telethon_dp and getattr(instance, "m__telethon", False):
                self.telethon_dp.register_raw(instance)

            is_telethon_module = getattr(instance, "m__telethon", False)
            if not is_telethon_module:
                self.command_handlers.update(instance.command_handlers)
                if instance.watcher_handlers:
                    self.watcher_handlers.extend(instance.watcher_handlers)
                self.message_handlers.update(instance.message_handlers)
                self.callback_handlers.update(instance.callback_handlers)
                self.inline_handlers.update(instance.inline_handlers)
            else:
                self.command_handlers.update(instance.command_handlers)

        if not instance:
            pass

        for name, func in instance.command_handlers.copy().items():
            if getattr(func, "is_hidden", ""):
                self.hidden.append(name)

        return instance

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

        original_source = module_source

        if self.load_guard:
            verdict = await self.load_guard(module_source, origin)
            if verdict is not True:
                return verdict

        is_telethon = self._is_telethon_module(original_source)

        if is_telethon:
            if not utils.is_tl_enabled():
                return "OTL"
            module_source = inter.transform(original_source)
        else:
            module_source = original_source

        module_name = f"shizu.modules.{self.me.id}-{''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))}"
        pattern = re.compile(r"@loader\.module\((.*?)\)\nclass\s+(\w+)\(")

        if match := pattern.search(module_source):
            module_name = f"shizu.modules.{match[2]}"
        else:
            return False

        if match := re.search(r"# ?only: ?(.+)", module_source):
            allowed_accounts = match[1].split(",") if match else []
            if str((await self._app.get_me()).id) not in allowed_accounts:
                return "NFA"

        if re.search(r"# ?tl-only", module_source) and not utils.is_tl_enabled():
            return "OTL"
        try:
            spec = ModuleSpec(
                module_name, StringLoader(module_source, origin), origin=origin
            )
            spec.has_location = bool(origin) and os.path.isfile(origin)

            instance = self.register_instance(
                module_name, spec=spec, is_telethon=is_telethon
            )

        except ImportError:
            pass

            if did_requirements:
                return True
            try:
                requirements = [
                    x
                    for x in map(
                        str.strip,
                        VALID_PIP_PACKAGES.search(module_source)[1].split(" "),
                    )
                    if x and x[0] not in ("-", "_", ".")
                ]
            except TypeError:
                return False

            pass

            await self.bot_manager.bot.send_message(
                self._db.get("shizu.chat", "logs", None),
                f"⤵️ <b>Installing packages:</b> <code>{', '.join(requirements)}</code>...",
            )

            try:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        *(["--user"] if sys.prefix == sys.base_prefix else []),
                        *requirements,
                    ],
                    check=True,
                )
            except subprocess.CalledProcessError:
                pass

            return await self.load_module(original_source, origin, True)
        except Exception as error:
            item = logger_.CustomException.from_exc_info(*sys.exc_info())
            exc = (
                "🚫 <b>Error while loading module</b>"
                "\n\n"
                + "\n".join(item.full_stack.splitlines()[:-1])
                + "\n\n"
                + "😵 "
                + item.full_stack.splitlines()[-1]
            )
            await self.bot_manager.bot.send_message(
                self._db.get("shizu.chat", "logs", None), exc, parse_mode="html"
            )
            return False

        if not instance:
            return False

        try:
            self.config_reconfigure(instance, self._db)
            if not await self.send_on_load(instance, Translator(self._app, self._db)):
                return False
        except Exception:
            logging.exception("Failed to start module %s", instance.name)
            return False

        return instance.name

    async def send_on_loads(self) -> bool:
        """Sends commands to execute the function"""
        for module in list(self.modules):
            self.config_reconfigure(module, self._db)
            await self.send_on_load(module, Translator(self._app, self._db))

    @staticmethod
    def config_reconfigure(module: Module, db):
        """Reconfigures the module"""
        if hasattr(module, "config"):
            modcfg = db.get(module.name, "__config__", {})
            for conf in module.config.keys():
                if conf in modcfg.keys():
                    value = modcfg[conf]
                    if (
                        hasattr(module.config, "_config_values")
                        and conf in module.config._config_values
                    ):
                        config_value = module.config._config_values[conf]
                        if config_value.validator:
                            try:
                                value = config_value.validator.validate(value)
                                modcfg[conf] = value
                                db.set(module.name, "__config__", modcfg)
                            except (ValueError, TypeError):
                                value = module.config.getdef(conf)
                    module.config[conf] = value
                else:
                    try:
                        value = os.environ[f"{module.name}.{conf}"]
                        if (
                            hasattr(module.config, "_config_values")
                            and conf in module.config._config_values
                        ):
                            config_value = module.config._config_values[conf]
                            if config_value.validator:
                                try:
                                    value = config_value.validator.validate(value)

                                    modcfg[conf] = value
                                    db.set(module.name, "__config__", modcfg)
                                except (ValueError, TypeError):
                                    value = module.config.getdef(conf)
                        module.config[conf] = value
                    except KeyError:
                        module.config[conf] = module.config.getdef(conf)

    async def send_on_load(self, module: Module, translator: Translator) -> bool:
        """Used to perform the function after loading the module"""
        if hasattr(module, "_client_ready_called") and module._client_ready_called:
            return True

        for _, method in iter_attrs(module):
            if hasattr(method, "strings"):
                method.strings = Strings(method, translator, self._db)
                method.translator = translator

        for _, method in iter_attrs(module):
            if isinstance(method, InfiniteLoop):
                setattr(method, "module_instance", module)

                if method.autostart:
                    method.start()

        module._client_ready_called = True

        client = self._app
        if getattr(module, "m__telethon", False) and utils.is_tl_enabled():
            client = getattr(self._app, "tl", None)
            if client in (None, "Not enabled"):
                return True
            if getattr(module, "client", None) is None:
                module._client = module.client = module.tl = client

        for hook, args in (
            (module.on_load, (self._app,)),
            (module.client_ready, (client, self._db)),
        ):
            try:
                await hook(*_hook_args(hook, args))
            except (LoadError, SelfUnload) as error:
                reason = str(error) or type(error).__name__
                logging.error("Module %s was unloaded: %s", module.name, reason)
                module._load_error = reason
                with contextlib.suppress(Exception):
                    self.unload_module(module, True)
                return False
            except Exception:
                logging.exception("%s failed in module %s", hook.__name__, module.name)

        return True

    @property
    def commands(self) -> Dict[str, FunctionType]:
        return self.command_handlers

    @property
    def security(self):
        return dispatcher.security_manager()

    def dispatch(self, command: str) -> tuple:
        """Resolve an alias and return `(command, handler)`; handler is None when unknown"""
        command = command.lower()
        command = self.aliases.get(command, command).lower()
        return command, self.command_handlers.get(command)

    def last_command(self, message) -> Union[tuple, None]:
        chat_id = getattr(message, "chat_id", None) or getattr(getattr(message, "chat", None), "id", None)
        return self.last_commands.get(chat_id)

    def log(self, type_: str, *, group: Any = None, affected_uids: Any = None, data: Any = None):
        """Record an action performed by a module in the Shizu log"""
        details = ", ".join(
            f"{key}={value}"
            for key, value in (("group", group), ("users", affected_uids), ("data", data))
            if value is not None
        )
        logging.getLogger("shizu.actions").info("%s%s", type_, f" ({details})" if details else "")

    async def check_security(self, message, func) -> bool:
        """Whether the sender of `message` may run `func` (a handler or a permission bitmask)"""
        command = None
        if not isinstance(func, int):
            command = next((name for name, handler in self.command_handlers.items() if handler == func), None)
        return await self.security.check(message, func, command, getattr(self._app, "tl", None))

    def _module_client(self):
        tl = getattr(self._app, "tl", None)
        return tl if utils.is_tl_enabled() and tl not in (None, "Not enabled") else self._app

    async def import_library(self, url: str, *, suspend_on_error: bool = False) -> "Library":
        """Load a shared library from `url` once; later calls return the same instance"""
        if url in self._libraries:
            return self._libraries[url]
        try:
            response = await utils.run_sync(requests.get, url, timeout=30)
            response.raise_for_status()
            source = response.text
        except Exception as error:
            raise LoadError(f"Could not download library {url}: {error}") from error

        if self.load_guard:
            verdict = await self.load_guard(source, url)
            if verdict is not True:
                raise LoadError(f"Library {url} is not approved yet ({verdict})")

        library = await self._exec_library(url, inter.transform(source), source)
        self._libraries[url] = library
        return library

    async def _exec_library(self, url: str, code: str, source: str, retried: bool = False) -> "Library":
        name = "shizu.modules.__lib_" + re.sub(r"\W", "_", urlparse(url).path.rsplit("/", 1)[-1][:-3] or "lib")
        spec = ModuleSpec(name, StringLoader(code, url), origin=url)
        module = module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except ImportError as error:
            match = VALID_PIP_PACKAGES.search(source)
            if retried or not match:
                raise LoadError(f"Library {url} failed to import: {error}") from error
            await utils.run_sync(
                subprocess.run,
                [sys.executable, "-m", "pip", "install",
                 *(["--user"] if sys.prefix == sys.base_prefix else []),
                 *match[1].split()],
                check=False,
            )
            return await self._exec_library(url, code, source, True)

        classes = [
            value
            for value in vars(module).values()
            if inspect.isclass(value) and issubclass(value, Library) and value is not Library
        ]
        if not classes:
            raise LoadError(f"{url} does not define a library class")
        library = classes[0]()
        library.name = library.name or classes[0].__name__
        client = self._module_client()
        library.client = library._client = client
        library.db = self._db
        library.all_modules = library.allmodules = self
        library.inline = self.bot_manager
        library.tg_id = library._tg_id = self.me.id
        library.lookup = self._lookup
        library.source_url = url
        if hasattr(library, "config"):
            self.config_reconfigure(library, self._db)
        await library.init()
        return library

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
            [[
                {"text": "✅ Join", "callback": functools.partial(decide, True)},
                {"text": "❌ Decline", "callback": functools.partial(decide, False)},
            ]]
        )
        await self.bot_manager.bot.send_message(
            self.me.id,
            f"📨 <b>{utils.escape_html(getattr(module, 'name', 'Module'))}</b> asks to join "
            f"<code>{utils.escape_html(str(peer))}</code>\n\n<i>{utils.escape_html(reason)}</i>",
            reply_markup=markup,
        )
        return False

    async def call_hook(self, module: Module, hook: str):
        func = getattr(module, hook, None)
        if not callable(func):
            return
        try:
            client = getattr(module, "client", None) or self._app
            await func(*_hook_args(func, (client, self._db)))
        except Exception:
            logging.exception("%s failed in module %s", hook, getattr(module, "name", module))

    def find_module_strict(self, name: str) -> Union[Module, None]:
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
        if is_replace:
            module = module_name
        else:
            module = self.find_module_strict(module_name)
            if not module or self.is_core(module):
                return False

            with contextlib.suppress(TypeError, OSError):
                path = inspect.getfile(module.__class__)
                if os.path.isfile(path):
                    os.remove(path)

            spec = getattr(inspect.getmodule(module), "__spec__", None)
            if spec and spec.origin != "<string>":
                self._db.set(
                    __name__,
                    "modules",
                    [
                        m
                        for m in self._db.get(__name__, "modules", [])
                        if m != spec.origin
                    ],
                )

        def owned(handler) -> bool:
            return getattr(handler, "__self__", None) is module

        if module in self.modules:
            self.modules.remove(module)
        self.watcher_handlers[:] = [w for w in self.watcher_handlers if not owned(w)]
        for registry in (
            self.command_handlers,
            self.message_handlers,
            self.inline_handlers,
            self.callback_handlers,
        ):
            for key in [k for k, v in registry.items() if owned(v)]:
                del registry[key]

        if self.telethon_dp:
            self.telethon_dp.unregister_raw(module)

        if callable(getattr(module, "on_unload", None)):
            asyncio.ensure_future(self.call_hook(module, "on_unload"))

        for attr in vars(type(module)).values():
            if isinstance(attr, InfiniteLoop) and attr.module_instance is module:
                asyncio.ensure_future(attr.stop())

        module_module = inspect.getmodule(module)
        if module_module and module_module.__name__ in sys.modules:
            del sys.modules[module_module.__name__]

        return module.name

    def get_module(
        self, name: str, by_commands_too: bool = False, _=None
    ) -> Union[Module, None]:
        name = name.lower()

        for module in self.modules:
            if module.name.lower() == name:
                return module

        for module in self.modules:
            if module.__doc__ and name in module.__doc__.lower():
                return module

        for module in self.modules:
            if name in module.name.lower():
                return module

        if by_commands_too:
            for cmd_name, handler in self.command_handlers.items():
                if name in cmd_name.lower():
                    return handler.__self__

        return None


current_module = sys.modules[__name__]
setattr(current_module, "tds", tds)
setattr(current_module, "ConfigValue", ConfigValue)
setattr(current_module, "validators", validators)
setattr(current_module, "watcher", watcher)
