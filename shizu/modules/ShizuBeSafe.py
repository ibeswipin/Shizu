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

import ast
import asyncio
import contextlib
import difflib
import functools
import hashlib
import io
import logging
import os
import re
import time
from urllib.parse import urlparse

from aiogram.types import CallbackQuery, InputFile
from pyrogram import Client, types

from shizu import loader, utils

URL_RE = re.compile(r"https?://[^\s'\"<>)\]]+")
NAME_RE = re.compile(r"class\s+(\w+)\s*\(")
REQUIRED_RE = re.compile(r"^\s*# ?required:\s*(.+)$", re.MULTILINE)
DEFAULT_TRUSTED = ["https://raw.githubusercontent.com/ibeswipin/ShizuMods/"]
LOG_LIMIT = 50
PENDING_LIMIT = 20


def summarize(source: str) -> dict:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        imports = None
    else:
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add("." * node.level + (node.module or "").split(".")[0])
    hosts = {urlparse(u).hostname for u in URL_RE.findall(source)} - {None}
    match = NAME_RE.search(source)
    return {
        "name": match.group(1) if match else "?",
        "lines": source.count("\n") + 1,
        "imports": sorted(imports) if imports is not None else None,
        "hosts": sorted(hosts),
        "requires": sorted(
            {pkg for line in REQUIRED_RE.findall(source) for pkg in line.split()}
        ),
    }


def normalize_prefix(url: str) -> str:
    url = url.strip()
    return url if url.endswith("/") else url + "/"


def is_url(origin: str) -> bool:
    return bool(origin) and origin.startswith(("http://", "https://"))


