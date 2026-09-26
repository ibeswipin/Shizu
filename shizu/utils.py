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

# some piece of code taken from: https://github.com/hikariatama/Hikka/blob/master/hikka/utils.py

import asyncio
import logging
import requests
import functools
import random
import sys
import string
import git
import typing
import contextlib
import io
import os
import grapheme

from types import FunctionType

from typing import Any, List, Literal, Tuple, Union, AsyncIterator

from pyrogram.types import Chat, Message, User
from pyrogram import Client, enums, types

from pyrogram.raw.types.message_entity_unknown import MessageEntityUnknown
from pyrogram.raw.types.message_entity_mention import MessageEntityMention
from pyrogram.raw.types.message_entity_hashtag import MessageEntityHashtag
from pyrogram.raw.types.message_entity_bot_command import MessageEntityBotCommand
from pyrogram.raw.types.message_entity_url import MessageEntityUrl
from pyrogram.raw.types.message_entity_email import MessageEntityEmail
from pyrogram.raw.types.message_entity_bold import MessageEntityBold
from pyrogram.raw.types.message_entity_italic import MessageEntityItalic
from pyrogram.raw.types.message_entity_code import MessageEntityCode
from pyrogram.raw.types.message_entity_pre import MessageEntityPre
from pyrogram.raw.types.message_entity_text_url import MessageEntityTextUrl
from pyrogram.raw.types.message_entity_mention_name import MessageEntityMentionName
from pyrogram.raw.types.input_message_entity_mention_name import (
    InputMessageEntityMentionName,
)
from pyrogram.raw.types.message_entity_phone import MessageEntityPhone
from pyrogram.raw.types.message_entity_cashtag import MessageEntityCashtag
from pyrogram.raw.types.message_entity_underline import MessageEntityUnderline
from pyrogram.raw.types.message_entity_strike import MessageEntityStrike
from pyrogram.raw.types.message_entity_blockquote import MessageEntityBlockquote
from pyrogram.raw.types.message_entity_bank_card import MessageEntityBankCard
from pyrogram.raw.types.message_entity_spoiler import MessageEntitySpoiler
from pyrogram.raw.types.message_entity_custom_emoji import MessageEntityCustomEmoji


from shizu import database


FormattingEntity = Union[
    MessageEntityUnknown,
    MessageEntityMention,
    MessageEntityHashtag,
    MessageEntityBotCommand,
    MessageEntityUrl,
    MessageEntityEmail,
    MessageEntityBold,
    MessageEntityItalic,
    MessageEntityCode,
    MessageEntityPre,
    MessageEntityTextUrl,
    MessageEntityMentionName,
    InputMessageEntityMentionName,
    MessageEntityPhone,
    MessageEntityCashtag,
    MessageEntityUnderline,
    MessageEntityStrike,
    MessageEntityBlockquote,
    MessageEntityBankCard,
    MessageEntitySpoiler,
    MessageEntityCustomEmoji,
]

ListLike = Union[list, set, tuple]


db = database.db

logger = logging.getLogger(__name__)


def get_random_smartphone() -> str:
    """Returns a random smartphone model"""

    devices = requests.get(
        "https://gist.githubusercontent.com/ibeswipin/e5927fdd510097c37b5047fae333b8b4/raw/a8456cd97445b672fec6ac7a7aba843f73e3863c/phones.json"
    ).json()
    return random.choice(devices)


def get_lang_flag(countrycode: str) -> str:
    """
    Gets an emoji of specified country code
    :param countrycode: 2-letter country code
    :return: Emoji flag
    """
    if (
        len(
            code := [
                c
                for c in countrycode.lower()
                if c in string.ascii_letters + string.digits
            ]
        )
        == 2
    ):
        return "".join([chr(ord(c.upper()) + (ord("🇦") - ord("A"))) for c in code])

    return countrycode.encode("utf-8")


def chunks(_list: Union[list, tuple, set], n: int, /) -> list:
    """Split provided `_list` into chunks of `n`"""
    return [_list[i : i + n] for i in range(0, len(_list), n)]


def get_full_command(
    message: Message,
) -> Union[Tuple[Literal[""], Literal[""], Literal[""]], Tuple[str, str, str]]:
    """Output tuple from prefix, command and arguments

    Parameters:
        message (`program.types.Message`):
    Message
    """
    message.text = str(message.text or message.caption)
    prefixes = database.db.get("shizu.loader", "prefixes", ["."])

    for prefix in prefixes:
        if (
            message.text
            and len(message.text) > len(prefix)
            and message.text.startswith(prefix)
        ):
            command, *args = message.text[len(prefix) :].split(maxsplit=1)
            break
    else:
        return "", "", ""

    return prefixes[0], command.lower(), args[-1] if args else ""


def is_telethon_message(message: Any) -> bool:
    return hasattr(message, "raw_text") and hasattr(message, "chat_id")


def _raw_text(message: Any) -> str:
    if is_telethon_message(message):
        return message.raw_text or ""
    return getattr(message, "text", message) or ""


