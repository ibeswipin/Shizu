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


# meta banner: https://github.com/ibeswipin/Shizu/raw/refs/heads/beta/assets/banners/ShizuHelp.png

import html
import re
from difflib import SequenceMatcher

from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

from shizu import loader, utils
from shizu.telegram.rich import button_rows, form_html

EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`"
RU = "йцукенгшщзхъфывапролджэячсмитьбюё"
TO_RU = str.maketrans(EN, RU)
TO_EN = str.maketrans(RU, EN)
TRANSLIT = str.maketrans(
    {
        **dict(zip("абвгдезийклмнопрстуфхцыэ", "abvgdezijklmnoprstufhcye")),
        "ё": "e", "ж": "zh", "ч": "ch", "ш": "sh", "щ": "sh",
        "ю": "yu", "я": "ya", "ъ": "", "ь": "",
    }
)
TAGS = r"</?(?:b|i|u|s|code|pre|a|blockquote|emoji|tg-emoji|tg-spoiler)\b[^>]*>"


def describe(doc) -> str:
    return " ".join(html.unescape(re.sub(TAGS, "", doc or "No description")).split())


def name_score(query: str, name: str) -> float:
    name = name.lower()
    if name == query:
        return 100
    if name.startswith(query):
        return 90
    if query in name:
        return 75
    ratio = SequenceMatcher(None, query, name).ratio()
    return ratio * 70 if ratio >= 0.6 else 0


def doc_score(query: str, doc: str) -> float:
    words = re.findall(r"\w+", doc.lower())
    terms = re.findall(r"\w+", query)
    if not words or not terms:
        return 0
    found = sum(
        any(
            word.startswith(term)
            or len(term) > 3
            and SequenceMatcher(None, term, word).ratio() >= 0.8
            for word in words
        )
        for term in terms
    )
    return 50 * found / len(terms)


@loader.module(name="ShizuHelp", author="shizu")
class Help(loader.Module):
    """[module] - Show help"""

    strings = {}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "core_modules",
                "▫️",
                lambda m: self.strings("core_modules_emoji"),
                label=lambda: self.strings("cfg_label_core_modules"),
            ),
            loader.ConfigValue(
                "custom_modules",
                "👩‍🎤",
                lambda m: self.strings("custom_module_emoji"),
                label=lambda: self.strings("cfg_label_custom_modules"),
            ),
        )

    PAGE_LIMIT = 3500
    SECTIONS = ("internal", "external")
    SECTION_EMOJI = {"internal": "🛠", "external": "🧩"}
    PREMIUM_EMOJI = {
        "core_modules": '<tg-emoji emoji-id="5019413195186504264">⚙️</tg-emoji>',
        "custom_modules": '<tg-emoji emoji-id="5161221487608201804">🔵</tg-emoji>',
        "telethon": '<tg-emoji emoji-id="5377437404078546699">💜</tg-emoji>',
    }

    def _emoji(self, key):
        premium = getattr(self.me, "is_premium", False)
        if key == "telethon":
            return self.PREMIUM_EMOJI[key] if premium else "🪢"
        value = self.config[key]
        if premium and value == self.config.getdef(key):
            return self.PREMIUM_EMOJI[key]
        return value

    def _line(self, module):
        prefix = self.db.get("shizu.loader", "prefixes", ["."])[0]
        commands = [
            f"<code>{utils.escape_html(prefix + command)}</code>"
            for command in module.command_handlers
            if command not in self.hidden
        ]
        inline = [
            f"<code>{utils.escape_html(command)}</code>"
            for command in module.inline_handlers
        ]
        if not commands and not inline:
            return None

        if getattr(module, "m__telethon", False):
            emoji = self._emoji("telethon")
        elif self.all_modules.is_core(module):
            emoji = self._emoji("core_modules")
        else:
            emoji = self._emoji("custom_modules")

        line = f"{emoji} <b>{utils.escape_html(module.name)}</b> — " + "  ".join(
            commands
        )
        if inline:
            line += (" · " if commands else "") + "🤖 " + "  ".join(inline)
        return line

    def _sections(self) -> dict:
        sections = {section: [] for section in self.SECTIONS}
        for module in sorted(
            self.all_modules.modules, key=lambda mod: mod.name.lower()
        ):
            if line := self._line(module):
                sections[
                    "internal" if self.all_modules.is_core(module) else "external"
                ].append(line)
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
            self.SECTION_EMOJI[section],
            self.strings(section + "_title"),
            len(sections[section]),
            "\n" + "\n".join(pages[page]) + "\n",
            utils.escape_html(prefix),
        )

        markup = []
        if all(sections.values()):
            markup.append(
                [
                    {
                        "text": ("• " if name == section else "")
                        + f"{self.SECTION_EMOJI[name]} {self.strings(name + '_title')} · {len(sections[name])}",
                        "callback": self.inline__help_page,
                        "args": (name, 0),
                    }
                    for name in self.SECTIONS
                ]
            )
        markup += self.bot.build_pagination(
            self.inline__help_page, len(pages), current_page=page + 1, args=(section,)
        )
        close = self.strings("close")
        markup.append(
            [{"text": close, "callback": self.inline__help_close, "style": "danger"}]
        )
        head, *body = text.split("\n")
        rich = {
            "html": f"<h3>{head}</h3>"
            + "".join(f"<p>{line}</p>" for line in body if line)
            + button_rows(markup)
        }
        return text, markup, rich

    def _search(self, query: str) -> list:
        query = query.lower().strip()
        variants = {
            query,
            query.translate(TO_RU),
            query.translate(TO_EN),
            query.translate(TRANSLIT),
        }
        aliases = {}
        for alias, command in self.all_modules.aliases.items():
            aliases.setdefault(command, []).append(alias)
        results = {}
        for module in self.all_modules.modules:
            commands = [c for c in module.command_handlers if c not in self.hidden]
            if not commands and not module.inline_handlers:
                continue
            module_doc = describe(module.__doc__)
            for variant in variants:
                score = max(
                    name_score(variant, module.name), doc_score(variant, module_doc)
                )
                key = (module.name, None)
                if score > results.get(key, (0,))[0]:
                    results[key] = (score, module, None)
                for command in commands:
                    names = [command, *aliases.get(command, [])]
                    score = max(
                        max(name_score(variant, name) for name in names),
                        doc_score(variant, describe(module.command_handlers[command].__doc__)),
                    )
                    key = (module.name, command)
                    if score > results.get(key, (0,))[0]:
                        results[key] = (score, module, command)
        return sorted(
            (result for result in results.values() if result[0] >= 40),
            key=lambda result: (-result[0], result[1].name, result[2] or ""),
        )

    async def inline__help_page(self, call, section: str, page: int = 0):
        text, markup, rich = self._overview(self._sections(), section, page)
        await call.edit(text, markup, rich_message=rich)

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
            for _, module, command in self._search(query):
                name = utils.escape_html(module.name)
                if command is None:
                    results.append(
                        f"• <b>{name}</b> — {utils.escape_html(describe(module.__doc__))}"
                    )
                else:
                    doc = describe(module.command_handlers[command].__doc__)
                    results.append(
                        f"• <code>{utils.escape_html(prefix + command)}</code> — <b>{name}</b>\n"
                        f"  └ {utils.escape_html(doc)}"
                    )

            if not results:
                return await send_response(
                    f"🔍 <b>No results found for:</b> <code>{utils.escape_html(query)}</code>"
                )

            result_text = (
                f"🔍 <b>Search Results:</b> <code>{utils.escape_html(query)}</code>\n\n"
                + "\n".join(results[:15])
            )
            if len(results) > 15:
                result_text += f"\n\n... and {len(results) - 15} more results"

            return await send_response(result_text)

        if not args:
            sections = self._sections()
            section = "external" if sections["external"] else "internal"
            text, markup, rich = self._overview(sections, section)
            return await message.answer(text, reply_markup=markup, rich_message=rich)

        module = self.all_modules.get_module(args.lower(), True, True)
        if module is None:
            found = self._search(args)
            if found and found[0][0] >= 70:
                module = found[0][1]
            else:
                text = "<b><emoji id=5465665476971471368>❌</emoji> There is no such module</b>"
                names = list(dict.fromkeys(result[1].name for result in found))[:3]
                if names:
                    text += "\n\n🔍 <b>Did you mean:</b> " + ", ".join(
                        f"<code>{utils.escape_html(name)}</code>" for name in names
                    )
                return await send_response(text)

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

        name = module.name
        logo = utils.shizu_logo(self.me, "")
        if logo and self.all_modules.is_core(module) and name.startswith("Shizu"):
            name = name.removeprefix("Shizu")
        header = f"<b>{utils.escape_html(name)}</b>"
        if logo:
            header = f"{logo} {header}"
        if module.__doc__:
            header += f" — {utils.escape_html(describe(module.__doc__))}"
        text = header + "\n\n" + "\n".join(lines)
        banner = self.all_modules.meta(module).get("banner", "")
        if not re.fullmatch(r"https?://\S+", banner):
            return await send_response(text)
        rich = form_html(text, [])
        rich["html"] = '<img src="tg://photo?id=banner"/>' + rich["html"]
        rich["media"] = [
            {"id": "banner", "media": {"type": "photo", "media": banner}}
        ]
        return await utils.answer(message, text, rich_message=rich)

    async def help_inline_handler(self, app, inline_query, args):
        """Modules and their commands - help [query]"""
        prefix = self.db.get("shizu.loader", "prefixes", ["."])[0]
        bot_username = (await self.bot.bot.get_me()).username
        results = []
        modules = (
            dict.fromkeys(result[1] for result in self._search(args))
            if args.strip()
            else sorted(
                self.all_modules.modules,
                key=lambda mod: (not self.all_modules.is_core(mod), len(mod.name)),
            )
        )

        for module in modules:
            commands = [c for c in module.command_handlers if c not in self.hidden]
            if not commands and not module.inline_handlers:
                continue

            escape = utils.escape_html
            text = (
                f"🐙 <b>{escape(module.name)}</b>\n"
                f"ℹ️ {escape(describe(module.__doc__))}\n\n"
            )
            text += "\n".join(
                f"▫️ <code>{escape(prefix + c)}</code> - "
                f"{escape(describe(module.command_handlers[c].__doc__))}"
                for c in commands
            )
            text += "".join(
                f"\n🤖 <code>@{bot_username} {escape(c)}</code> - {escape(describe(f.__doc__))}"
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
