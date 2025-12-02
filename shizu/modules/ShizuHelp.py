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


from pyrogram import Client, types
from .. import loader, utils


@loader.module(name="ShizuHelp", author="shizu")
class Help(loader.Module):
    """[module] - Show help"""

    strings = {}

    def __init__(self):
        self.config = loader.ModuleConfig(
            "core_modules",
            "▫️",
            lambda m: self.strings("core_modules_emoji"),
            "custom_modules",
            "👩‍🎤",
            lambda m: self.strings("custom_module_emoji"),
        )

    @loader.command()
    async def help(self, app: Client, message: types.Message):
        """Show help"""

        args = message.get_args()
        dop_help = "<emoji id=5100652175172830068>🔸</emoji>"
        bot_username = (await self.bot.bot.get_me()).username

        sorted_modules = sorted(
            self.all_modules.modules,
            key=lambda mod: (mod.name not in self.cmodules, len(mod.name)),
        )

        if not args:
            text = ""
            for module in sorted_modules:
                commands = inline = ""
                commands += " <b>|</b> ".join(
                    f"{command}"
                    for command in module.command_handlers
                    if command not in self.hidden
                )

                if module.inline_handlers:
                    if commands:
                        inline += " <b><emoji id=5258093637450866522>🤖</emoji></b> "
                    else:
                        inline += "<b><emoji id=5258093637450866522>🤖</emoji></b>: "

                inline += " <b>|</b> ".join(
                    f"{inline_command}" for inline_command in module.inline_handlers
                )

                if commands or inline:
                    if hasattr(module, 'm__telethon') and module.m__telethon:
                        module_emoji = "🪢"
                    elif module.name in self.cmodules:
                        module_emoji = self.config["core_modules"]
                    else:
                        module_emoji = self.config["custom_modules"]

                    text += (
                        f"\n<b>{module_emoji} {module.name}</b> - [ "
                        + (commands or "")
                        + (inline or "")
                        + " ]"
                    )

            help_emoji = "<emoji id=6334457642064283339>🐙</emoji>"

            return await message.answer(
                self.strings("available").format(
                    help_emoji, len(self.all_modules.modules) - 1, text
                )
            )

        if not (module := self.all_modules.get_module(args.lower(), True, True)):
            return await message.answer(
                "<b><emoji id=5465665476971471368>❌</emoji> There is no such module</b>",
            )

        prefix = self.db.get("shizu.loader", "prefixes", ["."])[0]
        command_descriptions = "\n".join(
            f"{dop_help} <code>{prefix + command}</code> - {module.command_handlers[command].__doc__ or 'No description'}"
            for command in module.command_handlers
        )
        inline_descriptions = "\n".join(
            f"{dop_help} <code>@{bot_username} {command}</code> - {module.inline_handlers[command].__doc__ or 'No description'}"
            for command in module.inline_handlers
        )
        modname = module.name
        header = (
            f"<emoji id=6334457642064283339>🐙</emoji> <b>{modname}</b>\n"
            f"<emoji id=5787544344906959608>ℹ️</emoji>"
            f" {module.__doc__ or 'No description'}\n\n"
        )

        return await message.answer(
            header + command_descriptions + "\n" + inline_descriptions
        )

    @loader.command()
    async def support(self, app, message):
        """Support"""
        await message.answer(
            self.strings("support"),
            reply_markup=[
                [{"text": self.strings("button"), "url": "https://t.me/shizu_talks"}]
            ],
            prev=True,
        )

    @loader.command()
    async def ubinfo(self, app, message):
        """Info about Shizu-Userbot"""
        await message.answer(
            self.strings("info_ub"),
            disable_web_page_preview=True,
        )
