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

import contextlib
import re
import sys

from meval import meval
from pyrogram import Client, types
from pyrogram.types.messages_and_media.message import Str
from telethon.sessions import StringSession

from shizu import loader, logger, utils


@loader.module(name="ShizuEval", author="hikamoru")
class EvaluatorMod(loader.Module):
    """Execute Python code"""

    strings = {}

    @loader.command(aliases=["e"])
    async def eval(self, app: Client, message: types.Message):
        """Execute Python code. Usage: e [--lang python|html|curl|...] <code>"""
        args = message.get_args_raw()

        try:
            language = None
            if args.split(maxsplit=1)[:1] == ["--lang"]:
                parts = args.split(maxsplit=2)
                if len(parts) != 3 or not re.fullmatch(
                    r"[A-Za-z][A-Za-z0-9_+.-]{0,31}", parts[1]
                ):
                    raise ValueError("Usage: e --lang <language> <code>")
                _, language, args = parts

            result = await meval(args, globals(), **self.getattrs(app, message))
            if isinstance(result, Str):
                result = result.html
                language = language or "html"
            language = language or "python"

            return await message.answer(
                "<b>🖥 Code:</b>\n"
                f"<pre language='python'>{utils.escape_html(args)}</pre>\n\n"
                f"✅ <b>Result:</b>\n"
                f"<pre language='{language}'>"
                f"{utils.escape_html(await self.censor(app, str(result)))}</pre>",
            )
        except Exception:
            item = logger.CustomException.from_exc_info(*sys.exc_info())
            exc = (
                "\n\n"
                + "\n".join(item.full_stack.splitlines()[:-1])
                + "\n\n"
                + "😵 "
                + item.full_stack.splitlines()[-1]
            )
            exc = await self.censor(app, exc)
            return await message.answer(
                "<b>🖥 Code:</b>\n"
                f"<pre language='python'>{utils.escape_html(args)}</pre>\n\n"
                "🚫 <b>Result:</b>\n"
                f"<pre language='error'>{exc}</pre>",
            )

    async def _sessions(self, app: Client) -> list:
        if getattr(self, "_session_strings", None) is None:
            sessions = []
            with contextlib.suppress(Exception):
                sessions.append(await app.export_session_string())
            with contextlib.suppress(Exception):
                client = getattr(app, "tl", None)
                # Mask credentials even when the connection is temporarily down.
                if getattr(client, "connection_state", None) is not None:
                    sessions.append(StringSession.save(client.session))
            self._session_strings = [s for s in sessions if s]
        return self._session_strings

    async def censor(self, app: Client, text: str) -> str:
        for session in await self._sessions(app):
            text = text.replace(session, "StringSession(**************************)")

        if token := self.db.get("shizu.bot", "token", None):
            text = text.replace(token, f"{token.split(':')[0]}:{'*' * 26}")

        return text

    def getattrs(self, app: Client, message: types.Message):
        reply = message.reply_to_message
        if isinstance(reply, types.Message):
            reply.text = utils.get_message_text(reply)
            reply.caption = utils.get_message_text(reply, caption=True)
        return {
            "self": self,
            "db": self.db,
            "app": app,
            "c": app,
            "tl": app.tl,
            "client": app,
            "bot": app,
            "message": message,
            "m": message,
            "chat": message.chat,
            "user": message.from_user,
            "reply": reply,
            "r": reply,
            "utils": utils,
            "ruser": getattr(reply, "from_user", None),
        }
