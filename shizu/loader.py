#    Sh1t-UB (telegram userbot by sh1tn3t)
#    Copyright (C) 2021-2022 Sh1tN3t

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

# -----------------------------------------------------------------------------

# Shizu Copyright (C) 2023-2024  AmoreForever

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
import random
import re
import string
import subprocess
import sys
import typing
from importlib.abc import SourceLoader
from importlib.machinery import ModuleSpec
from importlib.util import module_from_spec, spec_from_file_location
from types import FunctionType
from typing import Any, Dict, List, Union

import requests
from pyrogram import Client, filters, types

from . import bot, database, dispatcher, utils, logger as logger_, extrapatchs
from .types import InfiniteLoop
from .translator import Strings, Translator
from .inter import inter

VALID_URL = r"[-[\]_.~:/?#@!$&'()*+,;%<=>a-zA-Z0-9]+"
VALID_PIP_PACKAGES = re.compile(
    r"^\s*# required:(?: ?)((?:{url} )*(?:{url}))\s*$".format(url=VALID_URL),
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


def get_command_handlers(instance: Module) -> Dict[str, FunctionType]:
    """Returns a dictionary of command names with their corresponding functions"""

    return {
        method_name.replace("_cmd", "").replace("cmd", "").lower(): method
        for method_name, method in inspect.getmembers(instance, inspect.ismethod)
        if hasattr(method, "is_command")
        or method_name.endswith("_cmd")
        or method_name.endswith("cmd")
    }


def get_watcher_handlers(instance: Module) -> List[FunctionType]:
    """Returns a list of watchers"""
    return [
        getattr(instance, method_name)
        for method_name in dir(instance)
        if (
            callable(getattr(instance, method_name))
            and method_name.startswith("watcher")
        )
    ]


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


def get_callback_handlers(instance: Module) -> Dict[str, FunctionType]:
    """Returns a dictionary of names with callback handler functions"""
    return {
        method_name[:-17].lower(): getattr(instance, method_name)
        for method_name in dir(instance)
        if (
            callable(getattr(instance, method_name))
            and len(method_name) > 17
            and method_name.endswith("_callback_handler")
        )
    }


def get_inline_handlers(instance: Module) -> Dict[str, FunctionType]:
    """Returns a dictionary of names with inline handler functions"""
    instance_methods = dir(instance)

    return {
        method_name[:-15].lower(): method
        for method_name in instance_methods
        if (
            callable((method := getattr(instance, method_name)))
            and method_name[-15:] == "_inline_handler"
        )
    }


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


def command(aliases: list = None, hidden: bool = False):
    def decorator(func):
        if hidden:
            func.is_hidden = True

        if aliases:
            list_ = database.db.get(__name__, "aliases", {})

            for alias in aliases:
                list_[alias] = func.__name__

            database.db.set(__name__, "aliases", list_)

        func.is_command = True
        return func

    return decorator


def on_bot(custom_filters):
    """Creates a filter for bot command"""
    return lambda func: setattr(func, "_filters", custom_filters) or func


class ModuleConfig(dict):
    """Like a dict but contains doc for each key"""

    def __init__(self, *entries):
        keys = []
        values = []
        defaults = []
        docstrings = []
        for i, entry in enumerate(entries):
            if i % 3 == 0:
                keys.append(entry)
            elif i % 3 == 1:
                values.append(entry)
                defaults.append(entry)
            else:
                docstrings.append(entry)

        super().__init__(zip(keys, values))
        self._docstrings = dict(zip(keys, docstrings))
        self._defaults = dict(zip(keys, defaults))

    def getdoc(self, key, message=None):
        """Get the documentation by key"""
        ret = self._docstrings[key]
        if callable(ret):
            try:
                ret = ret(message)
            except TypeError:  # Invalid number of params
                logging.debug("%s using legacy doc trnsl", key)
                ret = ret()

        return ret or "No description"

    def getdef(self, key):
        """Get the default value by key"""
        return self._defaults[key]


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
        ]

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

        extrapatchs.MessageMagic(types.Message, app)

        try:
            app.inline_bot = self.bot_manager.bot
            app.bot = self.bot_manager.bot
        except Exception as error:
            logging.exception(f"Error loading bot: {error}")

        for local_module in filter(
            lambda file_name: file_name.endswith(".py")
            and not file_name.startswith("_"),
            os.listdir(self._local_modules_path),
        ):
            module_name = f"shizu.modules.{local_module[:-3]}"
            file_path = os.path.join(
                os.path.abspath("."), self._local_modules_path, local_module
            )
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    source_code = f.read()

                is_telethon = self._is_telethon_module(source_code)

                if is_telethon:
                    transformed_code = inter.transform(source_code)

                    temp_dir = os.path.join(os.path.dirname(file_path), "__temp__")
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_file = os.path.join(temp_dir, local_module)

                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(transformed_code)

                    instance = self.register_instance(module_name, temp_file)

                    if instance and is_telethon:
                        instance.m__telethon = True

                    try:
                        os.remove(temp_file)
                    except:
                        pass
                else:
                    self.register_instance(module_name, file_path)

            except Exception as error:
                logging.exception(f"Error loading local module {module_name}: {error}")

        await self.send_on_loads()

        for custom_module in self._db.get(__name__, "modules", []):
            try:
                r = await utils.run_sync(requests.get, custom_module)
                await self.load_module(r.text, r.url)
            except requests.exceptions.RequestException as error:
                logging.exception(
                    f"Error while downloading custom module {custom_module}: {error}"
                )

        logging.info("Dialogs loaded")
        logging.info("Modules loaded")
        return True

    def register_instance(
        self, module_name: str, file_path: str = "", spec: ModuleSpec = None
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

            for module in self.modules:
                if module.__class__.__name__ == value.__name__:
                    self.unload_module(module, True)
                    
            value.db = self._db
            value.all_modules = self
            value.bot = self.bot_manager
            value._bot = self.bot_manager.bot
            value.inline_bot = self.bot_manager.bot
            value.me = self.me
            value.tg_id = self.me.id
            value.app = self._app
            value._app = self._app
            value.strings = Strings(value, Translator(self._app, self._db), self._db)
            value.userbot = "Shizu"
            value.cmodules = self.cmodules
            value.get_mod = self.get_module
            value.prefix = self._db.get("shizu.loader", "prefixes", ["."])
            value.lookup = self._lookup

            instance = value()

            instance.reconfmod = self.config_reconfigure
            instance.shizu = True
            instance.hidden = self.hidden

            instance.command_handlers = get_command_handlers(instance)
            instance.watcher_handlers = get_watcher_handlers(instance)

            instance.message_handlers = get_message_handlers(instance)
            instance.callback_handlers = get_callback_handlers(instance)
            instance.inline_handlers = get_inline_handlers(instance)

            self.modules.append(instance)
            self.command_handlers.update(instance.command_handlers)
            self.watcher_handlers.extend(instance.watcher_handlers)

            self.message_handlers.update(instance.message_handlers)
            self.callback_handlers.update(instance.callback_handlers)
            self.inline_handlers.update(instance.inline_handlers)

        if not instance:
            logging.warning(f"Module {module_name} not found")

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

        is_telethon = self._is_telethon_module(original_source)

        if is_telethon:
            module_source = inter.transform(original_source)
        else:
            module_source = original_source

        module_name = f"shizu.modules.{self.me.id}-{''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))}"
        pattern = re.compile(r"@loader\.module\((.*?)\)\nclass\s+(\w+)\(")

        if match := pattern.search(module_source):
            module_name = f"shizu.modules.{match[2]}"
        else:
            return logging.error("Module class not found")

        if match := re.search(r"# ?only: ?(.+)", module_source):
            allowed_accounts = match[1].split(",") if match else []
            if str((await self._app.get_me()).id) not in allowed_accounts:
                logging.error(
                    "Module %s is forbidden, because it is not for this account",
                    module_name,
                )
                return "NFA"

        if re.search(r"# ?tl-only", module_source) and not utils.is_tl_enabled():
            logging.error(
                "You have not enabled telethon, so you can't use module %s",
                module_name,
            )
            return "OTL"
        try:
            spec = ModuleSpec(
                module_name, StringLoader(module_source, origin), origin=origin
            )

            instance = self.register_instance(module_name, spec=spec)

            if instance and is_telethon:
                instance.m__telethon = True

        except ImportError as error:
            logging.error(error)

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
                return logging.warn("No packages are specified for installation")

            logging.warning(f"Installing Packages: {', '.join(requirements)}...")

            await self.bot_manager.bot.send_message(
                self._db.get("shizu.chat", "logs", None),
                f"⤵️ <b>Installing Packages:</b> <code>{', '.join(requirements)}</code>...",
            )

            try:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--user",
                        *requirements,
                    ],
                    check=True,
                )
            except subprocess.CalledProcessError as error:
                logging.exception(f"Ошибка при установке пакетов: {error}")

            return await self.load_module(module_source, origin, True)
        except Exception as error:
            item = logger_.CustomException.from_exc_info(*sys.exc_info())
            exc = (
                "🚫 <b>Error while loading modue</b>"
                "\n\n"
                + "\n".join(item.full_stack.splitlines()[:-1])
                + "\n\n"
                + "😵 "
                + item.full_stack.splitlines()[-1]
            )
            await self.bot_manager.bot.send_message(
                self._db.get("shizu.chat", "logs", None), exc, parse_mode="html"
            )
            return logging.error(f"Error loading the module {origin}: {error}")

        if not instance:
            return False

        try:
            await self.send_on_load(instance, Translator(self._app, self._db))
            self.config_reconfigure(instance, self._db)

        except Exception as error:
            return logging.error(error)

        return instance.name

    async def send_on_loads(self) -> bool:
        """Sends commands to execute the function"""
        for module_name in self.modules:
            await self.send_on_load(module_name, Translator(self._app, self._db))
            self.config_reconfigure(module_name, self._db)

    @staticmethod
    def config_reconfigure(module: Module, db):
        """Reconfigures the module"""
        if hasattr(module, "config"):
            modcfg = db.get(module.name, "__config__", {})
            for conf in module.config.keys():
                if conf in modcfg.keys():
                    module.config[conf] = modcfg[conf]
                else:
                    try:
                        module.config[conf] = os.environ[f"{module.name}.{conf}"]
                    except KeyError:
                        module.config[conf] = module.config.getdef(conf)

    async def send_on_load(self, module: Module, translator: Translator) -> bool:
        """Used to perform the function after loading the module"""
        for _, method in iter_attrs(module):
            if hasattr(method, "strings"):
                method.strings = Strings(method, translator, self._db)
                method.translator = translator

        for _, method in iter_attrs(module):
            if isinstance(method, InfiniteLoop):
                setattr(method, "module_instance", module)

                if method.autostart:
                    method.start()

        try:
            await module.on_load(self._app)
        except Exception as error:
            return logging.exception(error)

        return True

    def unload_module(self, module_name: str = None, is_replace: bool = False) -> str:
        """Unloads the loaded (if loaded) module"""
        if module_name in self.cmodules:
            return False
        if is_replace:
            module = module_name
        else:
            if not (module := self.get_module(module_name)):
                return False

            with contextlib.suppress(TypeError):
                path = inspect.getfile(module.__class__)

                logging.info(f"Removing {path}")

                if os.path.exists(path):
                    os.remove(path)

            if (get_module := inspect.getmodule(module)).__spec__.origin != "<string>":
                set_modules = set(self._db.get(__name__, "modules", []))
                self._db.set(
                    "shizu.loader",
                    "modules",
                    list(set_modules - {get_module.__spec__.origin}),
                )

            for alias, command in self.aliases.copy().items():
                if command in module.command_handlers:
                    del self.aliases[alias]
                    del self.command_handlers[command]

        self.modules.remove(module)
        self.command_handlers = dict(
            set(self.command_handlers.items()) ^ set(module.command_handlers.items())
        )
        self.watcher_handlers = list(
            set(self.watcher_handlers) ^ set(module.watcher_handlers)
        )

        self.inline_handlers = dict(
            set(self.inline_handlers.items()) ^ set(module.inline_handlers.items())
        )
        self.callback_handlers = dict(
            set(self.callback_handlers.items()) ^ set(module.callback_handlers.items())
        )

        return module.name

    def get_module(
        self, name: str, by_commands_too: bool = False, advanced=False
    ) -> Union[Module, None]:
        name = name.lower()
        lowercase_names = {module.name.lower() for module in self.modules}

        if name in lowercase_names:
            return next(
                module for module in self.modules if module.name.lower() == name
            )

        if advanced:
            if description := next(
                (module for module in self.modules if name in module.__doc__.lower()),
                None,
            ):
                return description
            elif name_mathing := next(
                (module for module in self.modules if name in module.name.lower()), None
            ):
                return name_mathing

        if by_commands_too:
            if matching_commands := [
                cmd_name
                for cmd_name in self.command_handlers
                if name in cmd_name.lower()
            ]:
                return self.command_handlers[matching_commands[0]].__self__

        return None


current_module = sys.modules[__name__]
setattr(current_module, "tds", tds)
