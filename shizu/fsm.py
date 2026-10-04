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

# ---------------------------------------------------------------------------

# Shizu Copyright (C) 2023-2024 hikamoru

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

import asyncio
import logging
from types import TracebackType

from pyrogram import Client, types


class Conversation:
    def __init__(self, app: Client, chat_id: str | int, purge: bool = False) -> None:
        """Initializing a class

        Parameters:
            app (``program.Client`):
                Client

            chat_id (`str` | `int`):
                The chat to send the message to

            purge (`bool`, optional):
                Delete messages after the dialog ends
        """
        self.app = app
        self.chat_id = chat_id
        self.purge = purge

        self.messages_to_purge: list[types.Message] = []

    async def __aenter__(self) -> "Conversation":
        return self

    async def __aexit__(
        self, exc_type: type, exc_value: Exception, exc_traceback: TracebackType
    ) -> bool:
        if all([exc_type, exc_value, exc_traceback]):
            logging.exception(exc_value)
        elif self.purge:
            await self._purge()

        return self.messages_to_purge.clear()

    async def ask(self, text: str, *args, **kwargs) -> types.Message:
        """Send a message

        Parameters:
            text (`str`):
                Message text

            args (`list`, optional):
                Arguments for sending a message

            kwargs (`dict`, optional):
                Parameters for sending a message
        """
        message = await self.app.send_message(self.chat_id, text, *args, **kwargs)

        self.messages_to_purge.append(message)
        return message

    async def ask_media(
        self, file_path: str, media_type: str, *args, **kwargs
    ) -> types.Message:
        """Send File

        Parameters:
            file_path (`str`):
                Link or path to the file

            media_type (`str`):
                The type of media being sent

            args (`list`, optional):
                Arguments for sending a message

            kwargs (`dict`, optional):
                Parameters for sending a message
        """
        available_media = [
            "animation",
            "audio",
            "document",
            "photo",
            "sticker",
            "video",
            "video_note",
            "voice",
        ]
        if media_type not in available_media:
            raise TypeError("This type of media is not supported")

        message = await getattr(self.app, f"send_{media_type}")(
            self.chat_id, file_path, *args, **kwargs
        )

        self.messages_to_purge.append(message)
        return message

    async def get_response(self, timeout: int = 30) -> types.Message:
        """Returns a response

        Parameter:
            timeout (`int`, optional):
                Response waiting time
        """
        for _ in range(timeout):
            async for response in self.app.get_chat_history(self.chat_id, limit=1):
                if not response.from_user or not response.from_user.is_self:
                    self.messages_to_purge.append(response)
                    return response

            await asyncio.sleep(1)

        raise RuntimeError("Response timeout expired")

    async def get_another_same(self) -> types.Message:
        """Returns a response"""
        return await self.get_response()

    async def _purge(self) -> bool:
        """Delete all sent and received messages"""
        for message in self.messages_to_purge:
            await message.delete()

        return True
