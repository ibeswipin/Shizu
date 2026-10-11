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


import difflib
import hashlib
import inspect
import io
import logging
import os
import re
import time
from urllib.parse import quote, unquote, urlparse

import requests
from aiogram.types import InputFile
from pyrogram import Client, enums, types

from shizu import loader, utils
from shizu.remote import RemoteModuleError

VALID_URL = r"[-[\]_.~:/?#@!$&'()*+,;%<=>a-zA-Z0-9]+"

VALID_PIP_PACKAGES = re.compile(
    rf"^\s*# required:(?: ?)((?:{VALID_URL} )*(?:{VALID_URL}))\s*$",
    re.MULTILINE,
)
GIT_REGEX = re.compile(
    r"^https://github\.com(/[a-z0-9-]+/[a-z0-9_.-]+)(?:/tree/([a-z0-9_.-]+)((?:/[a-z0-9_.-]+)*))?/?\Z",
    flags=re.IGNORECASE,
)

logger = logging.getLogger(__name__)


class RepositoryLink(loader.Validators.Link):
    def validate(self, value):
        value = super().validate(value)
        if not GIT_REGEX.fullmatch(value):
            raise ValueError(
                "Use a GitHub repository link: "
                "https://github.com/owner/repository[/tree/branch/path]"
            )
        return value


class PrivateRepository:
    def validate(self, value):
        if not isinstance(value, dict) or set(value) != {"url", "token"}:
            raise ValueError('Use an object with "url" and "token" fields')
        try:
            url = RepositoryLink().validate(value["url"])
        except (ValueError, TypeError):
            raise ValueError("Invalid private repository URL") from None
        token = value["token"]
        if not isinstance(token, str) or not token.strip():
            raise ValueError("A private repository token is required")
        token = token.strip()
        if not token.isascii() or any(
            ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in token
        ):
            raise ValueError("Invalid private repository token")
        return {"url": url, "token": token}


