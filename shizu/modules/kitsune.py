# -*- coding: utf-8 -*-

# █ █ █ █▄▀ ▄▀█ █▀▄▀█ █▀█ █▀█ █ █
# █▀█ █ █ █ █▀█ █ ▀ █ █▄█ █▀▄ █▄█

# 🔒 Licensed under the GNU GPLv3
# 🌐 https://www.gnu.org/licenses/agpl-3.0.html
# 👤 https://t.me/hikamor


import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import time
import zipfile
from datetime import datetime

from aiogram.types import InputFile
from pyrogram import Client, enums, filters, types
from pyrogram.handlers import DeletedMessagesHandler, EditedMessageHandler

from .. import loader, utils

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath("shizu/__kitsune__")
CACHE_FILE = os.path.join(BASE_DIR, "cache.json")
MEDIA_KINDS = (
    "photo",
    "video",
    "video_note",
    "voice",
    "audio",
    "animation",
    "document",
    "sticker",
)
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096


@loader.module("KitsuneSpy", "hikamoru", 2.0)
class KitsuneSpy(loader.Module):
    """Saves deleted and edited messages from private chats. Works only while the userbot is online"""

    strings = {
        "deleted": "🗑 <b>{user}</b> deleted a message\n🕔 <i>sent {time}</i>",
        "edited": "✏️ <b>{user}</b> edited a message\n🕔 <i>sent {time}</i>\n\n<b>Before:</b>\n{old}\n\n<b>After:</b>\n{new}",
        "content": "\n\n{}",
        "media_label": "📎 {}",
        "who_to_black_list": "<emoji id=5971793326599311892>❓</emoji> <b>Who do you want to add to the blacklist?</b> Reply, @username or ID",
        "who_to_unblack_list": "<emoji id=5971793326599311892>❓</emoji> <b>Who do you want to remove from the blacklist?</b> Reply, @username or ID",
        "user_added_to_blacklist": "<emoji id=5370990890095484658>👻</emoji> <b>{} added to the blacklist</b>",
        "user_removed_from_blacklist": "<emoji id=5190498248145515563>🫂</emoji> <b>{} removed from the blacklist</b>",
        "user_not_found": "<emoji id=5789837793018515028>⚠️</emoji> <b>User not found</b>",
        "blacklist": "🃏 <b>Blacklist:</b>\n\n{}",
        "blacklist_empty": "🃏 <b>Blacklist is empty</b>",
        "kitsune_enabled": "<emoji id=5204139459414597710>🕵️‍♀️</emoji> <b>Message tracking enabled</b>",
        "kitsune_disabled": "<emoji id=5204139459414597710>🕵️‍♀️</emoji> <b>Message tracking disabled</b>",
        "cache_cleared": "<emoji id=5870977305857232786>🧹</emoji> <b>Cache cleared</b>",
        "cache_info": "🗃 <b>Saved messages:</b> {}\n🗑 <b>Deleted:</b> {}\n✏️ <b>Edited:</b> {}\n💾 <b>Media:</b> {}\n⏳ <b>Kept for:</b> {}",
        "forever": "forever",
        "export_empty": "📭 <b>Nothing to export</b>",
        "export_building": "📦 <b>Building the archive: {} messages...</b>",
        "export_done": "🦊 KitsuneSpy export · {} messages · {}",
        "cfg_persist": "Keep the cache in a file so it survives restarts. It is stored in shizu/__kitsune__, not in the main database",
        "cfg_media_types": "Media types to save: " + ", ".join(MEDIA_KINDS),
        "cfg_ttl": "How many hours to keep messages (0 = forever)",
        "cfg_max_messages": "Maximum number of saved messages (0 = no limit)",
        "cfg_max_media_mb": "Do not save media larger than this size in MB (0 = no limit)",
        "cfg_track_edits": "Notify about edited messages",
    }

    strings_ru = {
        "deleted": "🗑 <b>{user}</b> удалил(а) сообщение\n🕔 <i>отправлено {time}</i>",
        "edited": "✏️ <b>{user}</b> изменил(а) сообщение\n🕔 <i>отправлено {time}</i>\n\n<b>Было:</b>\n{old}\n\n<b>Стало:</b>\n{new}",
        "who_to_black_list": "<emoji id=5971793326599311892>❓</emoji> <b>Кого добавить в чёрный список?</b> Ответ, @username или ID",
        "who_to_unblack_list": "<emoji id=5971793326599311892>❓</emoji> <b>Кого убрать из чёрного списка?</b> Ответ, @username или ID",
        "user_added_to_blacklist": "<emoji id=5370990890095484658>👻</emoji> <b>{} добавлен(а) в чёрный список</b>",
        "user_removed_from_blacklist": "<emoji id=5190498248145515563>🫂</emoji> <b>{} убран(а) из чёрного списка</b>",
        "user_not_found": "<emoji id=5789837793018515028>⚠️</emoji> <b>Пользователь не найден</b>",
        "blacklist": "🃏 <b>Чёрный список:</b>\n\n{}",
        "blacklist_empty": "🃏 <b>Чёрный список пуст</b>",
        "kitsune_enabled": "<emoji id=5204139459414597710>🕵️‍♀️</emoji> <b>Отслеживание сообщений включено</b>",
        "kitsune_disabled": "<emoji id=5204139459414597710>🕵️‍♀️</emoji> <b>Отслеживание сообщений выключено</b>",
        "cache_cleared": "<emoji id=5870977305857232786>🧹</emoji> <b>Кэш очищен</b>",
        "cache_info": "🗃 <b>Сохранено сообщений:</b> {}\n🗑 <b>Удалённых:</b> {}\n✏️ <b>Изменённых:</b> {}\n💾 <b>Медиа:</b> {}\n⏳ <b>Хранятся:</b> {}",
        "forever": "бессрочно",
        "export_empty": "📭 <b>Нечего экспортировать</b>",
        "export_building": "📦 <b>Собираю архив: {} сообщений...</b>",
        "export_done": "🦊 Экспорт KitsuneSpy · {} сообщений · {}",
        "cfg_persist": "Хранить кэш в файле, чтобы он переживал перезапуск. Лежит в shizu/__kitsune__, не в основной БД",
        "cfg_media_types": "Какие медиа сохранять: " + ", ".join(MEDIA_KINDS),
        "cfg_ttl": "Сколько часов хранить сообщения (0 = бессрочно)",
        "cfg_max_messages": "Максимум сохранённых сообщений (0 = без лимита)",
        "cfg_max_media_mb": "Не сохранять медиа больше этого размера в МБ (0 = без лимита)",
        "cfg_track_edits": "Уведомлять об изменённых сообщениях",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            "persist",
            True,
            lambda m: self.strings("cfg_persist"),
            "media_types",
            ["photo", "video_note", "video", "voice", "audio", "sticker"],
            lambda m: self.strings("cfg_media_types"),
            "ttl_hours",
            0,
            lambda m: self.strings("cfg_ttl"),
            "max_messages",
            0,
            lambda m: self.strings("cfg_max_messages"),
            "max_media_mb",
            0,
            lambda m: self.strings("cfg_max_media_mb"),
            "track_edits",
            True,
            lambda m: self.strings("cfg_track_edits"),
        )
        self.cache = {}
        self._save_task = None

    async def on_load(self, app: Client):
        os.makedirs(BASE_DIR, exist_ok=True)
        with contextlib.suppress(Exception):
            os.chmod(BASE_DIR, 0o700)
        if self.db.get("KitsuneSpy", "messages") is not None:
            self.db.pop("KitsuneSpy", "messages")
        if self.config["persist"]:
            with contextlib.suppress(FileNotFoundError, ValueError):
                with open(CACHE_FILE, encoding="utf-8") as f:
                    self.cache = json.load(f)
        self._prune()

        app.add_handler(DeletedMessagesHandler(self._on_deleted), group=66)
        app.add_handler(
            EditedMessageHandler(self._on_edited, filters.private & filters.incoming),
            group=89,
        )

    def _enabled(self) -> bool:
        return self.db.get("KitsuneSpy", "enabled", False)

    def _blacklist(self) -> list:
        return self.db.get("KitsuneSpy", "blacklist", [])

    def _schedule_save(self):
        if not self.config["persist"] or (self._save_task and not self._save_task.done()):
            return

        async def save_later():
            await asyncio.sleep(5)
            tmp = CACHE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False)
            os.replace(tmp, CACHE_FILE)
            with contextlib.suppress(Exception):
                os.chmod(CACHE_FILE, 0o600)

        self._save_task = asyncio.ensure_future(save_later())

    def _drop(self, key: str):
        entry = self.cache.pop(key, None)
        if entry and entry.get("media_dir"):
            shutil.rmtree(entry["media_dir"], ignore_errors=True)

    def _prune(self):
        ttl = float(self.config["ttl_hours"] or 0)
        if ttl > 0:
            deadline = time.time() - ttl * 3600
            for key in [k for k, v in self.cache.items() if v.get("ts", 0) < deadline]:
                self._drop(key)
        limit = int(self.config["max_messages"] or 0)
        overflow = len(self.cache) - limit if limit > 0 else 0
        if overflow > 0:
            for key in sorted(self.cache, key=lambda k: self.cache[k].get("ts", 0))[:overflow]:
                self._drop(key)
        self._schedule_save()

    @staticmethod
    def _user_link(user: types.User) -> str:
        name = " ".join(filter(None, [user.first_name, user.last_name])) or str(user.id)
        return f"<a href='tg://user?id={user.id}'>{utils.escape_html(name)}</a>"

    @staticmethod
    def _html(message: types.Message) -> str:
        text = message.text or message.caption
        return text.html if text else ""

    @staticmethod
    def _fmt_time(ts: float) -> str:
        return time.strftime("%d.%m.%Y %H:%M", time.localtime(ts))

    def _media_kind(self, message: types.Message):
        for kind in MEDIA_KINDS:
            if getattr(message, kind, None) and kind in self.config["media_types"]:
                return kind, getattr(message, kind)
        return None, None

    async def watcher_message(self, app: Client, message: types.Message):
        if (
            not self._enabled()
            or not message.from_user
            or message.outgoing
            or message.from_user.is_self
            or message.from_user.is_bot
            or message.chat.type != enums.ChatType.PRIVATE
            or message.via_bot
            or message.from_user.id in self._blacklist()
        ):
            return

        user = message.from_user
        entry = {
            "user": self._user_link(user),
            "user_id": user.id,
            "user_name": " ".join(filter(None, [user.first_name, user.last_name])),
            "username": user.username,
            "text": self._html(message),
            "ts": time.time(),
        }

        kind, media = self._media_kind(message)
        size = getattr(media, "file_size", 0) or 0
        limit_mb = int(self.config["max_media_mb"] or 0)
        if kind and (limit_mb <= 0 or size <= limit_mb * 1024 * 1024):
            media_dir = os.path.join(BASE_DIR, str(message.id))
            try:
                path = await message.download(file_name=media_dir + os.sep)
            except Exception:
                logger.exception("KitsuneSpy could not download media")
                shutil.rmtree(media_dir, ignore_errors=True)
            else:
                entry.update({"kind": kind, "path": path, "media_dir": media_dir})
        elif kind:
            entry["kind_skipped"] = kind

        if not entry["text"] and "path" not in entry and "kind_skipped" not in entry:
            return

        self.cache[str(message.id)] = entry
        self._prune()

    async def _on_deleted(self, app: Client, messages: list):
        if not self._enabled():
            return
        for message in messages:
            if message.chat and message.chat.type in (
                enums.ChatType.CHANNEL,
                enums.ChatType.SUPERGROUP,
            ):
                continue
            entry = self.cache.get(str(message.id))
            if not entry or entry.get("deleted_at"):
                continue
            entry["deleted_at"] = time.time()
            try:
                await self._notify_deleted(entry)
            except Exception:
                logger.exception("KitsuneSpy could not send deleted message")
        self._schedule_save()

    async def _notify_deleted(self, entry: dict):
        head = self.strings("deleted").format(user=entry["user"], time=self._fmt_time(entry["ts"]))
        if skipped := entry.get("kind_skipped"):
            head += "\n" + self.strings("media_label").format(skipped)
        body = self.strings("content").format(entry["text"]) if entry["text"] else ""
        bot = self.bot.bot

        path = entry.get("path")
        if path and os.path.isfile(path):
            kind = entry["kind"]
            caption = head + body
            if len(caption) > CAPTION_LIMIT or kind in ("sticker", "video_note"):
                await bot.send_message(self.tg_id, (head + body)[:TEXT_LIMIT])
                caption = None
            send = getattr(bot, f"send_{kind}")
            kwargs = {kind: InputFile(path)}
            if caption:
                kwargs["caption"] = caption
            await send(self.tg_id, **kwargs)
            return

        await bot.send_message(self.tg_id, (head + body)[:TEXT_LIMIT])

    async def _on_edited(self, app: Client, message: types.Message):
        if not self._enabled() or not self.config["track_edits"]:
            return
        entry = self.cache.get(str(message.id))
        new = self._html(message)
        if not entry or new == entry["text"]:
            return
        await self.bot.bot.send_message(
            self.tg_id,
            self.strings("edited").format(
                user=entry["user"],
                time=self._fmt_time(entry["ts"]),
                old=entry["text"] or "—",
                new=new or "—",
            )[:TEXT_LIMIT],
        )
        entry.setdefault("edits", []).append({"ts": time.time(), "text": entry["text"]})
        entry["text"] = new
        self._schedule_save()

    async def _resolve_user(self, app: Client, message: types.Message):
        reply = message.reply_to_message
        if reply and reply.from_user:
            return reply.from_user
        args = utils.get_args(message)
        if not args:
            return None
        try:
            return await app.get_users(int(args) if args.lstrip("-").isdigit() else args)
        except Exception:
            return None

    @loader.command()
    async def kitsune(self, app: Client, message: types.Message):
        """Enable/disable message tracking"""
        enabled = not self._enabled()
        self.db.set("KitsuneSpy", "enabled", enabled)
        await utils.answer(
            message, self.strings("kitsune_enabled" if enabled else "kitsune_disabled")
        )

    @loader.command()
    async def kclear(self, app: Client, message: types.Message):
        """Clear the cache of saved messages and media"""
        for key in list(self.cache):
            self._drop(key)
        for name in os.listdir(BASE_DIR):
            path = os.path.join(BASE_DIR, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif path != CACHE_FILE:
                os.remove(path)
        self._schedule_save()
        await utils.answer(message, self.strings("cache_cleared"))

    @loader.command()
    async def kcache(self, app: Client, message: types.Message):
        """Show cache size"""
        media = sum(1 for e in self.cache.values() if e.get("path"))
        deleted = sum(1 for e in self.cache.values() if e.get("deleted_at"))
        edited = sum(1 for e in self.cache.values() if e.get("edits"))
        ttl = self.config["ttl_hours"] or 0
        await utils.answer(
            message,
            self.strings("cache_info").format(
                len(self.cache), deleted, edited, media,
                ttl if ttl > 0 else self.strings("forever"),
            ),
        )

    def _matches(self, entry: dict, mode: str, user) -> bool:
        if user is not None and entry.get("user_id") != user.id and f"id={user.id}'" not in entry["user"]:
            return False
        if mode == "deleted":
            return bool(entry.get("deleted_at"))
        if mode == "edited":
            return bool(entry.get("edits"))
        return True

    @staticmethod
    def _plain(html: str) -> str:
        return re.sub(r"<[^>]+>", "", html or "").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")

    @staticmethod
    def _iso(ts):
        return datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else None

    def _export_record(self, key: str, entry: dict, media_name) -> dict:
        iso = self._iso
        return {
            "message_id": int(key),
            "user_id": entry.get("user_id"),
            "user_name": entry.get("user_name") or self._plain(entry["user"]),
            "username": entry.get("username"),
            "sent_at": iso(entry.get("ts")),
            "deleted_at": iso(entry.get("deleted_at")),
            "text": self._plain(entry.get("text")),
            "text_html": entry.get("text"),
            "edits": [{"at": iso(e["ts"]), "text_before": self._plain(e["text"])} for e in entry.get("edits", [])],
            "media_type": entry.get("kind") or entry.get("kind_skipped"),
            "media_file": media_name,
        }

    @loader.command()
    async def kexport(self, app: Client, message: types.Message):
        """[all | deleted | edited] [reply | @username | ID] — export saved messages to a zip archive in Saved Messages"""
        args = utils.get_args(message).split()
        mode = args.pop(0) if args and args[0] in ("all", "deleted", "edited") else "all"
        user = None
        if message.reply_to_message or args:
            user = await self._resolve_user(app, message) if not args else None
            if args:
                try:
                    user = await app.get_users(int(args[0]) if args[0].lstrip("-").isdigit() else args[0])
                except Exception:
                    user = None
            if not user:
                return await utils.answer(message, self.strings("user_not_found"))

        items = sorted(
            ((k, e) for k, e in self.cache.items() if self._matches(e, mode, user)),
            key=lambda item: item[1].get("ts", 0),
        )
        if not items:
            return await utils.answer(message, self.strings("export_empty"))

        await utils.answer(message, self.strings("export_building").format(len(items)))
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        archive = os.path.join(BASE_DIR, f"kitsune_{mode}_{stamp}.zip")
        records, lines = [], []
        try:
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
                for key, entry in items:
                    media_name = None
                    path = entry.get("path")
                    if path and os.path.isfile(path):
                        media_name = f"media/{key}_{os.path.basename(path)}"
                        zf.write(path, media_name)
                    record = self._export_record(key, entry, media_name)
                    records.append(record)
                    lines.append(self._export_line(record))
                zf.writestr("messages.json", json.dumps(records, ensure_ascii=False, indent=2))
                zf.writestr("messages.txt", "\n\n".join(lines))
            await app.send_document(
                "me",
                archive,
                caption=self.strings("export_done").format(len(records), mode),
            )
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.remove(archive)
        with contextlib.suppress(Exception):
            await message.delete()

    @staticmethod
    def _export_line(r: dict) -> str:
        who = r["user_name"] + (f" (@{r['username']})" if r["username"] else "") + f" [{r['user_id']}]"
        out = [f"#{r['message_id']} · {r['sent_at']} · {who}"]
        if r["deleted_at"]:
            out.append(f"deleted: {r['deleted_at']}")
        for e in r["edits"]:
            out.append(f"before edit {e['at']}: {e['text_before']}")
        if r["media_type"]:
            out.append(f"media: {r['media_type']}" + (f" -> {r['media_file']}" if r["media_file"] else ""))
        if r["text"]:
            out.append(r["text"])
        return "\n".join(out)

    @loader.command()
    async def kblackadd(self, app: Client, message: types.Message):
        """<reply | @username | ID> — do not save messages from this user"""
        await self._blacklist_change(app, message, add=True)

    @loader.command()
    async def kblackdel(self, app: Client, message: types.Message):
        """<reply | @username | ID> — remove a user from the blacklist"""
        await self._blacklist_change(app, message, add=False)

    async def _blacklist_change(self, app: Client, message: types.Message, add: bool):
        if not message.reply_to_message and not utils.get_args(message):
            return await utils.answer(
                message, self.strings("who_to_black_list" if add else "who_to_unblack_list")
            )
        user = await self._resolve_user(app, message)
        if not user:
            return await utils.answer(message, self.strings("user_not_found"))
        blacklist = set(self._blacklist())
        if add:
            blacklist.add(user.id)
            for key in [k for k, v in self.cache.items() if v.get("user_id") == user.id or f"id={user.id}'" in v["user"]]:
                self._drop(key)
            self._schedule_save()
        else:
            blacklist.discard(user.id)
        self.db.set("KitsuneSpy", "blacklist", list(blacklist))
        key = "user_added_to_blacklist" if add else "user_removed_from_blacklist"
        await utils.answer(message, self.strings(key).format(self._user_link(user)))

    @loader.command()
    async def kblacklist(self, app: Client, message: types.Message):
        """Show the blacklist"""
        ids = self._blacklist()
        if not ids:
            return await utils.answer(message, self.strings("blacklist_empty"))
        lines = []
        for user_id in ids:
            try:
                lines.append("• " + self._user_link(await app.get_users(user_id)))
            except Exception:
                lines.append(f"• <code>{user_id}</code>")
        await utils.answer(message, self.strings("blacklist").format("\n".join(lines)))
