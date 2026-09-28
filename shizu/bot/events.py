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

"""
    █ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
    █▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

    Copyright 2022 t.me/hikariatama
    Licensed under the GNU GPLv3
"""

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

import html
import json
import re
import time
import sys
import inspect

import logging
import traceback
import asyncio
import functools
import contextlib
import aiogram
import pyrogram

from aiogram.types import (
    CallbackQuery,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQueryResultPhoto,
    InlineQueryResultVideo,
    InlineQueryResultAudio,
    InlineQueryResultGif,
)
from typing import Union, List, Any, Optional

from shizu import utils, logger as lo
from shizu.security import EVERYONE, mask_of
from shizu.bot.types import Item
from shizu import database
from shizu.translator import Translator

logger = logging.getLogger(__name__)


def array_sum(array: list) -> Any:
    """Performs basic sum operation on array"""

    result = []
    for item in array:
        result += item

    return result


async def delete(self: Any = None, form: Any = None, form_uid: Any = None) -> bool:
    """
    Params `self`, `form`, `form_uid` are
    for internal use only, do not try to pass them
    """
    try:
        await self._app.delete_messages(
            self._forms[form_uid]["chat"], self._forms[form_uid]["message_id"]
        )

        del self._forms[form_uid]

    except Exception:
        return False

    return True


async def edit(
    text: str,
    reply_markup: List[List[dict]] = None,
    force_me: Union[bool, None] = True,
    always_allow: Union[List[int], None] = None,
    self: Any = None,
    query: Any = None,
    form: Any = None,
    form_uid: Any = None,
    inline_message_id: Union[str, None] = None,
    disable_web_page_preview: bool = True,
) -> None:
    """
    Do not edit or pass `self`, `query`, `form`, `form_uid`
    params, they are for internal use only
    """
    if reply_markup:
        if isinstance(reply_markup, dict):
            reply_markup = [[reply_markup]]
        if isinstance(reply_markup[0], dict):
            reply_markup = [[_] for _ in reply_markup]
    if reply_markup is None:
        reply_markup = []

    if not isinstance(text, str):
        logger.error("Invalid type for `text`")
        return False

    if form:
        if isinstance(reply_markup, list):
            form["buttons"] = reply_markup
        if isinstance(force_me, bool):
            form["force_me"] = force_me
        if isinstance(always_allow, list):
            form["always_allow"] = always_allow

    try:
        await self.bot.edit_message_text(
            text,
            inline_message_id=inline_message_id or query.inline_message_id,
            parse_mode="HTML",
            disable_web_page_preview=disable_web_page_preview,
            reply_markup=self._generate_markup(reply_markup),
        )
    except aiogram.utils.exceptions.MessageNotModified:
        with contextlib.suppress(aiogram.utils.exceptions.InvalidQueryID):
            await query.answer()
    except aiogram.utils.exceptions.RetryAfter as e:
        logger.info(f"Sleeping {e.timeout}s on aiogram FloodWait...")
        await asyncio.sleep(e.timeout)
        return await edit(
            text,
            reply_markup,
            force_me,
            always_allow,
            self,
            query,
            form,
            form_uid,
            inline_message_id,
        )
    except aiogram.utils.exceptions.MessageIdInvalid:
        with contextlib.suppress(aiogram.utils.exceptions.InvalidQueryID):
            await query.answer(
                "Couldn't edit the message because it was deleted :("
            )


async def answer(
    text: str = None,
    app: Any = None,
    message: Message = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
    **kwargs,
) -> bool:
    try:
        await app.bot.send_message(
            message.chat.id,
            text,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            **kwargs,
        )
    except Exception:
        return False

    return True


class InlineCall(CallbackQuery):
    def __init__(self):
        super().__init__()
        self.delete = None
        self.unload = None
        self.edit = functools.partial(edit, self=self)
        self.delete = functools.partial(delete, self=self)
    


