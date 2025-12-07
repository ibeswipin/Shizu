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

from shizu import loader, utils

logger = logging.getLogger(__name__)


@loader.module("ShizuOwner", "hikamoru")
class ShizuOwner(loader.Module):
    """Give owner permissions to users"""

    strings = {}

    async def close_(self, call):
        await call.delete()

    async def owner_off_on(self, call, status):
        self.db.set("shizu.owner", "status", status)
        await call.edit(
            self.strings("owner_on") if status else self.strings("owner_off"),
            reply_markup=[
                [
                    {
                        "text": (
                            self.strings("button_off")
                            if status
                            else self.strings("button_on")
                        ),
                        "callback": self.owner_off_on,
                        "kwargs": {"status": False} if status else {"status": True},
                    },
                    {
                        "text": self.strings("advanced_security"),
                        "callback": self.advanced_security,
                    },
                ],
                [{"text": self.strings("close"), "callback": self.close_}],
            ],
        )

    async def advanced_security(self, call):
        await call.edit(
            self.strings("advanced_security"),
            reply_markup=[
                [
                    {
                        "text": self.strings("add_owner"),
                        "input": self.strings("enter_id"),
                        "handler": self.add_owner_hnd,
                        "args": (call.inline_message_id,),
                    },
                    {
                        "text": self.strings("del_owner"),
                        "input": self.strings("enter_id"),
                        "handler": self.del_owner_hnd,
                        "args": (call.inline_message_id,),
                    },
                ],
                [
                    {
                        "text": self.strings("back"),
                        "callback": self.owner_off_on,
                        "kwargs": {
                            "status": self.db.get("shizu.owner", "status", False)
                        },
                    },
                    {"text": self.strings("close"), "callback": self.close_},
                ],
            ],
        )

    async def add_owner_hnd(self, call: "aiogram.types.CallbackQuery", query, cid):
        user_id = (await self.app.get_users(query)).id
        self.db.set(
            "shizu.me",
            "owners",
            list(set(self.db.get("shizu.me", "owners", []) + [int(user_id)])),
        )
        await call.edit(
            self.strings("successfull"),
            reply_markup=[
                [
                    {
                        "text": self.strings("back"),
                        "callback": self.advanced_security,
                    },
                    {"text": self.strings("close"), "callback": self.close_},
                ]
            ],
            inline_message_id=cid,
        )

    async def del_owner_hnd(self, call: "aiogram.types.CallbackQuery", query, cid):
        user_id = (await self.app.get_users(query)).id

        self.db.set(
            "shizu.me",
            "owners",
            list(set(self.db.get("shizu.me", "owners", [])) - {int(user_id)}),
        )
        await call.edit(
            self.strings("successfull"),
            reply_markup=[
                [
                    {
                        "text": self.strings("back"),
                        "callback": self.advanced_security,
                    },
                    {"text": self.strings("close"), "callback": self.close_},
                ]
            ],
            inline_message_id=cid,
        )

    @loader.command()
    async def ownermod(self, app, message):
        """Switch owner mode"""
        status = self.db.get("shizu.owner", "status", False)
        await message.answer(
            self.strings("owner_on") if status else self.strings("owner_off"),
            reply_markup=[
                [
                    {
                        "text": (
                            self.strings("button_off")
                            if status
                            else self.strings("button_on")
                        ),
                        "callback": self.owner_off_on,
                        "kwargs": {"status": False} if status else {"status": True},
                    },
                    {
                        "text": self.strings("advanced_security"),
                        "callback": self.advanced_security,
                    },
                ],
                [
                    {"text": self.strings("close"), "callback": self.close_},
                ],
            ],
        )

    @loader.command()
    async def addowner(self, app, message):
        """Give owner permissions to user - <user_id>"""

        user = utils.get_args(message)
        user_id = (await app.get_users(user)).id

        if not user:
            await utils.answer(message, self.strings("who"))
            return

        if user in self.db.get("shizu.me", "owners", []):
            await utils.answer(message, self.strings("already"))
            return

        self.db.set(
            "shizu.me",
            "owners",
            list(set(self.db.get("shizu.me", "owners", []) + [user_id])),
        )

        await utils.answer(
            message, self.strings("done").format((await app.get_users(user_id)).mention)
        )

    @loader.command()
    async def delowner(self, app, message):
        """Remove owner permissions from user - <user_id>"""

        user = utils.get_args(message)
        user_id = (await app.get_users(user)).id

        if not user:
            await utils.answer(message, self.strings("whod"))
            return

        if user_id not in self.db.get("shizu.me", "owners", []):
            await utils.answer(message, self.strings("not_owner"))
            return

        self.db.set(
            "shizu.me",
            "owners",
            list(set(self.db.get("shizu.me", "owners", [])) - {user_id}),
        )

        self.db.save()

        await utils.answer(
            message,
            self.strings("doned").format((await app.get_users(user_id)).mention),
        )

    @loader.command()
    async def owners(self, app, message):
        """Show owners"""
        owners = self.db.get("shizu.me", "owners", [])

        if not owners:
            await utils.answer(message, self.strings("no_owners"))
            return

        await utils.answer(
            message,
            self.strings("owners").format(
                "\n".join(
                    [f"• {(await app.get_users(user)).mention}" for user in owners]
                )
            ),
        )
