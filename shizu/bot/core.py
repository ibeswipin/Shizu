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
import contextlib
import sys

from aiogram import Bot, Dispatcher, exceptions, types as aiotypes
from pyrogram import Client

from typing import Union, NoReturn

from shizu.bot.events import Events
from shizu.bot.token_manager import TokenManager

from shizu import database, types

with contextlib.suppress(Exception):
    bot = Bot(token=database.db.get("shizu.bot", "token", None), parse_mode="html")
    dp = Dispatcher(bot)


class BotManager(Events, TokenManager):
    """Bot manager"""

    def __init__(
        self, app: Client, db: database.Database, all_modules: types.ModulesManager
    ) -> None:
        """Initializing a class

        Parameters:
            app (``program.Client`):
        Client

                    db (``database.Database`):
        Database

                    all_modules (`loader.Modules"):
        Modules
        """
        super().__init__()
        self._app = app
        self._app._inline = self
        self._db = db
        self._all_modules = all_modules
        self._forms = {}
        self._markup_ttl = 60 * 60 * 24
        self._custom_map = {}
        self._me = self._db.get("shizu.me", "me", None)
        self._token = self._db.get("shizu.bot", "token", None)

    async def load(self) -> Union[bool, NoReturn]:
        """Loads the bot manager"""
        if not self._token:
            self._token = await self._create_bot()
            if self._token is False:
                error_text = "A user bot needs a bot. Solve the problem of creating a bot and start the user bot again"
                logging.error(error_text)
                return sys.exit(1)

            self._db.set("shizu.bot", "token", self._token)

        try:
            self.bot = Bot(self._token, parse_mode="html")
        except (exceptions.ValidationError, exceptions.Unauthorized):
            logging.error("Invalid token. Attempt to recreate the token")

            self._db.set("shizu.bot", "token", self._token)
            return await self.load()

        self._dp = Dispatcher(self.bot)
        self._dp.register_message_handler(
            self._message_handler, lambda _: True, content_types=["any"]
        )
        self._dp.register_chosen_inline_handler(
            self._chosen_inline_handler, lambda chosen_inline_query: True
        )
        self._dp.register_inline_handler(self._inline_handler, lambda _: True)
        self._dp.register_callback_query_handler(
            self._callback_query_handler, lambda _: True
        )

        asyncio.ensure_future(self._dp.start_polling())

        self.bot.manager = self
        return True
