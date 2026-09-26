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
import json

from typing import Union
from pyrogram.types import Message
from aiogram.types import CallbackQuery

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

        if isinstance(validator, v.Boolean) or (validator is None and isinstance(default, bool)):
            return "bool"
        if isinstance(validator, v.Choice):
            return "choice"
        if isinstance(validator, v.Series) or (validator is None and isinstance(default, list)):
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
        await target.edit(text, reply_markup=markup, inline_message_id=inline_message_id)

    def _close_row(self, back_callback, *args) -> list:
        return [
            {"text": self.strings("back"), "callback": back_callback, "args": args},
            {"text": self.strings("close"), "callback": self.inline__close},
        ]

    def _global_view(self, page: int = 0):
        mods = [m.name for m in self.all_modules.modules if getattr(m, "config", None)]
        pages = max(1, -(-len(mods) // self.MODULES_PER_PAGE))
        page = min(page, pages - 1)
        chunk = mods[page * self.MODULES_PER_PAGE : (page + 1) * self.MODULES_PER_PAGE]

        markup = utils.chunks(
            [{"text": name, "callback": self.inline__configure, "args": (name,)} for name in chunk],
            3,
        )
        markup += self.bot.build_pagination(
            self.inline__global_config, pages, current_page=page + 1
        )
        markup += [[{"text": self.strings("close"), "callback": self.inline__close}]]
        return self.strings("configure"), markup

    def _module_view(self, module, page: int = 0):
        options = list(module.config)
        pages = max(1, -(-len(options) // self.OPTIONS_PER_PAGE))
        page = min(page, pages - 1)
        chunk = options[page * self.OPTIONS_PER_PAGE : (page + 1) * self.OPTIONS_PER_PAGE]

        markup = utils.chunks(
            [
                {
                    "text": ("✏️ " if self._is_modified(module, option) else "") + option,
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
        markup += [self._close_row(self.inline__global_config)]
        return self.strings("configuring_mod").format(utils.escape_html(module.name)), markup

    def _option_view(self, module, option, inline_message_id: str, note: str = ""):
        mod = module.name
        current = module.config[option]
        kind = self._kind(module, option)
        markup = []

        if kind == "bool":
            markup.append([
                {
                    "text": self.strings("false") if current else self.strings("true"),
                    "callback": self.inline__set_value,
                    "args": (mod, option, not current),
                }
            ])
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
            markup.append([
                {
                    "text": f"{delta:+}",
                    "callback": self.inline__increment_value,
                    "args": (mod, option, delta),
                }
                for delta in (-10, -1, 1, 10)
            ])
        elif kind == "list":
            markup.append([
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
            ])
            if module.config.getdef(option):
                markup.append([
                    {
                        "text": self.strings("choose_button"),
                        "callback": self.inline__choose,
                        "args": (mod, option),
                    }
                ])

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

    async def _refresh_option(self, call, module, option, note: str = "", inline_message_id=None):
        inline_message_id = inline_message_id or call.inline_message_id
        text, markup = self._option_view(module, option, inline_message_id, note)
        await call.edit(text, reply_markup=markup, inline_message_id=inline_message_id)

    async def _apply(self, call, mod: str, option: str, get_value, inline_message_id=None):
        module = self._module(mod)
        if not module or option not in module.config:
            return await call.edit("🚫", reply_markup=[], inline_message_id=inline_message_id)

        try:
            value = get_value(module)
        except (ValueError, TypeError) as e:
            note = self.strings("validation_error").format(utils.escape_html(str(e)))
            return await self._refresh_option(call, module, option, note, inline_message_id)

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
            lambda module: self._parse(module, option, query) if query.strip() else None,
            inline_message_id,
        )

    async def inline__set_value(self, call: CallbackQuery, mod: str, option: str, value) -> None:
        await self._apply(call, mod, option, lambda module: self._check(module, option, value))

    async def inline__increment_value(
        self, call: CallbackQuery, mod: str, option: str, delta: int
    ) -> None:
        await self._apply(
            call,
            mod,
            option,
            lambda module: self._check(module, option, module.config[option] + delta),
        )

    async def inline__set_to_default(self, call: CallbackQuery, mod: str, option: str) -> None:
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
            return self._check(module, option, list(module.config[option] or []) + [item])

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

    async def inline__configure(self, call: CallbackQuery, mod: str, page: int = 0) -> None:
        module = self._module(mod)
        if module:
            await self._show(call, *self._module_view(module, page))

    async def inline__global_config(
        self, call: Union[Message, CallbackQuery], page: int = 0
    ) -> None:
        await self._show(call, *self._global_view(page))

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
                    message, f"❌ Module '{utils.escape_html(args)}' not found or has no config"
                )
                return

            if self.db.pop(module.name, "__config__"):
                self.db.save()
                self.reconfmod(module, self.db)
                await utils.answer(
                    message, f"✅ Reset configs for module '{utils.escape_html(module.name)}'"
                )
            else:
                await utils.answer(
                    message, f"ℹ️ Module '{utils.escape_html(module.name)}' has no custom configs"
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

    async def cfgstatscmd(self, app, message: Message) -> None:
        """Show statistics about module configs"""
        modules_with_configs = 0
        total_options = 0
        modified_configs = 0
        total_modified_options = 0

        for module in self.all_modules.modules:
            if hasattr(module, "config"):
                modules_with_configs += 1
                total_options += len(module.config)
                module_configs = self.db.get(module.name, "__config__", {})
                if module_configs:
                    modified_configs += 1
                    total_modified_options += len(module_configs)

        stats_text = (
            f"📊 <b>Config Statistics</b>\n\n"
            f"• Modules with configs: <b>{modules_with_configs}</b>\n"
            f"• Total config options: <b>{total_options}</b>\n"
            f"• Modified modules: <b>{modified_configs}</b>\n"
            f"• Modified options: <b>{total_modified_options}</b>\n"
            f"• Default options: <b>{total_options - total_modified_options}</b>"
        )

        await utils.answer(message, stats_text)

    async def cfgfindvalcmd(self, app, message: Message) -> None:
        """Find configs by value (search in values)"""
        query = utils.get_args_raw(message)
        if not query:
            await utils.answer(
                message,
                "❌ Please provide a search query\nUsage: <code>.cfgfindval &lt;value&gt;</code>",
            )
            return

        query_lower = str(query).lower()
        results = []

        for module in self.all_modules.modules:
            if hasattr(module, "config"):
                for option in module.config:
                    if self._is_hidden(module, option):
                        continue
                    current_value = str(module.config[option])
                    if query_lower in current_value.lower():
                        results.append(
                            f"• <b>{module.name}</b>.<code>{option}</code> = <code>{self._display(module, option, current_value)}</code>"
                        )

        if not results:
            await utils.answer(
                message, f"❌ No configs found with value matching '{utils.escape_html(query)}'"
            )
            return

        result_text = f"🔍 <b>Configs with value '{utils.escape_html(query)}':</b>\n\n" + "\n".join(
            results[:30]
        )
        if len(results) > 30:
            result_text += f"\n\n... and {len(results) - 30} more results"

        await utils.answer(message, result_text)

    async def cfgcopycmd(self, app, message: Message) -> None:
        """Copy config option from one module to another"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(
                message,
                "❌ Usage: <code>.cfgcopy &lt;source_module&gt; &lt;option&gt; &lt;target_module&gt;</code>\n"
                "Example: <code>.cfgcopy Module1 option_name Module2</code>",
            )
            return

        parts = args.split(None, 2)
        if len(parts) < 3:
            await utils.answer(
                message, "❌ Invalid format. Expected: source_module option target_module"
            )
            return

        source_module_name, option_name, target_module_name = parts

        source_module = self.all_modules.get_module(source_module_name)
        target_module = self.all_modules.get_module(target_module_name)

        if not source_module or not hasattr(source_module, "config"):
            await utils.answer(
                message, f"❌ Source module '{source_module_name}' not found"
            )
            return

        if not target_module or not hasattr(target_module, "config"):
            await utils.answer(
                message, f"❌ Target module '{target_module_name}' not found"
            )
            return

        if option_name not in source_module.config:
            await utils.answer(
                message,
                f"❌ Option '{option_name}' not found in '{source_module_name}'",
            )
            return

        if option_name not in target_module.config:
            await utils.answer(
                message,
                f"❌ Option '{option_name}' not found in '{target_module_name}'",
            )
            return

        value = source_module.config[option_name]

        # Validate value if validator exists
        if (
            hasattr(target_module.config, "_config_values")
            and option_name in target_module.config._config_values
        ):
            config_value = target_module.config._config_values[option_name]
            if config_value.validator:
                try:
                    value = config_value.validator.validate(value)
                except ValueError as e:
                    await utils.answer(message, f"❌ Validation error: {e}")
                    return

        self.db.setdefault(target_module.name, {}).setdefault("__config__", {})[
            option_name
        ] = value
        target_module.config[option_name] = value
        self.reconfmod(target_module, self.db)
        self.db.save()

        await utils.answer(
            message,
            f"✅ Copied <code>{option_name}</code> from <b>{source_module_name}</b> to <b>{target_module_name}</b>\n"
            f"Value: <code>{self._display(target_module, option_name, value)}</code>",
        )

    async def cfgvalidatecmd(self, app, message: Message) -> None:
        """Validate all module configs"""
        errors = []
        warnings = []
        validated = 0

        for module in self.all_modules.modules:
            if hasattr(module, "config"):
                module_configs = self.db.get(module.name, "__config__", {})
                for option in module.config:
                    if option in module_configs:
                        value = module_configs[option]
                        if (
                            hasattr(module.config, "_config_values")
                            and option in module.config._config_values
                        ):
                            config_value = module.config._config_values[option]
                            if config_value.validator:
                                try:
                                    validated_value = config_value.validator.validate(
                                        value
                                    )
                                    if validated_value != value:
                                        # Value was corrected
                                        module_configs[option] = validated_value
                                        module.config[option] = validated_value
                                        warnings.append(
                                            f"• <b>{module.name}</b>.<code>{option}</code>: corrected"
                                        )
                                    validated += 1
                                except (ValueError, TypeError) as e:
                                    errors.append(
                                        f"• <b>{module.name}</b>.<code>{option}</code>: {str(e)}"
                                    )

        if errors or warnings:
            # Save corrected values
            for module in self.all_modules.modules:
                if hasattr(module, "config"):
                    module_configs = self.db.get(module.name, "__config__", {})
                    if module_configs:
                        self.db.set(module.name, "__config__", module_configs)
            self.db.save()

        result_text = (
            f"✅ <b>Config Validation</b>\n\nValidated: <b>{validated}</b> options\n\n"
        )

        if warnings:
            result_text += f"⚠️ <b>Corrected ({len(warnings)}):</b>\n" + "\n".join(
                warnings[:10]
            )
            if len(warnings) > 10:
                result_text += f"\n... and {len(warnings) - 10} more"
            result_text += "\n\n"

        if errors:
            result_text += f"❌ <b>Errors ({len(errors)}):</b>\n" + "\n".join(
                errors[:10]
            )
            if len(errors) > 10:
                result_text += f"\n... and {len(errors) - 10} more"
        elif not warnings:
            result_text += "✅ All configs are valid!"

        await utils.answer(message, result_text)

    async def cfgmodifiedcmd(self, app, message: Message) -> None:
        """Show all modified (non-default) configs"""
        modified = []

        for module in self.all_modules.modules:
            if hasattr(module, "config"):
                module_configs = self.db.get(module.name, "__config__", {})
                if module_configs:
                    for option, value in module_configs.items():
                        default_value = module.config.getdef(option)
                        if value != default_value:
                            modified.append(
                                f"• <b>{module.name}</b>.<code>{option}</code>\n"
                                f"  Default: <code>{self._display(module, option, default_value)}</code>\n"
                                f"  Current: <code>{self._display(module, option, value)}</code>"
                            )

        if not modified:
            await utils.answer(
                message,
                "ℹ️ No modified configs found. All configs are using default values.",
            )
            return

        result_text = (
            f"📝 <b>Modified Configs ({len(modified)}):</b>\n\n"
            + "\n\n".join(modified[:20])
        )
        if len(modified) > 20:
            result_text += f"\n\n... and {len(modified) - 20} more modified configs"

        await utils.answer(message, result_text)

    async def cfgsetallcmd(self, app, message: Message) -> None:
        """Set config option for multiple modules at once"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(
                message,
                "❌ Usage: <code>.cfgsetall &lt;option&gt; &lt;value&gt; [module1] [module2] ...</code>\n"
                "If no modules are specified, it applies to all modules with this option",
            )
            return

        parts = args.split(None, 1)
        if len(parts) < 2:
            await utils.answer(message, "❌ Option name and value are required")
            return

        option_name, rest = parts
        tokens = rest.split()
        module_names = []
        while len(tokens) > 1 and self.all_modules.get_module(tokens[-1]):
            module_names.insert(0, tokens.pop())
        value_str = " ".join(tokens)

        updated = 0
        errors = []

        modules_to_update = []
        if module_names:
            for name in module_names:
                module = self.all_modules.get_module(name)
                if (
                    module
                    and hasattr(module, "config")
                    and option_name in module.config
                ):
                    modules_to_update.append(module)
        else:
            # Apply to all modules with this option
            for module in self.all_modules.modules:
                if hasattr(module, "config") and option_name in module.config:
                    modules_to_update.append(module)

        if not modules_to_update:
            await utils.answer(
                message, f"❌ No modules found with option '{option_name}'"
            )
            return

        for module in modules_to_update:
            try:
                validated_value = self._parse(module, option_name, value_str)

                self.db.setdefault(module.name, {}).setdefault("__config__", {})[
                    option_name
                ] = validated_value
                module.config[option_name] = validated_value
                self.reconfmod(module, self.db)
                updated += 1
            except (ValueError, TypeError) as e:
                errors.append(f"{module.name}: {str(e)}")

        self.db.save()

        result_text = (
            f"✅ Updated <code>{option_name}</code> in <b>{updated}</b> module(s)\n"
        )
        result_text += f"Value: <code>{utils.escape_html(value_str)}</code>"

        if errors:
            result_text += f"\n\n❌ Errors:\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                result_text += f"\n... and {len(errors) - 5} more"

        await utils.answer(message, result_text)

    @loader.watcher(
        only_messages=True,
    )
    async def cfg_watcher(self, app, message: Message) -> None:
        with contextlib.suppress(Exception):
            if (
                not getattr(message, "via_bot", False)
                or message.via_bot.id != (await self.bot.bot.get_me()).id
                or "This message will be deleted..."
                not in getattr(message, "text", "")
            ):
                return

            await message.delete()