def get_args(message: typing.Union[Message, str]) -> typing.Union[str, List[str]]:
    """
    Arguments of a command: a string for Pyrogram messages and plain strings,
    a list of shell-like split arguments for Telethon messages
    """
    text = _raw_text(message)
    if is_telethon_message(message):
        raw = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
        try:
            import shlex

            return shlex.split(raw)
        except ValueError:
            return raw.split()

    if not text:
        return ""

    args = text.split()[1:]
    return " ".join(args) if args else ""


def restart():
    """Restart the bot"""
    sys.stdout.flush()
    sys.stderr.flush()
    os.execl(sys.executable, sys.executable, "-m", "shizu")


def get_args_raw(message: typing.Union[Message, str]) -> str:
    """
    Get the parameters to the command as a raw string (not split)
    :param message: Message or string to get arguments from
    :return: Raw string of arguments
    """
    if not (text := _raw_text(message)):
        return False if not is_telethon_message(message) else ""

    return args[1] if len(args := text.split(maxsplit=1)) > 1 else ""


def get_args_html(message: typing.Union[Message, str]) -> str:
    """
    Get arguments from message in html format.
    """
    try:
        if is_telethon_message(message):
            from telethon.extensions import html as tl_html

            args = tl_html.unparse(message.message or "", message.entities or []).split(maxsplit=1)[1]
        else:
            args = message.text.html.split(maxsplit=1)[1]
    except Exception:
        args = ""

    return args


async def invite_bot(app: Client, chat):
    """
    Invite the bot to the chat.
    """
    await app.add_chat_members(chat, (await app.bot.get_me()).username)


async def create_chat(
    app: Client,
    title: str = None,
    description=None,
    supergroup: bool = False,
    inline_bot: bool = False,
    promote: bool = False,
):
    """
    Create a chat in the Telegram app.

    Parameters:
    - app (Client): The Telegram client used to create the chat.
    - title (str): The title of the chat.
    - description (str, optional): The description of the chat. Defaults to None.
    - supergroup (bool, optional): Indicates if the chat is a supergroup. Defaults to False.
    - inline_bot (bool, optional): Indicates if the chat is an inline bot. Defaults to False.
    - promote (bool, optional): Indicates if the chat bot should be promoted to an administrator. Defaults to False.

    Returns:
    - chat: The created chat object.
    """

    chat = None
    title = f"shizu-{random_id(10)}" if title is None else title

    if not supergroup:
        chat = await app.create_group(
            title,
            "me",
        )
    else:
        if description is None:
            description = "This is a supergroup created by Shizu"
        chat = await app.create_supergroup(title, description)

    if inline_bot:
        with contextlib.suppress(Exception):
            bot_ = (await app.bot.get_me()).username
            await app.add_chat_members(chat.id, [bot_])

            if promote:
                await app.promote_chat_member(chat.id, bot_)
                await app.set_administrator_title(chat.id, bot_, "Shizu Inline")

    return chat


def get_base_dir() -> str:
    """Get directory of this file"""
    from . import loader

    return get_dir(loader.__file__)


def get_dir(mod: str) -> str:
    """Get directory of given module"""
    return os.path.abspath(os.path.dirname(os.path.abspath(mod)))


async def smart_split(
    client: Client,
    text: str,
    entities: List[FormattingEntity],
    length: int = 4096,
    split_on: ListLike = ("\n", " "),
    min_length: int = 1,
) -> AsyncIterator[str]:
    """
    Split the message into smaller messages.
    A grapheme will never be broken. Entities will be displaced to match the right location. No inputs will be mutated.
    The end of each message except the last one is stripped of characters from [split_on]
    :param text: the plain text input
    :param entities: the entities
    :param length: the maximum length of a single message
    :param split_on: characters (or strings) which are preferred for a message break
    :param min_length: ignore any matches on [split_on] strings before this number of characters into each message
    :return: iterator, which returns strings

    """

    # Authored by @bsolute
    # https://t.me/LonamiWebs/27777

    encoded = text.encode("utf-16le")
    pending_entities = entities
    text_offset = 0
    bytes_offset = 0
    text_length = len(text)
    bytes_length = len(encoded)

    while text_offset < text_length:
        if bytes_offset + length * 2 >= bytes_length:
            yield client.parser.unparse(
                text[text_offset:],
                list(sorted(pending_entities, key=lambda x: x.offset)),
                True,
            )
            break

        codepoint_count = len(
            encoded[bytes_offset : bytes_offset + length * 2].decode(
                "utf-16le",
                errors="ignore",
            )
        )

        for search in split_on:
            search_index = text.rfind(
                search,
                text_offset + min_length,
                text_offset + codepoint_count,
            )
            if search_index != -1:
                break
        else:
            search_index = text_offset + codepoint_count

        split_index = grapheme.safe_split_index(text, search_index)

        split_offset_utf16 = (
            len(text[text_offset:split_index].encode("utf-16le"))
        ) // 2
        exclude = 0

        while (
            split_index + exclude < text_length
            and text[split_index + exclude] in split_on
        ):
            exclude += 1

        current_entities = []
        entities = pending_entities.copy()
        pending_entities = []

        for entity in entities:
            if (
                entity.offset < split_offset_utf16
                and entity.offset + entity.length > split_offset_utf16 + exclude
            ):
                # spans boundary
                current_entities.append(
                    _copy_tl(
                        entity,
                        client,
                        length=split_offset_utf16 - entity.offset,
                    )
                )
                pending_entities.append(
                    _copy_tl(
                        entity,
                        client,
                        offset=0,
                        length=entity.offset
                        + entity.length
                        - split_offset_utf16
                        - exclude,
                    )
                )
            elif entity.offset < split_offset_utf16 < entity.offset + entity.length:
                # overlaps boundary
                current_entities.append(
                    _copy_tl(
                        entity,
                        client,
                        length=split_offset_utf16 - entity.offset,
                    )
                )
            elif entity.offset < split_offset_utf16:
                # wholly left
                current_entities.append(_copy_tl(entity, client))
            elif (
                entity.offset + entity.length
                > split_offset_utf16 + exclude
                > entity.offset
            ):
                # overlaps right boundary
                pending_entities.append(
                    _copy_tl(
                        entity,
                        client,
                        offset=0,
                        length=entity.offset
                        + entity.length
                        - split_offset_utf16
                        - exclude,
                    )
                )
            elif entity.offset + entity.length > split_offset_utf16 + exclude:
                pending_entities.append(
                    _copy_tl(
                        entity,
                        client,
                        offset=entity.offset - split_offset_utf16 - exclude,
                    )
                )

        current_text = text[text_offset:split_index]
        yield client.parser.unparse(
            current_text, list(sorted(current_entities, key=lambda x: x.offset)), True
        )

        text_offset = split_index + exclude
        bytes_offset += len(current_text.encode("utf-16le"))


