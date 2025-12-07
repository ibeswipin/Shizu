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

    async def inline__close(self, call: CallbackQuery) -> None:
        await call.delete()

    async def inline__set_to_default(
        self,
        call: CallbackQuery,
        mod: str,
        option: str,
        inline_message_id: str,
    ) -> None:
        for module in self.all_modules.modules:
            if module.name == mod:
                with contextlib.suppress(KeyError):
                    del self.db.setdefault(module.name, {}).setdefault(
                        "__config__", {}
                    )[option]
                self.reconfmod(module, self.db)
                self.db.save()

        await call.edit(
            self.strings("restored"),
            reply_markup=[
                [
                    {
                        "text": self.strings("back"),
                        "callback": self.inline__configure_option,
                        "args": (mod, option),
                    },
                    {"text": self.strings("close"), "callback": self.inline__close},
                ]
            ],
            inline_message_id=inline_message_id,
        )

    def _get_validator_info(self, module, option):
        if (
            hasattr(module.config, "_config_values")
            and option in module.config._config_values
        ):
            config_value = module.config._config_values[option]
            if config_value and config_value.validator:
                validator = config_value.validator
                info = []
                validator_type = type(validator).__name__
                
                if hasattr(validator, "minimum") and validator.minimum is not None:
                    info.append(f"Min: {validator.minimum}")
                if hasattr(validator, "maximum") and validator.maximum is not None:
                    info.append(f"Max: {validator.maximum}")
                if hasattr(validator, "pattern"):
                    info.append(f"Pattern: {validator.pattern.pattern}")
                
                if info:
                    return config_value, " | ".join(info)
                else:
                    return config_value, f"Validator: {validator_type}"
        return None, None

    async def inline__set_config(
        self,
        call: CallbackQuery,
        query: str,
        mod: str,
        option: str,
        inline_message_id: str,
    ) -> None:
        validation_error = None
        with contextlib.suppress(ValueError, SyntaxError):
            query = ast.literal_eval(query)

        for module in self.all_modules.modules:
            if module.name == mod:
                if query is not None and query != "":
                    config_value, validator_info = self._get_validator_info(
                        module, option
                    )
                    if config_value and config_value.validator:
                        try:
                            query = config_value.validator.validate(query)
                        except ValueError as e:
                            validation_error = str(e)
                            await call.answer(
                                f"Validation error: {validation_error}", show_alert=True
                            )
                            return

                    self.db.setdefault(module.name, {}).setdefault("__config__", {})[
                        option
                    ] = query
                    module.config[option] = query
                else:
                    with contextlib.suppress(KeyError):
                        del self.db.setdefault(module.name, {}).setdefault(
                            "__config__", {}
                        )[option]

                self.reconfmod(module, self.db)
                self.db.save()

        await call.edit(
            self.strings("option_saved").format(mod, option, query),
            reply_markup=[
                [
                    {
                        "text": self.strings("back"),
                        "callback": self.inline__configure_option,
                        "args": (mod, option),
                    },
                    {"text": self.strings("close"), "callback": self.inline__close},
                ]
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__add_item(
        self,
        call: CallbackQuery,
        query: str,
        mod: str,
        option: str,
        inline_message_id: str,
    ) -> None:
        with contextlib.suppress(ValueError, SyntaxError):
            query = ast.literal_eval(query)

        for module in self.all_modules.modules:
            if module.name == mod:
                config_value, _ = self._get_validator_info(module, option)
                if config_value and config_value.validator:
                    try:
                        query = config_value.validator.validate(query)
                    except ValueError as e:
                        await call.answer(
                            f"Validation error: {str(e)}", show_alert=True
                        )
                        return

                try:
                    self.db.setdefault(module.name, {}).setdefault("__config__", {})[
                        option
                    ] += [query]

                except KeyError:
                    self.db.setdefault(module.name, {}).setdefault("__config__", {})[
                        option
                    ] = module.config[option] + [query]

                self.reconfmod(module, self.db)
                self.db.save()

        await call.edit(
            self.strings("option_added").format(query),
            reply_markup=[
                [
                    {
                        "text": self.strings("back"),
                        "callback": self.inline__add_delete,
                        "args": (mod, option),
                    },
                    {"text": self.strings("close"), "callback": self.inline__close},
                ]
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__remove_item(
        self,
        call: CallbackQuery,
        query: str,
        mod: str,
        option: str,
        inline_message_id: str,
    ) -> None:
        with contextlib.suppress(ValueError, SyntaxError):
            query = ast.literal_eval(query)

        for module in self.all_modules.modules:
            if module.name == mod:
                try:
                    self.db.setdefault(module.name, {}).setdefault("__config__", {})[
                        option
                    ].remove(query)

                except KeyError:
                    self.db.setdefault(module.name, {}).setdefault("__config__", {})[
                        option
                    ] = module.config[option].remove(query)

                self.reconfmod(module, self.db)
                self.db.save()

        await call.edit(
            self.strings("opeion_removed").format(query),
            reply_markup=[
                [
                    {
                        "text": self.strings("back"),
                        "callback": self.inline__add_delete,
                        "args": (mod, option),
                    },
                    {"text": self.strings("close"), "callback": self.inline__close},
                ]
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__true_false(
        self, call: CallbackQuery, mod: str, config_opt: str
    ) -> None:
        for module in self.all_modules.modules:
            if module.name == mod:
                if isinstance(module.config[config_opt], bool):
                    await call.edit(
                        self.strings("configuring_option").format(
                            utils.escape_html(config_opt),
                            utils.escape_html(mod),
                            utils.escape_html(module.config.getdoc(config_opt)),
                            utils.escape_html(module.config.getdef(config_opt)),
                            utils.escape_html(module.config[config_opt]),
                        ),
                        reply_markup=[
                            [
                                {
                                    "text": (
                                        self.strings("false")
                                        if module.config[config_opt]
                                        else self.strings("true")
                                    ),
                                    "callback": self.inline__true_false_set,
                                    "args": (
                                        not module.config[config_opt],
                                        mod,
                                        config_opt,
                                        call.inline_message_id,
                                    ),
                                }
                            ],
                            [
                                {
                                    "text": self.strings("back"),
                                    "callback": self.inline_advanced,
                                    "args": (mod, config_opt),
                                },
                                {
                                    "text": self.strings("close"),
                                    "callback": self.inline__close,
                                },
                            ],
                        ],
                    )
                else:
                    return await call.answer("This option doesn't have a boolean type!")

    async def inline__true_false_set(
        self,
        call: CallbackQuery,
        query: bool,
        mod: str,
        option: str,
        inline_message_id: str,
    ) -> None:
        for module in self.all_modules.modules:
            if module.name == mod:
                self.db.setdefault(module.name, {}).setdefault("__config__", {})[
                    option
                ] = query
                module.config[option] = query
                self.reconfmod(module, self.db)
                self.db.save()

        await self.inline__true_false(call, mod, option)

    async def inline__add_delete(
        self, call: CallbackQuery, mod: str, config_opt: str
    ) -> None:
        for module in self.all_modules.modules:
            if module.name == mod:
                if isinstance(module.config[config_opt], list):
                    await call.edit(
                        self.strings("configuring_option").format(
                            utils.escape_html(config_opt),
                            utils.escape_html(mod),
                            utils.escape_html(module.config.getdoc(config_opt)),
                            utils.escape_html(module.config.getdef(config_opt)),
                            utils.escape_html(module.config[config_opt]),
                        ),
                        reply_markup=[
                            [
                                {
                                    "text": self.strings("add_value_to_list_button"),
                                    "input": self.strings("enter_value"),
                                    "handler": self.inline__add_item,
                                    "args": (mod, config_opt, call.inline_message_id),
                                },
                                {
                                    "text": self.strings(
                                        "remove_value_from_list_button"
                                    ),
                                    "input": self.strings("enter_value"),
                                    "handler": self.inline__remove_item,
                                    "args": (mod, config_opt, call.inline_message_id),
                                },
                            ],
                            [
                                {
                                    "text": self.strings("back"),
                                    "callback": self.inline_advanced,
                                    "args": (mod, config_opt),
                                },
                                {
                                    "text": self.strings("close"),
                                    "callback": self.inline__close,
                                },
                            ],
                        ],
                    )
                else:
                    return await call.answer("This option doesn't have a list type!")

    async def inline_advanced(
        self, call: CallbackQuery, mod: str, config_opt: str
    ) -> None:
        for module in self.all_modules.modules:
            if module.name == mod:
                await call.edit(
                    self.strings("advanced").format(utils.escape_html(mod)),
                    reply_markup=[
                        [
                            {
                                "text": self.strings("true_false_button"),
                                "callback": self.inline__true_false,
                                "args": (mod, config_opt),
                            },
                            {
                                "text": self.strings("add_delete_button"),
                                "callback": self.inline__add_delete,
                                "args": (mod, config_opt),
                            },
                        ],
                        [
                            {
                                "text": self.strings("choose_button"),
                                "callback": self.inline__choose,
                                "args": (mod, config_opt),
                            }
                        ],
                        [
                            {
                                "text": self.strings("back"),
                                "callback": self.inline__configure_option,
                                "args": (mod, config_opt),
                            },
                            {
                                "text": self.strings("close"),
                                "callback": self.inline__close,
                            },
                        ],
                    ],
                )

    async def inline__choose(
        self, call: CallbackQuery, mod: str, config_opt: str
    ) -> None:
        for module in self.all_modules.modules:
            if module.name == mod:
                if not isinstance(module.config[config_opt], list):
                    return await call.answer("This option doesn't have a default list!")

                if not self.db.get(module.name, "__config__", {}).get(config_opt):
                    self.db.setdefault(module.name, {}).setdefault("__config__", {})[
                        config_opt
                    ] = module.config.getdef(config_opt)[:]

                    self.reconfmod(module, self.db)
                    self.db.save()

                kb = []
                ops = [str(i) for i in module.config[config_opt]]
                v = module.config.getdef(config_opt)[:]

                for mod_row in utils.chunks(v, 3):
                    row = [
                        {
                            "text": f"{'✅' if btn in ops else '❌'} {btn}",
                            "callback": self.inline__choose_set,
                            "args": (mod, config_opt, btn),
                        }
                        for btn in mod_row
                    ]
                    kb += [row]

                kb += [
                    [
                        {
                            "text": self.strings["back"],
                            "callback": self.inline_advanced,
                            "args": (mod, config_opt),
                        },
                        {
                            "text": self.strings["close"],
                            "callback": self.inline__close,
                        },
                    ]
                ]

                await call.edit(
                    self.strings("configuring_option").format(
                        utils.escape_html(config_opt),
                        utils.escape_html(mod),
                        utils.escape_html(module.config.getdoc(config_opt)),
                        utils.escape_html(module.config.getdef(config_opt)),
                        utils.escape_html(module.config[config_opt]),
                    ),
                    reply_markup=kb,
                )

    async def inline__choose_set(
        self,
        call: CallbackQuery,
        mod: str,
        option: str,
        value: str,
    ) -> None:
        for module in self.all_modules.modules:
            if module.name == mod:
                if value in module.config[option]:
                    module.config[option] = [
                        v for v in module.config[option] if v != value
                    ]
                else:
                    module.config[option].append(value)

                self.db.setdefault(module.name, {}).setdefault("__config__", {})[
                    option
                ] = module.config[option][:]

                self.reconfmod(module, self.db)
                self.db.save()

                await self.inline__choose(call, mod, option)

    async def inline__increment_value(
        self,
        call: CallbackQuery,
        mod: str,
        option: str,
        delta: int,
        inline_message_id: str,
    ) -> None:
        for module in self.all_modules.modules:
            if module.name == mod:
                current_value = module.config[option]
                if isinstance(current_value, (int, float)):
                    new_value = current_value + delta
                    config_value, _ = self._get_validator_info(module, option)
                    if config_value and config_value.validator:
                        try:
                            new_value = config_value.validator.validate(new_value)
                        except ValueError as e:
                            await call.answer(
                                f"Validation error: {str(e)}", show_alert=True
                            )
                            return

                    self.db.setdefault(module.name, {}).setdefault("__config__", {})[
                        option
                    ] = new_value
                    module.config[option] = new_value
                    self.reconfmod(module, self.db)
                    self.db.save()

                    await self.inline__configure_option(call, mod, option)

    async def inline__configure_option(
        self, call: CallbackQuery, mod: str, config_opt: str
    ) -> None:
        for module in self.all_modules.modules:
            if module.name == mod:
                config_value, validator_info = self._get_validator_info(
                    module, config_opt
                )
                current_value = module.config[config_opt]
                
                is_numeric = isinstance(current_value, (int, float))
                if not is_numeric and current_value is not None:
                    try:
                        float(current_value)
                        is_numeric = True
                    except (ValueError, TypeError):
                        pass
                
                has_validator = config_value is not None and config_value.validator is not None
                
                is_float_or_int_validator = False
                if has_validator:
                    validator = config_value.validator
                    validator_type = type(validator).__name__
                    is_float_or_int_validator = validator_type in ("Float", "Integer")

                doc = module.config.getdoc(config_opt)
                if validator_info:
                    doc = f"{doc}\n\n{validator_info}"

                markup = []
                if (is_numeric or is_float_or_int_validator) and has_validator:
                    markup.append(
                        [
                            {
                                "text": "-1",
                                "callback": self.inline__increment_value,
                                "args": (mod, config_opt, -1, call.inline_message_id),
                            },
                            {
                                "text": "+1",
                                "callback": self.inline__increment_value,
                                "args": (mod, config_opt, 1, call.inline_message_id),
                            },
                            {
                                "text": "-10",
                                "callback": self.inline__increment_value,
                                "args": (mod, config_opt, -10, call.inline_message_id),
                            },
                            {
                                "text": "+10",
                                "callback": self.inline__increment_value,
                                "args": (mod, config_opt, 10, call.inline_message_id),
                            },
                        ]
                    )

                markup.extend(
                    [
                        [
                            {
                                "text": self.strings("ent_value"),
                                "input": self.strings("enter_value"),
                                "handler": self.inline__set_config,
                                "args": (mod, config_opt, call.inline_message_id),
                            },
                            {
                                "text": self.strings("restore_def_button"),
                                "callback": self.inline__set_to_default,
                                "args": (mod, config_opt, call.inline_message_id),
                            },
                        ],
                        [
                            {
                                "text": self.strings("advanced_button"),
                                "callback": self.inline_advanced,
                                "args": (mod, config_opt),
                            }
                        ],
                        [
                            {
                                "text": self.strings("back"),
                                "callback": self.inline__configure,
                                "args": (mod,),
                            },
                            {
                                "text": self.strings("close"),
                                "callback": self.inline__close,
                            },
                        ],
                    ]
                )

                await call.edit(
                    self.strings("configuring_option").format(
                        utils.escape_html(config_opt),
                        utils.escape_html(mod),
                        utils.escape_html(doc),
                        utils.escape_html(module.config.getdef(config_opt)),
                        utils.escape_html(module.config[config_opt]),
                    ),
                    reply_markup=markup,
                )

    async def inline__configure(self, call: CallbackQuery, mod: str) -> None:
        btns = []
        with contextlib.suppress(Exception):
            for module in self.all_modules.modules:
                if module.name == mod:
                    for param in module.config:
                        btns += [
                            {
                                "text": param,
                                "callback": self.inline__configure_option,
                                "args": (mod, param),
                            }
                        ]

        await call.edit(
            self.strings("configuring_mod").format(utils.escape_html(mod)),
            reply_markup=list(utils.chunks(btns, 2))
            + [
                [
                    {
                        "text": self.strings("back"),
                        "callback": self.inline__global_config,
                    },
                    {"text": self.strings("close"), "callback": self.inline__close},
                ]
            ],
        )

    async def inline__global_config(self, call: Union[Message, CallbackQuery]) -> None:
        to_config = [
            mod.name for mod in self.all_modules.modules if hasattr(mod, "config")
        ]
        kb = []
        for mod_row in utils.chunks(to_config, 3):
            row = [
                {"text": btn, "callback": self.inline__configure, "args": (btn,)}
                for btn in mod_row
            ]
            kb += [row]

        kb += [[{"text": self.strings("close"), "callback": self.inline__close}]]

        if isinstance(call, Message):
            await call.answer(self.strings("configure"), reply_markup=kb)
        else:
            await call.edit(self.strings("configure"), reply_markup=kb)

    async def configcmd(self, app, message: Message) -> None:
        """Configure modules"""

        await self.inline__global_config(message)

    async def resetcfgcmd(self, app, message: Message) -> None:
        """Reset all configs to defaults (or specific module if provided)"""
        args = utils.get_args_raw(message)
        
        if args:
            # Reset specific module
            module = self.all_modules.get_module(args)
            if not module or not hasattr(module, "config"):
                await utils.answer(message, f"❌ Module '{args}' not found or has no config")
                return
            
            module_configs = self.db.get(module.name, "__config__", {})
            if module_configs:
                del self.db.get(module.name, {})["__config__"]
                self.reconfmod(module, self.db)
                self.db.save()
                await utils.answer(message, f"✅ Reset configs for module '{args}'")
            else:
                await utils.answer(message, f"ℹ️ Module '{args}' has no custom configs")
        else:
            # Reset all modules
            reset_count = 0
            for module in self.all_modules.modules:
                if hasattr(module, "config"):
                    module_configs = self.db.get(module.name, "__config__", {})
                    if module_configs:
                        with contextlib.suppress(KeyError):
                            del self.db.get(module.name, {})["__config__"]
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
            await utils.answer(message, "❌ Please provide a search query\nUsage: <code>.cfgfindval &lt;value&gt;</code>")
            return

        query_lower = str(query).lower()
        results = []

        for module in self.all_modules.modules:
            if hasattr(module, "config"):
                for option in module.config:
                    current_value = str(module.config[option])
                    if query_lower in current_value.lower():
                        results.append(
                            f"• <b>{module.name}</b>.<code>{option}</code> = <code>{utils.escape_html(current_value)}</code>"
                        )

        if not results:
            await utils.answer(message, f"❌ No configs found with value matching '{query}'")
            return

        result_text = f"🔍 <b>Configs with value '{query}':</b>\n\n" + "\n".join(results[:30])
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
                "Example: <code>.cfgcopy Module1 option_name Module2</code>"
            )
            return

        parts = args.split(None, 2)
        if len(parts) < 3:
            await utils.answer(message, "❌ Invalid format. Need: source_module option target_module")
            return

        source_module_name, option_name, target_module_name = parts

        source_module = self.all_modules.get_module(source_module_name)
        target_module = self.all_modules.get_module(target_module_name)

        if not source_module or not hasattr(source_module, "config"):
            await utils.answer(message, f"❌ Source module '{source_module_name}' not found")
            return

        if not target_module or not hasattr(target_module, "config"):
            await utils.answer(message, f"❌ Target module '{target_module_name}' not found")
            return

        if option_name not in source_module.config:
            await utils.answer(message, f"❌ Option '{option_name}' not found in '{source_module_name}'")
            return

        if option_name not in target_module.config:
            await utils.answer(message, f"❌ Option '{option_name}' not found in '{target_module_name}'")
            return

        value = source_module.config[option_name]
        
        # Validate value if validator exists
        if hasattr(target_module.config, "_config_values") and option_name in target_module.config._config_values:
            config_value = target_module.config._config_values[option_name]
            if config_value.validator:
                try:
                    value = config_value.validator.validate(value)
                except ValueError as e:
                    await utils.answer(message, f"❌ Validation error: {e}")
                    return

        self.db.setdefault(target_module.name, {}).setdefault("__config__", {})[option_name] = value
        target_module.config[option_name] = value
        self.reconfmod(target_module, self.db)
        self.db.save()

        await utils.answer(
            message,
            f"✅ Copied <code>{option_name}</code> from <b>{source_module_name}</b> to <b>{target_module_name}</b>\n"
            f"Value: <code>{utils.escape_html(str(value))}</code>"
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
                        if hasattr(module.config, "_config_values") and option in module.config._config_values:
                            config_value = module.config._config_values[option]
                            if config_value.validator:
                                try:
                                    validated_value = config_value.validator.validate(value)
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

        result_text = f"✅ <b>Config Validation</b>\n\nValidated: <b>{validated}</b> options\n\n"
        
        if warnings:
            result_text += f"⚠️ <b>Corrected ({len(warnings)}):</b>\n" + "\n".join(warnings[:10])
            if len(warnings) > 10:
                result_text += f"\n... and {len(warnings) - 10} more"
            result_text += "\n\n"
        
        if errors:
            result_text += f"❌ <b>Errors ({len(errors)}):</b>\n" + "\n".join(errors[:10])
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
                                f"  Default: <code>{utils.escape_html(str(default_value))}</code>\n"
                                f"  Current: <code>{utils.escape_html(str(value))}</code>"
                            )

        if not modified:
            await utils.answer(message, "ℹ️ No modified configs found. All configs are using default values.")
            return

        result_text = f"📝 <b>Modified Configs ({len(modified)}):</b>\n\n" + "\n\n".join(modified[:20])
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
                "If no modules specified, applies to all modules with this option"
            )
            return

        parts = args.split(None, 1)
        if len(parts) < 2:
            await utils.answer(message, "❌ Need option name and value")
            return

        option_name, rest = parts
        # Try to parse value and module list
        if " " in rest:
            # Has module list
            value_str, *module_names = rest.rsplit(" ", len(rest.split()) - 1)
            try:
                value = ast.literal_eval(value_str)
            except (ValueError, SyntaxError):
                value = value_str
        else:
            # Only value, apply to all modules
            value_str = rest
            module_names = []
            try:
                value = ast.literal_eval(value_str)
            except (ValueError, SyntaxError):
                value = value_str

        updated = 0
        errors = []

        modules_to_update = []
        if module_names:
            for name in module_names:
                module = self.all_modules.get_module(name)
                if module and hasattr(module, "config") and option_name in module.config:
                    modules_to_update.append(module)
        else:
            # Apply to all modules with this option
            for module in self.all_modules.modules:
                if hasattr(module, "config") and option_name in module.config:
                    modules_to_update.append(module)

        if not modules_to_update:
            await utils.answer(message, f"❌ No modules found with option '{option_name}'")
            return

        for module in modules_to_update:
            try:
                # Validate if validator exists
                if hasattr(module.config, "_config_values") and option_name in module.config._config_values:
                    config_value = module.config._config_values[option_name]
                    if config_value.validator:
                        validated_value = config_value.validator.validate(value)
                    else:
                        validated_value = value
                else:
                    validated_value = value

                self.db.setdefault(module.name, {}).setdefault("__config__", {})[option_name] = validated_value
                module.config[option_name] = validated_value
                self.reconfmod(module, self.db)
                updated += 1
            except (ValueError, TypeError) as e:
                errors.append(f"{module.name}: {str(e)}")

        self.db.save()

        result_text = f"✅ Updated <code>{option_name}</code> in <b>{updated}</b> module(s)\n"
        result_text += f"Value: <code>{utils.escape_html(str(value))}</code>"
        
        if errors:
            result_text += f"\n\n❌ Errors:\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                result_text += f"\n... and {len(errors) - 5} more"

        await utils.answer(message, result_text)

    async def watcher(self, app, message: Message) -> None:
        with contextlib.suppress(Exception):
            if (
                not getattr(message, "via_bot", False)
                or message.via_bot.id != (await self.bot.bot.get_me()).id
                or "This message is gonna be deleted..."
                not in getattr(message, "text", "")
            ):
                return

            await message.delete()
