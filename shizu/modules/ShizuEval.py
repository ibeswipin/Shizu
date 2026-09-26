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

import contextlib
import sys
from meval import meval
from pyrogram import Client, types

from shizu import loader, utils, logger


@loader.module(name="ShizuEval", author="hikamoru")
class EvaluatorMod(loader.Module):
    """Execute Python code"""
    
    
    strings = {}

    @loader.command(aliases=["e"])
    async def eval(self, app: Client, message: types.Message):
        """Execute Python code and return the result"""
        args = message.get_args_raw()

        try:
            result = await meval(args, globals(), **self.getattrs(app, message))

            return await message.answer(
                "<b>🖥 Code:</b>\n"
                f"<pre language='python'>{args}</pre>\n\n"
                f"✅ <b>Result:</b>\n"
                f"<code>{utils.escape_html(await self.censor(app, str(result)))}</code>",
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
                f"<pre language='python'>{args}</pre>\n\n"
                "🚫 <b>Result:</b>\n"
                f"<pre language='error'>{exc}</pre>",
            )

    async def _sessions(self, app: Client) -> list:
        if getattr(self, "_session_strings", None) is None:
            sessions = []
            with contextlib.suppress(Exception):
                sessions.append(await app.export_session_string())
            with contextlib.suppress(Exception):
                if utils.is_tl_enabled() and app.tl != "Not enabled":
                    from telethon.sessions import StringSession

                    sessions.append(StringSession.save(app.tl.session))
            self._session_strings = [s for s in sessions if s]
        return self._session_strings

    async def censor(self, app: Client, text: str) -> str:
        for session in await self._sessions(app):
            text = text.replace(session, "StringSession(**************************)")

        if token := self.db.get("shizu.bot", "token", None):
            text = text.replace(token, f'{token.split(":")[0]}:{"*" * 26}')

        return text

    def getattrs(self, app: Client, message: types.Message):
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
            "reply": message.reply_to_message,
            "r": message.reply_to_message,
            "utils": utils,
            "ruser": getattr(message.reply_to_message, "from_user", None),
        }
