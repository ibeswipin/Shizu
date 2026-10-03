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

import io
import os
import requests
import inspect

from aiogram.types import CallbackQuery
from pyrogram import Client, types

from shizu import loader, utils


@loader.module("ShizuModulesHelper", "hikamoru")
class ModulesLinkMod(loader.Module):
    """Link or file of the installed module"""

    strings = {}

    CORE_DIR = os.path.realpath("shizu")

    def _source(self, module) -> bytes:
        mod = inspect.getmodule(module)
        name = getattr(mod, "__name__", "")
        if source := self.all_modules.raw_modules.get(name):
            return source.encode("utf-8")
        origin = self._origin(module)
        if os.path.isfile(origin):
            with open(origin, "rb") as file:
                return file.read()
        loader_ = getattr(getattr(mod, "__spec__", None), "loader", None)
        if data := getattr(loader_, "data", None):
            return data if isinstance(data, bytes) else data.encode("utf-8")
        return inspect.getsource(mod).encode("utf-8")

    @staticmethod
    def _origin(module) -> str:
        spec = getattr(inspect.getmodule(module), "__spec__", None)
        return getattr(spec, "origin", None) or "<string>"

    @classmethod
    def _core_file(cls, name: str):
        path = os.path.realpath(os.path.join(cls.CORE_DIR, name.removesuffix(".py") + ".py"))
        if not path.startswith(cls.CORE_DIR + os.sep) or not os.path.isfile(path):
            return None
        return path

    @loader.command()
    async def ml(self, app: Client, message: types.Message):
        """Get a module's link or file. Usage: ml <module name or command> | -c <core file, e.g. loader or web/core> to get a core file"""

        args = message.get_args_raw().strip()

        if not args:
            return await message.answer(
                self.strings("what_"),
            )

        if args == "-c" or args.startswith("-c "):
            name = args[2:].strip()
            if not name or not (path := self._core_file(name)):
                return await message.answer(
                    self.strings("nope_"),
                )

            with open(path, "rb") as file:
                source_code = io.BytesIO(file.read())
            source_code.name = os.path.basename(path)

            return await message.answer(
                source_code, doc=True, caption=self.strings("core_file").format(utils.escape_html(name))
            )

        if not (module := self.all_modules.get_module(args, True, True)):
            return await message.answer(
                self.strings("nope_"),
            )

        try:
            source = self._source(module)
        except Exception:
            return await message.answer("❌ Source unavailable for this module!")

        source_code = io.BytesIO(source)
        source_code.name = f"{module.name}.py"

        origin = self._origin(module)
        caption = (
            f'<emoji id=5260730055880876557>⛓</emoji> <a href="{utils.escape_html(origin)}">Link</a> of <code>{module.name}</code> module:\n\n'
            f"<b>{utils.escape_html(origin)}</b>"
            if origin.startswith(("http://", "https://"))
            else f"<emoji id=5870528606328852614>📁</emoji> <b>File of <code>{module.name}</code></b>"
        )

        return await message.answer(source_code, doc=True, caption=caption)

    @loader.command()
    async def aeliscmd(self, app, message):
        """Search for a module in the Aelis API"""
        args = message.get_args_raw()
        if not args:
            return await message.answer(self.strings("what_"))
        await message.answer(self.strings("search_"))
        module = requests.get(f"https://aelis.pythonanywhere.com/get/{args}").json()
        if not module:
            return await message.answer(self.strings("nope_"))
        text = self.strings("module_").format(
            f"https://aelis.pythonanywhere.com/view/{module['name']}",
            module["name"],
            module["description"],
            ", ".join(
                [f"<code>{self.prefix[0]}{i}</code>" for i in module["commands"]]
            ),
            module["link"],
        )
        return await message.answer(
            text,
            reply_markup=[
                [
                    {
                        "text": self.strings("source"),
                        "url": f"https://aelis.pythonanywhere.com/view/{module['name']}",
                    },
                    {
                        "text": self.strings("install"),
                        "callback": self.module_load,
                        "kwargs": {"link": module["link"], "text": text},
                    },
                ]
            ],
            photo=module["banner"] or None,
            force_me=True,
        )

    async def module_load(self, call: CallbackQuery, link: str, text: str):
        r = await utils.run_sync(requests.get, link)
        mod = await self.all_modules.load_module(r.text, r.url)
        module = self.all_modules.get_module(mod, True)
        if module is True:
            return await call.edit(
                text,
                reply_markup=[[{"text": self.strings("restart"), "data": "empty"}]],
            )

        if not module:
            return await call.edit(
                text, reply_markup=[[{"text": self.strings("error"), "data": "empty"}]]
            )

        if module == "DAR":
            return await call.edit(
                text, reply_markup=[[{"text": self.strings("error"), "data": "empty"}]]
            )

        self.db.set(
            "shizu.loader",
            "modules",
            list(set(self.db.get("shizu.loader", "modules", []) + [link])),
        )
        return await call.edit(
            text, reply_markup=[[{"text": self.strings("success"), "data": "empty"}]]
        )