class Events(Item):
    """Events handler for inline forms and lists"""

    def __init__(self):
        self._forms = {}
        self._custom_map = {}
        self._states = {}
        self._me = database.db.get("shizu.me", "me")

    def ss(self, user_id: int, state) -> None:
        """Set a custom state for a user talking to the bot; False clears it"""
        if state is False or state is None:
            self._states.pop(user_id, None)
        else:
            self._states[user_id] = state

    def gs(self, user_id: int):
        """Custom state of a user talking to the bot, False when unset"""
        return self._states.get(user_id, False)

    @staticmethod
    def sanitise_text(text: str) -> str:
        """Make userbot HTML safe for the Bot API: custom emoji tags become plain emoji"""
        text = re.sub(r"<emoji[^>]*>(.*?)</emoji>", r"\1", str(text or ""), flags=re.S)
        return re.sub(r"</?tg-emoji[^>]*>", "", text)

    async def query_gallery(self, query: InlineQuery, items: list) -> bool:
        """Answer an inline query with a list of photos
        (dicts with `photo_url`/`photo`, `title`, `description`, `caption`)"""
        results = [
            {
                "photo": item.get("photo_url") or item.get("photo"),
                "thumb": item.get("thumb_url") or item.get("thumb"),
                "title": item.get("title"),
                "description": item.get("description"),
                "caption": item.get("caption"),
                "reply_markup": item.get("reply_markup"),
            }
            for item in items
            if item.get("photo_url") or item.get("photo")
        ]
        if not results:
            return False
        await self._answer_results(query, results)
        return True

    def generate_markup(self, markup) -> InlineKeyboardMarkup:
        """Build an inline keyboard from button dicts"""
        if isinstance(markup, dict):
            markup = [[markup]]
        elif markup and isinstance(markup[0], dict):
            markup = [markup]
        return self._generate_markup(markup or [])

    async def _message_handler(self, message: Message) -> Message:
        setattr(message, "answer", functools.partial(answer, app=self, message=message))

        for func in self._all_modules.message_handlers.values():
            if not await self._check_filters(func, func.__self__, message):
                continue
            try:
                await func(self._app, message)
            except Exception as error:
                logging.exception(error)

        for module in list(self._all_modules.modules):
            watcher = getattr(module, "aiogram_watcher", None)
            if not callable(watcher):
                continue
            try:
                await watcher(message)
            except Exception:
                logger.exception("aiogram_watcher of %s failed", getattr(module, "name", module))
        return message

    async def gallery(
        self,
        message,
        next_handler,
        caption="",
        *,
        force_me: bool = True,
        always_allow: list = None,
        ttl: int = False,
        preload: int = False,
        gif: bool = False,
        manual_security: bool = False,
        disable_security: bool = False,
        silent: bool = False,
        reply_markup: list = None,
        **kwargs,
    ):
        """Photo (or gif) viewer with previous / next buttons; `next_handler`
        is a list of URLs or a (sync or async) callable returning a URL or a list of them"""
        history, pool = [], []

        async def fetch() -> str:
            if isinstance(next_handler, (list, tuple)):
                index = len(history)
                return next_handler[index] if index < len(next_handler) else None
            if not pool:
                result = next_handler()
                if inspect.isawaitable(result):
                    result = await result
                pool.extend(result if isinstance(result, (list, tuple)) else [result])
            return pool.pop(0) if pool else None

        def caption_for(index: int) -> str:
            text = caption(history[index]) if callable(caption) else caption
            return self.sanitise_text(text)

        first = await fetch()
        if not first:
            return False
        history.append(first)
        position = {"index": 0}
        extra = reply_markup or []
        if isinstance(extra, dict):
            extra = [[extra]]
        elif extra and isinstance(extra[0], dict):
            extra = [extra]

        def keyboard():
            row = []
            if position["index"] > 0:
                row.append({"text": "⬅️", "callback": functools.partial(navigate, -1)})
            if not isinstance(next_handler, (list, tuple)) or position["index"] + 1 < len(next_handler):
                row.append({"text": "➡️", "callback": functools.partial(navigate, 1)})
            row.append({"text": "🔻", "callback": close})
            buttons = [row, *extra]
            for button in (b for r in buttons for b in r):
                button["force_me"] = force_me and not disable_security
            return buttons

        allowed = set(always_allow or [])

        async def guard(call) -> bool:
            if disable_security or not force_me or self._is_owner(call.from_user.id) or call.from_user.id in allowed:
                return True
            await call.answer("🚫 You are not allowed to press this button!")
            return False

        async def navigate(step: int, call):
            if not await guard(call):
                return
            target = position["index"] + step
            if target < 0:
                return await call.answer()
            if target >= len(history):
                url = await fetch()
                if not url:
                    return await call.answer("No more items", show_alert=False)
                history.append(url)
            position["index"] = target
            media_cls = aiogram.types.InputMediaAnimation if gif else aiogram.types.InputMediaPhoto
            await self.bot.edit_message_media(
                media=media_cls(history[target], caption=caption_for(target), parse_mode="HTML"),
                inline_message_id=call.inline_message_id,
                chat_id=None if call.inline_message_id else call.message.chat.id,
                message_id=None if call.inline_message_id else call.message.message_id,
                reply_markup=self._generate_markup(keyboard()),
            )
            await call.answer()

        async def close(call):
            if not await guard(call):
                return
            if call.inline_message_id:
                await self.bot.edit_message_caption(
                    inline_message_id=call.inline_message_id, caption="🔻", reply_markup=None
                )
            else:
                await call.message.delete()

        return await self.form(
            caption_for(0),
            message,
            reply_markup=keyboard(),
            force_me=force_me,
            always_allow=list(allowed),
            ttl=ttl,
            **({"gif": first} if gif else {"photo": first}),
        )

    def _is_owner(self, user_id: int) -> bool:
        return user_id in (self._me, database.db.get("shizu.me", "me")) or user_id in database.db.get(
            "shizu.me", "owners", []
        )

    async def _inline_handler(self, inline_query: InlineQuery) -> InlineQuery:
        """Handles inline queries"""
        query = inline_query.query.strip()
        cmd, _, args = query.partition(" ")
        func = self._all_modules.inline_handlers.get(cmd.lower()) if query else None
        public = bool(func) and bool(mask_of(func) & EVERYONE)

        if not self._is_owner(inline_query.from_user.id) and not public:
            return await inline_query.answer(
                [
                    InlineQueryResultArticle(
                        id=utils.random_id(),
                        title="Available only to the userbot owner",
                        input_message_content=InputTextMessageContent(
                            "🚸 <b>Unfortunately, this is only available to the userbot owner</b>"
                        ),
                        thumb_url="https://cdn-icons-png.flaticon.com/512/7754/7754235.png",
                    )
                ],
                cache_time=0,
            )
        if not query:
            return await self._answer_inline_commands(inline_query)

        if func:
            return await self._run_inline_handler(func, inline_query, args.strip())

        try:
            if self._forms[query].get("type", None) == "form":
                if self._forms[query].get("rich_message"):
                    result = {
                        "type": "article",
                        "id": utils.random_id(),
                        "title": "Shizu",
                        "input_message_content": {
                            "rich_message": self._forms[query]["rich_message"]
                        },
                    }
                    try:
                        return await self.bot.request(
                            "answerInlineQuery",
                            {
                                "inline_query_id": inline_query.id,
                                "results": json.dumps([result]),
                                "cache_time": 0,
                                "is_personal": True,
                            },
                        )
                    except Exception:
                        logger.warning(
                            "Could not answer inline query with a rich message",
                            exc_info=True,
                        )
                        return await inline_query.answer(
                            [
                                InlineQueryResultArticle(
                                    id=utils.random_id(),
                                    title="Shizu",
                                    input_message_content=InputTextMessageContent(
                                        self._forms[query]["text"],
                                        "HTML",
                                        disable_web_page_preview=True,
                                    ),
                                )
                            ],
                            cache_time=0,
                            is_personal=True,
                        )
                if self._forms[query].get("photo", None):
                    return await inline_query.answer(
                        [
                            InlineQueryResultPhoto(
                                id=utils.random_id(),
                                title="Shizu",
                                description="🐙 Shizu Userbot",
                                caption=self._forms[query].get("text", None),
                                photo_url=self._forms[query].get("photo", None),
                                thumb_url=self._forms[query].get("photo", None),
                                reply_markup=self._generate_markup(query, for_inline_query=True),
                            )
                        ],
                        cache_time=60,
                    )
                if self._forms[query].get("video", None):
                    return await inline_query.answer(
                        [
                            InlineQueryResultVideo(
                                id=utils.random_id(),
                                title="Shizu",
                                description="🐙 Shizu Userbot",
                                caption=self._forms[query].get("text", None),
                                video_url=self._forms[query].get("video", None),
                                thumb_url=self._forms[query].get("video", None),
                                reply_markup=self._generate_markup(query, for_inline_query=True),
                                mime_type="video/mp4",
                            )
                        ],
                        cache_time=60,
                    )
                if self._forms[query].get("gif", None):
                    return await inline_query.answer(
                        [
                            InlineQueryResultGif(
                                id=utils.random_id(),
                                title="Shizu",
                                caption=self._forms[query].get("text", None),
                                gif_url=self._forms[query].get("gif", None),
                                thumb_url=self._forms[query].get("gif", None),
                                reply_markup=self._generate_markup(query, for_inline_query=True),
                            )
                        ],
                        cache_time=60,
                    )
                if self._forms[query].get("audio", None):
                    return await inline_query.answer(
                        [
                            InlineQueryResultAudio(
                                id=utils.random_id(),
                                title=self._forms[query].get("audio_title") or "Shizu",
                                performer=self._forms[query].get("audio_performer"),
                                caption=self._forms[query].get("text", None),
                                audio_url=self._forms[query].get("audio", None),
                                reply_markup=self._generate_markup(query, for_inline_query=True),
                            )
                        ],
                        cache_time=60,
                    )

                return await inline_query.answer(
                    [
                        InlineQueryResultArticle(
                            id=utils.random_id(),
                            title="Shizu",
                            input_message_content=InputTextMessageContent(
                                self._forms[query]["text"],
                                "HTML",
                                disable_web_page_preview=True,
                            ),
                            reply_markup=self._generate_markup(query, for_inline_query=True),
                        )
                    ],
                    cache_time=60,
                )
            if self._forms[query].get("type", None) == "list":
                return await inline_query.answer(
                    [
                        InlineQueryResultArticle(
                            id=utils.rand(20),
                            title="Shizu",
                            input_message_content=InputTextMessageContent(
                                self._forms[query].get(
                                    "text",
                                    self._forms[query].get("strings", ["..."])[0],
                                ),
                                "HTML",
                                disable_web_page_preview=True,
                            ),
                            reply_markup=self._generate_markup(query, for_inline_query=True),
                        )
                    ],
                    cache_time=60,
                )
            if self._forms[query].get("type", None) == "gallery":
                return await inline_query.answer(
                    [
                        InlineQueryResultArticle(
                            id=utils.rand(20),
                            title="Shizu",
                            input_message_content=InputTextMessageContent(
                                self._forms[query].get("text", None),
                                "HTML",
                                disable_web_page_preview=True,
                            ),
                            reply_markup=self._generate_markup(query, for_inline_query=True),
                        )
                    ],
                    cache_time=60,
                )
        except KeyError:
            for form in self._forms.copy().values():
                for button in array_sum(form.get("buttons", [])):
                    if (
                        "_switch_query" in button
                        and "input" in button
                        and button["_switch_query"] == query.split()[0]
                        and inline_query.from_user.id
                        in [self._me]
                        + form["always_allow"]
                        + self._db.get("shizu.me", "owners", []) + [self._me]
                    ):
                        await inline_query.answer(
                            [
                                InlineQueryResultArticle(
                                    id=utils.rand(20),
                                    title=button["input"],
                                    description="⚠️ Please do not remove the identifier!",
                                    input_message_content=InputTextMessageContent(
                                        "🔄 <b>Just ignore this message...</b>\n"
                                        "<i>This message will be deleted...</i>",
                                        "HTML",
                                        disable_web_page_preview=True,
                                    ),
                                )
                            ],
                            cache_time=60,
                        )

                        return

            return await self._answer_inline_commands(inline_query, cmd)

    async def _run_inline_handler(self, func, inline_query: InlineQuery, args: str):
        inline_query.args = args
        try:
            params = [
                p for p in inspect.signature(func).parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]
        except (TypeError, ValueError):
            params = []
        try:
            if getattr(func.__self__, "m__telethon", False) or len(params) == 1:
                result = await func(inline_query)
            elif len(params) >= 3 and params[2].name == "args":
                result = await func(self._app, inline_query, args)
            else:
                result = await func(self._app, inline_query)
        except Exception:
            logger.exception("Inline handler %s failed", getattr(func, "__name__", func))
            return
        if result:
            await self._answer_results(inline_query, result)

    async def _answer_results(self, inline_query: InlineQuery, result) -> None:
        """Answer an inline query with result dicts returned by a handler"""
        items = [result] if isinstance(result, dict) else list(result)
        answers = []
        for item in items[:50]:
            markup = item.get("reply_markup")
            if isinstance(markup, dict):
                markup = [[markup]]
            elif markup and isinstance(markup[0], dict):
                markup = [markup]
            keyboard = self._generate_markup(markup) if markup else None
            text = self.sanitise_text(item.get("message") or item.get("caption") or item.get("title", ""))
            common = {"id": utils.random_id(), "reply_markup": keyboard}
            if item.get("photo"):
                answers.append(
                    InlineQueryResultPhoto(
                        photo_url=item["photo"],
                        thumb_url=item.get("thumb") or item["photo"],
                        title=item.get("title"),
                        description=item.get("description"),
                        caption=text,
                        parse_mode="HTML",
                        **common,
                    )
                )
            elif item.get("gif"):
                answers.append(
                    InlineQueryResultGif(
                        gif_url=item["gif"],
                        thumb_url=item.get("thumb") or item["gif"],
                        title=item.get("title"),
                        caption=text,
                        parse_mode="HTML",
                        **common,
                    )
                )
            else:
                answers.append(
                    InlineQueryResultArticle(
                        title=item.get("title", "Shizu"),
                        description=item.get("description"),
                        input_message_content=InputTextMessageContent(
                            text, "HTML", disable_web_page_preview=True
                        ),
                        thumb_url=item.get("thumb"),
                        **common,
                    )
                )
        await inline_query.answer(answers, cache_time=0, is_personal=True)

    async def _answer_inline_commands(
        self, inline_query: InlineQuery, prefix: str = ""
    ) -> None:
        """Answers with inline commands starting with prefix"""
        tr = Translator(self._app, self._db).gettext
        username = (await self.bot.me).username
        results = []

        for command, func in self._all_modules.inline_handlers.items():
            if not command.startswith(prefix.lower()) or not await self._check_filters(
                func, func.__self__, inline_query
            ):
                continue

            doc = html.unescape(re.sub(r"<[^>]+>", "", func.__doc__ or "")).strip()
            results.append(
                InlineQueryResultArticle(
                    id=utils.random_id(),
                    title=command,
                    description=doc or tr("shizu.bot.inline_no_description"),
                    input_message_content=InputTextMessageContent(
                        f"💬 <code>@{username} {command}</code>\n{utils.escape_html(doc)}",
                        "HTML",
                    ),
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton(
                            tr("shizu.bot.inline_run"),
                            switch_inline_query_current_chat=f"{command} ",
                        )
                    ),
                    thumb_url="https://cdn-icons-png.flaticon.com/512/5278/5278692.png",
                )
            )

        if not results:
            results.append(
                InlineQueryResultArticle(
                    id=utils.random_id(),
                    title=tr("shizu.bot.inline_no_commands"),
                    input_message_content=InputTextMessageContent(
                        tr("shizu.bot.inline_no_commands")
                    ),
                    thumb_url="https://cdn-icons-png.flaticon.com/512/2190/2190577.png",
                )
            )

        await inline_query.answer(results[:50], cache_time=0)

    def _generate_markup(self, form_uid: Union[str, list], for_inline_query: bool = False) -> InlineKeyboardMarkup:
        """Generate markup for form
        
        Args:
            form_uid: Form ID or list of buttons
            for_inline_query: If True, filters out buttons that are not allowed in inline query results
        """
        if isinstance(form_uid, str) and isinstance(
            self._forms[form_uid]["buttons"], InlineKeyboardMarkup
        ):
            return self._forms[form_uid]["buttons"]
        elif isinstance(form_uid, InlineKeyboardMarkup):
            return form_uid

        markup = InlineKeyboardMarkup()

        for row in (
            self._forms[form_uid]["buttons"] if isinstance(form_uid, str) else form_uid
        ):
            for button in row:
                if "callback" in button and not isinstance(button["callback"], str):
                    func = button["callback"]
                    button["_callback"] = func
                    button["callback"] = getattr(
                        func, "__qualname__", type(func).__name__
                    )

                if "callback" in button and "_callback_data" not in button:
                    button["_callback_data"] = utils.rand(30)
                    self._custom_map[button["_callback_data"]] = button

                if "handler" in button and not isinstance(button["handler"], str):
                    func = button["handler"]
                    try:
                        button["handler"] = (
                            f"{func.__self__.__class__.__name__}.{func.__func__.__name__}"
                        )
                    except Exception:
                        logger.exception(
                            "Error while building markup! "
                            "You probably passed a wrong type "
                            "to the `handler` field. Contact "
                            "the module developer."
                        )
                        return None

                if "input" in button and "_switch_query" not in button:
                    button["_switch_query"] = utils.rand(10)

        for row in (
            self._forms[form_uid]["buttons"] if isinstance(form_uid, str) else form_uid
        ):
            line = []
            for button in row:
                try:
                    if "url" in button:
                        line += [
                            InlineKeyboardButton(
                                button["text"],
                                url=button["url"],
                            )
                        ]
                    elif "callback" in button:
                        line += [
                            InlineKeyboardButton(
                                button["text"], callback_data=button["_callback_data"]
                            )
                        ]
                    elif "input" in button:
                        line += [
                            InlineKeyboardButton(
                                button["text"],
                                switch_inline_query_current_chat=button["_switch_query"]
                                + " ",
                            )
                        ]
                    elif "data" in button:
                        line += [
                            InlineKeyboardButton(
                                button["text"], callback_data=button["data"]
                            )
                        ]
                    elif for_inline_query:
                        logger.warning(
                            f"Button skipped in inline query result (not allowed): {button}"
                        )
                        continue
                    else:
                        logger.warning(
                            "Button was not added to the "
                            "form because it is not structured "
                            f"properly. {button}"
                        )
                except KeyError:
                    logger.exception(
                        "Error while building markup! You probably "
                        "passed a wrong type combination for a button. "
                        "Contact the module developer."
                    )
                    return

            if line:
                markup.row(*line)

        return markup

    async def _callback_query_handler(
        self, query: CallbackQuery, reply_markup: List[List[dict]] = None
    ) -> None:
        """Callback query handler (button presses)"""
        if reply_markup is None:
            reply_markup = []

        for mod in self._all_modules.modules:
            if (
                not hasattr(mod, "callback_handlers")
                or not isinstance(mod.callback_handlers, dict)
                or not mod.callback_handlers
            ):
                continue

            query.edit = functools.partial(edit, self=self, query=query)

            for query_func in mod.callback_handlers.values():
                try:
                    await query_func(query)
                except Exception:
                    logger.exception("Error on running callback watcher!")
                    await query.answer(
                        "An error occurred while processing the request. See the logs for details",
                        show_alert=True,
                    )

        for form_uid, form in self._forms.copy().items():
            if not form.get("buttons", False) or isinstance(
                form["buttons"], InlineKeyboardMarkup
            ):
                continue

            for button in array_sum(form.get("buttons", [])):
                if button.get("_callback_data", None) == query.data:
                    if (
                        form["force_me"]
                        and query.from_user.id != self._me
                        and (
                            query.from_user.id
                            not in form["always_allow"]
                            + self._db.get("shizu.me", "owners", [] + [self._me])
                        )
                    ):
                        await query.answer(
                            "🚫 You are not allowed to press this button!"
                        )
                        return

                    query.edit = functools.partial(
                        edit, self=self, query=query, form=form, form_uid=form_uid
                    )

                    query.delete = functools.partial(
                        delete, self=self, form=form, form_uid=form_uid
                    )

                    query.form = {"id": form_uid, **form}

                    try:
                        return await button["_callback"](
                            query,
                            *button.get("args", []),
                            **button.get("kwargs", {}),
                        )
                    except Exception:
                        logger.exception("Error on running callback watcher!")
                        await query.answer(
                            "An error occurred while "
                            "processing the request. "
                            "See the logs for details",
                            show_alert=True,
                        )
                        return

                    del self._forms[form_uid]

        if query.data in self._custom_map:
            if (
                self._custom_map[query.data].get("force_me", None)
                and query.from_user.id != self._me
                and query.from_user.id not in self._db.get("shizu.me", "owners", []) + [self._me] 
            ):
                await query.answer("🚫 You are not allowed to press this button!")
                return

            button = self._custom_map[query.data]
            await button["handler" if "handler" in button else "_callback"](query)
            return

    async def _chosen_inline_handler(
        self, chosen_inline_query: aiogram.types.ChosenInlineResult
    ) -> None:
        query = chosen_inline_query.query

        for form_uid, form in self._forms.copy().items():
            for button in array_sum(form.get("buttons", [])):
                if (
                    "_switch_query" in button
                    and "input" in button
                    and button["_switch_query"] == query.split()[0]
                    and chosen_inline_query.from_user.id
                    in [self._me]
                    + form["always_allow"]
                    + self._db.get("shizu.me", "owners", []) + [self._me]
                ):
                    query = query.split(maxsplit=1)[1] if len(query.split()) > 1 else ""

                    call = InlineCall()
                    call.inline_message_id = chosen_inline_query.inline_message_id

                    call.edit = functools.partial(
                        edit,
                        self=self,
                        query=chosen_inline_query,
                        form=form,
                        form_uid=form_uid,
                    )

                    for module in self._all_modules.modules:
                        if module.__class__.__name__ == button["handler"].split(".")[
                            0
                        ] and hasattr(module, button["handler"].split(".")[1]):
                            return await getattr(
                                module, button["handler"].split(".")[1]
                            )(
                                call,
                                query,
                                *button.get("args", []),
                                **button.get("kwargs", {}),
                            )

    async def form(
        self,
        text: str,
        message: Union[Message, int],
        reply_markup: List[List[dict]] = None,
        force_me: bool = True,
        prev: bool = True,
        msg_id: int = None,
        always_allow: List[int] = None,
        ttl: Union[int, bool] = False,
        photo: str = None,
        video: str = None,
        gif: str = None,
        audio: str = None,
        rich_message: dict = None,
        **kwargs,
    ) -> Union[str, bool]:
        """Creates inline form with callback

        Args:
                text
                        Content of inline form. HTML markdown supported

                message
                        Where to send inline. Can be either `Message` or `int`

                reply_markup
                        List of buttons to insert in markup. List of dicts with
                        keys: text, callback

                force_me
                        Either this form buttons must be pressed only by owner scope or no

                always_allow
                        Users, that are allowed to press buttons in addition to previous rules
                reply_to_message_id
                        Message to reply to

                rich_message
                        Raw InputRichMessage payload for Telegram Bot API 10.2+
        """

        if reply_markup is None:
            reply_markup = []

        if always_allow is None:
            always_allow = []

        if reply_markup is None:
            reply_markup = []
        elif isinstance(reply_markup, dict):
            reply_markup = [[reply_markup]]
        elif reply_markup and isinstance(reply_markup[0], dict):
            reply_markup = [reply_markup]

        if isinstance(audio, dict):
            kwargs.setdefault("audio_title", audio.get("title"))
            kwargs.setdefault("audio_performer", audio.get("performer"))
            audio = audio.get("url")

        if not isinstance(text, str):
            logger.error("Invalid type for `text`")
            return False

        if not isinstance(reply_markup, list):
            logger.error("Invalid type for `reply_markup`")
            return False

        if not all(
            all(isinstance(button, dict) for button in row) for row in reply_markup
        ):
            logger.error("Invalid type for one of the buttons. It must be `dict`")
            return False

        if not all(
            all(
                "url" in button
                or "callback" in button
                or "input" in button
                or "data" in button
                for button in row
            )
            for row in reply_markup
        ):
            logger.error(
                "Invalid button specified. "
                "Button must contain one of the following fields:\n"
                "  - `url`\n"
                "  - `callback`\n"
                "  - `input`\n"
                "  - `data`"
            )
            return False

        if not isinstance(force_me, bool):
            logger.error("Invalid type for `force_me`")
            return False

        if not isinstance(always_allow, list):
            logger.error("Invalid type for `always_allow`")
            return False

        if not isinstance(ttl, int) and ttl:
            logger.error("Invalid type for `ttl`")
            return False

        form_uid = utils.rand(30)

        self._forms[form_uid] = {
            "type": "form",
            "text": text,
            "buttons": reply_markup,
            "force_me": force_me,
            "always_allow": always_allow,
            "chat": None,
            "message_id": None,
            "uid": form_uid,
            **({"photo": photo} if photo else {}),
            **({"video": video} if video else {}),
            **({"gif": gif} if gif else {}),
            **({"audio": audio} if audio else {}),
            **({"audio_title": kwargs["audio_title"]} if kwargs.get("audio_title") else {}),
            **({"audio_performer": kwargs["audio_performer"]} if kwargs.get("audio_performer") else {}),
            **({"rich_message": rich_message} if rich_message else {}),
        }

        if isinstance(message, pyrogram.types.Message) and prev:
            if message.from_user.id != self._me:
                soo = await message.reply("🐙 Loading inline form...")
            else:
                soo = await message.edit("🐙")
        else:
            soo = None
        try:
            results = await self._app.get_inline_bot_results(
                (await self._app.inline_bot.get_me()).username, form_uid
            )
            q = await self._app.send_inline_bot_result(
                getattr(message, "chat_id", None) or message.chat.id,
                results.query_id,
                results.results[0].id,
                reply_to_message_id=msg_id or None,
            )
            if soo:
                await self._app.delete_messages(soo.chat.id, soo.id)
            elif prev and hasattr(message, "chat_id") and getattr(message, "out", False):
                with contextlib.suppress(Exception):
                    await message.delete()
        except Exception as erro:
            msg = (
                "🚫 <b>A problem occurred with the inline bot "
                "while processing the query. Check the logs for "
                f"details.</b>\n\n {erro}"
            )
            item = lo.CustomException.from_exc_info(*sys.exc_info())
            exc = item.message + "\n\n" + item.full_stack

            log_message = "🚫 <b>Inline bot invoke failed!</b>\n\n" + f"{(exc)}"

            await self._app.bot.send_message(
                self._db.get("shizu.chat", "logs", None), log_message
            )

            del self._forms[form_uid]
            if hasattr(message, "chat_id") and hasattr(message, "respond"):
                await (message.edit if message.out else message.respond)(msg)
            else:
                await self._app.send_message(message.chat.id, msg)

            return False
        self._forms[form_uid]["chat"] = message.chat.id
        self._forms[form_uid]["message_id"] = q.id

        if isinstance(message, Message):
            await message.delete()

        return form_uid

    def build_pagination(
        self,
        callback,
        total_pages: int,
        unit_id: Optional[str] = None,
        current_page: Optional[int] = None,
        args: tuple = (),
    ) -> List[List[dict]]:
        if current_page is None:
            current_page = self._forms[unit_id]["current_index"] + 1

        n, c = total_pages, current_page

        if n <= 1:
            return []

        if n <= 5:
            pages = [(str(p), p) for p in range(1, n + 1)]
        elif c <= 3:
            pages = [(str(p), p) for p in range(1, 4)] + [("4 ›", 4), (f"{n} »", n)]
        elif c > n - 3:
            pages = [("« 1", 1), (f"‹ {n - 3}", n - 3)] + [
                (str(p), p) for p in range(n - 2, n + 1)
            ]
        else:
            pages = [
                ("« 1", 1),
                (f"‹ {c - 1}", c - 1),
                (str(c), c),
                (f"{c + 1} ›", c + 1),
                (f"{n} »", n),
            ]

        return [
            [
                {
                    "text": f"· {p} ·" if p == c else text,
                    "callback": callback,
                    "args": (*args, p - 1),
                }
                for text, p in pages
            ]
        ]

    async def list(
        self,
        message: Union[Message, int],
        strings: List[str],
        prev: bool = True,
        *,
        force_me: Optional[bool] = True,
        always_allow: Optional[list] = None,
        custom_buttons: Optional[List[List[dict]]] = None,
        silent: bool = False,
        disable_security: bool = False,
        **kwargs,
    ) -> Union[str, bool]:
        """
        Send inline list to chat
        :param message: Where to send list. Can be either `Message` or chat id
        :param strings: List of strings, which should become inline list
        :param force_me: Either this list buttons must be pressed only by owner scope or no
        :param always_allow: Users, that are allowed to press buttons in addition to previous rules
        :param custom_buttons: Buttons to add above the pagination
        :param silent: Don't show "Loading inline list..." message
        :param disable_security: Allow anyone to press the buttons
        :return: List id if sent, otherwise `False`
        """
        if not isinstance(strings, list) or not strings:
            logger.error("Invalid type for `strings`")
            return False

        if always_allow and not isinstance(always_allow, list):
            logger.error("Invalid type for `always_allow`")
            return False

        unit_id = utils.rand(16)
        self._forms[unit_id] = {
            "type": "list",
            "uid": unit_id,
            "chat": None,
            "message_id": None,
            "strings": strings,
            "current_index": 0,
            "custom_buttons": custom_buttons or [],
            "force_me": bool(force_me) and not disable_security,
            "always_allow": always_allow or [],
        }
        self._forms[unit_id]["buttons"] = self._list_buttons(unit_id)

        chat_id = message if isinstance(message, int) else message.chat.id

        if isinstance(message, Message) and prev and not silent:
            with contextlib.suppress(Exception):
                await message.edit("🐙 Loading inline list...")

        try:
            results = await self._app.get_inline_bot_results(
                (await self._app.inline_bot.get_me()).username, unit_id
            )
            q = await self._app.send_inline_bot_result(
                chat_id, results.query_id, results.results[0].id
            )
        except Exception as e:
            logger.exception("Can't send list")

            exc = "\n".join(traceback.format_exc().splitlines()[1:])
            msg = (
                f"<b>🚫 List invoke failed!</b>\n\n"
                f"<b>🧾 Logs:</b>\n<code>{utils.escape_html(exc)}</code>\n\n"
                f"<b>🥲 What: <code>{utils.escape_html(str(e))}</code></b>"
            )

            del self._forms[unit_id]
            if isinstance(message, Message):
                await (message.edit if message.outgoing else message.reply)(msg)
            else:
                await self._app.send_message(chat_id, msg)

            return False

        self._forms[unit_id]["chat"] = chat_id
        self._forms[unit_id]["message_id"] = q.id

        if isinstance(message, Message):
            with contextlib.suppress(Exception):
                await message.delete()

        return unit_id

    def _list_buttons(self, unit_id: str) -> List[List[dict]]:
        form = self._forms[unit_id]
        return (
            form["custom_buttons"]
            + self.build_pagination(
                self._list_page, len(form["strings"]), unit_id, args=(unit_id,)
            )
            + [[{"text": "🔻 Close", "callback": self._list_page, "args": (unit_id, "close")}]]
        )

    async def _list_page(self, call: CallbackQuery, unit_id: str, page: Union[int, str]):
        form = self._forms.get(unit_id)
        if not form:
            return await call.answer("⌛️ Expired", show_alert=True)

        if page == "close":
            if not await call.delete():
                await call.answer("Can't delete this message", show_alert=True)
            return

        if page == form["current_index"]:
            return await call.answer()

        form["current_index"] = page
        form["buttons"] = self._list_buttons(unit_id)

        try:
            await self.bot.edit_message_text(
                inline_message_id=call.inline_message_id,
                text=form["strings"][page],
                reply_markup=self._generate_markup(unit_id),
                disable_web_page_preview=True,
            )
            await call.answer()
        except aiogram.utils.exceptions.RetryAfter as e:
            await call.answer(
                f"Got FloodWait. Wait for {e.timeout} seconds", show_alert=True
            )
        except Exception:
            logger.exception("Exception while trying to edit list")
            await call.answer("Error occurred", show_alert=True)
