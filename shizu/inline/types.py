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

"""Hikka compatible `..inline.types` names mapped onto Shizu / aiogram types"""

from aiogram.types import CallbackQuery, InlineQuery, Message

from shizu.bot.events import InlineCall

InlineMessage = CallbackQuery
BotInlineCall = InlineCall
BotInlineMessage = Message
BotMessage = Message


def __getattr__(name: str):
    compat = type(name, (), {"__module__": __name__})
    globals()[name] = compat
    return compat
