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

from shizu import loader, utils


@loader.module("ShizuPermissions", "hikamoru")
class ShizuPermissions(loader.Module):
    """Give command permissions to users"""

    strings = {
        "name": "ShizuPermissions",
        "no_args": "❌ Please provide user ID or username and command name\nUsage: <code>.addperm &lt;user&gt; &lt;command&gt;</code>",
        "user_not_found": "❌ User not found",
        "command_not_found": "❌ Command <code>{}</code> not found",
        "perm_added": "✅ Added permission for user {} to use command <code>{}</code>",
        "perm_removed": "✅ Removed permission for user {} to use command <code>{}</code>",
        "perm_exists": "❌ User {} already has permission for command <code>{}</code>",
        "perm_not_exists": "❌ User {} doesn't have permission for command <code>{}</code>",
        "user_perms": "👤 User {} has access to commands:\n{}",
        "no_perms": "❌ User {} has no command permissions",
        "all_perms": "📋 All users with permissions:\n{}",
        "no_users": "❌ No users have command permissions",
        "my_perms": "🔐 Your available commands:\n{}",
        "no_my_perms": "❌ You don't have access to any commands",
    }

    strings_ru = {
        "no_args": "❌ Укажите ID пользователя или username и название команды\nИспользование: <code>.addperm &lt;user&gt; &lt;command&gt;</code>",
        "user_not_found": "❌ Пользователь не найден",
        "command_not_found": "❌ Команда <code>{}</code> не найдена",
        "perm_added": "✅ Добавлено разрешение для пользователя {} использовать команду <code>{}</code>",
        "perm_removed": "✅ Удалено разрешение для пользователя {} использовать команду <code>{}</code>",
        "perm_exists": "❌ Пользователь {} уже имеет разрешение на команду <code>{}</code>",
        "perm_not_exists": "❌ Пользователь {} не имеет разрешения на команду <code>{}</code>",
        "user_perms": "👤 Пользователь {} имеет доступ к командам:\n{}",
        "no_perms": "❌ У пользователя {} нет разрешений на команды",
        "all_perms": "📋 Все пользователи с разрешениями:\n{}",
        "no_users": "❌ Нет пользователей с разрешениями",
        "my_perms": "🔐 Ваши доступные команды:\n{}",
        "no_my_perms": "❌ У вас нет доступа ни к одной команде",
    }

    @loader.command()
    async def addperm(self, app, message: Message):
        """Give command permission to user - .addperm <user> <command>"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("no_args"))
            return

        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            await utils.answer(message, self.strings("no_args"))
            return

        user_arg, command = parts
        command = command.lower().strip()

        try:
            user_obj = await app.get_users(user_arg)
            user_id = user_obj.id
        except Exception:
            await utils.answer(message, self.strings("user_not_found"))
            return

        if not hasattr(self, 'all_modules') or command not in self.all_modules.command_handlers:
            await utils.answer(message, self.strings("command_not_found").format(command))
            return

        perms = self.db.get("shizu.permissions", "users", {})
        user_id_str = str(user_id)

        if user_id_str not in perms:
            perms[user_id_str] = []

        if command in perms[user_id_str]:
            await utils.answer(
                message,
                self.strings("perm_exists").format(user_obj.mention, command)
            )
            return

        perms[user_id_str].append(command)
        self.db.set("shizu.permissions", "users", perms)
        self.db.save()

        await utils.answer(
            message,
            self.strings("perm_added").format(user_obj.mention, command)
        )

    @loader.command()
    async def delperm(self, app, message: Message):
        """Remove command permission from user - .delperm <user> <command>"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("no_args"))
            return

        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            await utils.answer(message, self.strings("no_args"))
            return

        user_arg, command = parts
        command = command.lower().strip()

        try:
            user_obj = await app.get_users(user_arg)
            user_id = user_obj.id
        except Exception:
            await utils.answer(message, self.strings("user_not_found"))
            return

        perms = self.db.get("shizu.permissions", "users", {})
        user_id_str = str(user_id)

        if user_id_str not in perms or command not in perms[user_id_str]:
            await utils.answer(
                message,
                self.strings("perm_not_exists").format(user_obj.mention, command)
            )
            return

        perms[user_id_str].remove(command)
        if not perms[user_id_str]:
            del perms[user_id_str]
        self.db.set("shizu.permissions", "users", perms)
        self.db.save()

        await utils.answer(
            message,
            self.strings("perm_removed").format(user_obj.mention, command)
        )

    @loader.command()
    async def listperms(self, app, message: Message):
        """List all users with permissions"""
        perms = self.db.get("shizu.permissions", "users", {})

        if not perms:
            await utils.answer(message, self.strings("no_users"))
            return

        result_lines = []
        for user_id_str, commands in perms.items():
            try:
                user_id = int(user_id_str)
                user_obj = await app.get_users(user_id)
                user_mention = user_obj.mention
            except Exception:
                user_mention = f"ID: {user_id_str}"

            commands_list = ", ".join([f"<code>{cmd}</code>" for cmd in commands])
            result_lines.append(f"• {user_mention}: {commands_list}")

        await utils.answer(
            message,
            self.strings("all_perms").format("\n".join(result_lines))
        )

    @loader.command()
    async def userperms(self, app, message: Message):
        """Show permissions for user - .userperms <user>"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("no_args"))
            return

        try:
            user_obj = await app.get_users(args)
            user_id = str(user_obj.id)
        except Exception:
            await utils.answer(message, self.strings("user_not_found"))
            return

        perms = self.db.get("shizu.permissions", "users", {})

        if user_id not in perms or not perms[user_id]:
            await utils.answer(
                message,
                self.strings("no_perms").format(user_obj.mention)
            )
            return

        commands_list = "\n".join([f"• <code>{cmd}</code>" for cmd in perms[user_id]])
        await utils.answer(
            message,
            self.strings("user_perms").format(user_obj.mention, commands_list)
        )

    @loader.command()
    async def myperms(self, app, message: Message):
        """Show your available commands"""
        user_id = str(message.from_user.id)
        perms = self.db.get("shizu.permissions", "users", {})

        if user_id not in perms or not perms[user_id]:
            await utils.answer(message, self.strings("no_my_perms"))
            return

        commands_list = "\n".join([f"• <code>{cmd}</code>" for cmd in perms[user_id]])
        await utils.answer(
            message,
            self.strings("my_perms").format(commands_list)
        )
