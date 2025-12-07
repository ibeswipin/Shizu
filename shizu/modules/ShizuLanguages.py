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


import shutil
import os
from shizu import loader, utils, translator


@loader.module("ShizuLanguages", "hikamoru", 1.0)
class ShizuLanguages(loader.Module):
    """To change language of Shizu"""

    strings = {}

    async def setlangcmd(self, app, message):
        """Change default language"""
        args = utils.get_args_raw(message)
        if not args or any(len(i) != 2 for i in args.split(" ")):
            await utils.answer(message, self.strings("incorrect_language"))
            return

        self.db.set("shizu.me", "lang", args.lower())

        await message.answer(
            self.strings("language_saved").format(utils.get_lang_flag(args.lower()))
        )

    async def loadlgpackcmd(self, app, message):
        """Load language pack (reply to file .json and write language code)"""
        reply = message.reply_to_message
        args = utils.get_args_raw(message)

        if not reply or not reply.document:
            await utils.answer(message, self.strings("reply_to"))
            return

        if not reply.document.file_name.endswith(".json"):
            await utils.answer(message, self.strings("must_be_json"))
            return

        if not args:
            await utils.answer(message, self.strings("specify_lang"))
            return

        if len(args) != 2:
            await utils.answer(message, self.strings("incorrect_language"))
            return

        await message.answer(self.strings("downloading"))
        mm = await app.download_media(reply, f"{args.lower()}.json")
        check_dir = f"{utils.get_base_dir()}/langpacks"
        if not os.path.exists(check_dir):
            os.mkdir(check_dir)
        langpack_path = f"{utils.get_base_dir()}/langpacks/{args.lower()}.json"
        shutil.move(mm, langpack_path)

        tr = translator.Translator(app, self.db)
        await tr.init()
        await message.answer(
            self.strings("language_saved").format(utils.get_lang_flag(args.lower()))
        )

    @loader.command()
    async def langs(self, app, message):
        """Available languages"""
        langs = ["us", "ru", "kz", "ua", "uz", "jp", "kr"]
        if os.path.exists(f"{utils.get_base_dir()}/langpacks"):
            langs += [
                i.split(".")[0]
                for i in os.listdir(f"{utils.get_base_dir()}/langpacks")
                if i.endswith(".json")
            ]
        await message.answer(
            "🌍 <b>Available languages:</b>\n"
            + "\n".join(
                f"{utils.get_lang_flag(lang)} <code>{lang}</code>" for lang in langs
            ),
            reply_markup=utils.chunks(
                [
                    {
                        "text": f"{utils.get_lang_flag(lang)} {lang}",
                        "callback": self.setlang_cb,
                        "args": (lang,),
                    }
                    for lang in langs
                ],
                3,
            ),
        )

    async def setlang_cb(self, app, lang):
        self.db.set("shizu.me", "lang", lang)
        await app.edit(self.strings("language_saved").format(utils.get_lang_flag(lang)))
