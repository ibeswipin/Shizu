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
import io
import logging
import os
import re
import time
from urllib.parse import urlparse

import requests
from pyrogram import Client, enums, types

from shizu import loader, utils
from shizu.remote import RemoteModuleError

VALID_URL = r"[-[\]_.~:/?#@!$&'()*+,;%<=>a-zA-Z0-9]+"

VALID_PIP_PACKAGES = re.compile(
    rf"^\s*# required:(?: ?)((?:{VALID_URL} )*(?:{VALID_URL}))\s*$",
    re.MULTILINE,
)
GIT_REGEX = re.compile(
    r"^https://github\.com((?:/[a-z0-9-]+){2})(?:/tree/([a-z0-9-]+)((?:/[a-z0-9-]+)*))?/?$",
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
        """Download a module by link or repository name; installed URLs use their pinned source"""
        args = (message.get_args_raw() or "").strip()
        registry = self.all_modules.remote_modules
        if registry.is_remote(args):
            return await self._install_remote(message, args)

        try:
            repositories = [(self.config["repo"], None)]
            if self.config["private_repo"] and self.config["private_token"]:
                repositories.append(
                    (self.config["private_repo"], self.config["private_token"])
                )
            catalogs = []
            for repo, token in repositories:
                raw = await self.get_git_raw_link(repo, token)
                if not raw:
                    return await message.answer(self.strings("invalid_repo"))
                headers = {"Authorization": f"token {token}"} if token else None
                response = await registry.request(raw + "all.txt", headers)
                try:
                    if response.status_code != 200:
                        return await message.answer(
                            self.strings("no_all").format(utils.escape_html(raw)),
                            disable_web_page_preview=True,
                        )
                    catalogs.append((repo, raw, response.text.splitlines(), headers))
                finally:
                    response.close()
        except (
            RemoteModuleError,
            requests.exceptions.RequestException,
            OSError,
        ) as error:
            return await message.answer(
                self.strings("remote_error").format(utils.escape_html(str(error)))
            )

        if not args:
            pages = [
                self.strings("mods_in_repo").format(
                    "🫦" if headers else "🎍", utils.escape_html(repo)
                )
                + "\n".join(
                    f"• <code>{utils.escape_html(name)}</code>" for name in names
                )
                for repo, _, names, headers in catalogs
            ]
            if len(pages) > 1:
                return await self.bot.list(
                    message, pages, disable_web_page_preview=True
                )
            return await message.answer(pages[0], disable_web_page_preview=True)

        for _, raw, names, headers in catalogs:
            if args in names:
                return await self._install_remote(message, raw + args + ".py", headers)
        return await message.answer(self.strings("inc_link"))

    def _remote_headers(self, url: str):
        repo, token = self.config["private_repo"], self.config["private_token"]
        match = GIT_REGEX.search(repo or "")
        parsed = urlparse(url)
        if (
            token
            and match
            and parsed.hostname == "raw.githubusercontent.com"
            and parsed.port in (None, 443)
            and parsed.path.startswith(match[1] + "/")
        ):
            return {"Authorization": f"token {token}"}
        return None

    async def _install_remote(self, message, url: str, headers=None):
        dop_help = "<emoji id=5100652175172830068>▫️</emoji>"
        try:
            item = await self.all_modules._remote_source(url, headers)
            await message.answer(self.strings("check"))
            name = await self.all_modules.load_module(item.source, item.url)
        except (
            RemoteModuleError,
            requests.exceptions.RequestException,
            OSError,
        ) as error:
            return await message.answer(
                self.strings("remote_error").format(utils.escape_html(str(error)))
            )
        if name == "PENDING":
            return await self._review(message, item.source, dop_help)
        errors = {
            "DENIED": "denied",
            "NFA": "not_for_this_account",
            "OTL": "only_telethon",
        }
        if name in errors:
            return await message.answer(self.strings(errors[name]))
        if name is True:
            return await message.answer(self.strings("dep_installed_req_res"))
        if not name or not (module := self.all_modules.find_module_strict(name)):
            return await message.answer(self.strings("not_module"))
        await self.all_modules.call_hook(module, "on_dlmod")
        return await message.answer(await self._loaded_text(module, dop_help))

    @loader.command()
    async def updatemod(self, app: Client, message: types.Message):
        """Review a remote module or library update. Usage: updatemod <module name | https URL>"""
        if not message.from_user or message.from_user.id != self.me.id:
            return
        args = (message.get_args_raw() or "").strip()
        registry = self.all_modules.remote_modules
        if registry.is_remote(args):
            url = args
        elif module := self.all_modules.find_module_strict(args):
            url = self._origin(module)
        else:
            urls = [
                url
                for url, lib in self.all_modules._libraries.items()
                if lib.name.lower() == args.lower()
            ]
            url = urls[0] if len(urls) == 1 else None
        if not url or not registry.is_remote(url):
            return await message.answer(self.strings("update_usage"))
        try:
            registry.validate_url(url)
            token, update = await registry.prepare_update(
                url, self._remote_headers(url)
            )
        except (
            RemoteModuleError,
            requests.exceptions.RequestException,
            OSError,
        ) as error:
            return await message.answer(
                self.strings("remote_error").format(utils.escape_html(str(error)))
            )
        if update.candidate.sha256 == update.previous_sha256:
            registry.cancel_update(token)
            return await message.answer(self.strings("up_to_date"))
        return await message.answer(
            self.strings("update_review").format(
                utils.escape_html(url), update.previous_sha256, update.candidate.sha256
            ),
            reply_markup=[
                [
                    {
                        "text": self.strings("update_confirm"),
                        "callback": self.inline__update,
                        "args": (token, True),
                    },
                    {
                        "text": self.strings("update_cancel"),
                        "callback": self.inline__update,
                        "args": (token, False),
                    },
                ],
                [
                    {
                        "text": self.strings("code"),
                        "callback": self.inline__update_code,
                        "args": (token,),
                    }
                ],
            ],
            force_me=True,
        )

    async def inline__update_code(self, call, token: str):
        if call.from_user.id != self.me.id:
            return await call.answer(self.strings("update_owner"), show_alert=True)
        try:
            update = self.all_modules.remote_modules.pending_update(token)
        except RemoteModuleError as error:
            return await call.answer(str(error), show_alert=True)
        await call.answer()
        file = io.BytesIO(update.candidate.source.encode("utf-8"))
        file.name = "module-update.py"
        await self.app.send_document(call.form["chat"], file)

    async def inline__update(self, call, token: str, allow: bool):
        if call.from_user.id != self.me.id:
            return await call.answer(self.strings("update_owner"), show_alert=True)
        registry = self.all_modules.remote_modules
        if not allow:
            try:
                registry.pending_update(token)
            except RemoteModuleError as error:
                return await call.answer(str(error), show_alert=True)
            registry.cancel_update(token)
            await call.answer()
            return await call.edit(self.strings("update_cancelled"))
        try:
            item = registry.confirm_update(token)
        except (RemoteModuleError, OSError) as error:
            return await call.answer(str(error), show_alert=True)
        await call.answer()
        try:
            if registry.kind(item.url) == "library":
                result = (
                    await self.all_modules.load_guard(item.source, item.url)
                    if self.all_modules.load_guard
                    else True
                )
                if result is True:
                    result = await self.all_modules.review_remote_library(
                        item.source, item.url
                    )
            else:
                result = await self.all_modules.load_module(item.source, item.url)
        except Exception as error:
            registry.rollback_update(item.url, item.sha256)
            logger.exception("Failed to apply confirmed update of %s", item.url)
            return await call.edit(
                self.strings("remote_error").format(utils.escape_html(str(error)))
            )
        if result == "PENDING":
            return await call.edit(self.strings("pending"))
        if result in ("LIBRARY_UPDATED", "LIBRARY_READY"):
            return await call.edit(self.strings("library_updated"))
        if (
            isinstance(result, str)
            and result not in ("DENIED", "NFA", "OTL")
            and (module := self.all_modules.find_module_strict(result))
        ):
            await self.all_modules.call_hook(module, "on_dlmod")
            return await call.edit(await self._loaded_text(module, "▫️"))
        registry.rollback_update(item.url, item.sha256)
        await call.edit(self.strings("update_failed"))

    async def get_git_raw_link(self, repo_url: str, token: str = None):
        self.all_modules.remote_modules.validate_url(repo_url)
        match = GIT_REGEX.search(repo_url)
        if not match:
            return False

        repo_path, branch, path = match.group(1), match.group(2), match.group(3)

        headers = {"Authorization": f"token {token}"} if token else None
        r = await self.all_modules.remote_modules.request(
            f"https://api.github.com/repos{repo_path}", headers
        )
        try:
            if r.status_code != 200:
                return False
            branch = branch or r.json().get("default_branch", "")
        finally:
            r.close()

        return f"https://raw.githubusercontent.com{repo_path}/{branch}{path or ''}/"

    async def _loaded_text(self, module, dop_help: str) -> str:
        bot_username = (await self.bot.bot.get_me()).username
        prefix = self.db.get("shizu.loader", "prefixes", ["."])[0]
        command_descriptions = "\n".join(
            f"{dop_help} <code>{utils.escape_html(prefix + command)}</code> - {utils.escape_html(module.command_handlers[command].__doc__ or 'No description')}"
            for command in module.command_handlers
        )
        inline_descriptions = "\n".join(
            f"{dop_help} <code>@{utils.escape_html(bot_username)} {utils.escape_html(command)}</code> - {utils.escape_html(module.inline_handlers[command].__doc__ or 'No description')}"
            for command in module.inline_handlers
        )
        header = self.strings("loaded").format(
            utils.escape_html(str(module.name).capitalize()),
            utils.escape_html(module.__doc__ or "No description"),
        )
        footer = (
            f"<emoji id=5190458330719461749>🧑‍💻</emoji> <code>{utils.escape_html(str(module.author))}</code>"
            if getattr(module, "author", None)
            else ""
        )
        return (
            header + command_descriptions + "\n" + inline_descriptions + "\n" + footer
        )

    def _besafe(self):
        return getattr(self.all_modules.load_guard, "__self__", None)

    async def _review(self, message, source: str, dop_help: str):
        besafe = self._besafe()
        digest = besafe.digest(source) if besafe else None
        if digest not in getattr(besafe, "pending", {}):
            return await message.answer(self.strings("pending"))

        name = besafe.pending[digest]["name"]
        return await message.answer(
            self.strings("review").format(utils.escape_html(name)),
            reply_markup=[
                [
                    {
                        "text": self.strings("install"),
                        "callback": self.inline__review,
                        "args": (digest, True, dop_help),
                    },
                    {
                        "text": self.strings("deny"),
                        "callback": self.inline__review,
                        "args": (digest, False, dop_help),
                    },
                ],
                [
                    {
                        "text": self.strings("code"),
                        "callback": self.inline__review_code,
                        "args": (digest,),
                    }
                ],
            ],
            force_me=True,
        )

    async def inline__review(self, call, digest: str, allow: bool, dop_help: str):
        besafe = self._besafe()
        if not besafe or digest not in besafe.pending:
            return await call.answer(self.strings("review_gone"), show_alert=True)

        await call.answer()
        item, result = await besafe.decide(digest, allow)
        name = utils.escape_html(item["name"])
        if not allow:
            return await call.edit(besafe.strings("denied").format(name))
        if item.get("load_error"):
            return await call.edit(
                self.strings("remote_error").format(
                    utils.escape_html(item["load_error"])
                )
            )
        if result is True:
            return await call.edit(self.strings("dep_installed_req_res"))
        if result in ("LIBRARY_UPDATED", "LIBRARY_READY"):
            return await call.edit(self.strings("library_updated"))
        if isinstance(result, str) and (
            module := self.all_modules.find_module_strict(result)
        ):
            return await call.edit(await self._loaded_text(module, dop_help))
        await call.edit(
            besafe.strings("approved_only").format(name, utils.escape_html(str(result)))
        )

    async def inline__review_code(self, call, digest: str):
        besafe = self._besafe()
        if not besafe or digest not in besafe.pending:
            return await call.answer(self.strings("review_gone"), show_alert=True)

        await call.answer()
        item = besafe.pending[digest]
        file = io.BytesIO(item["source"].encode("utf-8"))
        file.name = f"{item['name']}.py"
        await self.app.send_document(call.form["chat"], file)

    @loader.command(aliases=["lm"])
    async def loadmod(self, app: Client, message: types.Message):
        """Load a module from a file. Usage: reply to the file"""
        reply = message.reply_to_message
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
            with open(file, encoding="utf-8") as file:
                module_source = file.read()

        except UnicodeDecodeError:
            return await message.answer("❌ Incorrect file encoding")
        await message.answer(self.strings("check"))

        module_name = await self.all_modules.load_module(module_source)
        if module_name is True:
            return await message.answer(self.strings("dep_installed_req_res"))

        if module_name == "PENDING":
            return await self._review(message, module_source, dop_help)

        if module_name == "DENIED":
            return await message.answer(self.strings("denied"))

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

        await self.all_modules.call_hook(module, "on_dlmod")

        return await message.answer(await self._loaded_text(module, dop_help))

    @loader.command()
    async def unloadmod(self, app: Client, message: types.Message):
        """Unload a module. Usage: unloadmod <module name>"""

        module = self.all_modules.find_module_strict(message.get_args_raw())

        if not module:
            return await message.answer(self.strings("inc_module_name"))

        if self.all_modules.is_core(module):
            return await message.answer(self.strings("core_unload"))

        name = self.all_modules.unload_module(module.name)
        return await message.answer(self.strings("unloaded").format(name))

    @loader.command()
    async def unloadall(self, app: Client, message: types.Message):
        """Unload all modules"""

        self._local_modules_path: str = "./shizu/modules"

        self.all_modules.remote_modules.clear_modules()

        for local_module in filter(
            lambda file_name: (
                file_name.endswith(".py") and not file_name.startswith("Shizu")
            ),
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
        path = os.path.realpath(
            os.path.join(cls.CORE_DIR, name.removesuffix(".py") + ".py")
        )
        if not os.path.isfile(path):
            path = os.path.realpath(os.path.join(path[:-3], "__init__.py"))
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
                source_code,
                doc=True,
                caption=self.strings("core_file").format(utils.escape_html(name)),
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
