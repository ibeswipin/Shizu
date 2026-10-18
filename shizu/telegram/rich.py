import contextlib
import copy
import html
import io
import logging
import re
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import aiohttp
from pyrogram import enums, types

logger = logging.getLogger(__name__)

_BLOCKS = {
    "paragraph": "Paragraph",
    "heading": "SectionHeading",
    "pre": "Preformatted",
    "footer": "Footer",
    "divider": "Divider",
    "mathematical_expression": "MathematicalExpression",
    "anchor": "Anchor",
    "list": "List",
    "blockquote": "BlockQuotation",
    "expandable_blockquote": "ExpandableBlockQuotation",
    "pullquote": "PullQuotation",
    "collage": "Collage",
    "slideshow": "Slideshow",
    "table": "Table",
    "details": "Details",
    "map": "Map",
    "buttons": "Buttons",
    "animation": "Animation",
    "audio": "Audio",
    "document": "Document",
    "photo": "Photo",
    "video": "Video",
    "voice_note": "VoiceNote",
    "thinking": "Thinking",
}
_TEXT = {
    "bold": "Bold",
    "italic": "Italic",
    "underline": "Underline",
    "strikethrough": "Strikethrough",
    "spoiler": "Spoiler",
    "code": "Code",
    "subscript": "Subscript",
    "superscript": "Superscript",
    "marked": "Marked",
    "url": "Url",
    "custom_emoji": "CustomEmoji",
    "anchor": "Anchor",
    "anchor_link": "AnchorLink",
    "reference": "Reference",
    "reference_link": "ReferenceLink",
    "mathematical_expression": "MathematicalExpression",
    "date_time": "DateTime",
    "text_mention": "TextMention",
    "email_address": "EmailAddress",
    "phone_number": "PhoneNumber",
    "bank_card_number": "BankCardNumber",
    "mention": "Mention",
    "hashtag": "Hashtag",
    "cashtag": "Cashtag",
    "bot_command": "BotCommand",
    "button": "Button",
}
_MEDIA = {
    "photo": "Photo",
    "video": "Video",
    "animation": "Animation",
    "audio": "Audio",
    "document": "Document",
    "voice_note": "VoiceNote",
}
_CALLBACK_HTML = re.compile(
    r'<tg-button\b[^>]*\b(?:type\s*=\s*[\'"](?:callback_data|web_app|login_url|switch_inline_query)[\'"]|ref\s*=)',
    re.I,
)


def _text(value):
    if isinstance(value, list):
        return [_text(item) for item in value]
    if not isinstance(value, dict):
        return value
    kind = value["type"]
    fields = {key: item for key, item in value.items() if key != "type"}
    if "text" in fields:
        fields["text"] = _text(fields["text"])
    if kind == "text_mention":
        fields["user"] = types.User(id=fields["user"]["id"])
    if kind == "date_time":
        fields["date"] = datetime.fromtimestamp(fields.pop("unix_time"))
    if kind == "button":
        fields["button"] = _button(fields["button"])
    return getattr(types, "RichText" + _TEXT[kind])(**fields)


def _button(value):
    fields = dict(value)
    fields["text"] = _text(fields["text"])
    fields["style"] = enums.ButtonStyle(fields.get("style", "default"))
    return types.RichMessageButton(**fields)


def _media(value):
    fields = {key: item for key, item in value.items() if key != "type"}
    return getattr(types, "InputMedia" + _MEDIA[value["type"]])(**fields)


