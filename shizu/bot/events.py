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
from shizu.bot.types import Item
from shizu import database

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
                "I should have edited some message, but it is deleted :("
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


class InlineCall:
    def __init__(self):
        self.delete = None
        self.unload = None
        self.edit = None
        super().__init__()


class Events(Item):
    """Events handler for inline forms and lists"""

    def __init__(self):
        self._forms = {}
        self._custom_map = {}
        self._me = database.db.get("shizu.me", "me")

    async def _message_handler(self, message: Message) -> Message:
        setattr(message, "answer", functools.partial(answer, app=self, message=message))

        for func in self._all_modules.message_handlers.values():
            if not await self._check_filters(func, func.__self__, message):
                continue
            try:
                await func(self._app, message)
            except Exception as error:
                logging.exception(error)
        return message

    async def _inline_handler(self, inline_query: InlineQuery) -> InlineQuery:
        """Handles inline queries"""
        if inline_query.from_user.id != database.db.get(
            "shizu.me", "me"
        ) and inline_query.from_user.id not in database.db.get(
            "shizu.me", "owners", []
        ):
            return await inline_query.answer(
                [
                    InlineQueryResultArticle(
                        id=utils.random_id(),
                        title="Available only for the owner of the user bot",
                        input_message_content=InputTextMessageContent(
                            "🚸 <b>Unfortunately, this is only available to the owner of the user bot</b>"
                        ),
                        thumb_url="https://cdn-icons-png.flaticon.com/512/7754/7754235.png",
                    )
                ],
                cache_time=0,
            )
        if not (query := inline_query.query):
            commands = ""
            for command, func in self._all_modules.inline_handlers.items():
                if await self._check_filters(func, func.__self__, inline_query):
                    commands += (
                        f"\n💬 <code>@{(await self.bot.me).username} {command}</code>"
                    )

            message = InputTextMessageContent(
                f"👇 <b>Available commands</b>\n" f"{commands}" if commands else "\xad"
            )

            return await inline_query.answer(
                [
                    InlineQueryResultArticle(
                        id=utils.random_id(),
                        title="Available commands",
                        description=(
                            "👇 Available commands"
                            if commands
                            else "🚫 There is no inline commands"
                        ),
                        input_message_content=message,
                        thumb_url=(
                            "https://cdn-icons-png.flaticon.com/512/5278/5278692.png"
                            if commands
                            else "https://cdn-icons-png.flaticon.com/512/2190/2190577.png"
                        ),
                    )
                ],
                cache_time=0,
            )

        query_ = query.split()

        cmd = query_[0]
        args = " ".join(query_[1:])

        if func := self._all_modules.inline_handlers.get(cmd):
            if (
                len(vars_ := inspect.getfullargspec(func).args) > 3
                and vars_[3] == "args"
            ):
                await func(self._app, inline_query, args)
            else:
                await func(self._app, inline_query)

        try:
            if self._forms[query].get("type", None) == "form":
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
                                reply_markup=self._generate_markup(query),
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
                                reply_markup=self._generate_markup(query),
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
                                reply_markup=self._generate_markup(query),
                            )
                        ],
                        cache_time=60,
                    )
                if self._forms[query].get("audio", None):
                    return await inline_query.answer(
                        [
                            InlineQueryResultAudio(
                                id=utils.random_id(),
                                title="Shizu",
                                caption=self._forms[query].get("text", None),
                                audio_url=self._forms[query].get("audio", None),
                                reply_markup=self._generate_markup(query),
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
                            reply_markup=self._generate_markup(query),
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
                            reply_markup=self._generate_markup(query),
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
                            reply_markup=self._generate_markup(query),
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
                                    description="⚠️ Please, do not remove identifier!",
                                    input_message_content=InputTextMessageContent(
                                        "🔄 <b>Just ignore this message...</b>\n"
                                        "<i>This message is gonna be deleted...</i>",
                                        "HTML",
                                        disable_web_page_preview=True,
                                    ),
                                )
                            ],
                            cache_time=60,
                        )

                        return

    def _generate_markup(self, form_uid: Union[str, list]) -> InlineKeyboardMarkup:
        """Generate markup for form"""
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
                    try:
                        button["callback"] = (
                            f"{func.__self__.__class__.__name__}.{func.__func__.__name__}"
                        )
                    except Exception:
                        logger.exception(
                            "Error while forming markup! "
                            "Probably, you passed wrong type "
                            "to `callback` field, contact "
                            "developer of module."
                        )
                        return None

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
                            "Error while forming markup! "
                            "Probably, you passed wrong type "
                            "to `handler` field, contact "
                            "developer of module."
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
                    else:
                        logger.warning(
                            "Button have not been added to "
                            "form, because it is not structured "
                            f"properly. {button}"
                        )
                except KeyError:
                    logger.exception(
                        "Error while forming markup! Probably, you "
                        "passed wrong type combination for button. "
                        "Contact developer of module."
                    )
                    return

            markup.row(*line)

        return markup

    async def _callback_query_handler(
        self, query: CallbackQuery, reply_markup: List[List[dict]] = None
    ) -> None:
        """Callback query handler (buttons' presses)"""
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
                        "Error occured while processing request. More info in logs",
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
                            "Error occurred while "
                            "processing request. "
                            "More info in logs",
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
        """

        if reply_markup is None:
            reply_markup = []

        if always_allow is None:
            always_allow = []

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
                message.chat.id,
                results.query_id,
                results.results[0].id,
                reply_to_message_id=msg_id or None,
            )
            if soo:
                await self._app.delete_messages(soo.chat.id, soo.id)
        except Exception as erro:
            msg = (
                "🚫 <b>A problem occurred with inline bot "
                "while processing query. Check logs for "
                f"further info.</b>\n\n {erro}"
            )
            item = lo.CustomException.from_exc_info(*sys.exc_info())
            exc = item.message + "\n\n" + item.full_stack

            log_message = "🚫 <b>Inline bot invoke failed!</b>\n\n" + f"{(exc)}"

            await self._app.bot.send_message(
                self._db.get("shizu.chat", "logs", None), log_message
            )

            del self._forms[form_uid]
            if isinstance(message, Message):
                await (message.edit if message.out else message.respond)(msg)
            else:
                await self._app.send_message(message.chat.id, msg)

            return False
        self._forms[form_uid]["chat"] = message.chat.id
        self._forms[form_uid]["message_id"] = q.id

        if isinstance(message, Message):
            await message.delete()

        return form_uid

    async def list(
        self,
        message: Message,
        strings: List[str],
        prev: bool = True,
        *,
        force_me: Optional[bool] = True,
        always_allow: Optional[list] = None,
        manual_security: Optional[bool] = False,
        disable_security: Optional[bool] = False,
        ttl: Optional[Union[int, bool]] = False,
        **kwargs,
    ) -> bool:
        """
        Send inline list to chat
        :param message: Where to send list. Can be either `Message` or `int`
        :param strings: List of strings, which should become inline list
        :param force_me: Either this list buttons must be pressed only by owner scope or no
        :param always_allow: Users, that are allowed to press buttons in addition to previous rules
        :param ttl: Time, when the list is going to be unloaded. Unload means, that the list
                    will become unusable. Pay attention, that ttl can't
                    be bigger, than default one (1 day) and must be either `int` or `False`
        :param on_unload: Callback, called when list is unloaded and/or closed. You can clean up trash
                          or perform another needed action
        :param manual_security: By default, Shizu will try to inherit inline buttons security from the caller (command)
                                If you want to avoid this, pass `manual_security=True`
        :param disable_security: By default, Shizu will try to inherit inline buttons security from the caller (command)
                                 If you want to disable all security checks on this list in particular, pass `disable_security=True`
        :param silent: Whether the list must be sent silently (w/o "Loading inline list..." message)
        :return: If list is sent, returns :obj:`InlineMessage`, otherwise returns `False`
        """

        if not isinstance(manual_security, bool):
            logger.error("Invalid type for `manual_security`")
            return False

        if not isinstance(disable_security, bool):
            logger.error("Invalid type for `disable_security`")
            return False

        if not isinstance(force_me, bool):
            logger.error("Invalid type for `force_me`")
            return False

        if not isinstance(strings, list) or not strings:
            logger.error("Invalid type for `strings`")
            return False

        if len(strings) > 50:
            logger.error(f"Too much pages for `strings` ({len(strings)})")
            return False

        if always_allow and not isinstance(always_allow, list):
            logger.error("Invalid type for `always_allow`")
            return False

        if not always_allow:
            always_allow = []

        if not isinstance(ttl, int) and ttl:
            logger.error("Invalid type for `ttl`")
            return False

        if isinstance(ttl, int) and (ttl > self._markup_ttl or ttl < 10):
            ttl = self._markup_ttl
            logger.debug("Defaulted ttl, because it breaks out of limits")

        unit_id = utils.rand(16)
        btn_call_data = {
            key: utils.rand(10) for key in {"back", "next", "show_current"}
        }

        perms_map = None

        self._forms[unit_id] = {
            "type": "list",
            "chat": None,
            "message_id": None,
            "uid": unit_id,
            "btn_call_data": btn_call_data,
            "current_index": 0,
            "strings": strings,
            "future": asyncio.Event(),
            **({"ttl": round(time.time()) + ttl} if ttl else {}),
            **({"force_me": force_me} if force_me else {}),
            **({"disable_security": disable_security} if disable_security else {}),
            **({"always_allow": always_allow} if always_allow else {}),
            **({"perms_map": perms_map} if perms_map else {}),
            **({"message": message} if isinstance(message, Message) else {}),
        }

        default_map = {}
        default_map.update(
            {"ttl": self._forms[unit_id]["ttl"]}
            if "ttl" in self._forms[unit_id]
            else {}
        )
        default_map.update({"always_allow": always_allow} if always_allow else {})
        default_map.update({"force_me": force_me} if force_me else {})
        default_map.update(
            {"disable_security": disable_security} if disable_security else {}
        )
        default_map.update({"perms_map": perms_map} if perms_map else {})
        default_map.update({"message": message} if isinstance(message, Message) else {})

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton(
                text="«",
                callback_data=self._forms[unit_id]["btn_call_data"]["back"],
            ),
            InlineKeyboardButton(
                f"• {self._forms[unit_id]['current_index'] + 1} •",
                callback_data=self._forms[unit_id]["btn_call_data"]["show_current"],
            ),
            InlineKeyboardButton(
                text="»",
                callback_data=self._forms[unit_id]["btn_call_data"]["next"],
            ),
        )

        self._forms[unit_id]["buttons"] = markup

        self._custom_map[btn_call_data["back"]] = {
            "handler": functools.partial(
                self._list_back,
                btn_call_data=btn_call_data,
                unit_id=unit_id,
            ),
            **default_map,
        }

        self._custom_map[btn_call_data["next"]] = {
            "handler": functools.partial(
                self._list_next,
                btn_call_data=btn_call_data,
                unit_id=unit_id,
            ),
            **default_map,
        }

        self._custom_map[btn_call_data["show_current"]] = {
            "handler": functools.partial(
                self._list_show_current,
                unit_id=unit_id,
            )
        }

        if isinstance(message, pyrogram.types.Message) and prev:
            message: pyrogram.types.Message
            try:
                status_message = await message.edit("🐙 Loading inline list...")
            except Exception:
                status_message = None
        else:
            status_message = None

        async def answer(msg: str):
            nonlocal message
            if isinstance(message, Message):
                await (message.edit if message.out else message.respond)(msg)
            else:
                await self._app.send_message(message.chat.id, msg)

        try:
            results = await self._app.get_inline_bot_results(
                (await self._app.inline_bot.get_me()).username, unit_id
            )

            if status_message:
                await self._app.delete_messages(
                    status_message.chat.id, status_message.id
                )

            await self._app.send_inline_bot_result(
                message.chat.id,
                results.query_id,
                results.results[0].id,
                reply_to_message_id=status_message.id if status_message else None,
            )

        except Exception as e:
            logger.exception("Can't send list")

            exc = traceback.format_exc()
            exc = "\n".join(exc.splitlines()[1:])
            msg = (
                f"<b>🚫 List invoke failed!</b>\n\n"
                f"<b>🧾 Logs:</b>\n<code>{exc}</code>\n\n"
                f"<b>🥲 What: <code>{e}</code></b>"
            )

            del self._forms[unit_id]
            await answer(msg)

            return False

        await self._forms[unit_id]["future"].wait()
        del self._forms[unit_id]["future"]

        self._forms[unit_id]["chat"] = message
        self._forms[unit_id]["message_id"] = message.message_id

        if isinstance(message, Message) and message.out:
            await message.delete()

        if status_message and not message.out:
            await status_message.delete()

        return unit_id

    async def _list_back(
        self,
        call: CallbackQuery,
        btn_call_data: List[str] = None,
        unit_id: str = None,
    ):
        if not self._forms[unit_id]["current_index"]:
            await call.answer("No way back", show_alert=True)
            return

        self._forms[unit_id]["current_index"] -= 1

        try:
            await self.bot.edit_message_text(
                inline_message_id=call.inline_message_id,
                text=self._forms[unit_id]["strings"][
                    self._forms[unit_id]["current_index"]
                ],
                reply_markup=self._list_markup(unit_id),
                disable_web_page_preview=True,
            )
            await call.answer()
        except aiogram.utils.exceptions.RetryAfter as e:
            await call.answer(
                f"Got FloodWait. Wait for {e.timeout} seconds",
                show_alert=True,
            )
        except Exception:
            logger.exception("Exception while trying to edit list")
            await call.answer("Error occurred", show_alert=True)
            return

    async def _list_next(
        self,
        call: CallbackQuery,
        btn_call_data: List[str] = None,
        unit_id: str = None,
    ):
        self._forms[unit_id]["current_index"] += 1
        if self._forms[unit_id]["current_index"] >= len(
            self._forms[unit_id]["strings"]
        ):
            await call.answer("No entries left...", show_alert=True)
            self._forms[unit_id]["current_index"] -= 1
            return

        try:
            await self.bot.edit_message_text(
                inline_message_id=call.inline_message_id,
                text=self._forms[unit_id]["strings"][
                    self._forms[unit_id]["current_index"]
                ],
                reply_markup=self._list_markup(unit_id),
                disable_web_page_preview=True,
            )
            await call.answer()
        except aiogram.utils.exceptions.RetryAfter as e:
            await call.answer(
                f"Got FloodWait. Wait for {e.timeout} seconds",
                show_alert=True,
            )
            return
        except Exception:
            logger.exception("Exception while trying to edit list")
            await call.answer("Error occurred", show_alert=True)
            return

    def _list_markup(self, unit_id: str) -> InlineKeyboardMarkup:
        """Converts `btn_call_data` into a aiogram markup"""
        markup = InlineKeyboardMarkup()
        markup.add(
            *(
                [
                    InlineKeyboardButton(
                        f"« [{self._forms[unit_id]['current_index']} / {len(self._forms[unit_id]['strings'])}]",
                        callback_data=self._forms[unit_id]["btn_call_data"]["back"],
                    )
                ]
                if self._forms[unit_id]["current_index"] > 0
                else []
            ),
            InlineKeyboardButton(
                f"• {self._forms[unit_id]['current_index'] + 1} •",
                callback_data=self._forms[unit_id]["btn_call_data"]["show_current"],
            ),
            *(
                [
                    InlineKeyboardButton(
                        f" [{self._forms[unit_id]['current_index'] + 2} / {len(self._forms[unit_id]['strings'])}] » ",
                        callback_data=self._forms[unit_id]["btn_call_data"]["next"],
                    ),
                ]
                if self._forms[unit_id]["current_index"]
                < len(self._forms[unit_id]["strings"]) - 1
                else []
            ),
        )

        return markup

    async def _list_show_current(self, call: CallbackQuery, unit_id: str = None):
        await call.answer(
            f"Current page: {self._forms[unit_id]['current_index'] + 1} / {len(self._forms[unit_id]['strings'])}",
            show_alert=True,
        )
