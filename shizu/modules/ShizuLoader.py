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

# -------------------------------------------------------------------------

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



import logging
import os
import re
import time
from typing import List

import requests
from pyrogram import Client, enums, types

from shizu import loader, utils

VALID_URL = r"[-[\]_.~:/?#@!$&'()*+,;%<=>a-zA-Z0-9]+"

VALID_PIP_PACKAGES = re.compile(
    r"^\s*# required:(?: ?)((?:{url} )*(?:{url}))\s*$".format(url=VALID_URL),
    re.MULTILINE,
)
GIT_REGEX = re.compile(
    r"^https?://github\.com((?:/[a-z0-9-]+){2})(?:/tree/([a-z0-9-]+)((?:/[a-z0-9-]+)*))?/?$",
    flags=re.IGNORECASE,
)

logger = logging.getLogger(__name__)


@loader.module(name="ShizuLoader", author="shizu")
class Loader(loader.Module):
    """Mainly used to load modules"""

    strings = {}

    def __init__(self):
        self.config = loader.ModuleConfig(
            "repo",
            "https://github.com/AmoreForever/ShizuMods",
            "Repository link",
            "private_repo",
            None,
            "Private repository link",
            "private_token",
            None,
            "Private repository token",
        )

    @loader.command(aliases=["dlm"])
    async def dlmod(self, app: Client, message: types.Message):
        """Download module by link. Usage: dlmod <link or all or nothing>"""

        args = message.get_args_raw()

        bot_username = (await self.bot.bot.get_me()).username
        dop_help = "<emoji id=5100652175172830068>▫️</emoji>"
        modules_repo = self.config["repo"]
        private = self.config["private_repo"], self.config["private_token"]

        api_result = await self.get_git_raw_link(modules_repo)

        if not api_result:
            return await message.answer(self.strings("invalid_repo"))

        raw_link = api_result

        modules = await utils.run_sync(requests.get, f"{raw_link}all.txt")

        if modules.status_code != 200:
            return await message.answer(
                self.strings("no_all").format(raw_link), disable_web_page_preview=True
            )

        modules: List[str] = modules.text.splitlines()

        if self.config["private_repo"] and self.config["private_token"]:
            api_resultP = await self.get_git_raw_link(private[0], private[1])

            if not api_resultP:
                return await message.answer(self.strings("invalid_repo"))

            headers = {"Authorization": f"token {private[1]}"}

            modulesP = await utils.run_sync(
                requests.get, f"{api_resultP}all.txt", headers=headers
            )

            if modulesP.status_code != 200:
                return await message.answer(
                    self.strings("no_all").format(api_resultP),
                    disable_web_page_preview=True,
                )

            modulesP: List[str] = modulesP.text.splitlines()

        if not args:
            text = self.strings("mods_in_repo").format("🎍", modules_repo) + "\n".join(
                map("• <code>{}</code>".format, modules)
            )

            if self.config["private_repo"] and self.config["private_token"]:
                textP = self.strings("mods_in_repo").format(
                    "🫦", private[0]
                ) + "\n".join(map("• <code>{}</code>".format, modulesP))

                return await self.bot.list(
                    message,
                    [text, textP],
                    disable_web_page_preview=True,
                )

            return await message.answer(text, disable_web_page_preview=True)

        error_text: str = None
        module_name: str = None
        is_private = False

        if args not in modules and (
            not self.config["private_repo"]
            or not self.config["private_token"]
            or args not in modulesP
        ):
            r = await utils.run_sync(requests.get, args)
            if r.status_code != 200:
                raise requests.exceptions.ConnectionError

            await message.answer(self.strings("check"))

            module_name = await self.all_modules.load_module(r.text, r.url)

        if args in modules:
            args = raw_link + args + ".py"
            r = await utils.run_sync(requests.get, args)
            if r.status_code != 200:
                raise requests.exceptions.ConnectionError

            await message.answer(self.strings("check"))

            module_name = await self.all_modules.load_module(r.text, r.url)

        if (
            self.config["private_repo"]
            and self.config["private_token"]
            and args in modulesP
        ):
            args = api_resultP + args + ".py"

            headers = {"Authorization": f"token {private[1]}"}

            r = await utils.run_sync(requests.get, args, headers=headers)

            if r.status_code != 200:
                raise requests.exceptions.ConnectionError

            await message.answer(self.strings("check"))

            module_name = await self.all_modules.load_module(r.text, "<string>")
            is_private = True

        try:
            if module_name == "NFA":
                error_text = self.strings("not_for_this_account")
            if module_name is True:
                error_text = self.strings("dep_installed_req_res")
            if not module_name:
                error_text = self.strings("not_module")

        except requests.exceptions.MissingSchema:
            error_text = self.strings("inc_link")
        except requests.exceptions.ConnectionError:
            error_text = self.strings("inc_link")
        except requests.exceptions.RequestException:
            error_text = self.strings("unex_error")

        if error_text:
            return await message.answer(error_text)

        if not is_private:
            self.db.set(
                "shizu.loader",
                "modules",
                list(set(self.db.get("shizu.loader", "modules", []) + [args])),
            )

        if is_private:
            with open(
                f"./shizu/modules/{module_name}.py", "w", encoding="utf-8"
            ) as file:
                file.write(r.text)

        if not (module := self.all_modules.get_module(module_name, True)):
            return await message.answer(
                "<b><emoji id=5465665476971471368>❌</emoji> There is no such module</b>",
            )

        prefix = self.db.get("shizu.loader", "prefixes", ["."])[0]
        command_descriptions = "\n".join(
            f"{dop_help} <code>{prefix + command}</code> - {module.command_handlers[command].__doc__ or 'No description'}"
            for command in module.command_handlers
        )
        inline_descriptions = "\n".join(
            f"{dop_help} <code>@{bot_username} {command}</code> - {module.inline_handlers[command].__doc__ or 'No description'}"
            for command in module.inline_handlers
        )
        modname = str(module.name).capitalize()

        header = self.strings("loaded").format(
            modname, module.__doc__ or "No description"
        )
        footer = (
            f"<emoji id=5190458330719461749>🧑‍💻</emoji> <code>{module.author}</code>"
            if module.author
            else ""
        )
        return await message.answer(
            header + command_descriptions + "\n" + inline_descriptions + "\n" + footer,
        )

    async def get_git_raw_link(self, repo_url: str, token: str = None):
        match = GIT_REGEX.search(repo_url)
        if not match:
            return False

        repo_path, branch, path = match.group(1), match.group(2), match.group(3)

        if token:
            headers = {"Authorization": f"token {token}"}
            r = await utils.run_sync(
                requests.get,
                f"https://api.github.com/repos{repo_path}",
                headers=headers,
            )
        else:
            r = await utils.run_sync(
                requests.get, f"https://api.github.com/repos{repo_path}"
            )

        if r.status_code != 200:
            return False

        branch = branch or r.json().get("default_branch", "")

        return f"https://raw.githubusercontent.com{repo_path}/{branch}{path or ''}/"

    @loader.command(aliases=["lm"])
    async def loadmod(self, app: Client, message: types.Message):
        """Load the module by file. Usage: <replay per file>"""
        reply = message.reply_to_message
        bot_username = (await self.bot.bot.get_me()).username
        dop_help = (
            "<emoji id=5100652175172830068>🔸</emoji>"
            if message.from_user.is_premium
            else "🔸"
        )

        file = (
            message if message.document else reply if reply and reply.document else None
        )

        if not file:
            return await message.answer(self.strings("no_repy_to_file"))

        await message.answer(self.strings("loading"))
        file = await file.download()

        for mod in self.cmodules:
            if file == mod:
                return await message.answer(self.strings("core_do"))

        try:
            with open(file, "r", encoding="utf-8") as file:
                module_source = file.read()

        except UnicodeDecodeError:
            return await message.answer("❌ Incorrect file encoding")
        await message.answer(self.strings("check"))

        module_name = await self.all_modules.load_module(module_source)
        if module_name is True:
            return await message.answer(self.strings("dep_installed_req_res"))

        if not module_name:
            return await message.answer(self.strings("not_module"))

        if module_name == "NFA":
            return await message.answer(self.strings("not_for_this_account"))

        if module_name == "OTL":
            return await message.answer(self.strings("only_telethon"))

        if module_name == "BAN":
            return await message.answer(self.strings("loaded_banned"))

        module = "_".join(module_name.lower().split())
        with open(f"shizu/modules/{module}.py", "w", encoding="utf-8") as file:
            file.write(module_source)

        if not (module := self.all_modules.get_module(module_name, True)):
            return await message.answer(
                "<b><emoji id=5465665476971471368>❌</emoji> There is no such module</b>",
            )

        prefix = self.db.get("shizu.loader", "prefixes", ["."])[0]
        command_descriptions = "\n".join(
            f"{dop_help} <code>{prefix + command}</code> - {module.command_handlers[command].__doc__ or 'No description'}"
            for command in module.command_handlers
        )
        inline_descriptions = "\n".join(
            f"{dop_help} <code>@{bot_username} {command}</code> - {module.inline_handlers[command].__doc__ or 'No description'}"
            for command in module.inline_handlers
        )
        modname = str(module.name).capitalize()

        header = self.strings("loaded").format(
            modname, module.__doc__ or "No description"
        )
        footer = (
            f"<emoji id=5190458330719461749>🧑‍💻</emoji> <code>{module.author}</code>"
            if module.author
            else ""
        )
        return await message.answer(
            header + command_descriptions + "\n" + inline_descriptions + "\n" + footer,
        )

    @loader.command()
    async def unloadmod(self, app: Client, message: types.Message):
        """Unload the module. Usage: unloadmod <module name>"""

        args = message.get_args_raw()

        if not (module_name := self.all_modules.unload_module(args)):
            return await message.answer(self.strings("inc_module_name"))

        if module_name in self.cmodules:
            logging.error("You can't unload core modules")
            return await message.answer(self.strings("core_unload"))

        return await message.answer(self.strings("unloaded").format(module_name))

    @loader.command()
    async def unloadall(self, app: Client, message: types.Message):
        """Unload all modules"""

        self._local_modules_path: str = "./shizu/modules"

        self.db.set("shizu.loader", "modules", [])

        for local_module in filter(
            lambda file_name: file_name.endswith(".py")
            and not file_name.startswith("Shizu"),
            os.listdir(self._local_modules_path),
        ):
            os.remove(f"{self._local_modules_path}/{local_module}")

        await message.answer(self.strings("all_unloaded"))
        ms = await message.answer(self.strings("restart"))

        self.db.set(
            "shizu.updater",
            "restart",
            {
                "chat": message.chat.username
                if message.chat.type == enums.ChatType.BOT
                else message.chat.id,
                "id": ms.id,
                "start": time.time(),
                "type": "restart",
            },
        )

        utils.restart()
