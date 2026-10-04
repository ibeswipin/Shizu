"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

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

import ast
import contextlib
import logging

from aiogram.types import CallbackQuery
from pyrogram.types import Message

from shizu import loader, utils

logger = logging.getLogger(__name__)


@loader.module("ShizuConfig", "hikamoru")
class ShizuConfig(loader.Module):
    """Interactive configurator for Shizu"""

    strings = {}

    MODULES_PER_PAGE = 15
    OPTIONS_PER_PAGE = 12

    async def inline__close(self, call: CallbackQuery) -> None:
        await call.delete()

    def _module(self, name: str):
        return next((m for m in self.all_modules.modules if m.name == name), None)

    @staticmethod
    def _validator(module, option):
        config_value = getattr(module.config, "_config_values", {}).get(option)
        return config_value.validator if config_value else None

    def _base_validator(self, module, option):
        validator = self._validator(module, option)
        if isinstance(validator, loader.Validators.Hidden):
            return validator.validator
        return validator

    def _is_hidden(self, module, option) -> bool:
        return isinstance(self._validator(module, option), loader.Validators.Hidden)

    def _is_modified(self, module, option) -> bool:
        return option in self.db.get(module.name, "__config__", {})

    def _kind(self, module, option) -> str:
        validator = self._base_validator(module, option)
        default = module.config.getdef(option)
        v = loader.Validators

        if isinstance(validator, v.Boolean) or (
            validator is None and isinstance(default, bool)
        ):
            return "bool"
        if isinstance(validator, v.Choice):
            return "choice"
        if isinstance(validator, v.Series) or (
            validator is None and isinstance(default, list)
        ):
            return "list"
        if isinstance(validator, (v.Integer, v.Float)) or (
            validator is None and isinstance(default, (int, float))
        ):
            return "number"
        return "text"

    def _validator_info(self, module, option) -> str:
        validator = self._base_validator(module, option)
        if validator is None:
            return ""

        info = []
        if getattr(validator, "minimum", None) is not None:
            info.append(f"Min: {validator.minimum}")
        if getattr(validator, "maximum", None) is not None:
            info.append(f"Max: {validator.maximum}")
        if hasattr(validator, "pattern"):
            info.append(f"Pattern: {validator.pattern.pattern}")
        if hasattr(validator, "possible_values"):
            info.append("Choice: " + ", ".join(map(str, validator.possible_values)))

        return " | ".join(info) or f"Validator: {type(validator).__name__}"

    def _display(self, module, option, value) -> str:
        if self._is_hidden(module, option):
            return "•" * 8 if value else ""
        text = str(value)
        if len(text) > 1000:
            text = text[:1000] + "…"
        return utils.escape_html(text)

    def _check(self, module, option, value):
        validator = self._validator(module, option)
        return validator.validate(value) if validator else value

    def _parse(self, module, option, raw: str):
        try:
            value = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            value = raw

        if self._validator(module, option) is None and isinstance(
            module.config.getdef(option), str
        ):
            value = raw

        return self._check(module, option, value)

    def _save(self, module, option, value) -> None:
        self.db.setdefault(module.name, {}).setdefault("__config__", {})[option] = value
        self.db.save()
        self.reconfmod(module, self.db)

    def _reset(self, module, option) -> None:
        self.db.get(module.name, "__config__", {}).pop(option, None)
        self.db.save()
        self.reconfmod(module, self.db)

    async def _show(self, target, text: str, markup: list, inline_message_id=None):
        if isinstance(target, Message):
            return await target.answer(text, reply_markup=markup)
        await target.edit(
            text, reply_markup=markup, inline_message_id=inline_message_id
        )

    def _close_row(self, back_callback, *args) -> list:
        return [
            {"text": self.strings("back"), "callback": back_callback, "args": args},
            {"text": self.strings("close"), "callback": self.inline__close},
        ]

    SECTIONS = ("internal", "external")
    SECTION_EMOJI = {"internal": "🛠", "external": "🧩"}

    def _section_of(self, module) -> str:
        return "internal" if module.name in self.all_modules.cmodules else "external"

    def _configurable(self) -> dict:
        sections = {section: [] for section in self.SECTIONS}
        for module in sorted(self.all_modules.modules, key=lambda m: m.name.lower()):
            if getattr(module, "config", None):
                sections[self._section_of(module)].append(module.name)
        return sections

    def _sections_view(self):
        sections = self._configurable()
        markup = [
            [
                {
                    "text": f"{self.SECTION_EMOJI[name]} {self.strings(name + '_title')} · {len(mods)}",
                    "callback": self.inline__global_config,
                    "args": (name, 0),
                }
                for name, mods in sections.items()
                if mods
            ]
        ]
        markup += [[{"text": self.strings("close"), "callback": self.inline__close}]]
        return self.strings("configure"), markup

    def _global_view(self, section: str = None, page: int = 0):
        sections = self._configurable()
        if section not in sections:
            return self._sections_view()
        mods = sections[section]
        pages = max(1, -(-len(mods) // self.MODULES_PER_PAGE))
        page = min(page, pages - 1)
        chunk = mods[page * self.MODULES_PER_PAGE : (page + 1) * self.MODULES_PER_PAGE]

        markup = utils.chunks(
            [
                {"text": name, "callback": self.inline__configure, "args": (name,)}
                for name in chunk
            ],
            3,
        )
        markup += self.bot.build_pagination(
            self.inline__global_config, pages, current_page=page + 1, args=(section,)
        )
        markup += [self._close_row(self.inline__global_config)]
        title = (
            f"{self.SECTION_EMOJI[section]} <b>{self.strings(section + '_title')}</b>"
        )
        return f"{self.strings('configure')}\n\n{title}", markup

    def _module_view(self, module, page: int = 0):
        options = list(module.config)
        pages = max(1, -(-len(options) // self.OPTIONS_PER_PAGE))
        page = min(page, pages - 1)
        chunk = options[
            page * self.OPTIONS_PER_PAGE : (page + 1) * self.OPTIONS_PER_PAGE
        ]

        markup = utils.chunks(
            [
                {
                    "text": ("✏️ " if self._is_modified(module, option) else "")
                    + option,
                    "callback": self.inline__configure_option,
                    "args": (module.name, option),
                }
                for option in chunk
            ],
            2,
        )
        markup += self.bot.build_pagination(
            self.inline__configure, pages, current_page=page + 1, args=(module.name,)
        )
        markup += [
            self._close_row(self.inline__global_config, self._section_of(module))
        ]
        return self.strings("configuring_mod").format(
            utils.escape_html(module.name)
        ), markup

    def _option_view(self, module, option, inline_message_id: str, note: str = ""):
        mod = module.name
        current = module.config[option]
        kind = self._kind(module, option)
        markup = []

        if kind == "bool":
            markup.append(
                [
                    {
                        "text": self.strings("false")
                        if current
                        else self.strings("true"),
                        "callback": self.inline__set_value,
                        "args": (mod, option, not current),
                    }
                ]
            )
        elif kind == "choice":
            markup += utils.chunks(
                [
                    {
                        "text": ("✅ " if value == current else "") + str(value),
                        "callback": self.inline__set_value,
                        "args": (mod, option, value),
                    }
                    for value in self._base_validator(module, option).possible_values
                ],
                3,
            )
        elif kind == "number":
            markup.append(
                [
                    {
                        "text": f"{delta:+}",
                        "callback": self.inline__increment_value,
                        "args": (mod, option, delta),
                    }
                    for delta in (-10, -1, 1, 10)
                ]
            )
        elif kind == "list":
            markup.append(
                [
                    {
                        "text": self.strings("add_value_to_list_button"),
                        "input": self.strings("enter_value"),
                        "handler": self.inline__add_item,
                        "args": (mod, option, inline_message_id),
                    },
                    {
                        "text": self.strings("remove_value_from_list_button"),
                        "input": self.strings("enter_value"),
                        "handler": self.inline__remove_item,
                        "args": (mod, option, inline_message_id),
                    },
                ]
            )
            if module.config.getdef(option):
                markup.append(
                    [
                        {
                            "text": self.strings("choose_button"),
                            "callback": self.inline__choose,
                            "args": (mod, option),
                        }
                    ]
                )

        markup.append(
            [
                {
                    "text": self.strings("ent_value"),
                    "input": self.strings("enter_value"),
                    "handler": self.inline__set_config,
                    "args": (mod, option, inline_message_id),
                }
            ]
            + (
                [
                    {
                        "text": self.strings("restore_def_button"),
                        "callback": self.inline__set_to_default,
                        "args": (mod, option),
                    }
                ]
                if self._is_modified(module, option)
                else []
            )
        )
        markup.append(self._close_row(self.inline__configure, mod))

        doc = module.config.getdoc(option)
        if info := self._validator_info(module, option):
            doc = f"{doc}\n\n{info}"

        text = self.strings("configuring_option").format(
            utils.escape_html(option),
            utils.escape_html(mod),
            utils.escape_html(doc),
            self._display(module, option, module.config.getdef(option)),
            self._display(module, option, current),
        )
        if note:
            text += f"\n\n{note}"

        return text, markup

    async def _refresh_option(
        self, call, module, option, note: str = "", inline_message_id=None
    ):
        inline_message_id = inline_message_id or call.inline_message_id
        text, markup = self._option_view(module, option, inline_message_id, note)
        await call.edit(text, reply_markup=markup, inline_message_id=inline_message_id)

    async def _apply(
        self, call, mod: str, option: str, get_value, inline_message_id=None
    ):
        module = self._module(mod)
        if not module or option not in module.config:
            return await call.edit(
                "🚫", reply_markup=[], inline_message_id=inline_message_id
            )

        try:
            value = get_value(module)
        except (ValueError, TypeError) as e:
            note = self.strings("validation_error").format(utils.escape_html(str(e)))
            return await self._refresh_option(
                call, module, option, note, inline_message_id
            )

        if value is None:
            self._reset(module, option)
        else:
            self._save(module, option, value)

        await self._refresh_option(
            call, module, option, self.strings("saved"), inline_message_id
        )

    async def inline__set_config(
        self, call, query: str, mod: str, option: str, inline_message_id: str
    ) -> None:
        await self._apply(
            call,
            mod,
            option,
            lambda module: (
                self._parse(module, option, query) if query.strip() else None
            ),
            inline_message_id,
        )

    async def inline__set_value(
        self, call: CallbackQuery, mod: str, option: str, value
    ) -> None:
        await self._apply(
            call, mod, option, lambda module: self._check(module, option, value)
        )

    async def inline__increment_value(
        self, call: CallbackQuery, mod: str, option: str, delta: int
    ) -> None:
        await self._apply(
            call,
            mod,
            option,
            lambda module: self._check(module, option, module.config[option] + delta),
        )

    async def inline__set_to_default(
        self, call: CallbackQuery, mod: str, option: str
    ) -> None:
        module = self._module(mod)
        if module:
            self._reset(module, option)
            await self._refresh_option(call, module, option, self.strings("restored"))

    async def inline__add_item(
        self, call, query: str, mod: str, option: str, inline_message_id: str
    ) -> None:
        def add(module):
            try:
                item = ast.literal_eval(query)
            except (ValueError, SyntaxError):
                item = query
            return self._check(
                module, option, list(module.config[option] or []) + [item]
            )

        await self._apply(call, mod, option, add, inline_message_id)

    async def inline__remove_item(
        self, call, query: str, mod: str, option: str, inline_message_id: str
    ) -> None:
        def remove(module):
            current = list(module.config[option] or [])
            left = [item for item in current if str(item) != query.strip()]
            if len(left) == len(current):
                raise ValueError(self.strings("value_not_found"))
            return left

        await self._apply(call, mod, option, remove, inline_message_id)

    async def inline__choose(self, call: CallbackQuery, mod: str, option: str) -> None:
        module = self._module(mod)
        if not module:
            return

        current = [str(item) for item in module.config[option] or []]
        markup = utils.chunks(
            [
                {
                    "text": f"{'✅' if str(item) in current else '❌'} {item}",
                    "callback": self.inline__choose_set,
                    "args": (mod, option, index),
                }
                for index, item in enumerate(module.config.getdef(option))
            ],
            3,
        )
        markup += [self._close_row(self.inline__configure_option, mod, option)]

        text, _ = self._option_view(module, option, call.inline_message_id)
        await call.edit(text, reply_markup=markup)

    async def inline__choose_set(
        self, call: CallbackQuery, mod: str, option: str, index: int
    ) -> None:
        module = self._module(mod)
        if not module:
            return

        item = module.config.getdef(option)[index]
        current = list(module.config[option] or [])
        if any(str(i) == str(item) for i in current):
            current = [i for i in current if str(i) != str(item)]
        else:
            current.append(item)

        try:
            self._save(module, option, self._check(module, option, current))
        except (ValueError, TypeError) as e:
            return await call.answer(str(e), show_alert=True)

        await self.inline__choose(call, mod, option)

    async def inline__configure_option(
        self, call: CallbackQuery, mod: str, config_opt: str
    ) -> None:
        module = self._module(mod)
        if module and config_opt in module.config:
            await self._refresh_option(call, module, config_opt)

    async def inline__configure(
        self, call: CallbackQuery, mod: str, page: int = 0
    ) -> None:
        module = self._module(mod)
        if module:
            await self._show(call, *self._module_view(module, page))

    async def inline__global_config(
        self, call: Message | CallbackQuery, section: str = None, page: int = 0
    ) -> None:
        await self._show(call, *self._global_view(section, page))

    async def configcmd(self, app, message: Message) -> None:
        """[module] - Configure modules"""
        args = utils.get_args_raw(message)
        module = self.all_modules.get_module(args) if args else None

        if module and getattr(module, "config", None):
            return await self._show(message, *self._module_view(module))

        await self.inline__global_config(message)

    async def resetcfgcmd(self, app, message: Message) -> None:
        """Reset all configs to defaults (or specific module if provided)"""
        args = utils.get_args_raw(message)

        if args:
            # Reset specific module
            module = self.all_modules.get_module(args)
            if not module or not hasattr(module, "config"):
                await utils.answer(
                    message,
                    f"❌ Module '{utils.escape_html(args)}' not found or has no config",
                )
                return

            if self.db.pop(module.name, "__config__"):
                self.db.save()
                self.reconfmod(module, self.db)
                await utils.answer(
                    message,
                    f"✅ Reset configs for module '{utils.escape_html(module.name)}'",
                )
            else:
                await utils.answer(
                    message,
                    f"ℹ️ Module '{utils.escape_html(module.name)}' has no custom configs",
                )
        else:
            # Reset all modules
            reset_count = 0
            for module in self.all_modules.modules:
                if hasattr(module, "config"):
                    if self.db.pop(module.name, "__config__"):
                        self.reconfmod(module, self.db)
                        reset_count += 1

            self.db.save()
            await utils.answer(
                message,
                f"✅ Reset configs for {reset_count} module(s)",
            )

    @loader.watcher(
        only_messages=True,
    )
    async def cfg_watcher(self, app, message: Message) -> None:
        with contextlib.suppress(Exception):
            if (
                not getattr(message, "via_bot", False)
                or message.via_bot.id != (await self.bot.bot.get_me()).id
                or "This message will be deleted..." not in getattr(message, "text", "")
            ):
                return

            await message.delete()
