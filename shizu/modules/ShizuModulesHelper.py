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

import io
import os
import requests
import inspect

from aiogram.types import CallbackQuery
from pyrogram import Client, types

from .. import loader, utils


@loader.module("ShizuModulesHelper", "hikamoru")
class ModulesLinkMod(loader.Module):
    """Link or file of the installed module"""

    strings = {}

    @loader.command()
    async def ml(self, app: Client, message: types.Message):
        """Get a link or a module file. Usage: ml <module name or command>  | -c <module name> get core file of project must be provided exact name of module"""

        args = message.get_args_raw()

        if not args:
            return await message.answer(
                self.strings("what_"),
            )

        if "-c" in args:  # it will search from core files
            args = args.replace("-c", "").strip()

            try:
                with open(f"shizu/{args}.py", "rb") as f:
                    source = f.read()

            except FileNotFoundError:
                return await message.answer(
                    self.strings("nope_"),
                )

            source_code = io.BytesIO(source)
            source_code.name = f"{args}.py"
            source_code.seek(0)

            return await message.answer(
                source_code, doc=True, caption=self.strings("core_file").format(args)
            )

        m = await message.answer(
            self.strings("search_"),
        )

        if not (module := self.all_modules.get_module(args, True, True)):
            return await message.answer(
                self.strings("nope_"),
            )

        get_module = inspect.getmodule(module)
        origin = get_module.__spec__.origin

        try:
            source = get_module.__loader__.data
        except AttributeError:
            source = inspect.getsource(get_module).encode("utf-8")

        source_code = io.BytesIO(source)
        source_code.name = f"{module.name}.py"
        source_code.seek(0)

        caption = (
            f'<emoji id=5260730055880876557>⛓</emoji> <a href="{origin}">Link</a> of <code>{module.name}</code> module:\n\n'
            f"<b>{origin}</b>"
            if origin != "<string>" and not os.path.exists(origin)
            else f"<emoji id=5870528606328852614>📁</emoji> <b>File of <code>{module.name}</code></b>"
        )

        await m.delete()
        return await message.answer(source_code, doc=True, caption=caption)

    @loader.command()
    async def aeliscmd(self, app, message):
        """Search module in Aelis API"""
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