def _copy_tl(o: FormattingEntity, client, **kwargs):
    if isinstance(o, types.MessageEntity):
        x: dict = o.default(o)
        del x["_"]
        x |= kwargs
        return type(o)(**x)

    d: dict = o.default(o)
    del d["_"]
    d |= kwargs
    entity = type(o)(**d)

    if isinstance(entity, InputMessageEntityMentionName):
        entity_type = enums.MessageEntityType.TEXT_MENTION
        user_id = entity.user_id.user_id
    else:
        info = {
            isinstance(
                entity, MessageEntityBankCard
            ): enums.MessageEntityType.BANK_CARD,
            isinstance(
                entity, MessageEntityBlockquote
            ): enums.MessageEntityType.BLOCKQUOTE,
            isinstance(entity, MessageEntityBold): enums.MessageEntityType.BOLD,
            isinstance(
                entity, MessageEntityBotCommand
            ): enums.MessageEntityType.BOT_COMMAND,
            isinstance(entity, MessageEntityCashtag): enums.MessageEntityType.CASHTAG,
            isinstance(entity, MessageEntityCode): enums.MessageEntityType.CODE,
            isinstance(entity, MessageEntityUnknown): enums.MessageEntityType.UNKNOWN,
            isinstance(
                entity, MessageEntityUnderline
            ): enums.MessageEntityType.UNDERLINE,
            isinstance(entity, MessageEntityUrl): enums.MessageEntityType.URL,
            isinstance(entity, MessageEntityTextUrl): enums.MessageEntityType.TEXT_LINK,
            isinstance(entity, MessageEntityItalic): enums.MessageEntityType.ITALIC,
            isinstance(
                entity, MessageEntityStrike
            ): enums.MessageEntityType.STRIKETHROUGH,
            isinstance(
                entity, MessageEntityCustomEmoji
            ): enums.MessageEntityType.CUSTOM_EMOJI,
            isinstance(entity, MessageEntityEmail): enums.MessageEntityType.EMAIL,
            isinstance(entity, MessageEntityHashtag): enums.MessageEntityType.HASHTAG,
            isinstance(
                entity, MessageEntityMentionName
            ): enums.MessageEntityType.MENTION,
            isinstance(entity, MessageEntitySpoiler): enums.MessageEntityType.SPOILER,
            isinstance(entity, MessageEntityMention): enums.MessageEntityType.MENTION,
            isinstance(entity, MessageEntityPre): enums.MessageEntityType.PRE,
            isinstance(
                entity, MessageEntityPhone
            ): enums.MessageEntityType.PHONE_NUMBER,
        }
        entity_type = info[True]
        user_id = getattr(entity, "user_id", None)

    return types.MessageEntity(
        type=entity_type,
        offset=entity.offset,
        length=entity.length,
        url=getattr(entity, "url", None),
        user=types.User._parse(client, {}.get(user_id)),
        language=getattr(entity, "language", None),
        custom_emoji_id=getattr(entity, "document_id", None),
        client=client,
    )