@loader.module(name="ShizuBeSafe", author="shizu")
class BeSafe(loader.Module):
    """Third-party modules load only after the owner reviews and approves them"""

    strings = {
        "card": (
            "🛡 <b>BeSafe: module is waiting for approval</b>\n\n"
            "📦 <b>Module:</b> <code>{name}</code>\n"
            "🌐 <b>Source:</b> <code>{origin}</code>\n"
            "📏 <b>Lines:</b> {lines} · <b>SHA-256:</b> <code>{digest}</code>\n"
            "📚 <b>Imports:</b> {imports}\n"
            "📥 <b>Installs packages:</b> {requires}\n"
            "🔗 <b>Addresses in code:</b> {hosts}\n"
            "{changed}\n"
            "<i>Open the code and read it before approving. An approved module gets full access to the account.</i>"
        ),
        "changed": "⚠️ <b>The code differs from the previously approved version of this source</b>\n",
        "unparsable": "the code could not be parsed",
        "none": "none",
        "file": "file",
        "btn_allow": "✅ Allow",
        "btn_deny": "❌ Deny",
        "btn_code": "📄 Code",
        "btn_diff": "🔀 Diff",
        "loaded": "✅ <b>Approved and loaded</b> <code>{}</code>",
        "approved_only": "✅ <b>Approved</b> <code>{}</code>, but it did not load: <code>{}</code>",
        "approved_restart": "✅ <b>Approved</b> <code>{}</code>. Dependencies are installed, restart required",
        "denied": "❌ <b>Denied</b> <code>{}</code>. This version will not load",
        "gone": "This request is no longer active",
        "not_you": "Only the account owner can decide",
        "status": (
            "🛡 <b>BeSafe</b>\n\n<b>Approved:</b> {}\n<b>Denied:</b> {}\n<b>Waiting:</b> {}\n"
            "<b>Trusted sources:</b>\n{}\n\n"
            "<code>.besafe list</code> · <code>.besafe log</code> · <code>.bstrust</code> · "
            "<code>.bsuntrust</code> · <code>.bsforget</code>"
        ),
        "list_line": "• <code>{}</code> {} — <code>{}</code>",
        "list_approved": "<b>✅ Approved</b>",
        "list_denied": "<b>❌ Denied</b>",
        "log_line": "{} · {} · <code>{}</code> {}",
        "act_allow": "✅ allowed",
        "act_deny": "❌ denied",
        "act_trusted": "🤝 trusted source",
        "act_bootstrap": "📦 already installed",
        "act_forget": "🗑 revoked",
        "forget_usage": "❔ <code>.bsforget &lt;hash start&gt;</code> — see <code>.besafe list</code>",
        "forgotten": "🗑 Decision revoked: {}",
        "not_found": "❌ No such hash, or it is ambiguous",
        "trust_usage": "❔ <code>.bstrust https://raw.githubusercontent.com/user/repo/</code>",
        "trusted": "🤝 Trusted source added: <code>{}</code>",
        "untrusted": "🗑 Trusted source removed: <code>{}</code>",
        "trust_missing": "❌ This source is not in the list",
        "too_many": "BeSafe: too many pending modules, request for {} skipped",
    }

    strings_ru = {
        "card": (
            "🛡 <b>BeSafe: модуль ждёт подтверждения</b>\n\n"
            "📦 <b>Модуль:</b> <code>{name}</code>\n"
            "🌐 <b>Источник:</b> <code>{origin}</code>\n"
            "📏 <b>Строк:</b> {lines} · <b>SHA-256:</b> <code>{digest}</code>\n"
            "📚 <b>Импорты:</b> {imports}\n"
            "📥 <b>Установит пакеты:</b> {requires}\n"
            "🔗 <b>Адреса в коде:</b> {hosts}\n"
            "{changed}\n"
            "<i>Открой код и прочитай его перед одобрением. Одобренный модуль получает полный доступ к аккаунту.</i>"
        ),
        "changed": "⚠️ <b>Код отличается от ранее одобренной версии из этого источника</b>\n",
        "unparsable": "код не разбирается",
        "none": "нет",
        "file": "файл",
        "btn_allow": "✅ Разрешить",
        "btn_deny": "❌ Отклонить",
        "btn_code": "📄 Код",
        "btn_diff": "🔀 Разница",
        "loaded": "✅ <b>Одобрено и загружено</b> <code>{}</code>",
        "approved_only": "✅ <b>Одобрено</b> <code>{}</code>, но не загрузилось: <code>{}</code>",
        "approved_restart": "✅ <b>Одобрено</b> <code>{}</code>. Зависимости установлены, нужна перезагрузка",
        "denied": "❌ <b>Отклонено</b> <code>{}</code>. Эта версия не загрузится",
        "gone": "Запрос уже неактивен",
        "not_you": "Решать может только владелец аккаунта",
        "status": (
            "🛡 <b>BeSafe</b>\n\n<b>Одобрено:</b> {}\n<b>Отклонено:</b> {}\n<b>Ожидают:</b> {}\n"
            "<b>Доверенные источники:</b>\n{}\n\n"
            "<code>.besafe list</code> · <code>.besafe log</code> · <code>.bstrust</code> · "
            "<code>.bsuntrust</code> · <code>.bsforget</code>"
        ),
        "list_line": "• <code>{}</code> {} — <code>{}</code>",
        "list_approved": "<b>✅ Одобрено</b>",
        "list_denied": "<b>❌ Отклонено</b>",
        "log_line": "{} · {} · <code>{}</code> {}",
        "act_allow": "✅ разрешён",
        "act_deny": "❌ отклонён",
        "act_trusted": "🤝 доверенный источник",
        "act_bootstrap": "📦 уже был установлен",
        "act_forget": "🗑 решение отозвано",
        "forget_usage": "❔ <code>.bsforget &lt;начало хэша&gt;</code> — смотри <code>.besafe list</code>",
        "forgotten": "🗑 Решение отозвано: {}",
        "not_found": "❌ Такого хэша нет или он неоднозначен",
        "trust_usage": "❔ <code>.bstrust https://raw.githubusercontent.com/user/repo/</code>",
        "trusted": "🤝 Доверенный источник добавлен: <code>{}</code>",
        "untrusted": "🗑 Доверенный источник удалён: <code>{}</code>",
        "trust_missing": "❌ Такого источника нет в списке",
        "too_many": "BeSafe: слишком много ожидающих модулей, запрос {} пропущен",
    }

    def __init__(self):
        self.pending = {}
        self.bootstrap = False

    async def on_load(self, app: Client):
        if not self.db.get(self.name, "initialized", False):
            self.db.set(self.name, "initialized", True)
            self.bootstrap = True
            asyncio.get_event_loop().call_later(300, setattr, self, "bootstrap", False)
        if self.db.get(self.name, "trusted", None) is None:
            self.db.set(self.name, "trusted", DEFAULT_TRUSTED)
        self.all_modules.load_guard = self.guard
        self.pending = self.db.get(self.name, "pending", {})
        for digest in list(self.pending):
            try:
                await self._send_card(digest)
            except Exception:
                logging.exception("BeSafe could not resend card %s", digest[:16])

    def _get(self, key: str, default):
        return self.db.get(self.name, key, default)

    def _save_pending(self):
        self.db.set(self.name, "pending", self.pending)

    def _log(self, action: str, digest: str, name: str, origin: str):
        log = self._get("log", [])[-(LOG_LIMIT - 1) :]
        log.append(
            {"time": int(time.time()), "action": action, "digest": digest,
             "name": name, "origin": origin}
        )
        self.db.set(self.name, "log", log)

    def _record(self, key: str, digest: str, name: str, origin: str):
        data = self._get(key, {})
        data[digest] = {"name": name, "origin": origin, "time": int(time.time())}
        self.db.set(self.name, key, data)

    def _approve(self, digest: str, source: str, origin: str, name: str, action: str):
        self._record("approved", digest, name, origin)
        self._log(action, digest, name, origin)
        if origin and origin != "<string>":
            sources = self._get("sources", {})
            sources[origin] = source
            self.db.set(self.name, "sources", sources)

    def _trusted(self, origin: str) -> bool:
        return is_url(origin) and any(
            origin.startswith(prefix) for prefix in self._get("trusted", [])
        )

    def _is_local_file(self, origin: str) -> bool:
        modules_dir = os.path.abspath(self.all_modules._local_modules_path)
        return bool(origin) and os.path.isfile(origin) and os.path.abspath(
            origin
        ).startswith(modules_dir + os.sep)

    async def guard(self, source: str, origin: str):
        digest = hashlib.sha256(source.encode()).hexdigest()
        if digest in self._get("approved", {}):
            return True
        if digest in self._get("denied", {}):
            return "DENIED"
        info = summarize(source)
        if self._trusted(origin):
            self._approve(digest, source, origin, info["name"], "trusted")
            return True
        known = origin in self.db.get("shizu.loader", "modules", []) or self._is_local_file(origin)
        if self.bootstrap and known:
            self._approve(digest, source, origin, info["name"], "bootstrap")
            return True
        if digest not in self.pending:
            if len(self.pending) >= PENDING_LIMIT:
                logging.warning(self.strings("too_many").format(info["name"]))
                return "PENDING"
            self.pending[digest] = {"source": source, "origin": origin, **info}
            self._save_pending()
            await self._send_card(digest)
        return "PENDING"

    def _code_list(self, items) -> str:
        return ", ".join(f"<code>{utils.escape_html(i)}</code>" for i in items)

    async def _send_card(self, digest: str):
        item = self.pending[digest]
        previous = self._get("sources", {}).get(item["origin"])
        none = self.strings("none")
        imports = (
            self.strings("unparsable")
            if item["imports"] is None
            else self._code_list(item["imports"]) or none
        )
        text = self.strings("card").format(
            name=utils.escape_html(item["name"]),
            origin=utils.escape_html(item["origin"] if is_url(item["origin"]) or self._is_local_file(item["origin"]) else self.strings("file")),
            lines=item["lines"],
            digest=digest[:16],
            imports=imports,
            requires=self._code_list(item.get("requires", [])) or none,
            hosts=self._code_list(item["hosts"]) or none,
            changed=self.strings("changed") if previous else "",
        )
        def button(key, handler):
            return {"text": self.strings(key), "callback": functools.partial(handler, digest)}

        row = [button("btn_code", self._code)]
        if previous:
            row.append(button("btn_diff", self._diff))
        markup = self.bot._generate_markup(
            [[button("btn_allow", self._allow), button("btn_deny", self._deny)], row]
        )
        if old := item.get("card"):
            with contextlib.suppress(Exception):
                await self.bot.bot.delete_message(*old)
        sent = await self.bot.bot.send_message(
            self.db.get("shizu.chat", "logs", None) or self.me.id,
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
        item["card"] = [sent.chat.id, sent.message_id]
        self._save_pending()

    async def _owner_item(self, call: CallbackQuery, digest: str):
        if call.from_user.id != self.me.id:
            await call.answer(self.strings("not_you"), show_alert=True)
            return None
        if digest not in self.pending:
            await call.answer(self.strings("gone"), show_alert=True)
            return None
        return self.pending[digest]

    def _persist(self, name: str, source: str, origin: str):
        if is_url(origin):
            modules = self.db.get("shizu.loader", "modules", [])
            if origin not in modules:
                self.db.set("shizu.loader", "modules", modules + [origin])
        elif not self._is_local_file(origin):
            path = os.path.join(
                self.all_modules._local_modules_path, "_".join(name.lower().split()) + ".py"
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(source)

    async def _allow(self, digest: str, call: CallbackQuery):
        if not (item := await self._owner_item(call, digest)):
            return
        del self.pending[digest]
        self._save_pending()
        self._approve(digest, item["source"], item["origin"], item["name"], "allow")
        await call.answer()
        result = await self.all_modules.load_module(item["source"], item["origin"])
        name = utils.escape_html(item["name"])
        if result is True:
            text = self.strings("approved_restart").format(name)
        elif isinstance(result, str) and result not in ("NFA", "OTL", "PENDING", "DENIED"):
            self._persist(result, item["source"], item["origin"])
            text = self.strings("loaded").format(utils.escape_html(result))
        else:
            text = self.strings("approved_only").format(name, utils.escape_html(str(result)))
        await call.message.edit_text(text)

    async def _deny(self, digest: str, call: CallbackQuery):
        if not (item := await self._owner_item(call, digest)):
            return
        del self.pending[digest]
        self._save_pending()
        self._record("denied", digest, item["name"], item["origin"])
        self._log("deny", digest, item["name"], item["origin"])
        modules = self.db.get("shizu.loader", "modules", [])
        if item["origin"] in modules:
            self.db.set(
                "shizu.loader", "modules", [m for m in modules if m != item["origin"]]
            )
        await call.message.edit_text(
            self.strings("denied").format(utils.escape_html(item["name"]))
        )

    async def _send_file(self, call: CallbackQuery, data: str, filename: str):
        await call.answer()
        await self.bot.bot.send_document(
            call.message.chat.id,
            InputFile(io.BytesIO(data.encode()), filename=filename),
            reply_to_message_id=call.message.message_id,
        )

    async def _code(self, digest: str, call: CallbackQuery):
        if item := await self._owner_item(call, digest):
            await self._send_file(call, item["source"], f"{item['name']}.py")

    async def _diff(self, digest: str, call: CallbackQuery):
        if not (item := await self._owner_item(call, digest)):
            return
        previous = self._get("sources", {}).get(item["origin"], "")
        diff = "".join(
            difflib.unified_diff(
                previous.splitlines(keepends=True),
                item["source"].splitlines(keepends=True),
                "approved.py",
                "new.py",
            )
        )
        await self._send_file(call, diff, f"{item['name']}.diff")

    @staticmethod
    def _is_self(message: types.Message) -> bool:
        return bool(message.from_user and message.from_user.is_self)

    def _origin_label(self, origin: str) -> str:
        return utils.escape_html(origin if origin and origin != "<string>" else self.strings("file"))

    @loader.command()
    async def besafe(self, app: Client, message: types.Message):
        """[list | log] — BeSafe status, decisions list or journal"""
        if not self._is_self(message):
            return
        arg = (message.get_args_raw() or "").strip()
        approved, denied = self._get("approved", {}), self._get("denied", {})
        if arg == "list":
            parts = []
            for title, data in (("list_approved", approved), ("list_denied", denied)):
                if data:
                    parts.append(self.strings(title))
                    parts.extend(
                        self.strings("list_line").format(
                            d[:12], utils.escape_html(i["name"]), self._origin_label(i.get("origin"))
                        )
                        for d, i in data.items()
                    )
            return await message.answer("\n".join(parts) or self.strings("none"))
        if arg == "log":
            lines = [
                self.strings("log_line").format(
                    time.strftime("%d.%m %H:%M", time.localtime(e["time"])),
                    self.strings("act_" + e["action"]),
                    e["digest"][:12],
                    utils.escape_html(e["name"]),
                )
                for e in reversed(self._get("log", []))
            ]
            return await message.answer("\n".join(lines) or self.strings("none"))
        trusted = "\n".join(
            f"• <code>{utils.escape_html(p)}</code>" for p in self._get("trusted", [])
        )
        await message.answer(
            self.strings("status").format(
                len(approved), len(denied), len(self.pending), trusted or self.strings("none")
            )
        )

    @loader.command()
    async def bsforget(self, app: Client, message: types.Message):
        """<hash start> — revoke an approval or a denial"""
        if not self._is_self(message):
            return
        prefix = (message.get_args_raw() or "").strip().lower()
        if len(prefix) < 6:
            return await message.answer(self.strings("forget_usage"))
        for key in ("approved", "denied"):
            data = self._get(key, {})
            matches = [d for d in data if d.startswith(prefix)]
            if len(matches) == 1:
                item = data.pop(matches[0])
                self.db.set(self.name, key, data)
                self._log("forget", matches[0], item["name"], item.get("origin"))
                return await message.answer(
                    self.strings("forgotten").format(utils.escape_html(item["name"]))
                )
        await message.answer(self.strings("not_found"))

    @loader.command()
    async def bstrust(self, app: Client, message: types.Message):
        """<url prefix> — add a trusted source (modules from it load without approval)"""
        if not self._is_self(message):
            return
        url = (message.get_args_raw() or "").strip()
        if not url.startswith("https://") or not urlparse(url).hostname:
            return await message.answer(self.strings("trust_usage"))
        url = normalize_prefix(url)
        trusted = self._get("trusted", [])
        if url not in trusted:
            self.db.set(self.name, "trusted", trusted + [url])
        await message.answer(self.strings("trusted").format(utils.escape_html(url)))

    @loader.command()
    async def bsuntrust(self, app: Client, message: types.Message):
        """<url prefix> — remove a trusted source"""
        if not self._is_self(message):
            return
        url = normalize_prefix(message.get_args_raw() or "")
        trusted = self._get("trusted", [])
        if url not in trusted:
            return await message.answer(self.strings("trust_missing"))
        self.db.set(self.name, "trusted", [t for t in trusted if t != url])
        await message.answer(self.strings("untrusted").format(utils.escape_html(url)))
