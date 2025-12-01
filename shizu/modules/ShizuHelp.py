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

    strings = {
        "available": "{} <b>{} modules available</b>\n{}",
        "support": "🧑‍🔬 <b>If you have any questions, suggestions or bug reports, please let us know in our support chat: @shizu_talks</b>",
        "button": "🗼 Support chat",
        "info_ub": (
            "🐙 <b>Shizu-Userbot\n\n"
            "• Repository: <a href='https://github.com/AmoreForever/Shizu'>GitHub</a>\n"
            "• Support: <a href='https://t.me/shizu_talks'>Shizu Talks</a>\n"
            "• Channel: <a href='https://t.me/shizuhub'>Shizu Hub</a>\n"
            "• Modules: <a href='https://t.me/shizumods'>Shizu Mods</a>\n"
            "• Developer: <a href='https://t.me/hikamoru'>Hikamoru</a></b>\n\n"
            "© <b>Shizu-Userbot is licensed under the <a href='https://www.gnu.org/licenses/agpl-3.0.html'>GNU GPLv3</a></b>"
        ),
        "core_modules_emoji": "This emoji for core modules",
        "custom_module_emoji": "This emoji for custom modules",
    }

    strings_ru = {
        "available": "{} <b>{} модулей доступно</b>\n{}",
        "support": "🧑‍🔬 <b>Если у вас есть вопросы, предложения или сообщения об ошибках, сообщите нам в нашем чате поддержки: @shizu_talks</b>",
        "button": "🗼 Чат поддержки",
        "info_ub": (
            "🐙 <b>Shizu-Userbot\n\n"
            "• Репозиторий: <a href='https://github.com/AmoreForever/Shizu'>GitHub</a>\n"
            "• Поддержка: <a href='https://t.me/shizu_talks'>Shizu Talks</a>\n"
            "• Канал: <a href='https://t.me/shizuhub'>Shizu Hub</a>\n"
            "• Модули: <a href='https://t.me/shizumods'>Shizu Mods</a>\n"
            "• Разработчик: <a href='https://t.me/hikamoru'>Hikamoru</a></b>\n\n"
            "© <b>Shizu-Userbot распространяется под лицензией <a href='https://www.gnu.org/licenses/agpl-3.0.html'>GNU GPLv3</a></b>"
        ),
        "core_modules_emoji": "Этот emoji для встроенных модулей",
        "custom_module_emoji": "Этот emoji для кастом модулей",
    }

    strings_uz = {
        "available": "{} <b>{} modullar mavjud</b>\n{}",
        "support": "🧑‍🔬 <b>Savollaringiz, takliflaringiz yoki xatolaringiz bo'lsa, iltimos, bizga yordam beruvchi chatga xabar bering: @shizu_talks</b>",
        "button": "🗼 Yordam chati",
        "info_ub": (
            "🐙 <b>Shizu-Userbot\n\n"
            "• Repository: <a href='https://github.com/AmoreForever/Shizu'>GitHub</a>\n"
            "• Yordam: <a href='https://t.me/shizu_talks'>Shizu Talks</a>\n"
            "• Kanal: <a href='https://t.me/shizuhub'>Shizu Hub</a>\n"
            "• Modullar: <a href='https://t.me/shizumods'>Shizu Mods</a>\n"
            "• Yaratuvchi: <a href='https://t.me/hikamoru'>Hikamoru</a></b>\n\n"
            "© <b>Shizu-Userbot <a href='https://www.gnu.org/licenses/agpl-3.0.html'>GNU GPLv3</a> litsenziyasi ostida tarqatilgan</b>"
        ),
        "core_modules_emoji": "Bu ichki modullar uchun emoji",
        "custom_module_emoji": "Bu maxsus modullar uchun emoji",
    }

    strings_jp = {
        "available": "{} <b>利用可能な {} のモジュールがあります</b>\n{}",
        "support": "🧑‍🔬 <b>質問、提案、バグ報告がある場合は、サポートチャットでお知らせください: @shizu_talks</b>",
        "button": "🗼 サポートチャット",
        "info_ub": (
            "🐙 <b>Shizu-Userbot\n\n"
            "• リポジトリ: <a href='https://github.com/AmoreForever/Shizu'>GitHub</a>\n"
            "• サポート: <a href='https://t.me/shizu_talks'>Shizu Talks</a>\n"
            "• チャンネル: <a href='https://t.me/shizuhub'>Shizu Hub</a>\n"
            "• モジュール: <a href='https://t.me/shizumods'>Shizu Mods</a>\n"
            "• 開発者: <a href='https://t.me/hikamoru'>Hikamoru</a></b>\n\n"
            "© <b>Shizu-Userbot は <a href='https://www.gnu.org/licenses/agpl-3.0.html'>GNU GPLv3</a> ライセンスの下で配布されています</b>"
        ),
        "core_modules_emoji": "この絵文字はコアモジュール用です",
        "custom_module_emoji": "この絵文字はカスタムモジュール用です",
    }

    strings_ua = {
        "available": "{} <b>{} модулів доступно</b>\n{}",
        "support": "🧑‍🔬 <b>Якщо у вас є питання, пропозиції або повідомлення про помилки, повідомте нам у нашому чаті підтримки: @shizu_talks</b>",
        "button": "🗼 Чат підтримки",
        "info_ub": (
            "🐙 <b>Shizu-Userbot\n\n"
            "• Репозиторій: <a href='https://github.com/AmoreForever/Shizu'>GitHub</a>\n"
            "• Підтримка: <a href='https://t.me/shizu_talks'>Shizu Talks</a>\n"
            "• Канал: <a href='https://t.me/shizuhub'>Shizu Hub</a>\n"
            "• Модулі: <a href='https://t.me/shizumods'>Shizu Mods</a>\n"
            "• Розробник: <a href='https://t.me/hikamoru'>Hikamoru</a></b>\n\n"
            "© <b>Shizu-Userbot поширюється під ліцензією <a href='https://www.gnu.org/licenses/agpl-3.0.html'>GNU GPLv3</a></b>"
        ),
        "core_modules_emoji": "Цей емодзі для ядерних модулів",
        "custom_module_emoji": "Цей емодзі для користувацьких модулів",
    }

    strings_kz = {
        "available": "{} <b>{} модуль қолжетімді</b>\n{}",
        "support": "🧑‍🔬 <b>Сұрақтарыңыз, ұсыныстарыңыз немесе қателер туралы хабарласу үшін, біздің қолдау құрамасында хабарласыңыз: @shizu_talks</b>",
        "button": "🗼 Қолдау құрамасы",
        "info_ub": (
            "🐙 <b>Shizu-Userbot\n\n"
            "• Repository: <a href='https://github.com/AmoreForever/Shizu'>GitHub</a>\n"
            "• Қолдау: <a href='https://t.me/shizu_talks'>Shizu Talks</a>\n"
            "• Канал: <a href='https://t.me/shizuhub'>Shizu Hub</a>\n"
            "• Модульдер: <a href='https://t.me/shizumods'>Shizu Mods</a>\n"
            "• Дамытушы: <a href='https://t.me/hikamoru'>Hikamoru</a></b>\n\n"
            "© <b>Shizu-Userbot <a href='https://www.gnu.org/licenses/agpl-3.0.html'>GNU GPLv3</a> лицензиясы бойынша жарияланады</b>"
        ),
        "core_modules_emoji": "Бұл жүйелік модульдер үшін емоджи",
        "custom_module_emoji": "Бұл қосымша модульдер үшін емоджи",
    }

    strings_kr = {
        "available": "{} <b>{} 모듈 사용 가능</b>\n{}",
        "support": "🧑‍🔬 <b>질문, 제안 또는 버그 보고가 있으면 지원 채팅에서 알려주세요: @shizu_talks</b>",
        "button": "🗼 지원 채팅",
        "info_ub": (
            "🐙 <b>Shizu-Userbot\n\n"
            "• 저장소: <a href='https://github.com/AmoreForever/Shizu'>GitHub</a>\n"
            "• 지원: <a href='https://t.me/shizu_talks'>Shizu Talks</a>\n"
            "• 채널: <a href='https://t.me/shizuhub'>Shizu Hub</a>\n"
            "• 모듈: <a href='https://t.me/shizumods'>Shizu Mods</a>\n"
            "• 개발자: <a href='https://t.me/hikamoru'>Hikamoru</a></b>\n\n"
            "© <b>Shizu-Userbot은 <a href='https://www.gnu.org/licenses/agpl-3.0.html'>GNU GPLv3</a> 라이선스 하에 배포됩니다</b>"
        ),
        "core_modules_emoji": "이 이모지는 코어 모듈용입니다",
        "custom_module_emoji": "이 이모지는 사용자 정의 모듈용입니다",
    }

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
