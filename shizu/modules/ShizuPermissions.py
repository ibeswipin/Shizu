# Shizu Copyright (C) 2023-2024  AmoreForever
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from pyrogram.types import Message
from pyrogram import Client
from aiogram.types import CallbackQuery
from typing import Union

from shizu import loader, utils


@loader.module("ShizuPermissions", "hikamoru")
class ShizuPermissions(loader.Module):
    """Give command permissions to users and manage command groups"""

    strings = {"name": "ShizuPermissions"}

    async def inline__close(self, call: CallbackQuery) -> None:
        """Close inline form"""
        await call.delete()

    async def inline__main_menu(self, call: Union[Message, CallbackQuery]) -> None:
        """Show main menu"""
        markup = [
            [
                {
                    "text": self.strings("button_add_permission"),
                    "callback": self.inline__add_permission_start,
                },
                {
                    "text": self.strings("button_remove_permission"),
                    "callback": self.inline__remove_permission_start,
                },
            ],
            [
                {
                    "text": self.strings("button_list_all_permissions"),
                    "callback": self.inline__list_all_permissions,
                },
                {
                    "text": self.strings("button_command_groups"),
                    "callback": self.inline__command_groups_menu,
                },
            ],
            [
                {
                    "text": self.strings("button_user_permissions"),
                    "callback": self.inline__user_permissions_start,
                },
                {
                    "text": self.strings("button_my_permissions"),
                    "callback": self.inline__my_permissions,
                },
            ],
            [
                {"text": self.strings("button_close"), "callback": self.inline__close},
            ],
        ]

        text = self.strings("main_menu")
        if isinstance(call, Message):
            await call.answer(text, reply_markup=markup)
        else:
            await call.edit(text, reply_markup=markup)

    @loader.command(aliases=["perms"])
    async def permissions(self, app: Client, message: Message):
        """Open permissions manager"""
        await self.inline__main_menu(message)

    async def inline__command_groups_menu(self, call: CallbackQuery) -> None:
        """Show command groups menu"""
        markup = [
            [
                {
                    "text": self.strings("button_list_groups"),
                    "callback": self.inline__list_groups,
                },
                {
                    "text": self.strings("button_create_group"),
                    "callback": self.inline__create_group_start,
                },
            ],
            [
                {
                    "text": self.strings("button_manage_groups"),
                    "callback": self.inline__manage_groups,
                },
                {
                    "text": self.strings("button_manage_users"),
                    "callback": self.inline__manage_users,
                },
            ],
            [
                {
                    "text": self.strings("button_my_groups"),
                    "callback": self.inline__my_groups,
                },
            ],
            [
                {
                    "text": self.strings("button_back"),
                    "callback": self.inline__main_menu,
                },
                {"text": self.strings("button_close"), "callback": self.inline__close},
            ],
        ]

        await call.edit(
            self.strings("groups_main_menu"),
            reply_markup=markup,
        )

    async def inline__list_groups(self, call: CallbackQuery) -> None:
        """List all groups"""
        groups = self.db.get("shizu.commandgroups", "groups", {})

        if not groups:
            await call.edit(
                self.strings("no_groups"),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__command_groups_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
            )
            return

        groups_list = "\n".join(
            [
                f"• <code>{name}</code> ({len(commands)} commands)"
                for name, commands in groups.items()
            ]
        )

        markup = []
        for group_name in groups.keys():
            markup.append(
                [
                    {
                        "text": f"📦 {group_name}",
                        "callback": self.inline__view_group,
                        "args": (group_name,),
                    }
                ]
            )

        markup.append(
            [
                {
                    "text": self.strings("button_back"),
                    "callback": self.inline__command_groups_menu,
                },
                {"text": self.strings("button_close"), "callback": self.inline__close},
            ]
        )

        await call.edit(
            self.strings("groups_list").format(groups_list),
            reply_markup=markup,
        )

    async def inline__view_group(self, call: CallbackQuery, group_name: str) -> None:
        """View group details"""
        groups = self.db.get("shizu.commandgroups", "groups", {})

        if group_name not in groups:
            await call.answer(
                self.strings("group_not_found").format(group_name), show_alert=True
            )
            await self.inline__list_groups(call)
            return

        commands = groups[group_name]
        if not commands:
            await call.edit(
                self.strings("group_empty").format(group_name),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_add_command"),
                            "callback": self.inline__add_command_start,
                            "args": (group_name,),
                        },
                        {
                            "text": self.strings("button_delete_group"),
                            "callback": self.inline__delete_group_confirm,
                            "args": (group_name,),
                        },
                    ],
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__list_groups,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ],
                ],
            )
            return

        commands_list = "\n".join([f"• <code>{cmd}</code>" for cmd in commands])

        markup = [
            [
                {
                    "text": self.strings("button_add_command"),
                    "callback": self.inline__add_command_start,
                    "args": (group_name,),
                },
                {
                    "text": self.strings("button_remove_command"),
                    "callback": self.inline__remove_command_start,
                    "args": (group_name,),
                },
            ],
            [
                {
                    "text": self.strings("button_delete_group"),
                    "callback": self.inline__delete_group_confirm,
                    "args": (group_name,),
                },
            ],
            [
                {
                    "text": self.strings("button_back"),
                    "callback": self.inline__list_groups,
                },
                {"text": self.strings("button_close"), "callback": self.inline__close},
            ],
        ]

        await call.edit(
            self.strings("group_info").format(group_name, commands_list),
            reply_markup=markup,
        )

    async def inline__create_group_start(self, call: CallbackQuery) -> None:
        """Start group creation process"""
        await call.edit(
            self.strings("enter_group_name"),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_enter_name"),
                        "input": self.strings("enter_group_name"),
                        "handler": self.inline__create_group_name,
                        "args": (call.inline_message_id,),
                    }
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__command_groups_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ],
            ],
        )

    async def inline__create_group_name(
        self, call: CallbackQuery, query: str, inline_message_id: str
    ) -> None:
        """Process group name and ask for commands"""
        group_name = query.strip().lower()

        groups = self.db.get("shizu.commandgroups", "groups", {})
        if group_name in groups:
            await call.edit(
                self.strings("group_exists").format(group_name),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__command_groups_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        await call.edit(
            self.strings("enter_commands"),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_enter_commands"),
                        "input": self.strings("enter_commands"),
                        "handler": self.inline__create_group_commands,
                        "args": (group_name, inline_message_id),
                    }
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__command_groups_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ],
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__create_group_commands(
        self, call: CallbackQuery, query: str, group_name: str, inline_message_id: str
    ) -> None:
        """Create group with commands"""
        commands = [cmd.lower().strip() for cmd in query.split()]

        invalid_commands = []
        valid_commands = []
        for cmd in commands:
            if cmd in self.all_modules.command_handlers:
                valid_commands.append(cmd)
            else:
                invalid_commands.append(cmd)

        groups = self.db.get("shizu.commandgroups", "groups", {})

        if invalid_commands and not valid_commands:
            invalid_msg = ", ".join([f"<code>{cmd}</code>" for cmd in invalid_commands])
            await call.edit(
                self.strings("invalid_commands").format(invalid_msg),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__command_groups_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        groups[group_name] = valid_commands
        self.db.set("shizu.commandgroups", "groups", groups)

        commands_list = "\n".join([f"• <code>{cmd}</code>" for cmd in valid_commands])

        if invalid_commands:
            invalid_msg = ", ".join([f"<code>{cmd}</code>" for cmd in invalid_commands])
            text = f"{self.strings('group_created').format(group_name, commands_list)}\n\n⚠️ {self.strings('invalid_commands').format(invalid_msg)}"
        else:
            text = self.strings("group_created").format(group_name, commands_list)

        await call.edit(
            text,
            reply_markup=[
                [
                    {
                        "text": self.strings("button_view_group"),
                        "callback": self.inline__view_group,
                        "args": (group_name,),
                    },
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__command_groups_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ],
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__delete_group_confirm(
        self, call: CallbackQuery, group_name: str
    ) -> None:
        """Confirm group deletion"""
        await call.edit(
            self.strings("delete_group_confirm").format(group_name),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_yes"),
                        "callback": self.inline__delete_group,
                        "args": (group_name,),
                    },
                    {
                        "text": self.strings("button_no"),
                        "callback": self.inline__view_group,
                        "args": (group_name,),
                    },
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__list_groups,
                    },
                ],
            ],
        )

    async def inline__delete_group(self, call: CallbackQuery, group_name: str) -> None:
        """Delete group"""
        groups = self.db.get("shizu.commandgroups", "groups", {})

        if group_name not in groups:
            await call.answer(
                self.strings("group_not_found").format(group_name), show_alert=True
            )
            await self.inline__list_groups(call)
            return

        user_groups = self.db.get("shizu.commandgroups", "user_groups", {})
        for user_id in list(user_groups.keys()):
            if group_name in user_groups[user_id]:
                user_groups[user_id].remove(group_name)
                if not user_groups[user_id]:
                    del user_groups[user_id]

        self.db.set("shizu.commandgroups", "user_groups", user_groups)
        del groups[group_name]
        self.db.set("shizu.commandgroups", "groups", groups)

        await call.edit(
            self.strings("group_deleted").format(group_name),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__list_groups,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ]
            ],
        )

    async def inline__add_command_start(
        self, call: CallbackQuery, group_name: str
    ) -> None:
        """Start adding command to group"""
        await call.edit(
            self.strings("enter_command"),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_enter_command"),
                        "input": self.strings("enter_command"),
                        "handler": self.inline__add_command,
                        "args": (group_name, call.inline_message_id),
                    }
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__view_group,
                        "args": (group_name,),
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ],
            ],
        )

    async def inline__add_command(
        self, call: CallbackQuery, query: str, group_name: str, inline_message_id: str
    ) -> None:
        """Add command to group"""
        command = query.strip().lower()

        groups = self.db.get("shizu.commandgroups", "groups", {})
        if group_name not in groups:
            await call.answer(
                self.strings("group_not_found").format(group_name), show_alert=True
            )
            await self.inline__list_groups(call)
            return

        if command not in self.all_modules.command_handlers:
            await call.edit(
                self.strings("command_not_found").format(command),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__view_group,
                            "args": (group_name,),
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        if command in groups[group_name]:
            await call.answer(
                self.strings("command_added").format(command, group_name),
                show_alert=True,
            )
            await self.inline__view_group(call, group_name)
            return

        groups[group_name].append(command)
        self.db.set("shizu.commandgroups", "groups", groups)

        await call.edit(
            self.strings("command_added").format(command, group_name),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_view_group"),
                        "callback": self.inline__view_group,
                        "args": (group_name,),
                    },
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__list_groups,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ],
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__remove_command_start(
        self, call: CallbackQuery, group_name: str
    ) -> None:
        """Start removing command from group"""
        groups = self.db.get("shizu.commandgroups", "groups", {})
        if group_name not in groups or not groups[group_name]:
            await call.answer(
                self.strings("group_empty").format(group_name), show_alert=True
            )
            await self.inline__view_group(call, group_name)
            return

        markup = []
        for cmd in groups[group_name]:
            markup.append(
                [
                    {
                        "text": f"➖ {cmd}",
                        "callback": self.inline__remove_command,
                        "args": (group_name, cmd),
                    }
                ]
            )

        markup.append(
            [
                {
                    "text": self.strings("button_back"),
                    "callback": self.inline__view_group,
                    "args": (group_name,),
                },
                {"text": self.strings("button_close"), "callback": self.inline__close},
            ]
        )

        await call.edit(
            self.strings("remove_command_text"),
            reply_markup=markup,
        )

    async def inline__remove_command(
        self, call: CallbackQuery, group_name: str, command: str
    ) -> None:
        """Remove command from group"""
        groups = self.db.get("shizu.commandgroups", "groups", {})

        if group_name not in groups:
            await call.answer(
                self.strings("group_not_found").format(group_name), show_alert=True
            )
            await self.inline__list_groups(call)
            return

        if command not in groups[group_name]:
            await call.answer(
                self.strings("command_not_in_group").format(command, group_name),
                show_alert=True,
            )
            await self.inline__view_group(call, group_name)
            return

        groups[group_name].remove(command)
        self.db.set("shizu.commandgroups", "groups", groups)

        await call.answer(
            self.strings("command_removed").format(command, group_name), show_alert=True
        )
        await self.inline__view_group(call, group_name)

    async def inline__manage_groups(self, call: CallbackQuery) -> None:
        """Manage groups menu"""
        groups = self.db.get("shizu.commandgroups", "groups", {})

        if not groups:
            await call.edit(
                self.strings("no_groups"),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_create_group"),
                            "callback": self.inline__create_group_start,
                        },
                    ],
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__command_groups_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ],
                ],
            )
            return

        markup = []
        for group_name in groups.keys():
            markup.append(
                [
                    {
                        "text": f"📦 {group_name}",
                        "callback": self.inline__view_group,
                        "args": (group_name,),
                    }
                ]
            )

        markup.append(
            [
                {
                    "text": self.strings("button_back"),
                    "callback": self.inline__command_groups_menu,
                },
                {"text": self.strings("button_close"), "callback": self.inline__close},
            ]
        )

        await call.edit(
            self.strings("manage_groups_text"),
            reply_markup=markup,
        )

    async def inline__manage_users(self, call: CallbackQuery) -> None:
        """Manage users menu"""
        groups = self.db.get("shizu.commandgroups", "groups", {})

        if not groups:
            await call.edit(
                self.strings("no_groups_available"),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_create_group"),
                            "callback": self.inline__create_group_start,
                        },
                    ],
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__command_groups_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ],
                ],
            )
            return

        markup = []
        for group_name in groups.keys():
            markup.append(
                [
                    {
                        "text": f"👤 {group_name}",
                        "callback": self.inline__manage_group_users,
                        "args": (group_name,),
                    }
                ]
            )

        markup.append(
            [
                {
                    "text": self.strings("button_back"),
                    "callback": self.inline__command_groups_menu,
                },
                {"text": self.strings("button_close"), "callback": self.inline__close},
            ]
        )

        await call.edit(
            self.strings("manage_users_text"),
            reply_markup=markup,
        )

    async def inline__manage_group_users(
        self, call: CallbackQuery, group_name: str
    ) -> None:
        """Manage users for a specific group"""
        groups = self.db.get("shizu.commandgroups", "groups", {})
        if group_name not in groups:
            await call.answer(
                self.strings("group_not_found").format(group_name), show_alert=True
            )
            await self.inline__manage_users(call)
            return

        user_groups = self.db.get("shizu.commandgroups", "user_groups", {})
        users_with_access = [
            user_id
            for user_id, user_groups_list in user_groups.items()
            if group_name in user_groups_list
        ]

        markup = [
            [
                {
                    "text": self.strings("button_give_access"),
                    "callback": self.inline__give_access_start,
                    "args": (group_name,),
                },
                {
                    "text": self.strings("button_remove_access"),
                    "callback": self.inline__remove_access_start,
                    "args": (group_name,),
                },
            ],
        ]

        if users_with_access:
            users_list = "\n".join(
                [f"• <code>{user_id}</code>" for user_id in users_with_access[:10]]
            )
            if len(users_with_access) > 10:
                users_list += f"\n... and {len(users_with_access) - 10} more"
            text = self.strings("users_with_access").format(group_name, users_list)
        else:
            text = self.strings("no_users_access").format(group_name)

        markup.append(
            [
                {
                    "text": self.strings("button_back"),
                    "callback": self.inline__manage_users,
                },
                {"text": self.strings("button_close"), "callback": self.inline__close},
            ]
        )

        await call.edit(text, reply_markup=markup)

    async def inline__give_access_start(
        self, call: CallbackQuery, group_name: str
    ) -> None:
        """Start giving access to group"""
        await call.edit(
            self.strings("enter_user"),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_enter_user"),
                        "input": self.strings("enter_user"),
                        "handler": self.inline__give_access,
                        "args": (group_name, call.inline_message_id),
                    }
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__manage_group_users,
                        "args": (group_name,),
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ],
            ],
        )

    async def inline__give_access(
        self, call: CallbackQuery, query: str, group_name: str, inline_message_id: str
    ) -> None:
        """Give access to group"""
        try:
            user_obj = await self._app.get_users(
                query if not query.isdigit() else int(query)
            )
            user_id = str(user_obj.id)
            user_mention = (
                f"@{user_obj.username}"
                if hasattr(user_obj, "username") and user_obj.username
                else f"<code>{utils.escape_html(str(user_id))}</code>"
            )
        except Exception:
            await call.edit(
                self.strings("user_not_found"),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__manage_group_users,
                            "args": (group_name,),
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        groups = self.db.get("shizu.commandgroups", "groups", {})
        if group_name not in groups:
            await call.answer(
                self.strings("group_not_found").format(group_name), show_alert=True
            )
            await self.inline__manage_users(call)
            return

        user_groups = self.db.get("shizu.commandgroups", "user_groups", {})
        if user_id not in user_groups:
            user_groups[user_id] = []

        if group_name in user_groups[user_id]:
            await call.answer(
                self.strings("group_given").format(user_mention, group_name),
                show_alert=True,
            )
            await self.inline__manage_group_users(call, group_name)
            return

        user_groups[user_id].append(group_name)
        self.db.set("shizu.commandgroups", "user_groups", user_groups)

        await call.edit(
            self.strings("group_given").format(user_mention, group_name),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__manage_group_users,
                        "args": (group_name,),
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ]
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__remove_access_start(
        self, call: CallbackQuery, group_name: str
    ) -> None:
        """Start removing access from group"""
        user_groups = self.db.get("shizu.commandgroups", "user_groups", {})
        users_with_access = [
            user_id
            for user_id, user_groups_list in user_groups.items()
            if group_name in user_groups_list
        ]

        if not users_with_access:
            await call.answer(self.strings("no_users_with_access"), show_alert=True)
            await self.inline__manage_group_users(call, group_name)
            return

        await call.edit(
            self.strings("enter_user"),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_enter_user"),
                        "input": self.strings("enter_user"),
                        "handler": self.inline__remove_access,
                        "args": (group_name, call.inline_message_id),
                    }
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__manage_group_users,
                        "args": (group_name,),
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ],
            ],
        )

    async def inline__remove_access(
        self, call: CallbackQuery, query: str, group_name: str, inline_message_id: str
    ) -> None:
        """Remove access from group"""
        try:
            user_obj = await self._app.get_users(
                query if not query.isdigit() else int(query)
            )
            user_id = str(user_obj.id)
            user_mention = (
                f"@{user_obj.username}"
                if hasattr(user_obj, "username") and user_obj.username
                else f"<code>{utils.escape_html(str(user_id))}</code>"
            )
        except Exception:
            await call.edit(
                self.strings("user_not_found"),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__manage_group_users,
                            "args": (group_name,),
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        user_groups = self.db.get("shizu.commandgroups", "user_groups", {})
        if user_id not in user_groups or group_name not in user_groups[user_id]:
            await call.edit(
                self.strings("group_not_given").format(user_mention, group_name),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__manage_group_users,
                            "args": (group_name,),
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        user_groups[user_id].remove(group_name)
        if not user_groups[user_id]:
            del user_groups[user_id]

        self.db.set("shizu.commandgroups", "user_groups", user_groups)

        await call.edit(
            self.strings("group_taken").format(group_name, user_mention),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__manage_group_users,
                        "args": (group_name,),
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ]
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__my_groups(self, call: CallbackQuery) -> None:
        """Show user's accessible groups"""
        user_id = str(call.from_user.id)
        user_groups = self.db.get("shizu.commandgroups", "user_groups", {})

        if user_id not in user_groups or not user_groups[user_id]:
            await call.edit(
                self.strings("no_my_groups"),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__command_groups_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
            )
            return

        groups = self.db.get("shizu.commandgroups", "groups", {})
        groups_list = []
        for group_name in user_groups[user_id]:
            if group_name in groups:
                cmd_count = len(groups[group_name])
                groups_list.append(
                    f"• <code>{group_name}</code> ({cmd_count} commands)"
                )

        if not groups_list:
            await call.edit(
                self.strings("no_my_groups"),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__command_groups_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
            )
            return

        await call.edit(
            self.strings("my_groups").format("\n".join(groups_list)),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__command_groups_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ]
            ],
        )

    async def inline__add_permission_start(self, call: CallbackQuery) -> None:
        """Start adding permission"""
        await call.edit(
            self.strings("enter_user_for_permission"),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_enter_user"),
                        "input": self.strings("enter_user_for_permission"),
                        "handler": self.inline__add_permission_user,
                        "args": (call.inline_message_id,),
                    }
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__main_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ],
            ],
        )

    async def inline__add_permission_user(
        self, call: CallbackQuery, query: str, inline_message_id: str
    ) -> None:
        """Process user and ask for command"""
        try:
            user_obj = await self._app.get_users(
                query if not query.isdigit() else int(query)
            )
            user_id = user_obj.id
        except Exception:
            await call.edit(
                self.strings("user_not_found"),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__add_permission_start,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        await call.edit(
            self.strings("enter_command_for_permission"),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_enter_command"),
                        "input": self.strings("enter_command_for_permission"),
                        "handler": self.inline__add_permission_command,
                        "args": (str(user_id), inline_message_id),
                    }
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__main_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ],
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__add_permission_command(
        self,
        call: CallbackQuery,
        query: str,
        user_id: str,
        inline_message_id: str,
    ) -> None:
        """Add permission"""
        command = query.lower().strip()

        try:
            user_obj = await self._app.get_users(int(user_id))
            user_mention = (
                f"@{user_obj.username}"
                if hasattr(user_obj, "username") and user_obj.username
                else f"<code>{utils.escape_html(str(user_id))}</code>"
            )
        except Exception:
            user_mention = f"<code>{utils.escape_html(str(user_id))}</code>"

        if command not in self.all_modules.command_handlers:
            await call.edit(
                self.strings("command_not_found").format(command),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__add_permission_start,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        perms = self.db.get("shizu.permissions", "users", {})

        if user_id not in perms:
            perms[user_id] = []

        if command in perms[user_id]:
            await call.edit(
                self.strings("perm_exists").format(user_mention, command),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__main_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        perms[user_id].append(command)
        self.db.set("shizu.permissions", "users", perms)
        self.db.save()

        await call.edit(
            self.strings("perm_added").format(user_mention, command),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__main_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ]
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__remove_permission_start(self, call: CallbackQuery) -> None:
        """Start removing permission"""
        await call.edit(
            self.strings("enter_user_for_permission"),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_enter_user"),
                        "input": self.strings("enter_user_for_permission"),
                        "handler": self.inline__remove_permission_user,
                        "args": (call.inline_message_id,),
                    }
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__main_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ],
            ],
        )

    async def inline__remove_permission_user(
        self, call: CallbackQuery, query: str, inline_message_id: str
    ) -> None:
        """Process user and ask for command"""
        try:
            user_obj = await self._app.get_users(
                query if not query.isdigit() else int(query)
            )
            user_id = user_obj.id
        except Exception:
            await call.edit(
                self.strings("user_not_found"),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__remove_permission_start,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        perms = self.db.get("shizu.permissions", "users", {})
        user_id_str = str(user_id)

        try:
            user_obj = await self._app.get_users(user_id)
            user_mention = (
                f"@{user_obj.username}"
                if hasattr(user_obj, "username") and user_obj.username
                else f"<code>{utils.escape_html(str(user_id))}</code>"
            )
        except Exception:
            user_mention = f"<code>{utils.escape_html(str(user_id))}</code>"

        if user_id_str not in perms or not perms[user_id_str]:
            await call.edit(
                self.strings("no_perms").format(user_mention),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__main_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        await call.edit(
            self.strings("enter_command_for_permission"),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_enter_command"),
                        "input": self.strings("enter_command_for_permission"),
                        "handler": self.inline__remove_permission_command,
                        "args": (user_id_str, inline_message_id),
                    }
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__main_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ],
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__remove_permission_command(
        self,
        call: CallbackQuery,
        query: str,
        user_id: str,
        inline_message_id: str,
    ) -> None:
        """Remove permission"""
        command = query.lower().strip()

        try:
            user_obj = await self._app.get_users(int(user_id))
            user_mention = (
                f"@{user_obj.username}"
                if hasattr(user_obj, "username") and user_obj.username
                else f"<code>{utils.escape_html(str(user_id))}</code>"
            )
        except Exception:
            user_mention = f"<code>{utils.escape_html(str(user_id))}</code>"

        perms = self.db.get("shizu.permissions", "users", {})

        if user_id not in perms or command not in perms[user_id]:
            await call.edit(
                self.strings("perm_not_exists").format(user_mention, command),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__main_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        perms[user_id].remove(command)
        if not perms[user_id]:
            del perms[user_id]
        self.db.set("shizu.permissions", "users", perms)
        self.db.save()

        await call.edit(
            self.strings("perm_removed").format(user_mention, command),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__main_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ]
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__list_all_permissions(self, call: CallbackQuery) -> None:
        """List all users with permissions"""
        perms = self.db.get("shizu.permissions", "users", {})

        if not perms:
            await call.edit(
                self.strings("no_users"),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__main_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
            )
            return

        result_lines = []
        for user_id_str, commands in perms.items():
            try:
                user_id = int(user_id_str)
                user_obj = await self._app.get_users(user_id)
                user_mention = (
                    f"@{user_obj.username}"
                    if hasattr(user_obj, "username") and user_obj.username
                    else f"<code>{utils.escape_html(str(user_id))}</code>"
                )
            except Exception:
                user_mention = self.strings("user_id_format").format(user_id_str)

            commands_list = ", ".join([f"<code>{cmd}</code>" for cmd in commands])
            result_lines.append(
                self.strings("user_perms_line").format(user_mention, commands_list)
            )

        await call.edit(
            self.strings("all_perms").format("\n".join(result_lines)),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__main_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ]
            ],
        )

    async def inline__user_permissions_start(self, call: CallbackQuery) -> None:
        """Start showing user permissions"""
        await call.edit(
            self.strings("enter_user_for_permission"),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_enter_user"),
                        "input": self.strings("enter_user_for_permission"),
                        "handler": self.inline__user_permissions,
                        "args": (call.inline_message_id,),
                    }
                ],
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__main_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ],
            ],
        )

    async def inline__user_permissions(
        self, call: CallbackQuery, query: str, inline_message_id: str
    ) -> None:
        """Show permissions for user"""
        try:
            user_obj = await self._app.get_users(
                query if not query.isdigit() else int(query)
            )
            user_id = str(user_obj.id)
            user_mention = (
                f"@{user_obj.username}"
                if hasattr(user_obj, "username") and user_obj.username
                else f"<code>{utils.escape_html(str(user_id))}</code>"
            )
        except Exception:
            await call.edit(
                self.strings("user_not_found"),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__user_permissions_start,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        perms = self.db.get("shizu.permissions", "users", {})

        if user_id not in perms or not perms[user_id]:
            await call.edit(
                self.strings("no_perms").format(user_mention),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__main_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
                inline_message_id=inline_message_id,
            )
            return

        commands_list = "\n".join(
            [self.strings("command_line").format(cmd) for cmd in perms[user_id]]
        )
        await call.edit(
            self.strings("user_perms").format(user_mention, commands_list),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__main_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ]
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__my_permissions(self, call: CallbackQuery) -> None:
        """Show user's accessible commands"""
        user_id = str(call.from_user.id)
        perms = self.db.get("shizu.permissions", "users", {})

        if user_id not in perms or not perms[user_id]:
            await call.edit(
                self.strings("no_my_perms"),
                reply_markup=[
                    [
                        {
                            "text": self.strings("button_back"),
                            "callback": self.inline__main_menu,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ],
            )
            return

        commands_list = "\n".join(
            [self.strings("command_line").format(cmd) for cmd in perms[user_id]]
        )
        await call.edit(
            self.strings("my_perms").format(commands_list),
            reply_markup=[
                [
                    {
                        "text": self.strings("button_back"),
                        "callback": self.inline__main_menu,
                    },
                    {
                        "text": self.strings("button_close"),
                        "callback": self.inline__close,
                    },
                ]
            ],
        )
