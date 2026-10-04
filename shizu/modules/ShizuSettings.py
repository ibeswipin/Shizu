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


import sys

from loguru import logger
from shizu import loader, utils
from pyrogram import Client, types

from shizu.telegram.exceptions import (
    AccountMismatch,
    TelegramConnectionError,
    TelethonSessionInvalid,
)
from shizu.telegram.services import TelegramConnectionService, TelegramDisconnectService


@loader.module(name="ShizuSettings", author="shizu")
class ShizuSettings(loader.Module):
    """Settings for Shizu userbot"""

    strings = {}

    async def on_load(self, app):
        if not self.db.get("shizu.me", "me", None):
            id_ = (await app.get_me()).id
            self.db.set("shizu.me", "me", id_)

        app.is_tl_enabled = utils.is_tl_enabled(app)

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

    async def close(self, call, purpose):
        if purpose == "enabletlmode" and getattr(self, "_connections", None):
            await self._connections.cancel((await self.app.get_me()).id)
        await call.delete()

    def _telethon_service(self) -> TelegramConnectionService:
        """Use one service per process so an outstanding 2FA step can be resumed."""
        if not getattr(self, "_connections", None):
            self._connections = getattr(
                self.app, "telethon_connections", None
            ) or TelegramConnectionService.from_environment(
                self.app.api_id, self.app.api_hash
            )
            self.app.telethon_connections = self._connections
        return self._connections

    async def _connected_telethon(self, result, call, inline_message_id=None):
        try:
            self.db.set("shizu.telethon", "enabled", True)
            self.db.set("shizu.telethon", "status", "active")
        finally:
            await result.client.disconnect()
        kwargs = {"inline_message_id": inline_message_id} if inline_message_id else {}
        await call.edit(self.strings["congratulations"], **kwargs)

    def _password_markup(self, inline_message_id):
        return [
            [
                {
                    "text": "🔐 2FA",
                    "input": "Telegram cloud password",
                    "handler": self.twofa_handler,
                    "args": (inline_message_id,),
                }
            ],
            [
                {
                    "text": self.strings["no_button"],
                    "callback": self.close,
                    "args": ("enabletlmode",),
                }
            ],
        ]

    @loader.command()
    async def setprefix(self, app: Client, message: types.Message):
        """Change the prefix. You can set several, separated by spaces. Usage: setprefix (prefix) [prefix, ...]"""
        args = utils.get_args_raw(message)

        if not (args := args.split()):
            return await message.answer(self.strings("ch_prefix"))

        self.db.set("shizu.loader", "prefixes", list(set(args)))
        prefixes = ", ".join(f"<code>{prefix}</code>" for prefix in args)
        return await message.answer(self.strings("prefix_changed").format(prefixes))

    @loader.command(aliases=["addalias", "delalias", "aliases"])
    async def alias(self, app: Client, message: types.Message):
        """[alias] [command] - Show aliases, add one (alias and command) or delete one (just the alias)"""
        args = utils.get_args_raw(message).lower().split()
        aliases = self.all_modules.aliases

        if not args:
            if not aliases:
                return await message.answer(self.strings("no_such_alias"))
            return await message.answer(
                "🗄 List of all aliases:\n"
                + "\n".join(
                    f"• <code>{alias}</code> ➜ {command}"
                    for alias, command in aliases.items()
                )
            )

        if len(args) == 1:
            if args[0] not in aliases:
                return await message.answer(self.strings("no_such_alias"))
            del aliases[args[0]]
            self.db.set("shizu.loader", "aliases", aliases)
            return await message.answer(self.strings("alias_removed").format(args[0]))

        if len(args) != 2:
            return await message.answer(self.strings("inc_args"))
        if args[0] in aliases:
            return await message.answer(self.strings("alias_already"))
        if not self.all_modules.command_handlers.get(args[1]):
            return await message.answer(self.strings("no_command"))

        aliases[args[0]] = args[1]
        self.db.set("shizu.loader", "aliases", aliases)
        return await message.answer(self.strings("alias_done").format(args[0], args[1]))

    async def yes(self, call, purpose):
        if purpose == "enabletlmode":
            try:
                result = await self._telethon_service().connect(
                    self.app, (await self.app.get_me()).id
                )
                if result.status == "need_2fa":
                    return await call.edit(
                        self.strings["enter_2fa"],
                        reply_markup=self._password_markup(call.inline_message_id),
                    )
                await self._connected_telethon(result, call)
            except TelegramConnectionError as error:
                await call.edit("❌ " + utils.escape_html(str(error)))

        if purpose == "stopshizu":
            await call.edit(self.strings["shutted_down"])
            sys.exit(0)

    async def twofa_handler(self, call, query: str, inline_message_id: str):
        """Resume the same QR login; never echo or persist the supplied password."""
        try:
            try:
                result = await self._telethon_service().connect(
                    self.app, (await self.app.get_me()).id, password=query
                )
                await self._connected_telethon(result, call, inline_message_id)
            except TelegramConnectionError as error:
                await call.edit(
                    "❌ " + utils.escape_html(str(error)),
                    inline_message_id=inline_message_id,
                    reply_markup=self._password_markup(inline_message_id),
                )
        except Exception as error:
            logger.warning("Telethon password handler failed: {}", type(error).__name__)
        finally:
            query = None

    @loader.command()
    async def disabletlmode(self, app: Client, message: types.Message):
        """Revoke the separate Telethon authorization and remove its encrypted session."""
        try:
            live_client = getattr(app, "tl", None)
            await TelegramDisconnectService(self._telethon_service()).disconnect(
                (await app.get_me()).id,
                client=live_client
                if live_client not in (None, "Not enabled")
                else None,
            )
        except TelegramConnectionError as error:
            return await message.answer("❌ " + utils.escape_html(str(error)))
        self.db.set("shizu.telethon", "enabled", False)
        self.db.set("shizu.telethon", "status", "disabled")
        app.is_tl_enabled = False
        if getattr(app, "tl", None) not in (None, "Not enabled"):
            await app.tl.disconnect()
        await message.answer(self.strings["telethon_disabled"])

    @loader.command()
    async def enabletlmode(self, app, message):
        """Enable Telethon mode"""
        live_client = getattr(app, "tl", None)
        if utils.is_tl_configured() and getattr(live_client, "connection_state", None):
            try:
                await self._telethon_service().verify(
                    live_client, (await app.get_me()).id
                )
            except (TelethonSessionInvalid, AccountMismatch):
                self.db.set("shizu.telethon", "enabled", False)
                self.db.set("shizu.telethon", "status", "invalid")
                app.is_tl_enabled = False
            except TelegramConnectionError as error:
                return await message.answer("❌ " + utils.escape_html(str(error)))
            else:
                app.is_tl_enabled = True
        if utils.is_tl_enabled(app) is False:
            return await message.answer(
                self.strings["are_you_sure"],
                reply_markup=self.markup_("enabletlmode"),
            )

        await message.answer(self.strings["already_enabled"])

    @loader.command()
    async def apiprotect(self, app: Client, message: types.Message):
        """Turn the protection against flood bans on or off"""
        enabled = not self.db.get("shizu.api", "protection", True)
        self.db.set("shizu.api", "protection", enabled)
        await message.answer(self.strings("api_on" if enabled else "api_off"))

    @loader.command(aliases=["stopshizu"])
    async def stop(self, app, message):
        """Turn off the bot"""

        await message.answer(
            self.strings["are_sure_to_stop"],
            reply_markup=self.markup_("stopshizu"),
        )

    @loader.command()
    async def purgecmd(self, app: Client, message: types.Message):
        """[user(-s)] - Delete message history starting from the replied message"""
        if not message.reply_to_message:
            await utils.answer(message, self.strings("from_where"))
            return

        from_users = set()
        args = utils.get_args(message)

        for arg in args:
            try:
                user = await app.get_users(arg)
                if isinstance(user, types.User):
                    from_users.add(user.id)
            except (ValueError, Exception):
                pass

        messages = []
        reply_id = message.reply_to_message.id
        current_id = message.id

        messages.append(current_id)

        async for msg in app.get_chat_history(
            chat_id=message.chat.id,
            limit=None,
            offset_id=current_id,
        ):
            if msg.id < reply_id:
                break

            if from_users:
                if not msg.from_user or msg.from_user.id not in from_users:
                    continue

            if hasattr(message.reply_to_message, "reply_to_top_id"):
                reply_top_id = getattr(
                    message.reply_to_message, "reply_to_top_id", None
                )
                if reply_top_id:
                    msg_top_id = (
                        getattr(msg.reply_to, "reply_to_top_id", None)
                        if msg.reply_to
                        else None
                    )
                    if msg_top_id != reply_top_id:
                        continue

            messages.append(msg.id)
            if len(messages) >= 99:
                await app.delete_messages(message.chat.id, messages)
                messages.clear()

        if messages:
            await app.delete_messages(message.chat.id, messages)

    @loader.command()
    async def delcmd(self, app: Client, message: types.Message):
        """Delete the replied message"""
        if message.reply_to_message:
            msg_to_delete = message.reply_to_message
        else:
            msg_to_delete = None
            async for msg in app.get_chat_history(
                message.chat.id, limit=1, offset_id=message.id
            ):
                msg_to_delete = msg
                break

            if not msg_to_delete:
                await utils.answer(message, self.strings("no_message_to_delete"))
                return

        await app.delete_messages(
            message.chat.id,
            [msg_to_delete.id, message.id],
        )
