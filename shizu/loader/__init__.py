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


import asyncio as asyncio
import contextlib as contextlib
import copy as copy
import functools as functools
import importlib as importlib
import inspect as inspect
import logging as logging
import os as os
import random as random
import re as re
import site as site
import string as string
import subprocess as subprocess
import sys as sys
import typing as typing
from importlib.abc import SourceLoader as SourceLoader
from importlib.machinery import ModuleSpec as ModuleSpec
from importlib.util import module_from_spec as module_from_spec
from importlib.util import spec_from_file_location as spec_from_file_location
from types import FunctionType as FunctionType
from typing import Any as Any
from urllib.parse import urlparse as urlparse

import requests as requests
from pyrogram import Client as Client
from pyrogram import filters as filters
from pyrogram import types as types

from shizu import bot as bot
from shizu import database as database
from shizu import dispatcher as dispatcher
from shizu import extrapatchs as extrapatchs
from shizu import health as health
from shizu import utils as utils
from shizu.besafe import BeSafe as BeSafe
from shizu.inter import inter as inter
from shizu.remote import RemoteModuleError as RemoteModuleError
from shizu.remote import RemoteModuleRegistry as RemoteModuleRegistry
from shizu.telegram.exceptions import TelegramConnectionError as TelegramConnectionError
from shizu.translator import Strings as Strings
from shizu.translator import Translator as Translator
from shizu.types import InfiniteLoop as InfiniteLoop
from shizu.types import StopLoop as StopLoop

from . import decorators as _decorators
from . import models as _models
from .compiler import StringLoader as StringLoader
from .config import ConfigValue as ConfigValue
from .config import ModuleConfig as ModuleConfig
from .config import Validators as Validators
from .config import validators as validators
from .decorators import SECURITY_FLAGS as SECURITY_FLAGS
from .decorators import _security_flag as _security_flag
from .decorators import callback_handler as callback_handler
from .decorators import command as command
from .decorators import debug_method as debug_method
from .decorators import inline_handler as inline_handler
from .decorators import loop as loop
from .decorators import module as module
from .decorators import on as on
from .decorators import on_bot as on_bot
from .decorators import ratelimit as ratelimit
from .decorators import raw_handler as raw_handler
from .decorators import tag as tag
from .decorators import tds as tds
from .decorators import watcher as watcher
from .dependencies import MODULE_DEPENDENCIES as MODULE_DEPENDENCIES
from .dependencies import VALID_PIP_PACKAGES as VALID_PIP_PACKAGES
from .dependencies import VALID_URL as VALID_URL
from .dependencies import DependencyInstaller as DependencyInstaller
from .handlers import _decorated as _decorated
from .handlers import get_callback_handlers as get_callback_handlers
from .handlers import get_command_handlers as get_command_handlers
from .handlers import get_inline_handlers as get_inline_handlers
from .handlers import get_message_handlers as get_message_handlers
from .handlers import get_raw_handlers as get_raw_handlers
from .handlers import get_watcher_handlers as get_watcher_handlers
from .lifecycle import _hook_args as _hook_args
from .lifecycle import iter_attrs as iter_attrs
from .manager import ModulesManager as ModulesManager
from .manager import logger_ as logger_
from .models import Library as Library
from .models import LoadError as LoadError
from .models import Module as Module
from .models import SelfUnload as SelfUnload

_db = None
_manager = None

DependencyInstaller.activate(MODULE_DEPENDENCIES)


async def _install_requirements(requirements):
    return await DependencyInstaller.install(requirements, MODULE_DEPENDENCIES)


async def download_and_install(url: str, message: Any = None) -> bool:
    """Download a module from `url`, load it and keep it installed across restarts"""
    if _manager is None:
        return False
    try:
        name = await _manager.load_remote_module(url)
    except requests.exceptions.HTTPError:
        return False
    if not isinstance(name, str) or name in ("NFA", "OTL", "PENDING", "DENIED"):
        return False
    if module := _manager.find_module_strict(name):
        await _manager.call_hook(module, "on_dlmod")
    return True


for _flag in SECURITY_FLAGS:
    globals()[_flag] = _security_flag(_flag)
    globals()[_flag].__module__ = __name__

# Function introspection uses their code locations; classes must retain their
# defining modules so inspect.getsource can find their class statements.
module.__module__ = __name__
tds.__module__ = __name__
watcher.__module__ = __name__
on.__module__ = __name__
loop.__module__ = __name__
debug_method.__module__ = __name__
command.__module__ = __name__
_security_flag.__module__ = __name__
inline_handler.__module__ = __name__
callback_handler.__module__ = __name__
raw_handler.__module__ = __name__
ratelimit.__module__ = __name__
tag.__module__ = __name__
on_bot.__module__ = __name__
get_command_handlers.__module__ = __name__
get_watcher_handlers.__module__ = __name__
get_message_handlers.__module__ = __name__
_decorated.__module__ = __name__
get_callback_handlers.__module__ = __name__
get_inline_handlers.__module__ = __name__
get_raw_handlers.__module__ = __name__
_hook_args.__module__ = __name__
iter_attrs.__module__ = __name__

# Forward annotations need runtime names for get_type_hints used by plugins.
_models.ModulesManager = ModulesManager
_decorators.Module = Module

current_module = sys.modules[__name__]
