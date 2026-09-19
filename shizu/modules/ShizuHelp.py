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


from shizu import loader, utils


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
    async def help(self, app=None, message=None):
        """Show help - <code>.help [module]</code> or <code>.help search &lt;query&gt;</code>"""
        if message is None:
            message = app
            app = None

        if hasattr(message, "get_args"):
            args = message.get_args()
        elif hasattr(message, "text"):
            text = message.text or ""
            parts = text.split(None, 1)
            args = parts[1] if len(parts) > 1 else ""
        else:
            args = ""

        prefix = self.db.get("shizu.loader", "prefixes", ["."])[0]
        bot_username = (await self.bot.bot.get_me()).username

        async def send_response(text):
            return await utils.answer(message, text)

        if args and args.lower().startswith("search "):
            query = args[7:].strip().lower()
            if not query:
                return await send_response(
                    "❌ <b>Usage:</b> <code>.help search &lt;query&gt;</code>"
                )

            results = []
            for module in self.all_modules.modules:
                if query in module.name.lower():
                    cmd_count = len(
                        [c for c in module.command_handlers if c not in self.hidden]
                    )
                    if cmd_count > 0:
                        results.append(
                            f"• <b>{module.name}</b> <i>({cmd_count} commands)</i>"
                        )

                for command in module.command_handlers:
                    if command not in self.hidden and query in command.lower():
                        doc = (
                            module.command_handlers[command].__doc__ or "No description"
                        )
                        results.append(
                            f"• <code>{prefix}{command}</code> - <b>{module.name}</b>\n"
                            f"  └ {doc[:60]}{'...' if len(doc) > 60 else ''}"
                        )

            if not results:
                return await send_response(
                    f"🔍 <b>No results found for:</b> <code>{query}</code>"
                )

            result_text = (
                f"🔍 <b>Search Results:</b> <code>{query}</code>\n\n"
                + "\n".join(results[:15])
            )
            if len(results) > 15:
                result_text += f"\n\n... and {len(results) - 15} more results"

            return await send_response(result_text)

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
                    if hasattr(module, "m__telethon") and module.m__telethon:
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

            return await send_response(
                self.strings("available").format(
                    help_emoji, len(self.all_modules.modules) - 1, text
                )
            )

        if not (module := self.all_modules.get_module(args.lower(), True, True)):
            return await send_response(
                "<b><emoji id=5465665476971471368>❌</emoji> There is no such module</b>",
            )

        dop_help = "<emoji id=5100652175172830068>🔸</emoji>"
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

        return await send_response(
            header + command_descriptions + "\n" + inline_descriptions
        )

    @loader.command()
    async def support(self, app=None, message=None):
        """Support"""
        if message is None:
            message = app
        await utils.answer(
            message,
            self.strings("support"),
            reply_markup=[
                [{"text": self.strings("button"), "url": "https://t.me/shizu_talks"}]
            ],
        )

    @loader.command()
    async def ubinfo(self, app=None, message=None):
        """Info about Shizu-Userbot"""
        if message is None:
            message = app
        await utils.answer(
            message,
            self.strings("info_ub"),
            disable_web_page_preview=True,
        )
