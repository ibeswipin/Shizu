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
import asyncio
import traceback
import os
import typing
import io
import contextlib
import json
import html
import re
import time

from datetime import datetime

from typing import Union
from aiogram import Bot, Dispatcher
from aiogram.utils.exceptions import MessageNotModified, NetworkError, RetryAfter
from loguru._better_exceptions import ExceptionFormatter
from loguru._colorizer import Colorizer
from loguru import logger
from logging.handlers import RotatingFileHandler

from aiogram.types import ParseMode

from shizu.database import db
from shizu import utils

FORMAT_FOR_FILES = "[{level}] {name}: {message}"

FORMAT_FOR_TGLOG = logging.Formatter(
    fmt="[%(levelname)s] %(name)s: %(message)s",
    datefmt=None,
    style="%",
)

with contextlib.suppress(Exception):  # will be simplified in the future
    bot = Bot(token=db.get("shizu.bot", "token", None), parse_mode="html")
    dp = Dispatcher(bot)


def get_valid_level(level: Union[str, int]):
    return int(level) if level.isdigit() else getattr(logging, level.upper(), None)


class CustomException:
    def __init__(
        self,
        message: str,
        local_vars: str,
        full_stack: str,
        sysinfo: typing.Optional[
            typing.Tuple[object, Exception, traceback.TracebackException]
        ] = None,
    ):
        self.message = message
        self.local_vars = local_vars
        self.full_stack = full_stack
        self.sysinfo = sysinfo
        self.debug_url = None

    @classmethod
    def from_exc_info(
        cls, exc_type: object, exc_value: Exception, tb: traceback.TracebackException
    ) -> "CustomException":
        def to_hashable(dictionary: dict) -> dict:
            dictionary = dictionary.copy()
            for key, value in dictionary.items():
                if isinstance(value, dict):
                    dictionary[key] = to_hashable(value)
                else:
                    try:
                        if (
                            getattr(getattr(value, "__class__", None), "__name__", None)
                            == "Database"
                        ):
                            dictionary[key] = "<Database>"
                        elif len(str(value)) > 512:
                            dictionary[key] = f"{str(value)[:512]}..."
                        else:
                            dictionary[key] = str(value)
                    except Exception:
                        dictionary[key] = f"<{value.__class__.__name__}>"

            return dictionary

        full_stack = "".join(traceback.format_exception(exc_type, exc_value, tb)).replace(
            "Traceback (most recent call last):\n", ""
        )

        # part HIkka: https://github.com/hikariatama/Hikka/blob/ce1f24f03313f8500de671815dde065fc8d86897/hikka/log.py#L76

        line_regex = r'  File "(.*?)", line ([0-9]+), in (.+)'

        def format_line(line: str) -> str:
            filename_, lineno_, name_ = re.search(line_regex, line).groups()
            with contextlib.suppress(Exception):
                filename_ = os.path.basename(filename_)

            return (
                f"➤ <code>{html.escape(filename_)}:{lineno_}</code> <b>in</b>"
                f" <code>{html.escape(name_)}</code>"
            )

        filename, lineno, name = next(
            (
                re.search(line_regex, line).groups()
                for line in reversed(full_stack.splitlines())
                if re.search(line_regex, line)
            ),
            (None, None, None),
        )

        full_stack = "\n".join(
            [
                (
                    format_line(line)
                    if re.search(line_regex, line)
                    else f"<code>{html.escape(line)}</code>"
                )
                for line in full_stack.splitlines()
            ]
        )

        with contextlib.suppress(Exception):
            filename = os.path.basename(filename)

        return CustomException(
            message=(
                f"<b>🌎 Where:</b> <code>{html.escape(filename)}:{lineno}</code> <b>in </b><code>{html.escape(name)}</code>\n"
                f"<b>⏳ When:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                f"<b>🤔 What:</b> <code>{html.escape(''.join(traceback.format_exception_only(exc_type, exc_value)).strip())}</code>"
            ),
            local_vars=(
                f"<code>{html.escape(json.dumps(to_hashable(tb.tb_frame.f_locals), indent=4))}</code>"
            ),
            full_stack=full_stack,
            sysinfo=(exc_type, exc_value, tb),
        )