@loader.module(name="ShizuLoader", author="shizu")
class Loader(loader.Module):
    """Mainly used to load modules"""

    strings = {}

    def __init__(self):
        self._catalog_cache = {}
        self._repo_cache = {}
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "repo",
                "https://github.com/AmoreForever/ShizuMods",
                lambda: self.strings("cfg_repo"),
                validator=RepositoryLink(),
                label=lambda: self.strings("cfg_label_repo"),
            ),
            loader.ConfigValue(
                "additional_repos",
                [],
                lambda: self.strings("cfg_additional_repos"),
                validator=loader.validators.Series(validator=RepositoryLink()),
                label=lambda: self.strings("cfg_label_additional_repos"),
            ),
            loader.ConfigValue(
                "private_repo",
                None,
                lambda: self.strings("cfg_private_repo"),
                validator=loader.validators.Union(
                    loader.validators.NoneType(), RepositoryLink()
                ),
                label=lambda: self.strings("cfg_label_private_repo"),
            ),
            loader.ConfigValue(
                "private_token",
                None,
                lambda: self.strings("cfg_private_token"),
                validator=loader.validators.Hidden(),
                label=lambda: self.strings("cfg_label_private_token"),
            ),
            loader.ConfigValue(
                "private_repos",
                [],
                lambda: self.strings("cfg_private_repos"),
                validator=loader.validators.Hidden(
                    loader.validators.Series(validator=PrivateRepository())
                ),
                label=lambda: self.strings("cfg_label_private_repos"),
            ),
            loader.ConfigValue(
                "notify_updates",
                True,
                lambda: self.strings("cfg_notify_updates"),
                validator=loader.validators.Boolean(),
                label=lambda: self.strings("cfg_label_notify_updates"),
            ),
            loader.ConfigValue(
                "update_check_interval",
                3600,
                lambda: self.strings("cfg_update_check_interval"),
                validator=loader.validators.Integer(minimum=300),
                label=lambda: self.strings("cfg_label_update_check_interval"),
            ),
        )

    def _repositories(self):
        repositories = {}
        for repo, token in [
            (repo, None)
            for repo in [self.config["repo"], *(self.config["additional_repos"] or [])]
            if repo
        ] + self._private_repositories():
            match = GIT_REGEX.fullmatch(repo)
            key = (match[1].lower(), match[2], match[3]) if match else repo
            repositories[key] = (repo, token)
        return list(repositories.values())

    def _private_repositories(self):
        repositories = []
        if self.config["private_repo"] and self.config["private_token"]:
            repositories.append(
                (self.config["private_repo"], self.config["private_token"])
            )
        repositories.extend(
            (entry["url"], entry["token"])
            for entry in self.config["private_repos"] or []
        )
        return repositories

    def _repository_module(self, url: str) -> bool:
        """Match the installed source to a configured repository and optional tree."""
        try:
            parsed = urlparse(url)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "raw.githubusercontent.com"
                or parsed.port not in (None, 443)
                or parsed.username is not None
                or parsed.password is not None
            ):
                return False
        except (ValueError, TypeError):
            return False
        for repo, _ in self._repositories():
            if not (match := GIT_REGEX.fullmatch(repo)):
                continue
            repo_path, branch, path = match.groups()
            if parsed.path[: len(repo_path)].lower() != repo_path.lower():
                continue
            remainder = parsed.path[len(repo_path) :]
            prefix = f"/{branch}{path or ''}/" if branch else "/"
            if remainder.startswith(prefix):
                return True
        return False

    def _watched_modules(self):
        return {
            url: module.name
            for module in list(self.all_modules.modules)
            if self._repository_module(url := self._origin(module))
        }

    @loader.loop(interval="update_check_interval", autostart=True, wait_before=True)
    async def check_module_updates(self):
        """Announce changed pinned sources without installing or approving them."""
        if not self.config["notify_updates"]:
            return
        registry = self.all_modules.remote_modules
        modules = self._watched_modules()
        notified = self.get("notified_updates", {})
        notified = {url: value for url, value in notified.items() if url in modules}
        if notified != self.get("notified_updates", {}):
            self.set("notified_updates", notified)
        for url, name in modules.items():
            try:
                record = registry.record(url)
                if not record or not record.get("sha256") or record.get("previous"):
                    continue
                token, update = await registry.prepare_update(
                    url, self._remote_headers(url)
                )
                registry.cancel_update(token)
                if update.candidate.sha256 == update.previous_sha256:
                    if url in notified:
                        notified.pop(url)
                        self.set("notified_updates", dict(notified))
                    continue
                fingerprint = {
                    "installed": update.previous_sha256,
                    "available": update.candidate.sha256,
                }
                state = notified.get(url, {})
                if any(state.get(key) != value for key, value in fingerprint.items()):
                    await self._send_module_update_notification(name, url)
                    state = {**fingerprint, "diff_sent": False}
                    notified[url] = state
                    self.set("notified_updates", dict(notified))
                if not state.get("diff_sent"):
                    await self.bot.bot.send_document(
                        self.me.id,
                        InputFile(
                            self._update_diff_file(update),
                            filename="module-update.diff",
                        ),
                        caption=self.strings("update_diff_caption").format(
                            utils.escape_html(name)
                        ),
                    )
                    notified[url] = {**state, "diff_sent": True}
                    self.set("notified_updates", dict(notified))
            except Exception:
                logger.exception(
                    "Failed to check or announce module update for %s", url
                )

    async def _send_module_update_notification(self, name, url):
        await self.bot.bot.send_message(
            self.me.id,
            self.strings("module_update_available").format(
                utils.escape_html(name),
                utils.escape_html(url),
                utils.escape_html(self.get_prefix()),
            ),
            reply_markup=self.bot._generate_markup(
                [
                    [
                        {
                            "text": self.strings("update_open"),
                            "callback": self.inline__module_update,
                            "args": (url, True),
                            "force_me": True,
                        },
                        {
                            "text": self.strings("update_skip"),
                            "callback": self.inline__module_update,
                            "args": (url, False),
                            "force_me": True,
                        },
                    ]
                ]
            ),
            disable_web_page_preview=True,
        )

    async def _edit_update_message(self, call, text, reply_markup=None):
        """Update cards work both in inline forms and in the bot's private chat."""
        if getattr(call, "message", None):
            return await call.message.edit_text(
                self.bot.sanitise_text(text),
                reply_markup=self.bot._generate_markup(reply_markup or []),
                disable_web_page_preview=True,
            )
        return await call.edit(text, reply_markup=reply_markup)

    async def inline__module_update(self, call, url: str, review: bool):
        if call.from_user.id != self.me.id:
            return await call.answer(self.strings("update_owner"), show_alert=True)
        await call.answer()
        if not review:
            return await self._edit_update_message(call, self.strings("update_skipped"))
        if url not in self._watched_modules():
            return await self._edit_update_message(
                call, self.strings("update_unavailable")
            )
        registry = self.all_modules.remote_modules
        try:
            token, update = await registry.prepare_update(
                url, self._remote_headers(url)
            )
        except (
            RemoteModuleError,
            requests.exceptions.RequestException,
            OSError,
        ) as error:
            return await self._edit_update_message(
                call, self.strings("remote_error").format(utils.escape_html(str(error)))
            )
        if update.candidate.sha256 == update.previous_sha256:
            registry.cancel_update(token)
            return await self._edit_update_message(call, self.strings("up_to_date"))
        try:
            return await self._edit_update_message(
                call, self._update_review_text(update), self._update_buttons(token)
            )
        except Exception:
            registry.cancel_update(token)
            raise

    @loader.command(aliases=["dlm"])
    async def dlmod(self, app: Client, message: types.Message):
        """Download a module by link or repository name; installed URLs use their pinned source"""
        args = (message.get_args_raw() or "").strip()
        registry = self.all_modules.remote_modules
        if registry.is_remote(args):
            return await self._install_remote(message, args)

        try:
            catalogs = []
            for repo, token in self._repositories():
                raw = await self.get_git_raw_link(repo, token)
                if not raw:
                    return await message.answer(self.strings("invalid_repo"))
                headers = {"Authorization": f"token {token}"} if token else None
                catalogs.append((repo, raw, await self._catalog(raw, headers), headers))
        except (
            RemoteModuleError,
            requests.exceptions.RequestException,
            OSError,
        ) as error:
            return await message.answer(
                self.strings("remote_error").format(utils.escape_html(str(error)))
            )

        if not args:
            pages = self._catalog_pages(catalogs)
            if not pages:
                return await message.answer(self.strings("no_repositories"))
            if len(pages) > 1:
                return await self.bot.list(
                    message, pages, disable_web_page_preview=True
                )
            return await message.answer(pages[0], disable_web_page_preview=True)

        for _, raw, names, headers in catalogs:
            if args in names:
                return await self._install_remote(
                    message, raw + quote(names[args], safe="/"), headers
                )
        return await message.answer(self.strings("inc_link"))

    @staticmethod
    def _catalog_entry(path):
        if not isinstance(path, str) or not path.lower().endswith(".py"):
            return None
        decoded = unquote(path)
        if (
            decoded.startswith("/")
            or "\\" in decoded
            or "://" in decoded
            or any(ord(char) < 32 or ord(char) == 127 for char in decoded)
            or any(part in ("", ".", "..") for part in decoded.split("/"))
        ):
            return None
        return path[:-3], path

    async def _catalog(self, raw, headers=None):
        key = self._repo_cache_key(raw, (headers or {}).get("Authorization", ""))
        cached = self._catalog_cache.get(key)
        if cached and cached[0] > time.monotonic():
            return dict(cached[1])
        response = await self.all_modules.remote_modules.request(
            raw + "all.txt", headers
        )
        try:
            if response.status_code == 200:
                names = {}
                for line in response.text.splitlines():
                    name = line.strip()
                    if not name or name.startswith("#"):
                        continue
                    entry = self._catalog_entry(
                        name if name.lower().endswith(".py") else name + ".py"
                    )
                    if entry is None:
                        raise RemoteModuleError("Invalid module path in all.txt.")
                    names.setdefault(*entry)
                self._cache_repo(self._catalog_cache, key, dict(names))
                return names
            if response.status_code != 404:
                raise RemoteModuleError(
                    f"Could not read the repository catalog (HTTP {response.status_code})."
                )
        finally:
            response.close()
        names = await self._github_catalog(raw, headers)
        self._cache_repo(self._catalog_cache, key, dict(names))
        return names

    @staticmethod
    def _repo_cache_key(url, token):
        return url, hashlib.sha256((token or "").encode()).hexdigest()

    @staticmethod
    def _cache_repo(cache, key, value):
        if len(cache) >= 64 and key not in cache:
            cache.pop(next(iter(cache)))
        cache[key] = (time.monotonic() + 300, value)

    async def _github_catalog(self, raw, headers=None):
        parsed = urlparse(raw)
        parts = parsed.path.strip("/").split("/", 3)
        if parsed.hostname != "raw.githubusercontent.com" or len(parts) < 3:
            raise RemoteModuleError("Cannot discover files for this repository URL.")
        owner, repo, branch = parts[:3]
        prefix = parts[3].rstrip("/") + "/" if len(parts) == 4 else ""
        url = f"https://api.github.com/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/git/trees/{quote(branch, safe='')}?recursive=1"
        response = await self.all_modules.remote_modules.request(
            url, {**(headers or {}), "Accept": "application/vnd.github+json"}
        )
        try:
            if response.status_code != 200:
                raise RemoteModuleError(
                    f"Could not list repository files (HTTP {response.status_code})."
                )
            try:
                data = response.json()
            except ValueError as error:
                raise RemoteModuleError(
                    "GitHub returned an invalid repository file list."
                ) from error
        finally:
            response.close()
        if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
            raise RemoteModuleError("GitHub returned an invalid repository file list.")
        if data.get("truncated"):
            raise RemoteModuleError(
                "GitHub returned an incomplete file list. Add an all.txt catalog to this repository."
            )
        names = {}
        for item in data["tree"]:
            if (
                not isinstance(item, dict)
                or item.get("type") != "blob"
                or item.get("mode") == "120000"
            ):
                continue
            path = item.get("path", "")
            if not isinstance(path, str) or not path.startswith(prefix):
                continue
            path = path[len(prefix) :]
            if any(part.startswith((".", "_")) for part in path.split("/")):
                continue
            entry = self._catalog_entry(path)
            if entry:
                names.setdefault(*entry)
        return dict(sorted(names.items(), key=lambda item: item[0].casefold()))

    def _catalog_pages(self, catalogs):
        pages = []
        for repo, _, names, headers in catalogs:
            title = self.strings("mods_in_repo").format(
                "🫦" if headers else "🎍", utils.escape_html(repo)
            )
            page = title
            if not names:
                pages.append(title + self.strings("no_modules"))
                continue
            for name in names:
                line = f"• <code>{utils.escape_html(name)}</code>\n"
                if len(page) + len(line) > 3500 and page != title:
                    pages.append(page.rstrip())
                    page = title
                page += line
            pages.append(page.rstrip())
        return pages

    def _remote_headers(self, url: str):
        try:
            parsed = urlparse(url)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "raw.githubusercontent.com"
                or parsed.port not in (None, 443)
                or parsed.username is not None
                or parsed.password is not None
                or any(part in (".", "..") for part in unquote(parsed.path).split("/"))
            ):
                return None
        except (ValueError, TypeError):
            return None
        candidates = []
        for repo, token in self._private_repositories():
            if not (match := GIT_REGEX.fullmatch(repo)):
                continue
            repo_path, branch, path = match.groups()
            remainder = parsed.path[len(repo_path) :]
            prefix = f"/{branch}{path or ''}/" if branch else "/"
            same_repo = parsed.path[: len(repo_path)].lower() == repo_path.lower()
            if same_repo and remainder.startswith(prefix):
                candidates.append((len(prefix), token))
        if candidates:
            # Prefer the most specific tree; a later entry wins for equal scopes.
            token = sorted(candidates, key=lambda item: item[0])[-1][1]
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
            "PREMIUM_REQUIRED": "premium_required",
        }
        if name in errors:
            return await message.answer(self.strings(errors[name]))
        if name is True:
            return await message.answer(self.strings("dep_installed_req_res"))
        if not name or not (module := self.all_modules.find_module_strict(name)):
            reason = getattr(self.all_modules, "get_load_error", lambda *_: "")(
                item.source, item.url
            )
            if reason:
                return await message.answer(
                    self.strings("load_failed").format(utils.escape_html(reason))
                )
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
            url = registry.source_url(url)
            token, update = await registry.prepare_update(
                url, self._remote_headers(registry.normalize_url(url))
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
            self._update_review_text(update),
            reply_markup=self._update_buttons(token),
            force_me=True,
        )

    def _update_review_text(self, update):
        return self.strings("update_review").format(
            utils.escape_html(update.candidate.url),
            update.previous_sha256,
            update.candidate.sha256,
        )

    def _update_buttons(self, token):
        return [
            [
                {
                    "text": self.strings("update_confirm"),
                    "callback": self.inline__update,
                    "args": (token, True),
                    "force_me": True,
                },
                {
                    "text": self.strings("update_cancel"),
                    "callback": self.inline__update,
                    "args": (token, False),
                    "force_me": True,
                },
            ],
            [
                {
                    "text": self.strings("code"),
                    "callback": self.inline__update_code,
                    "args": (token,),
                    "force_me": True,
                },
                {
                    "text": self.strings("update_diff"),
                    "callback": self.inline__update_diff,
                    "args": (token,),
                    "force_me": True,
                },
            ],
        ]

    @staticmethod
    def _update_diff_file(update):
        lines = difflib.unified_diff(
            update.previous_source.splitlines(keepends=True),
            update.candidate.source.splitlines(keepends=True),
            fromfile="installed.py",
            tofile="new.py",
        )
        diff = "".join(
            line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
            for line in lines
        )
        file = io.BytesIO(diff.encode("utf-8"))
        file.name = "module-update.diff"
        return file

    async def _send_update_file(self, call, file):
        if getattr(call, "message", None):
            return await self.bot.bot.send_document(
                call.message.chat.id, InputFile(file, filename=file.name)
            )
        return await self.app.send_document(call.form["chat"], file)

    async def inline__update_diff(self, call, token: str):
        if call.from_user.id != self.me.id:
            return await call.answer(self.strings("update_owner"), show_alert=True)
        try:
            update = self.all_modules.remote_modules.pending_update(token)
        except RemoteModuleError as error:
            return await call.answer(str(error), show_alert=True)
        await call.answer()
        return await self._send_update_file(call, self._update_diff_file(update))

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
        return await self._send_update_file(call, file)

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
            return await self._edit_update_message(
                call, self.strings("update_cancelled")
            )
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
            return await self._edit_update_message(
                call, self.strings("remote_error").format(utils.escape_html(str(error)))
            )
        if result == "PENDING":
            return await self._edit_update_message(call, self.strings("pending"))
        if result in ("LIBRARY_UPDATED", "LIBRARY_READY"):
            return await self._edit_update_message(
                call, self.strings("library_updated")
            )
        if (
            isinstance(result, str)
            and result not in ("DENIED", "NFA", "OTL", "PREMIUM_REQUIRED")
            and (module := self.all_modules.find_module_strict(result))
        ):
            await self.all_modules.call_hook(module, "on_dlmod")
            return await self._edit_update_message(
                call, await self._loaded_text(module, "▫️")
            )
        registry.rollback_update(item.url, item.sha256)
        reason = getattr(self.all_modules, "get_load_error", lambda *_: "")(
            item.source, item.url
        )
        if reason:
            return await self._edit_update_message(
                call, self.strings("load_failed").format(utils.escape_html(reason))
            )
        await self._edit_update_message(call, self.strings("update_failed"))

    async def get_git_raw_link(self, repo_url: str, token: str = None):
        self.all_modules.remote_modules.validate_url(repo_url)
        match = GIT_REGEX.search(repo_url)
        if not match:
            return False

        key = self._repo_cache_key(repo_url, token)
        cached = self._repo_cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

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

        raw = f"https://raw.githubusercontent.com{repo_path}/{branch}{path or ''}/"
        self._cache_repo(self._repo_cache, key, raw)
        return raw

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
                self.strings("load_failed").format(
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
            reason = getattr(self.all_modules, "get_load_error", lambda *_: "")(
                module_source
            )
            if reason:
                return await message.answer(
                    self.strings("load_failed").format(utils.escape_html(reason))
                )
            return await message.answer(self.strings("not_module"))

        if module_name == "NFA":
            return await message.answer(self.strings("not_for_this_account"))

        if module_name == "OTL":
            return await message.answer(self.strings("only_telethon"))

        if module_name == "PREMIUM_REQUIRED":
            return await message.answer(self.strings("premium_required"))

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