def _block(value):
    fields = {key: item for key, item in value.items() if key != "type"}
    kind = value["type"]
    for key in ("text", "credit", "summary"):
        if key in fields:
            fields[key] = _text(fields[key])
    if "blocks" in fields:
        fields["blocks"] = [_block(item) for item in fields["blocks"]]
    if "cells" in fields:
        fields["cells"] = [
            [
                types.RichBlockTableCell(**{**cell, "text": _text(cell.get("text"))})
                for cell in row
            ]
            for row in fields["cells"]
        ]
    if "items" in fields:
        fields["items"] = [
            types.InputRichBlockListItem(
                **{**item, "blocks": [_block(block) for block in item["blocks"]]}
            )
            for item in fields["items"]
        ]
    if "caption" in fields:
        caption = fields["caption"]
        fields["caption"] = (
            types.RichBlockCaption(
                **{key: _text(item) for key, item in caption.items()}
            )
            if kind
            in {
                "collage",
                "slideshow",
                "photo",
                "video",
                "audio",
                "animation",
                "document",
                "voice_note",
            }
            and isinstance(caption, dict)
            else _text(caption)
        )
    if "buttons" in fields:
        fields["buttons"] = [
            [_button(button) for button in row] for row in fields["buttons"]
        ]
    if kind in {"photo", "video", "audio", "animation", "document", "voice_note"}:
        fields[kind] = _media(fields[kind])
    return getattr(types, "InputRichBlock" + _BLOCKS[kind])(**fields)


def as_input(payload):
    if isinstance(payload, types.InputRichMessage):
        return payload
    fields = dict(payload)
    if fields.get("blocks"):
        fields["blocks"] = [_block(block) for block in fields["blocks"]]
    if fields.get("media"):
        fields["media"] = [
            types.InputRichMessageMedia(
                id=item["id"],
                media=_media(item["media"]),
            )
            for item in fields["media"]
        ]
    return types.InputRichMessage(**fields)