async def answer(
    message: Union[Message, List[Message]],
    response: Union[str, Any],
    doc: bool = False,
    photo_: bool = False,
    reply_markup: Any = None,
    **kwargs,
):
    """
    Sends a response message based on the given parameters.

    Args:
        message: The message or list of messages to respond to.
        response: The response message or content.
        doc: If True, sends the response as a document.
        photo_: If True, sends the response as a photo.
        reply_markup: The reply markup for the response.
        **kwargs: Additional keyword arguments.


    """
    messages = []
    is_telethon = hasattr(message, "reply_to_msg_id") or (
        hasattr(message, "reply_to") and not hasattr(message, "reply_to_message")
    )

    if is_telethon:
        from telethon.tl.types import Message as TelethonMessage

        if isinstance(message, TelethonMessage):
            app = message._client
            reply = getattr(message, "reply_to", None)
            reply_id = getattr(message, "reply_to_msg_id", None)
        else:
            app = getattr(message, "_client", None) or getattr(message, "client", None)
            reply = None
            reply_id = getattr(message, "reply_to_msg_id", None)
    else:
        app = message._client
        reply = getattr(message, "reply_to_message", None)
        reply_id = reply.id if reply else None

    if "disable_web_page_preview" in kwargs:
        disabled = kwargs.pop("disable_web_page_preview")
        if is_telethon:
            kwargs["link_preview"] = not disabled
        else:
            kwargs["link_preview_options"] = types.LinkPreviewOptions(
                is_disabled=disabled
            )

    if doc:
        if is_telethon:
            messages.append(await message.reply(file=response, **kwargs))
        else:
            app.me = await app.get_me()
            messages.append(await message.reply_document(response, **kwargs))
        return messages[0] if messages else None

    if photo_:
        if is_telethon:
            if "parse_mode" not in kwargs:
                kwargs["parse_mode"] = "html"
            await message.delete()
            messages.append(
                await app.send_file(
                    message.peer_id, response, reply_to=reply_id, **kwargs
                )
            )
        else:
            app.me = await app.get_me()
            await message.delete()
            messages.append(
                await app._inline.form(
                    message=message,
                    photo=response,
                    reply_markup=reply_markup,
                    **kwargs,
                )
                if reply_markup
                else await message.reply_photo(
                    response, reply_to_message_id=reply_id, **kwargs
                )
            )
        return messages[0] if messages else None

    if isinstance(response, str):
        if is_telethon:
            if "parse_mode" not in kwargs:
                kwargs["parse_mode"] = "html"

            if len(response) >= 4096:
                file = io.BytesIO(response.encode())
                file.name = "output.txt"
                messages.append(await message.reply(file=file, **kwargs))
            else:
                is_outgoing = getattr(message, "out", False) or (
                    hasattr(message, "from_id")
                    and message.from_id
                    and hasattr(message.from_id, "user_id")
                    and message.from_id.user_id == (await app.get_me()).id
                )

                if is_outgoing:
                    try:
                        await message.edit(response, **kwargs)
                        messages.append(message)
                    except Exception:
                        messages.append(
                            await app.send_message(
                                message.peer_id, response, reply_to=reply_id, **kwargs
                            )
                        )
                else:
                    messages.append(
                        await app.send_message(
                            message.peer_id, response, reply_to=reply_id, **kwargs
                        )
                    )
        else:
            info = await app.parser.parse(response, kwargs.get("parse_mode", None))
            text, entities = str(info["message"]), info.get("entities", [])
            if len(text) >= 4096:
                try:
                    strings = [
                        txt
                        async for txt in smart_split(
                            app, escape_html(text), entities, 4096
                        )
                    ]
                    messages.append(await app._inline.list(message, strings, **kwargs))
                except Exception:
                    file = io.BytesIO(text.encode())
                    file.name = "output.txt"
                    messages.append(await message.reply_document(file, **kwargs))
            else:
                messages.append(
                    await app._inline.form(
                        message=message,
                        text=response,
                        reply_markup=reply_markup,
                        msg_id=(
                            reply_id
                            if reply_id
                            else (
                                message.topic.id
                                if hasattr(message, "topic") and message.topic
                                else None
                            )
                        ),
                        **kwargs,
                    )
                    if reply_markup
                    else (
                        await message.edit(
                            text=response,
                            **kwargs,
                        )
                        if message.outgoing
                        or (
                            hasattr(message, "from_user")
                            and message.from_user
                            and message.from_user.is_self
                        )
                        else await app.send_message(
                            message.chat.id,
                            response,
                            reply_to_message_id=(
                                message.topic.id
                                if hasattr(message, "topic") and message.topic
                                else reply_id if reply_id else None
                            ),
                            **kwargs,
                        )
                    )
                )

    return messages[0] if messages else None


def array_sum(array: list) -> Any:
    """Performs basic sum operation on array (flattens nested lists)"""
    result = []
    for item in array:
        if isinstance(item, (list, tuple, set)):
            result.extend(array_sum(item))
        else:
            result.append(item)
    return result


def rand(size: int, /) -> str:
    """Return random string of len `size`"""
    return "".join(
        [random.choice("abcdefghijklmnopqrstuvwxyz1234567890") for _ in range(size)]
    )


