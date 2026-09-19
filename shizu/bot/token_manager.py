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
import re
import time
from typing import Union
from typing import Tuple

from pyrogram import errors

from shizu import fsm, utils
from shizu.bot.types import Item

FIND = True


logger = logging.getLogger(__name__)


class TokenManager(Item):
    """Class for managing bot tokens"""

    async def _find_bot(self) -> Union[Tuple[str, str], None]:
        """Find the bot"""

        async with fsm.Conversation(self._app, "@BotFather") as conv:
            logging.info("Checking for the presence of a bot...")

            try:
                await conv.ask("/cancel")
            except errors.UserIsBlocked:
                await self._app.unblock_user("@BotFather")

            await conv.get_response()
            await conv.ask("/mybots")

            time.sleep(1)

            r = await conv.get_response()

            time.sleep(1)

            if not r.reply_markup:
                return False

            data = r.reply_markup.inline_keyboard
            buttons_text = [button.text for row in data for button in row]

            buttons = [i for i in buttons_text if "shizu" in i]

            if not buttons:
                return False

            logger.info("Found bot: %s", buttons[0])

            resp = await conv.get_response()

            await resp.click(buttons[0])

            h2 = await conv.get_another_same()
            await h2.click(0)

            response = await conv.get_response()
            await self._app.send_message(buttons[0], "/start")
            if token_match := re.search(r"(\d+:[A-Za-z0-9_-]+)", response.text):
                return token_match[1]
            else:
                return None

    async def _create_bot(self) -> Union[str, None]:
        """Create and configure a bot"""

        logging.info("Started to search for a bot...")

        if token := await self._find_bot():
            logger.info("Found bot: %s", token)
            return token

        async with fsm.Conversation(self._app, "@BotFather", True) as conv:
            logging.info("The process of creating a new bot has begun...")

            try:
                await conv.ask("/cancel")
            except errors.UserIsBlocked:
                await self._app.unblock_user("@BotFather")

            await conv.get_response()

            await conv.ask("/newbot")

            response = await conv.get_response()

            error_phrases = ["That I cannot do.", "Sorry"]

            if any(phrase in response.text for phrase in error_phrases):
                logging.error(
                    "An error occurred when creating the bot. @BotFather's response:"
                )
                logging.error(response.text)

                if "too many attempts" in response.text:
                    seconds = response.text.split()[-2]
                    logger.error(f"Please repeat in {seconds} seconds")

            time.sleep(1)

            await conv.ask(
                f"🐙 Shizu UserBot of {utils.get_display_name(self._all_modules.me)[:45]}"
            )
            await conv.get_response()

            bot_username = f"shizu_{utils.random_id(6)}_bot"

            await conv.ask(bot_username)
            time.sleep(1)
            response = await conv.get_response()

            search = re.search(r"(?<=<code>)(.*?)(?=</code>)", response.text.html)
            if not search:
                logging.error("Произошла ошибка при создании бота. Ответ @BotFather:")
                return logging.error(response.text)

            token = search[0]

            await conv.ask("/setuserpic")
            await conv.get_response()

            await conv.ask(f"@{bot_username}")
            await conv.get_response()

            self._app.me = await self._app.get_me()

            await conv.ask_media("assets/bot.jpg", media_type="photo")

            time.sleep(1)

            await conv.get_response()

            await conv.ask("/setinline")
            await conv.get_response()

            await conv.ask(f"@{bot_username}")
            await conv.get_response()

            await conv.ask("shizu>>")
            await conv.get_response()

            time.sleep(1)

            await conv.ask("/setinlinefeedback")
            await conv.get_response()

            await conv.ask(f"@{bot_username}")
            await conv.get_response()

            time.sleep(1)

            await conv.ask("1/1000")
            await conv.get_response()

            await conv.ask("/setinlinefeedback")
            await conv.get_response()

            time.sleep(1)

            await conv.ask(f"@{bot_username}")
            await conv.get_response()

            await conv.ask("Enabled")
            await conv.get_response()

            logger.info(f"Bot successfully created @{bot_username}")
            await self._app.send_message(bot_username, "/start")

        return token