def as_dict(value):
    if isinstance(value, dict):
        return {key: as_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_dict(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, datetime):
        return int(value.timestamp())
    if not isinstance(value, types.Object):
        return value
    result = {
        key: as_dict(item)
        for key, item in vars(value).items()
        if not key.startswith("_") and item is not None
    }
    name = type(value).__name__
    if name.startswith("InputRichBlock") and name != "InputRichBlockListItem":
        result["type"] = next(
            key for key, suffix in _BLOCKS.items() if name == "InputRichBlock" + suffix
        )
    elif name.startswith("RichText"):
        result["type"] = next(
            key for key, suffix in _TEXT.items() if name == "RichText" + suffix
        )
    elif name.startswith("InputMedia"):
        result["type"] = next(
            key for key, suffix in _MEDIA.items() if name == "InputMedia" + suffix
        )
    if isinstance(value, types.RichTextTextMention):
        result["user"] = {
            "id": value.user.id,
            "is_bot": bool(value.user.is_bot),
            "first_name": value.user.first_name or "",
        }
    if isinstance(value, types.RichTextDateTime):
        result["unix_time"] = result.pop("date")
    if isinstance(value, types.RichTextCustomEmoji):
        result["custom_emoji_id"] = str(result["custom_emoji_id"])
    if isinstance(value, types.RichMessageButton) and result.get("style") == "default":
        result.pop("style")
    return result


def needs_bot(payload):
    if isinstance(payload, types.Object):
        payload = {
            key: value
            for key, value in vars(payload).items()
            if not key.startswith("_") and value is not None
        }
    if isinstance(payload, str):
        return bool(_CALLBACK_HTML.search(payload))
    if isinstance(payload, list):
        return any(needs_bot(item) for item in payload)
    if isinstance(payload, dict):
        return any(
            key in payload
            for key in (
                "callback_data",
                "callback",
                "data",
                "input",
                "web_app",
                "login_url",
                "switch_inline_query",
                "switch_inline_query_current_chat",
                "switch_inline_query_chosen_chat",
            )
        ) or any(needs_bot(value) for value in payload.values())
    return False


_TG_EMOJI_RE = re.compile(r'<tg-emoji\s+emoji-id="(\d+)">(.*?)</tg-emoji>', re.S)


def escape_button_label(text):
    """Escape a button label, keeping whitelisted <tg-emoji> custom-emoji tags."""
    text = text or ""
    parts, last = [], 0
    for match in _TG_EMOJI_RE.finditer(text):
        parts.append(html.escape(text[last : match.start()], quote=False))
        parts.append(
            f'<tg-emoji emoji-id="{match.group(1)}">'
            f"{html.escape(match.group(2), quote=False)}</tg-emoji>"
        )
        last = match.end()
    parts.append(html.escape(text[last:], quote=False))
    return "".join(parts)


def button_label_html(button):
    """Safe button label: escaped text with optional custom-emoji icons in front."""
    label = escape_button_label(button.get("text", ""))
    emoji = button.get("emoji") or []
    if isinstance(emoji, dict):
        emoji = [emoji]
    tags = "".join(
        f'<tg-emoji emoji-id="{item["id"]}">'
        f"{html.escape(item.get('fallback') or '⭐', quote=False)}</tg-emoji>"
        for item in emoji
        if str(item.get("id", "")).isdigit()
    )
    if tags:
        return f"{tags} {label}" if label else tags
    return label


def button_rows(markup):
    rows = ""
    for i, row in enumerate(markup):
        rows += "<tg-button-row>"
        for j, button in enumerate(row):
            button["ref"] = f"b{i}_{j}"
            rows += (
                f'<tg-button ref="{button["ref"]}">'
                f"{button_label_html(button)}</tg-button>"
            )
        rows += "</tg-button-row>"
    return rows


def form_html(text, markup):
    paragraphs = "".join(
        f"<p>{part.strip().replace(chr(10), '<br>')}</p>"
        for part in text.split("\n\n")
        if part.strip()
    )
    return {"html": paragraphs + button_rows(markup)}


def _with_url_buttons(payload, markup):
    rows = [[button for button in row if "url" in button] for row in markup or []]
    rows = [row for row in rows if row]
    if not rows:
        return payload
    payload = copy.deepcopy(as_dict(payload))
    if "html" in payload:
        for row in rows:
            payload["html"] += (
                "<tg-button-row>"
                + "".join(
                    f'<tg-button type="url" url="{html.escape(button["url"], quote=True)}">'
                    f"{button_label_html(button)}</tg-button>"
                    for button in row
                )
                + "</tg-button-row>"
            )
    elif "blocks" in payload:
        for row in rows:
            payload["blocks"].append(
                {
                    "type": "buttons",
                    "buttons": [
                        [
                            {"text": button["text"], "url": button["url"]}
                            for button in row
                        ]
                    ],
                }
            )
    else:
        raise ValueError("URL buttons require rich HTML or blocks")
    return payload


async def can_send_direct(app):
    if not hasattr(app, "send_rich_message"):
        return False
    try:
        me = await app.get_me()
        return bool(me.is_premium)
    except Exception:
        logger.debug("Could not check account Premium status", exc_info=True)
        return False


_URL_MEDIA_CACHE = {}


def _is_url(source):
    return isinstance(source, str) and source.startswith(("http://", "https://"))


async def _account_payload(payload):
    if isinstance(payload, str) or not any(
        _is_url(media["media"]) for media in _media_items(as_dict(payload))
    ):
        return payload
    payload = copy.deepcopy(as_dict(payload))
    for media in _media_items(payload):
        source = media["media"]
        if not _is_url(source):
            continue
        data = _URL_MEDIA_CACHE.get(source)
        if data is None:
            async with aiohttp.ClientSession() as session, session.get(source) as response:
                response.raise_for_status()
                data = await response.read()
            if len(_URL_MEDIA_CACHE) >= 16:
                _URL_MEDIA_CACHE.pop(next(iter(_URL_MEDIA_CACHE)))
            _URL_MEDIA_CACHE[source] = data
        file = io.BytesIO(data)
        file.name = PurePosixPath(urlsplit(source).path).name or media["type"]
        media["media"] = file
    return payload


async def send_direct(app, message, payload, *, reply_to_message_id=None, prev=True):
    chat_id = message if isinstance(message, int) else message.chat.id
    rich = not isinstance(payload, str)
    kwargs = (
        {"rich_message": as_input(await _account_payload(payload))}
        if rich
        else {"text": payload, "parse_mode": "html"}
    )
    outgoing = not isinstance(message, int) and (
        getattr(message, "outgoing", False)
        or getattr(getattr(message, "from_user", None), "is_self", False)
    )
    if outgoing and prev:
        try:
            return await app.edit_message_text(chat_id, message.id, **kwargs)
        except Exception as error:
            if getattr(error, "ID", None) == "MESSAGE_NOT_MODIFIED":
                return message
            if getattr(error, "ID", None) == "PREMIUM_ACCOUNT_REQUIRED":
                raise
            logger.debug("Could not edit command into rich response", exc_info=True)
    reply_id = reply_to_message_id
    if reply_id is None and not isinstance(message, int):
        reply_id = (
            getattr(message, "reply_to_message_id", None) if outgoing else message.id
        )
    send = app.send_rich_message if rich else app.send_message
    sent = await send(
        chat_id=chat_id,
        message_thread_id=getattr(message, "message_thread_id", None),
        direct_messages_topic_id=getattr(message, "direct_messages_topic_id", None),
        reply_parameters=types.ReplyParameters(message_id=reply_id)
        if reply_id
        else None,
        **kwargs,
    )
    if outgoing and prev and sent:
        with contextlib.suppress(Exception):
            await message.delete()
    return sent


async def inline_payload(inline, payload):
    payload = copy.deepcopy(as_dict(payload))
    cache = getattr(inline, "_rich_media_cache", None)
    if cache is None:
        cache = inline._rich_media_cache = {}
    for media in _media_items(payload):
        source, kind = media["media"], media["type"]
        method = "voice" if kind == "voice_note" else kind
        if isinstance(source, str) and not source.startswith(("http://", "https://")):
            continue
        key = (getattr(inline, "bot_id", None), kind, source)
        file_id = cache.get(key)
        if not file_id:
            uploaded = await getattr(inline.bot, "send_" + method)(
                inline._db.get("shizu.chat", "logs") or inline._me,
                **{method: source},
                disable_notification=True,
            )
            try:
                attachment = getattr(uploaded, method)
                file_id = (
                    attachment[-1].file_id if kind == "photo" else attachment.file_id
                )
                if len(cache) >= 128:
                    cache.pop(next(iter(cache)))
                cache[key] = file_id
            finally:
                with contextlib.suppress(Exception):
                    await inline.bot.delete_message(
                        uploaded.chat.id, uploaded.message_id
                    )
        media["media"] = file_id
    return payload


def _media_items(value):
    if isinstance(value, dict):
        if value.get("type") in _MEDIA and "media" in value:
            yield value
        else:
            for item in value.values():
                yield from _media_items(item)
    elif isinstance(value, list):
        for item in value:
            yield from _media_items(item)


async def send_rich(
    message,
    payload,
    fallback_text="",
    *,
    app=None,
    inline=None,
    reply_markup=None,
    reply_to_message_id=None,
    prev=True,
    **form_kwargs,
):
    app = app or message._client
    inline = inline or getattr(app, "_inline", None)
    if isinstance(reply_markup, dict):
        reply_markup = [[reply_markup]]
    elif reply_markup and isinstance(reply_markup[0], dict):
        reply_markup = [reply_markup]
    if (
        not needs_bot(payload)
        and not needs_bot(reply_markup)
        and await can_send_direct(app)
    ):
        try:
            return await send_direct(
                app,
                message,
                _with_url_buttons(payload, reply_markup),
                reply_to_message_id=reply_to_message_id,
                prev=prev,
            )
        except Exception:
            logger.debug(
                "Could not send rich response from Premium account; using inline bot",
                exc_info=True,
            )
    if inline is None:
        raise RuntimeError("Inline bot is unavailable for rich messages")
    if reply_to_message_id is None and not isinstance(message, int):
        outgoing = getattr(message, "outgoing", False) or getattr(
            getattr(message, "from_user", None), "is_self", False
        )
        reply_to_message_id = (
            getattr(message, "reply_to_message_id", None) if outgoing else message.id
        ) or getattr(message, "message_thread_id", None)
    result = await inline.form(
        text=fallback_text,
        message=message,
        rich_message=await inline_payload(inline, payload),
        reply_markup=reply_markup,
        msg_id=reply_to_message_id,
        prev=prev,
        _rich_routed=True,
        **form_kwargs,
    )
    if result is False:
        raise RuntimeError("Could not send rich response through the inline bot")
    return result