def run_sync(func: FunctionType, *args, **kwargs) -> asyncio.Future:
    """Runs asynchronously non-asink function

    Parameters:
            func (`types.FunctionType`):
    Function to run

            args (`list`):
    Arguments to the function

            kwargs (`dict`):
    Parameters to the function
    """
    return asyncio.get_event_loop().run_in_executor(
        None, functools.partial(func, *args, **kwargs)
    )


def get_display_name(entity: Union[User, Chat]) -> str:
    """Получить отображаемое имя

    Параметры:
        entity (``pyrogram.types.User`` | ``pyrogram.types.Chat``):
            Сущность, для которой нужно получить отображаемое имя
    """
    if title := getattr(entity, "title", None):
        return title
    name = " ".join(
        filter(None, [getattr(entity, "first_name", None), getattr(entity, "last_name", None)])
    )
    return name or getattr(entity, "username", None) or str(getattr(entity, "id", ""))


def escape_html(text):
    """Pass all untrusted/potentially corrupt input here"""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def get_platform() -> str:
    """Возращает платформу."""
    IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")
    IS_DOCKER = "DOCKER" in os.environ
    IS_WIN = "WINDIR" in os.environ
    IS_JAMHOST = "JAMHOST" in os.environ
    IS_WSL = False

    with contextlib.suppress(Exception):
        from platform import uname

        if "microsoft-standard" in uname().release:
            IS_WSL = True

    if IS_TERMUX:
        platform = "📱 Termux"
    elif IS_DOCKER:
        platform = "🐳 Docker"
    elif IS_WSL:
        platform = "🧱 WSL"
    elif IS_WIN:
        platform = "💻 Windows"
    elif IS_JAMHOST:
        platform = "🍓 JamHost"
    else:
        platform = "🖥️ VDS"

    return platform


def random_id(size: int = 10) -> str:
    """Returns a random identifier of the specified length

    Параметры:
        size (``int``, optional):
            length of the identifier
    """
    return "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(size)
    )


def is_tl_enabled() -> bool:
    """Check if telethon is enabled"""
    return any(("shizu-tl.session") in i for i in os.listdir())


async def respond(message, response: str, **kwargs):
    """Send a new message to the chat of `message` (Hikka compatibility)"""
    if hasattr(message, "respond") and hasattr(message, "chat_id"):
        kwargs.setdefault("parse_mode", "html")
        return await message.respond(response, **kwargs)
    return await message.reply(response, quote=False, **kwargs)


def get_chat_id(message: typing.Union[Message, Any]) -> int:
    """
    Get the chat ID, but without -100 if its a channel
    :param message: Message to get chat ID from
    :return: Chat ID
    """
    chat_id = getattr(message, "chat_id", None)

    if chat_id is None:
        chat = getattr(message, "chat", None)
        if chat is not None:
            chat_id = getattr(chat, "id", None)

    if chat_id is None:
        raise ValueError("Could not extract chat_id from message")

    if isinstance(chat_id, str):
        try:
            chat_id = int(chat_id)
        except ValueError:
            raise ValueError(f"Invalid chat_id format: {chat_id}")

    try:
        import telethon

        resolved = telethon.utils.resolve_id(chat_id)
        return resolved[0] if resolved else chat_id
    except (ImportError, AttributeError):
        chat_id_str = str(chat_id)
        if chat_id_str.startswith("-100"):
            return int(chat_id_str[4:])
        return chat_id


def available_branches() -> List[str]:
    """Returns a list of available branches"""
    return [head.name.split("/")[-1] for head in git.Repo().heads]


def render_table(rows, header=None) -> str:
    grid = [[str(c) for c in row] for row in rows]
    if header is not None:
        grid.insert(0, [str(c) for c in header])

    if not grid:
        return "<pre></pre>"

    ncols = max(len(row) for row in grid)
    grid = [row + [""] * (ncols - len(row)) for row in grid]
    widths = [max(len(row[i]) for row in grid) for i in range(ncols)]

    lines = [
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
        for row in grid
    ]
    if header is not None:
        lines.insert(1, "  ".join("-" * widths[i] for i in range(ncols)))

    return f"<pre>{escape_html(chr(10).join(lines))}</pre>"


def _rich_table_payload(rows, header=None, title=None) -> dict:
    """Build an InputRichMessage payload for Telegram Bot API 10.2+."""
    grid = [[str(cell) for cell in row] for row in rows]
    if header is not None:
        grid.insert(0, [str(cell) for cell in header])

    if not grid:
        raise ValueError("A rich table must contain at least one row")

    column_count = max(len(row) for row in grid)
    if column_count > 20:
        raise ValueError("Telegram rich tables support at most 20 columns")

    grid = [row + [""] * (column_count - len(row)) for row in grid]
    cells = []
    for row_index, row in enumerate(grid):
        is_header = header is not None and row_index == 0
        cells.append(
            [
                {
                    "text": cell,
                    **({"is_header": True} if is_header else {}),
                }
                for cell in row
            ]
        )

    blocks = []
    if title:
        blocks.append({"type": "heading", "text": str(title), "size": 3})
    blocks.append(
        {
            "type": "table",
            "cells": cells,
            "is_bordered": True,
            "is_striped": True,
            "is_compact": True,
        }
    )
    return {"blocks": blocks}


