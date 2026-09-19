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

import inspect
from types import FunctionType
from typing import Union

from aiogram.types import CallbackQuery, InlineQuery, Message
from pyrogram import Client

from shizu import database, types


class Item:
    """Base class for all classes"""

    def __init__(self) -> None:
        """Initializing a class"""
        self._all_modules: types.ModulesManager = None
        self._db: database.Database = None
        self._app: Client = None
        self._markup_ttl = 60 * 60 * 24
        self._custom_map = {}

    async def _check_filters(
        self,
        func: FunctionType,
        module: types.Module,
        update_type: Union[Message, InlineQuery, CallbackQuery],
    ) -> bool:
        """Checking filters"""
        if custom_filters := getattr(func, "_filters", None):
            coro = custom_filters(module, self._app, update_type)
            if inspect.iscoroutine(coro):
                coro = await coro

            if not coro:
                return False
        elif update_type.from_user.id != self._all_modules.me.id:
            return False

        return True
