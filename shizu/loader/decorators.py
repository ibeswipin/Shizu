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


from types import FunctionType
from typing import TYPE_CHECKING, Any

from pyrogram import filters

from shizu import database
from shizu.types import InfiniteLoop

if TYPE_CHECKING:
    from .models import Module


def module(
    name: str, author: str | None = None, version: int | float | None = None
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
    values = {
        key: value for key, value in kwargs.items() if not isinstance(value, bool)
    }
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
    interval: int | float | str | None = None,
    autostart: bool | None = False,
    wait_before: bool | None = False,
    time: str | list[str] | None = None,
) -> FunctionType:
    """
    Create new infinite loop from class method. Give exactly one of:
    :param interval: Delay between iterations in seconds, or a config key holding it
    :param time: "HH:MM", a list of them, or a config key holding them (server time)
    :param autostart: Start loop once module is loaded
    :param wait_before: Insert delay before actual iteration, rather than after
    :attr status: Boolean, describing whether the loop is running
    """

    def wrapped(func):
        return InfiniteLoop(func, interval, autostart, wait_before, time)

    return wrapped


def debug_method(*args, **kwargs):
    """Hikka compatibility: marks a debug method. Shizu has no debug runner, the method stays a plain method"""

    def decorator(func):
        func.is_debug_method = True
        func.debug_method_name = kwargs.get("name", func.__name__)
        return func

    if len(args) == 1 and callable(args[0]) and not kwargs:
        return decorator(args[0])
    return decorator


def command(aliases: list = None, hidden: bool = False, **kwargs: Any) -> FunctionType:
    """Command decorator with support for documentation parameters"""

    def decorator(func):
        if hidden:
            func.is_hidden = True

        if aliases:
            list_ = database.db.get("shizu.loader", "aliases", {})

            for alias in aliases:
                list_[alias] = func.__name__

            database.db.set("shizu.loader", "aliases", list_)

        for key, value in kwargs.items():
            if key.endswith("_doc"):
                setattr(func, key, value)

        func.is_command = True
        return func

    return decorator


def _security_flag(flag: str):
    def decorator(func):
        func.security = getattr(func, "security", set()) | {flag}
        return func

    decorator.__name__ = flag
    return decorator


def inline_handler(name: str = None, **kwargs):
    """Register a method as an inline command of the bot (`@bot name args`)"""

    def decorator(func):
        func.is_inline_handler = True
        label = name if isinstance(name, str) else None
        func.is_inline_handler_name = (
            label or func.__name__.removesuffix("_inline_handler")
        ).lower()
        return func

    return decorator(name) if callable(name) else decorator


def callback_handler(name: str = None, **kwargs):
    """Register a method that receives every button press of the bot"""

    def decorator(func):
        func.is_callback_handler = True
        label = name if isinstance(name, str) else None
        func.is_callback_handler_name = (
            label or func.__name__.removesuffix("_callback_handler")
        ).lower()
        return func

    return decorator(name) if callable(name) else decorator


def raw_handler(*updates):
    """Receive raw Telethon updates of the given types (all updates when empty)"""

    def decorator(func):
        func.raw_handler_updates = tuple(updates)
        return func

    return decorator


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


def on_bot(custom_filters):
    """Creates a filter for bot command"""
    return lambda func: setattr(func, "_filters", custom_filters) or func


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