async def _rich_table(message, rows, header, title, fallback_text):
    inline = getattr(message._client, "_inline", None)
    if inline is None or not hasattr(inline, "form"):
        raise RuntimeError("Inline bot is unavailable")

    result = await inline.form(
        text=fallback_text,
        message=message,
        rich_message=_rich_table_payload(rows, header, title),
    )
    if result is False:
        raise RuntimeError("Could not send a rich table through the inline bot")
    return result


async def send_table(message, rows, header=None, title=None):
    text = render_table(rows, header)
    if title:
        text = f"<b>{escape_html(title)}</b>\n{text}"

    try:
        return await _rich_table(message, rows, header, title, text)
    except Exception:
        logger.debug("Could not send rich table; using preformatted text", exc_info=True)

    return await answer(message, text)


_PROCESS_STARTED = __import__("time").time()

KAOMOJI = (
    "(｡◕‿◕｡)", "(◕‿◕✿)", "ʕ•ᴥ•ʔ", "(ᵔᴥᵔ)", "(¬‿¬)", "(✿◠‿◠)", "ヽ(•‿•)ノ",
    "(•̀ᴗ•́)و", "(＾▽＾)", "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧", "¯\\_(ツ)_/¯", "(っ˘ω˘ς)", "(＾• ω •＾)",
    "(=^･ω･^=)", "(˘▾˘~)", "(づ｡◕‿‿◕｡)づ", "(•ө•)♡", "٩(◕‿◕｡)۶", "(o^▽^o)",
)


def ascii_face() -> str:
    """Random kaomoji"""
    return escape_html(random.choice(KAOMOJI))


def get_args_split_by(message: Any, separator: str = ",") -> List[str]:
    """Command arguments split by `separator`, stripped and without empty items"""
    raw = get_args_raw(message) or ""
    return [part.strip() for part in raw.split(separator) if part.strip()]


def remove_html(text: str, escape: bool = False, keep_emojis: bool = False) -> str:
    """Strip HTML tags from `text`; optionally keep custom emoji tags"""
    import html as html_lib
    import re as re_lib

    keep = r"(?!/?(?:emoji|tg-emoji)\b)" if keep_emojis else ""
    stripped = re_lib.sub(rf"<{keep}/?[^>]*?>", "", str(text))
    return escape_html(html_lib.unescape(stripped)) if escape else html_lib.unescape(stripped)


def check_url(url: str) -> bool:
    """Whether `url` looks like an absolute http(s) link"""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(str(url))
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def get_git_hash() -> Union[str, bool]:
    """Commit hash of the running Shizu checkout, False outside of git"""
    try:
        return git.Repo(os.path.dirname(get_base_dir())).head.commit.hexsha
    except Exception:
        return False


def formatted_uptime() -> str:
    """Time since Shizu was started, like `1 day, 2:03:04`"""
    import datetime
    import time as time_lib

    return str(datetime.timedelta(seconds=round(time_lib.time() - _PROCESS_STARTED)))


def uptime() -> int:
    """Seconds since Shizu was started"""
    import time as time_lib

    return round(time_lib.time() - _PROCESS_STARTED)


def get_named_platform() -> str:
    """Human readable name of the host platform"""
    import platform as platform_lib

    named = get_platform()
    if named != "🖥️ VDS":
        return named
    system = platform_lib.system()
    if system == "Darwin":
        return "🍏 macOS"
    if system == "Linux":
        with contextlib.suppress(Exception):
            with open("/etc/os-release", encoding="utf-8") as file:
                info = dict(
                    line.strip().split("=", 1) for line in file if "=" in line
                )
            return f"🐧 {info.get('PRETTY_NAME', 'Linux').strip(chr(34))}"
        return "🐧 Linux"
    return f"💻 {system or 'Unknown'}"


def get_entity_url(entity: Any, openmessage: bool = False) -> str:
    """Link to a user, chat or channel"""
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}"
    entity_id = getattr(entity, "id", entity)
    is_user = hasattr(entity, "first_name") or type(entity).__name__ == "User"
    if is_user or isinstance(entity, int) and entity > 0:
        return (
            f"tg://openmessage?user_id={entity_id}"
            if openmessage
            else f"tg://user?id={entity_id}"
        )
    channel_id = str(entity_id)
    channel_id = channel_id[4:] if channel_id.startswith("-100") else channel_id.lstrip("-")
    return f"https://t.me/c/{channel_id}"


def get_link(entity: Any) -> str:
    """Link to a user or chat"""
    return get_entity_url(entity)


