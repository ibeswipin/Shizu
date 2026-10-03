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


import re

from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

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

    PAGE_LIMIT = 3500
    SECTIONS = ("internal", "external")

    def _line(self, module):
        prefix = self.db.get("shizu.loader", "prefixes", ["."])[0]
        commands = [
            f"<code>{utils.escape_html(prefix + command)}</code>"
            for command in module.command_handlers
            if command not in self.hidden
        ]
        inline = [f"<code>{utils.escape_html(command)}</code>" for command in module.inline_handlers]
        if not commands and not inline:
            return None

        if getattr(module, "m__telethon", False):
            emoji = "🪢"
        elif module.name in self.cmodules:
            emoji = self.config["core_modules"]
        else:
            emoji = self.config["custom_modules"]

        line = f"{emoji} <b>{utils.escape_html(module.name)}</b> — " + "  ".join(commands)
        if inline:
            line += (" · " if commands else "") + "🤖 " + "  ".join(inline)
        return line

    def _sections(self) -> dict:
        sections = {section: [] for section in self.SECTIONS}
        for module in sorted(self.all_modules.modules, key=lambda mod: mod.name.lower()):
            if line := self._line(module):
                sections["internal" if module.name in self.cmodules else "external"].append(line)
        return sections

    def _pages(self, lines: list) -> list:
        pages, page, size = [], [], 0
        for line in lines:
            if page and size + len(line) > self.PAGE_LIMIT:
                pages.append(page)
                page, size = [], 0
            page.append(line)
            size += len(line) + 1
        return pages + [page] if page or not pages else pages

    def _overview(self, sections: dict, section: str, page: int = 0):
        pages = self._pages(sections[section])
        page = min(page, len(pages) - 1)
        prefix = self.db.get("shizu.loader", "prefixes", ["."])[0]
        text = self.strings("available").format(
            "<emoji id=6334457642064283339>🐙</emoji>",
            self.strings(section + "_title"),
            len(sections[section]),
            "\n" + "\n".join(pages[page]) + "\n",
            utils.escape_html(prefix),
        )

        markup = []
        if all(sections.values()):
            markup.append([
                {
                    "text": ("• " if name == section else "") + f"{self.strings(name + '_title')} · {len(sections[name])}",
                    "callback": self.inline__help_page,
                    "args": (name, 0),
                }
                for name in self.SECTIONS
            ])
        markup += self.bot.build_pagination(
            self.inline__help_page, len(pages), current_page=page + 1, args=(section,)
        )
        markup.append([{"text": self.strings("close"), "callback": self.inline__help_close}])
        return text, markup

    async def inline__help_page(self, call, section: str, page: int = 0):
        await call.edit(*self._overview(self._sections(), section, page))

    async def inline__help_close(self, call):
        await call.delete()

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
                        doc = " ".join(
                            (module.command_handlers[command].__doc__ or "No description").split()
                        )
                        results.append(
                            f"• <code>{prefix}{command}</code> - <b>{module.name}</b>\n"
                            f"  └ {doc}"
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
            sections = self._sections()
            section = "external" if sections["external"] else "internal"
            return await message.answer(*self._overview(sections, section))

        if not (module := self.all_modules.get_module(args.lower(), True, True)):
            return await send_response(
                "<b><emoji id=5465665476971471368>❌</emoji> There is no such module</b>",
            )

        def describe(doc):
            tags = r"</?(?:b|i|u|s|code|pre|a|blockquote|emoji|tg-emoji|tg-spoiler)\b[^>]*>"
            return " ".join(re.sub(tags, "", doc or "No description").split())

        lines = [
            f"▫️ <code>{utils.escape_html(prefix + command)}</code> — "
            f"{utils.escape_html(describe(module.command_handlers[command].__doc__))}"
            for command in module.command_handlers
        ]
        lines += [
            f"🤖 <code>@{bot_username} {utils.escape_html(command)}</code> — "
            f"{utils.escape_html(describe(module.inline_handlers[command].__doc__))}"
            for command in module.inline_handlers
        ]

        header = f"<b>{utils.escape_html(module.name)}</b>"
        if module.__doc__:
            header += f" — {utils.escape_html(describe(module.__doc__))}"
        return await send_response(header + "\n\n" + "\n".join(lines))

    async def help_inline_handler(self, app, inline_query, args):
        """Modules and their commands - help [query]"""
        prefix = self.db.get("shizu.loader", "prefixes", ["."])[0]
        bot_username = (await self.bot.bot.get_me()).username
        query = args.lower()
        results = []

        for module in sorted(
            self.all_modules.modules,
            key=lambda mod: (mod.name not in self.cmodules, len(mod.name)),
        ):
            commands = [c for c in module.command_handlers if c not in self.hidden]
            if not commands and not module.inline_handlers:
                continue

            if query and query not in module.name.lower() and not any(
                query in c for c in [*commands, *module.inline_handlers]
            ):
                continue

            text = f"🐙 <b>{module.name}</b>\nℹ️ {module.__doc__ or 'No description'}\n\n"
            text += "\n".join(
                f"▫️ <code>{prefix}{c}</code> - {module.command_handlers[c].__doc__ or 'No description'}"
                for c in commands
            )
            text += "".join(
                f"\n🤖 <code>@{bot_username} {c}</code> - {f.__doc__ or 'No description'}"
                for c, f in module.inline_handlers.items()
            )

            results.append(
                InlineQueryResultArticle(
                    id=utils.random_id(),
                    title=module.name,
                    description=" | ".join([*commands, *module.inline_handlers])[:100],
                    input_message_content=InputTextMessageContent(
                        text[:4096], "HTML", disable_web_page_preview=True
                    ),
                )
            )

        await inline_query.answer(results[:50], cache_time=0)

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
