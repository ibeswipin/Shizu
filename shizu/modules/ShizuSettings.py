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

import re
import os

import sys

from loguru import logger
from .. import loader, utils
from pyrogram import Client, types

from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.errors.rpcerrorlist import UpdateAppToLoginError


@loader.module(name="ShizuSettings", author="shizu")
class ShizuSettings(loader.Module):
    """Settings for Shizu userbot"""

    strings = {}

    async def on_load(self, app):
        if not self.db.get("shizu.me", "me", None):
            id_ = (await app.get_me()).id
            self.db.set("shizu.me", "me", id_)

        app.is_tl_enabled = utils.is_tl_enabled()

    def markup_(self, purpose):
        return [
            [
                {
                    "text": self.strings["yes_button"],
                    "callback": self.yes,
                    "args": (purpose,),
                },
                {
                    "text": self.strings["no_button"],
                    "callback": self.close,
                    "args": (purpose,),
                },
            ]
        ]

    async def close(self, call, _):
        await call.delete()

    @loader.command()
    async def setprefix(self, app: Client, message: types.Message):
        """To change the prefix, you can have several pieces separated by a space. Usage: setprefix (prefix) [prefix, ...]"""
        args = utils.get_args_raw(message)

        if not (args := args.split()):
            return await message.answer(self.strings("ch_prefix"))

        self.db.set("shizu.loader", "prefixes", list(set(args)))
        prefixes = ", ".join(f"<code>{prefix}</code>" for prefix in args)
        return await message.answer(self.strings("prefix_changed").format(prefixes))

    @loader.command()
    async def addalias(self, app: Client, message: types.Message):
        """Add an alias. Usage: addalias (new alias) (command)"""

        args = utils.get_args_raw(message)

        if not (args := args.lower().split(maxsplit=1)):
            return await message.answer(self.strings("which_alias"))

        if len(args) != 2:
            return await message.answer(self.strings("inc_args"))

        aliases = self.all_modules.aliases
        if args[0] in aliases:
            return await message.answer(self.strings("alias_already"))

        if not self.all_modules.command_handlers.get(args[1]):
            return await message.answer(self.strings("no_command"))

        aliases[args[0]] = args[1]
        self.db.set("shizu.loader", "aliases", aliases)

        return await message.answer(
            self.strings("alias_done").format(
                args[0],
                args[1],
            )
        )

    @loader.command()
    async def delalias(self, app: Client, message: types.Message):
        """Delete the alias. Usage: delalas (alias)"""

        args = utils.get_args_raw(message)

        if not (args := args.lower()):
            return await message.answer(self.strings("which_delete"))

        aliases = self.all_modules.aliases
        if args not in aliases:
            return await message.answer(self.strings("no_such_alias"))

        del aliases[args]
        self.db.set("shizu.loader", "aliases", aliases)

        return await message.answer(self.strings("alias_removed").format(args))

    @loader.command()
    async def aliases(self, app: Client, message: types.Message):
        """Show all aliases"""
        if aliases := self.all_modules.aliases:
            return await message.answer(
                "🗄 List of all aliases:\n"
                + "\n".join(
                    f"• <code>{alias}</code> ➜ {command}"
                    for alias, command in aliases.items()
                ),
            )
        else:
            return await message.answer(self.strings("no_such_alias"))

    async def yes(self, call, purpose):
        if purpose == "enabletlmode":
            phone = phone = f"+{(await self.app.get_me()).phone_number}"
            api_id = self.app.api_id
            api_hash = self.app.api_hash

            client = TelegramClient(
                "shizu-tl",
                api_id,
                api_hash,
                device_model="MacBook Pro",
                app_version="11.12.0",
                system_version="14.0",
                lang_code="en",
                system_lang_code="en-US"
            )
            await client.connect()

            try:
                login = await client.send_code_request(phone=phone)
                await client.disconnect()
            except FloodWaitError as e:
                await client.disconnect()
                return await call.edit(f"Too many attempts, please wait  {e.seconds}")
            except UpdateAppToLoginError:
                await client.disconnect()
                return await call.edit(
                    "❌ <b>UpdateAppToLoginError</b>\n\n"
                    "Telegram requires app update. Please:\n"
                    "1. Update Telethon library: <code>pip install --upgrade telethon</code>\n"
                    "2. Or try using official Telegram app to login first"
                )

            async for message in self.app.get_chat_history(
                777000, limit=1, offset_id=-1
            ):
                t = message.text

            code = re.findall(r"(\d{5})", t)[0]

            global _client
            _client = TelegramClient(
                "shizu-tl",
                api_id,
                api_hash,
                device_model="MacBook Pro",
                app_version="11.12.0",
                system_version="14.0",
                lang_code="en",
                system_lang_code="en-US"
            )

            await _client.connect()

            try:
                await _client.sign_in(
                    phone=f"+{(await self.app.get_me()).phone_number}",
                    code=code,
                    phone_code_hash=login.phone_code_hash,
                )

                await client.disconnect()

                await call.edit(self.strings["congratulations"])

            except SessionPasswordNeededError:
                await call.edit(
                    self.strings["enter_2fa"],
                    reply_markup=[
                        [
                            {
                                "text": "🔐 2FA",
                                "input": "👓 Your 2FA code",
                                "handler": self.twofa_handler,
                                "args": (
                                    login.phone_code_hash,
                                    call.inline_message_id,
                                ),
                            },
                        ],
                    ],
                )

        if purpose == "stopshizu":
            await call.edit(self.strings["shutted_down"])
            sys.exit(0)

    async def twofa_handler(
        self,
        call: "aiogram.types.CallbackQuery",
        query: str,
        phone_code_hash: str,
        inline_message_id: str,
    ):
        try:
            await _client.sign_in(
                phone=f"+{(await self.app.get_me()).phone_number}",
                password=query,
                phone_code_hash=phone_code_hash,
            )
            await call.edit(
                self.strings["congratulations"], inline_message_id=inline_message_id
            )
        except Exception as e:
            await _client.disconnect()
            os.remove("shizu-tl.session")
            await call.edit(f"❌ {e}", inline_message_id=inline_message_id)

    @loader.command()
    async def enabletlmode(self, app, message):
        """Enable telethon mode"""
        if utils.is_tl_enabled() is False:
            return await message.answer(
                self.strings["are_you_sure"],
                reply_markup=self.markup_("enabletlmode"),
            )

        await message.answer(self.strings["already_enabled"])

    @loader.command()
    async def stopshizu(self, app, message):
        """Just turn off the bot"""

        await message.answer(
            self.strings["are_sure_to_stop"],
            reply_markup=self.markup_("stopshizu"),
        )