def get_message_link(message: Any, chat: Any = None) -> str:
    """Public or private link to a message"""
    chat = chat or getattr(message, "chat", None)
    message_id = getattr(message, "id", None)
    if getattr(message, "is_private", False) or type(chat).__name__ == "User":
        chat_id = getattr(chat, "id", None) or getattr(message, "chat_id", None)
        return f"tg://openmessage?user_id={chat_id}&message_id={message_id}"
    if username := getattr(chat, "username", None):
        return f"https://t.me/{username}/{message_id}"
    chat_id = str(getattr(chat, "id", None) or getattr(message, "chat_id", ""))
    chat_id = chat_id[4:] if chat_id.startswith("-100") else chat_id.lstrip("-")
    return f"https://t.me/c/{chat_id}/{message_id}"


def get_topic(message: Any) -> Union[int, None]:
    """Forum topic id of a message, None outside of topics"""
    if is_telethon_message(message):
        reply_to = getattr(message, "reply_to", None)
        if reply_to and getattr(reply_to, "forum_topic", False):
            return getattr(reply_to, "reply_to_top_id", None) or reply_to.reply_to_msg_id
        return None
    if getattr(message, "is_topic_message", False):
        return getattr(message, "message_thread_id", None)
    return None


async def get_user(message: Any) -> Any:
    """Sender of a message as a user entity (None for anonymous senders)"""
    if message is None:
        return None
    if is_telethon_message(message):
        try:
            return await message.get_sender()
        except Exception:
            return None
    return getattr(message, "from_user", None) or getattr(message, "sender_chat", None)


def _client_of(message: Any):
    return getattr(message, "_client", None) or getattr(message, "client", None)


async def answer_file(
    message: Any,
    file: Any,
    caption: str = None,
    **kwargs,
) -> Any:
    """Send `file` to the chat of `message`; an outgoing command message is deleted"""
    client = _client_of(message)
    if is_telethon_message(message):
        kwargs.setdefault("parse_mode", "html")
        reply_to = kwargs.pop("reply_to", None) or (
            message.reply_to_msg_id if message.out else message.id
        )
        sent = await client.send_file(
            message.chat_id, file, caption=caption, reply_to=reply_to, **kwargs
        )
        if message.out:
            with contextlib.suppress(Exception):
                await message.delete()
        return sent

    kwargs.pop("force_document", None)
    kwargs.pop("attributes", None)
    reply_to = getattr(getattr(message, "reply_to_message", None), "id", None)
    if not getattr(message, "outgoing", False):
        reply_to = message.id
    sent = await client.send_document(
        message.chat.id, file, caption=caption, reply_to_message_id=reply_to, **kwargs
    )
    if getattr(message, "outgoing", False):
        with contextlib.suppress(Exception):
            await message.delete()
    return sent


async def dnd(client: Any, peer: Any, archive: bool = True) -> bool:
    """Mute `peer` forever and optionally move it to the archive"""
    try:
        if hasattr(client, "get_input_entity"):
            from telethon.tl import functions as tl_functions, types as tl_types

            entity = await client.get_input_entity(peer)
            await client(
                tl_functions.account.UpdateNotifySettingsRequest(
                    peer=tl_types.InputNotifyPeer(entity),
                    settings=tl_types.InputPeerNotifySettings(
                        show_previews=False, silent=True, mute_until=2**31 - 1
                    ),
                )
            )
            if archive:
                await client(
                    tl_functions.folders.EditPeerFoldersRequest(
                        [tl_types.InputFolderPeer(entity, folder_id=1)]
                    )
                )
            return True

        from pyrogram.raw import functions as raw_functions, types as raw_types

        entity = await client.resolve_peer(peer)
        await client.invoke(
            raw_functions.account.UpdateNotifySettings(
                peer=raw_types.InputNotifyPeer(peer=entity),
                settings=raw_types.InputPeerNotifySettings(
                    show_previews=False, silent=True, mute_until=2**31 - 1
                ),
            )
        )
        if archive:
            await client.archive_chats(peer)
        return True
    except Exception:
        logging.getLogger(__name__).debug("dnd failed for %s", peer, exc_info=True)
        return False


async def _set_chat_photo(client: Any, entity: Any, avatar: str) -> None:
    data = avatar
    if check_url(avatar):
        response = await run_sync(requests.get, avatar, timeout=30)
        response.raise_for_status()
        data = io.BytesIO(response.content)
        data.name = "avatar.jpg"
    from telethon.tl.functions.channels import EditPhotoRequest

    uploaded = await client.upload_file(data)
    await client(EditPhotoRequest(entity, uploaded))


