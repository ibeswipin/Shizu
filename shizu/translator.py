"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

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

import os
import json
from functools import lru_cache

from . import utils


class Translator:
    def __init__(self, client, db):
        self._client = client
        self.db = db

    async def init(self) -> bool:
        return True

    @lru_cache(maxsize=64)
    def _load_langpack(self, lang: str):
        """Loads langpack file and caches result."""
        path = os.path.join(utils.get_base_dir(), f"langpacks/{lang}.json")

        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def _get_lang(self):
        return self.db.get("shizu.me", "lang", "en")

    def getkey(self, key: str):
        """
        Returns translated string from language pack with fallback logic:
        1) selected language
        2) english (default)
        3) return False if not found
        """
        lang = self._get_lang()

        lang_pack = self._load_langpack(lang)
        if key in lang_pack:
            return lang_pack[key]

        if lang != "en":
            default_pack = self._load_langpack("en")
            if key in default_pack:
                return default_pack[key]

        return False

    def gettext(self, key: str):
        """Public method: returns translation or key itself."""
        return self.getkey(key) or key


class Strings:
    """
    Allows using strings like:

        s = Strings(module, translator, db)
        text = s["start"]     → resolves to: "module_name.start"

    """

    def __init__(self, mod, translator, db):
        self._mod = mod
        self._translator = translator
        self._db = db
        self._base_strings = mod.strings

    def __getitem__(self, key: str) -> str:
        module_key = f"{self._mod.__module__}.{key}"

        if self._translator:
            tr = self._translator.getkey(module_key)
            if tr:
                return tr

        lang = self._db.get("shizu.me", "lang", "en")
        lang_attr = getattr(self._mod, f"strings_{lang}", self._base_strings)

        return lang_attr.get(key, self._base_strings.get(key, "Unknown string"))

    def __call__(self, key: str) -> str:
        return self.__getitem__(key)

    def __iter__(self):
        return iter(self._base_strings)