class StreamHandler(logging.Handler):
    """Handler for logging to stream (console)"""

    def __init__(self, lvl: int = logging.INFO):
        super().__init__(lvl)

    def format(self, record: logging.LogRecord):
        """Форматирует логи под нужный формат"""
        exception_lines = ""
        stripped_formatter = Colorizer.prepare_format(
            FORMAT_FOR_FILES + "{exception}"
        ).strip()

        if record.exc_info:
            exception_formatter = ExceptionFormatter(
                encoding="utf-8",
                backtrace=True,
                prefix="\n",
                hidden_frames_filename=logger.catch.__code__.co_filename,
            )

            type_, value, tb = record.exc_info
            exception_list = exception_formatter.format_exception(type_, value, tb)
            exception_lines = "".join(exception_list)

        return stripped_formatter.format(
            level=record.levelname,
            name=record.name,
            function=record.funcName,
            message=record.msg,
            exception=exception_lines,
        )


class MemoryHandler(logging.Handler):
    """Memory Logging handler"""

    def __init__(self, lvl: int = logging.INFO):
        super().__init__(0)
        self.target = StreamHandler(lvl)
        self.lvl = lvl

        self.capacity = 500
        self.buffer = []
        self.handled_buffer = []

    def dumps(self, lvl: int):
        """Returns a list of all incoming logs by minimum level"""
        sorted_logs = list(
            filter(lambda record: record.levelno >= lvl, self.handled_buffer)
        )
        self.handled_buffer = list(set(self.handled_buffer) ^ set(sorted_logs))
        return map(self.target.format, sorted_logs)

    def emit(self, record: logging.LogRecord):
        """Emit a log record"""
        if len(self.buffer + self.handled_buffer) >= self.capacity:
            if self.handled_buffer:
                del self.handled_buffer[0]
            else:
                del self.buffer[0]

        self.buffer.append(record)
        if record.levelno >= self.lvl >= 0:
            self.acquire()
            try:
                self.dop_log(record)
            finally:
                self.release()

    def dop_log(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

        self.handled_buffer = (
            self.handled_buffer[-(self.capacity - len(self.buffer)) :] + self.buffer
        )
        self.buffer = []


class Telegramhandler(logging.Handler):
    """Logging handler for telegram"""

    def __init__(self, lvl: int = logging.INFO):
        super().__init__(lvl)
        self.target = StreamHandler(lvl)
        self.lvl = lvl
        self.capacity = 500
        self.buffer = []
        self.handled_buffer = []
        self.msgs = []
        self.chat = db.get("shizu.chat", "logs")
        self.last_log_time = None
        self.time_threshold = 1
        self.manager = None
        self._uids = []

    def dumps(self, lvl: int):
        """Returns a list of all incoming logs by minimum level"""
        sorted_logs = list(
            filter(lambda record: record.levelno >= lvl, self.handled_buffer)
        )
        self.handled_buffer = list(set(self.handled_buffer) ^ set(sorted_logs))
        return map(self.target.format, sorted_logs)

    def emit(self, record: logging.LogRecord):
        current_time = time.time()

        if self.last_log_time is None:
            self.last_log_time = current_time

        item = None
        if record.exc_info and record.exc_info[1]:
            with contextlib.suppress(Exception):
                item = CustomException.from_exc_info(*record.exc_info)
                head = utils.escape_html(record.getMessage()[:300])
                item.message = f"<b>⛔ {head}</b>\n\n{item.message}"

        self.msgs.append(item or FORMAT_FOR_TGLOG.format(record))

        if (
            current_time - self.last_log_time >= self.time_threshold
            and self.msgs
            and self.chat
        ):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return

            asyncio.ensure_future(self.send_logs(self.msgs))
            self.msgs = []

            self.last_log_time = current_time

    @staticmethod
    def _pages(lines: typing.List[str], limit: int = 3500) -> typing.List[str]:
        pages, page = [], ""
        for line in lines:
            while len(line) > limit:
                pages += [page] if page else []
                pages.append(line[:limit])
                page, line = "", line[limit:]
            if len(page) + len(line) + 1 > limit:
                pages.append(page)
                page = ""
            page += line + "\n"
        return [p for p in pages + [page] if p.strip()]

    def _form(self) -> str:
        uid = utils.rand(30)
        self.manager._forms[uid] = {
            "type": "form",
            "text": "",
            "buttons": [],
            "force_me": True,
            "always_allow": [],
            "chat": None,
            "message_id": None,
            "uid": uid,
        }
        self._uids.append(uid)
        if len(self._uids) > 100:
            self.manager._forms.pop(self._uids.pop(0), None)
        return uid

    async def _send(self, text: str, make_buttons: typing.Callable[[str], list]):
        markup = None
        if self.manager:
            uid = self._form()
            self.manager._forms[uid].update(text=text, buttons=make_buttons(uid))
            markup = self.manager._generate_markup(uid)
        await bot.send_message(
            self.chat,
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            disable_notification=True,
            reply_markup=markup,
        )

    async def _edit(self, call, uid: str, text: str, buttons: list):
        form = self.manager._forms.get(uid)
        if not form:
            return await call.answer("⌛️ Expired")
        form.update(text=text, buttons=buttons)
        try:
            await call.message.edit_text(
                text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=self.manager._generate_markup(uid),
            )
        except MessageNotModified:
            await call.answer()

    def _page_buttons(self, uid: str, pages: list, i: int, exc=None) -> list:
        rows = self.manager.build_pagination(
            self._show, len(pages), current_page=i + 1, args=(uid, pages, exc)
        )
        if exc:
            rows.append([{"text": "⬅️ Back", "callback": self._short, "args": (uid, exc)}])
        return rows

    def _trace_button(self, uid: str, exc: CustomException) -> list:
        return [[{"text": "🪐 Full traceback", "callback": self._trace, "args": (uid, exc)}]]

    async def _show(self, call, uid: str, pages: list, exc, i: int):
        await self._edit(call, uid, pages[i], self._page_buttons(uid, pages, i, exc))

    async def _short(self, call, uid: str, exc: CustomException):
        await self._edit(call, uid, exc.message, self._trace_button(uid, exc))

    async def _trace(self, call, uid: str, exc: CustomException):
        text = exc.message + "\n\n<b>🪐 Full traceback:</b>\n" + exc.full_stack
        await self._show(call, uid, self._pages(text.splitlines()), exc, 0)

    async def send_logs(self, msgs):
        """Send logs to chat"""
        stamp = f"\n<b>⏳ Logged time:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>"
        lines = [m for m in msgs if isinstance(m, str)]
        pages = [
            f"<code>{utils.escape_html(p.strip())}</code>\n{stamp}"
            for p in self._pages("\n".join(lines).splitlines(), 3000)
        ]

        try:
            for exc in (m for m in msgs if isinstance(m, CustomException)):
                await self._send(exc.message, lambda uid: self._trace_button(uid, exc))

            if not pages:
                return

            if len(pages) > 1 and not self.manager:
                logs = io.BytesIO("\n".join(lines).encode("utf-8"))
                logs.name = "logs.txt"
                await bot.send_document(
                    self.chat,
                    document=logs,
                    caption="💾 <b>The message was too long, thus i send it as document</b>",
                    parse_mode="HTML",
                )
                return

            await self._send(pages[0], lambda uid: self._page_buttons(uid, pages, 0))
        except RetryAfter as e:
            self.last_log_time = time.time() + e.timeout
        except Exception:
            pass


def override_text(exception: Exception) -> typing.Optional[str]:
    """Returns error-specific description if available, else `None`"""
    if isinstance(exception, NetworkError):
        return "✈️ <b>You have problems with internet connection on your server.</b>"

    return None



def setup_logger(level: Union[str, int], log_file_path: str = "shizu.log"):
    """Setup logger"""

    level = get_valid_level(level) or 20

    handler = MemoryHandler(level)

    tg = Telegramhandler(level)

    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=5 * 1024 * 1024, backupCount=5
    )

    file_handler.setFormatter(
        logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    )

    logging.getLogger().addHandler(file_handler)
    logging.getLogger().addHandler(tg)

    logging.basicConfig(handlers=[handler, tg], level=level, force=True)

    # Suppress specific Pyrogram warnings
    class PyrogramFilter(logging.Filter):
        def filter(self, record):
            # Suppress "Server resent the older message" warnings
            if "Server resent the older message" in record.getMessage():
                return False
            return True
    
    pyrogram_logger = logging.getLogger("pyrogram")
    pyrogram_logger.setLevel(logging.CRITICAL)
    pyrogram_logger.addFilter(PyrogramFilter())
    
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
