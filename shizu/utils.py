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

# some piece of code taken from: https://github.com/hikariatama/Hikka/blob/master/hikka/utils.py

import asyncio
import logging
import requests
import functools
import random
import atexit
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


from . import database


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


def get_args(message: typing.Union[Message, str]) -> str:
    """
    Get arguments from message.
    """
    if not (message := getattr(message, "text", message)):
        return ""

    args = message.split()[1:]
    return " ".join(args) if args else ""


def restart():
    """Restart the bot"""
    return atexit.register(os.execl(sys.executable, sys.executable, "-m", "shizu"))


def get_args_raw(message: typing.Union[Message, str]) -> str:
    """
    Get the parameters to the command as a raw string (not split)
    :param message: Message or string to get arguments from
    :return: Raw string of arguments
    """
    if not (message := getattr(message, "text", message)):
        return False

    return args[1] if len(args := message.split(maxsplit=1)) > 1 else ""


def get_args_html(message: typing.Union[Message, str]) -> str:
    """
    Get arguments from message in html format.
    """
    try:
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
    app = message._client
    reply = message.reply_to_message

    if doc:
        app.me = await app.get_me()
        messages.append(await message.reply_document(response, **kwargs))
        return messages

    if photo_:
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
                response, reply_to_message_id=reply.id if reply else None, **kwargs
            )
        )
        return messages

    if isinstance(response, str):
        info = await app.parser.parse(response, kwargs.get("parse_mode", None))
        text, entities = str(info["message"]), info.get("entities", [])
        if len(text) >= 4096:
            try:
                strings = [
                    txt
                    async for txt in smart_split(app, escape_html(text), entities, 4096)
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
                        reply.id
                        if reply
                        else message.topic.id if message.topic else None
                    ),
                    **kwargs,
                )
                if reply_markup
                else (
                    await message.edit(
                        text=response,
                        **kwargs,
                    )
                    if message.outgoing or message.from_user.is_self
                    else await app.send_message(
                        message.chat.id,
                        response,
                        reply_to_message_id=(
                            message.topic.id
                            if message.topic
                            else None or reply.id if reply else None
                        ),
                        **kwargs,
                    )
                )
            )

    return messages[0]


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
    return (
        getattr(entity, "title", None)
        or entity.first_name
        or ("" + (f" {entity.last_name}" if entity.last_name else ""))
    )


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


def available_branches() -> List[str]:
    """Returns a list of available branches"""
    return [head.name.split("/")[-1] for head in git.Repo().heads]