async def asset_channel(
    client: Any,
    title: str,
    description: str,
    *,
    channel: bool = False,
    silent: bool = False,
    archive: bool = False,
    invite_bot: bool = False,
    avatar: str = None,
    ttl: int = None,
    _folder: str = None,
) -> Tuple[Any, bool]:
    """Find or create a service chat named `title`; returns `(entity, created)`"""
    from shizu import database

    assets = database.db.get("shizu.assets", "chats", {})
    if title in assets:
        with contextlib.suppress(Exception):
            return await client.get_entity(assets[title]), False

    async for dialog in client.iter_dialogs():
        if dialog.is_channel and dialog.title == title and dialog.entity.creator:
            assets[title] = dialog.entity.id
            database.db.set("shizu.assets", "chats", assets)
            return dialog.entity, False

    from telethon.tl.functions.channels import (
        CreateChannelRequest,
        EditAdminRequest,
        InviteToChannelRequest,
    )
    from telethon.tl.types import ChatAdminRights

    result = await client(
        CreateChannelRequest(
            title=title, about=description, megagroup=not channel, ttl_period=ttl
        )
    )
    entity = result.chats[0]
    assets[title] = entity.id
    database.db.set("shizu.assets", "chats", assets)

    if invite_bot:
        with contextlib.suppress(Exception):
            bot_username = database.db.get("shizu.bot", "username", None)
            bot_entity = await client.get_entity(bot_username) if bot_username else None
            if bot_entity:
                await client(InviteToChannelRequest(entity, [bot_entity]))
                await client(
                    EditAdminRequest(
                        entity,
                        bot_entity,
                        ChatAdminRights(
                            post_messages=True,
                            edit_messages=True,
                            delete_messages=True,
                            ban_users=True,
                            invite_users=True,
                            pin_messages=True,
                            change_info=True,
                        ),
                        "Shizu",
                    )
                )
    if avatar:
        with contextlib.suppress(Exception):
            await _set_chat_photo(client, entity, avatar)
    if silent or archive:
        await dnd(client, entity, archive)
    return entity, True


async def asset_forum_topic(
    client: Any,
    db: Any,
    peer: Any,
    title: str,
    description: str = None,
    icon_emoji_id: int = None,
    invite_bot: bool = False,
) -> Any:
    """Find or create a forum topic named `title` in `peer`"""
    from telethon.tl.functions.channels import (
        CreateForumTopicRequest,
        GetForumTopicsRequest,
        ToggleForumRequest,
    )

    entity = await client.get_entity(peer)
    if not getattr(entity, "forum", False):
        await client(ToggleForumRequest(entity, True))
    topics = await client(GetForumTopicsRequest(entity, offset_date=None, offset_id=0, offset_topic=0, limit=100))
    for topic in topics.topics:
        if getattr(topic, "title", None) == title:
            return topic
    result = await client(
        CreateForumTopicRequest(
            channel=entity,
            title=title,
            icon_emoji_id=icon_emoji_id,
            random_id=random.randint(1, 2**62),
        )
    )
    topic_id = next(
        u.id for u in result.updates if type(u).__name__ == "UpdateMessageID"
    )
    topics = await client(GetForumTopicsRequest(entity, offset_date=None, offset_id=0, offset_topic=0, limit=100))
    topic = next((t for t in topics.topics if t.id == topic_id), None)
    if description and topic is not None:
        with contextlib.suppress(Exception):
            await client.send_message(entity, description, reply_to=topic.id)
    return topic


def get_platform_name() -> str:
    """Human readable name of the host platform"""
    return get_named_platform()


def get_entity_id(entity: Any) -> int:
    """Marked peer id of a user, chat or channel (channels get the -100 prefix)"""
    if isinstance(entity, int):
        return entity
    try:
        from telethon import utils as tl_utils

        return tl_utils.get_peer_id(entity)
    except Exception:
        return getattr(entity, "id", entity)


async def get_target(message: Any, arg_no: int = 0) -> Union[int, None]:
    """User id the command targets: an argument (@username / id) or the replied sender"""
    client = _client_of(message)
    args = get_args(message)
    if isinstance(args, str):
        args = args.split()
    if len(args) > arg_no:
        target = args[arg_no]
        try:
            entity = await client.get_entity(int(target) if target.lstrip("-").isdigit() else target)
            return get_entity_id(entity)
        except Exception:
            if target.lstrip("-").isdigit():
                return int(target)
    if is_telethon_message(message) and message.is_reply:
        reply = await message.get_reply_message()
        return getattr(reply, "sender_id", None)
    reply = getattr(message, "reply_to_message", None)
    user = getattr(reply, "from_user", None)
    return getattr(user, "id", None)


async def set_avatar(client: Any, peer: Any, avatar: Any) -> bool:
    """Set the photo of a chat or channel from a URL, path or bytes"""
    try:
        entity = await client.get_entity(peer)
        await _set_chat_photo(client, entity, avatar)
        return True
    except Exception:
        logging.getLogger(__name__).debug("set_avatar failed for %s", peer, exc_info=True)
        return False


PLACEHOLDERS: dict = {}


def register_placeholder(name: str, callback: Any, description: str = None) -> None:
    """Make `{name}` available in the custom `.info` message; `callback` returns its value"""
    PLACEHOLDERS[name] = (callback, description)


async def get_placeholders() -> dict:
    """Current values of all registered placeholders"""
    values = {}
    for name, (callback, _) in list(PLACEHOLDERS.items()):
        try:
            value = callback() if callable(callback) else callback
            if asyncio.iscoroutine(value):
                value = await value
        except Exception:
            logging.getLogger(__name__).debug("placeholder %s failed", name, exc_info=True)
            value = ""
        values[name] = value
    return values
