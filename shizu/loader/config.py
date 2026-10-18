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


import copy
import json
import os
import re
from urllib.parse import urlparse

from shizu.loader.models import Module


class ConfigValue:
    """Config value descriptor for ModuleConfig compatibility"""

    def __init__(
        self,
        key,
        default,
        doc=None,
        validator=None,
        *,
        label=None,
        is_premium=False,
        tags=(),
    ):
        self.key = key
        self.default = default
        self.doc = doc
        self.validator = validator
        self.label = label
        self.tags = {tags} if isinstance(tags, str) else set(tags)
        self.is_premium = bool(is_premium or "is_premium" in self.tags)

    def validate(self, value):
        """Validate value using validator if present"""
        if self.validator:
            return self.validator.validate(value)
        return value


class Validators:
    """Validators for ConfigValue"""

    class Integer:
        def __init__(self, minimum=None, maximum=None):
            self.minimum = minimum
            self.maximum = maximum

        def validate(self, value):
            try:
                value = int(value)
                if self.minimum is not None and value < self.minimum:
                    raise ValueError(f"Value must be >= {self.minimum}")
                if self.maximum is not None and value > self.maximum:
                    raise ValueError(f"Value must be <= {self.maximum}")
                return value
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid integer value: {e}") from e

    class ValidationError(ValueError):
        """Raised by validators when a config value is rejected"""

    class RegExp:
        def __init__(self, pattern, description=None, flags=0):
            self.pattern = re.compile(pattern, flags)
            self.description = description

        def validate(self, value):
            if not self.pattern.match(str(value)):
                raise ValueError(
                    self.description
                    or f"Value does not match pattern: {self.pattern.pattern}"
                )
            return value

    class Series:
        def __init__(
            self, *args, validator=None, min_len=None, max_len=None, fixed_len=None
        ):
            if validator is not None:
                self.validators = (validator,)
            else:
                self.validators = args
            self.min_len = min_len
            self.max_len = max_len
            self.fixed_len = fixed_len

        def _check_length(self, value: list) -> list:
            if self.fixed_len is not None and len(value) != self.fixed_len:
                raise ValueError(f"List must contain exactly {self.fixed_len} items")
            if self.min_len is not None and len(value) < self.min_len:
                raise ValueError(f"List must contain at least {self.min_len} items")
            if self.max_len is not None and len(value) > self.max_len:
                raise ValueError(f"List must contain at most {self.max_len} items")
            return value

        def validate(self, value):
            if not isinstance(value, (list, tuple)):
                if isinstance(value, str):
                    try:
                        value = json.loads(value)

                        if not isinstance(value, list):
                            value = [value]
                    except (json.JSONDecodeError, ValueError):
                        value = [v.strip() for v in value.split(",") if v.strip()]
                else:
                    value = [str(value)] if value is not None else []

            if isinstance(value, tuple):
                value = list(value)

            if not self.validators:
                return self._check_length([str(v) for v in value])

            validated_list = []
            for v in value:
                for validator in self.validators:
                    v = validator.validate(v)
                validated_list.append(v)

            return self._check_length(validated_list)

    class Boolean:
        def validate(self, value):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)

    class NoneType:
        def validate(self, value):
            if value is None:
                return None
            raise ValueError("Value must be None")

    class String:
        def __init__(self, length=None, min_len=None, max_len=None):
            self.length = length
            self.min_len = min_len
            self.max_len = max_len

        def validate(self, value):
            value = str(value)
            if self.length is not None and len(value) != self.length:
                raise ValueError(f"Text must be exactly {self.length} characters long")
            if self.min_len is not None and len(value) < self.min_len:
                raise ValueError(
                    f"Text must be at least {self.min_len} characters long"
                )
            if self.max_len is not None and len(value) > self.max_len:
                raise ValueError(f"Text must be at most {self.max_len} characters long")
            return value

    class TelegramID:
        def validate(self, value):
            try:
                value = int(str(value).strip())
            except (TypeError, ValueError):
                raise ValueError("Value must be a Telegram ID (a number)") from None
            if not -(10**15) < value < 10**15 or value == 0:
                raise ValueError("Value is not a valid Telegram ID")
            return value

    class EntityLike:
        def validate(self, value):
            value = str(value).strip()
            if re.fullmatch(r"-?\d+", value):
                return int(value)
            if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,31}", value) or value.startswith(
                ("https://t.me/", "t.me/")
            ):
                return value
            raise ValueError("Value must be an ID, @username or t.me link")

    class Emoji:
        def __init__(self, length=None, min_len=None, max_len=None):
            self.length, self.min_len, self.max_len = length, min_len, max_len

        def validate(self, value):
            value = str(value)
            if any(ch.isalnum() for ch in value):
                raise ValueError("Value must contain only emoji")
            count = len(
                [
                    ch
                    for ch in value
                    if not ch.isspace() and ord(ch) not in (0x200D, 0xFE0F)
                ]
            )
            if self.length is not None and count != self.length:
                raise ValueError(f"Value must contain exactly {self.length} emoji")
            if self.min_len is not None and count < self.min_len:
                raise ValueError(f"Value must contain at least {self.min_len} emoji")
            if self.max_len is not None and count > self.max_len:
                raise ValueError(f"Value must contain at most {self.max_len} emoji")
            return value

    class Link:
        def validate(self, value):
            value = str(value).strip()
            if not value:
                raise ValueError("Link cannot be empty")

            original_value = value
            if not value.startswith(("http://", "https://")):
                value = "https://" + value

            parsed = urlparse(value)

            if parsed.scheme not in ("http", "https"):
                raise ValueError(
                    f"Invalid link scheme. Only http:// and https:// are allowed: {original_value}"
                )

            if not parsed.netloc:
                raise ValueError(
                    f"Invalid link format. Missing domain: {original_value}"
                )

            netloc = parsed.netloc.split(":")[0]
            is_valid_domain = (
                "." in netloc
                or netloc.lower() == "localhost"
                or re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", netloc)
            )

            if not is_valid_domain:
                raise ValueError(
                    f"Invalid link format. Invalid domain: {original_value}"
                )

            return value

    class Button:
        """One inline button as `Label - https://link`, or a {text, url[, style]} dict."""

        STYLES = {"primary", "success", "danger"}

        def validate(self, value):
            if isinstance(value, str):
                text, separator, url = value.partition(" - ")
                if not separator:
                    text, separator, url = value.partition("|")
                text, url = text.strip(), url.strip()
                if not separator or not text or not url:
                    raise ValueError(f"Use 'Label - https://link': {value!r}")
                value = {"text": text, "url": url}
            if not isinstance(value, dict):
                raise ValueError("A button is 'Label - link' or a {text, url} object")
            text = str(value.get("text", "")).strip()
            if not text:
                raise ValueError("Button text cannot be empty")
            button = {"text": text, "url": Validators.Link().validate(value.get("url", ""))}
            style = value.get("style")
            if style:
                if style not in self.STYLES:
                    raise ValueError(f"Unknown button style: {style}")
                button["style"] = style
            emoji = value.get("emoji")
            if emoji:
                if isinstance(emoji, str):
                    emoji_id, _, fallback = emoji.strip().partition(" ")
                    emoji = {"id": emoji_id, "fallback": fallback.strip() or "⭐"}
                if not isinstance(emoji, dict):
                    raise ValueError("Emoji must be an id or {id, fallback}")
                emoji_id = str(emoji.get("id", "")).strip()
                if not emoji_id.isdigit():
                    raise ValueError("Custom emoji id must be a number")
                button["emoji"] = {
                    "id": emoji_id,
                    "fallback": str(emoji.get("fallback") or "⭐").strip() or "⭐",
                }
            return button

    class Float:
        def __init__(self, minimum=None, maximum=None):
            self.minimum = minimum
            self.maximum = maximum

        def validate(self, value):
            try:
                value = float(value)
                if self.minimum is not None and value < self.minimum:
                    raise ValueError(f"Value must be >= {self.minimum}")
                if self.maximum is not None and value > self.maximum:
                    raise ValueError(f"Value must be <= {self.maximum}")
                return value
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid float value: {e}") from e

    class Hidden:
        def __init__(self, validator=None):
            self.validator = validator

        def validate(self, value):
            return self.validator.validate(value) if self.validator else value

    class IsPremium:
        def __init__(self, validator=None):
            self.validator = validator

        def validate(self, value):
            return self.validator.validate(value) if self.validator else value

    class Choice:
        def __init__(self, possible_values):
            self.possible_values = list(possible_values)

        def validate(self, value):
            for possible in self.possible_values:
                if value == possible or str(value) == str(possible):
                    return possible
            raise ValueError(
                f"Value must be one of: {', '.join(map(str, self.possible_values))}"
            )

    class MultiChoice:
        def __init__(self, possible_values):
            self.possible_values = list(possible_values)

        def validate(self, value):
            if isinstance(value, str):
                value = [v.strip() for v in value.split(",") if v.strip()]
            result = []
            for item in value or []:
                match = next(
                    (
                        p
                        for p in self.possible_values
                        if item == p or str(item) == str(p)
                    ),
                    None,
                )
                if match is None:
                    raise ValueError(
                        f"{item} is not one of: {', '.join(map(str, self.possible_values))}"
                    )
                if match not in result:
                    result.append(match)
            return result

    class Union:
        def __init__(self, *validators, validator=None):
            if validator is not None:
                self.validators = (validator,)
            else:
                self.validators = validators

        def validate(self, value):
            if not self.validators:
                return value

            errors = []
            for validator in self.validators:
                try:
                    return validator.validate(value)
                except ValueError as e:
                    errors.append(str(e))
                    continue

            raise ValueError(
                f"Value does not match any of the validators: {', '.join(errors)}"
            )


validators = Validators()


def has_validator(validator, kind):
    return isinstance(validator, kind) or (
        validator is not None
        and (
            has_validator(getattr(validator, "validator", None), kind)
            or any(
                has_validator(child, kind)
                for child in getattr(validator, "validators", ())
            )
        )
    )


def unwrap_validator(validator):
    while isinstance(validator, (Validators.Hidden, Validators.IsPremium)):
        validator = validator.validator
    return validator


class ModuleConfig(dict):
    """Like a dict but contains doc for each key"""

    def __init__(self, *entries):
        keys = []
        values = []
        defaults = []
        docstrings = []
        self._config_values = {}

        if entries and isinstance(entries[0], ConfigValue):
            for entry in entries:
                if isinstance(entry, ConfigValue):
                    keys.append(entry.key)
                    defaults.append(entry.default)
                    values.append(entry.default)
                    docstrings.append(entry.doc)
                    self._config_values[entry.key] = entry
        else:
            for i, entry in enumerate(entries):
                if i % 3 == 0:
                    keys.append(entry)
                elif i % 3 == 1:
                    values.append(entry)
                    defaults.append(entry)
                else:
                    docstrings.append(entry)

        super().__init__(zip(keys, values) if keys else {})
        self._storage = None
        self._docstrings = dict(zip(keys, docstrings)) if keys else {}
        self._defaults = (
            {key: copy.deepcopy(value) for key, value in zip(keys, defaults)}
            if keys
            else {}
        )

    def getdoc(self, key, message=None):
        """Get the documentation by key"""
        ret = self._docstrings.get(key)
        if ret is None:
            return "No description"
        if callable(ret):
            try:
                ret = ret(message)
            except TypeError:
                ret = ret()

        return ret or "No description"

    def getdef(self, key):
        """Get the default value by key"""
        return copy.deepcopy(self._defaults.get(key))

    def getlabel(self, key, message=None):
        label = getattr(self._config_values.get(key), "label", None)
        if callable(label):
            try:
                label = label(message)
            except TypeError:
                label = label()
        return str(label) if label else str(key)

    def is_available(self, key, is_premium=False):
        descriptor = self._config_values.get(key)
        return key in self and (
            is_premium
            or descriptor is None
            or not (
                descriptor.is_premium
                or has_validator(descriptor.validator, Validators.IsPremium)
            )
        )

    def visible_keys(self, is_premium=False):
        return [key for key in self if self.is_available(key, is_premium)]

    def bind(self, db, section: str) -> None:
        """Save values assigned from now on to `section` in `db`"""
        self._storage = (db, section)

    def __setitem__(self, key, value):
        config_value = self._config_values.get(key)
        if value is not None and config_value is not None and config_value.validator:
            value = config_value.validator.validate(value)
        super().__setitem__(key, value)
        if self._storage:
            db, section = self._storage
            stored = db.get(section, "__config__", {})
            stored[key] = value
            db.set(section, "__config__", stored)


class ModuleConfiguration:
    """Restore and validate module configuration without changing its storage keys."""

    @staticmethod
    def configure(module: Module, db):
        """Reconfigures the module"""
        if hasattr(module, "config"):
            modcfg = db.get(module.name, "__config__", {})
            for conf in module.config.keys():
                if conf in modcfg.keys():
                    value = modcfg[conf]
                    if (
                        hasattr(module.config, "_config_values")
                        and conf in module.config._config_values
                    ):
                        config_value = module.config._config_values[conf]
                        if config_value.validator:
                            try:
                                value = config_value.validator.validate(value)
                                modcfg[conf] = value
                                db.set(module.name, "__config__", modcfg)
                            except (ValueError, TypeError):
                                value = module.config.getdef(conf)
                    dict.__setitem__(module.config, conf, value)
                else:
                    try:
                        value = os.environ[f"{module.name}.{conf}"]
                        if (
                            hasattr(module.config, "_config_values")
                            and conf in module.config._config_values
                        ):
                            config_value = module.config._config_values[conf]
                            if config_value.validator:
                                try:
                                    value = config_value.validator.validate(value)

                                    modcfg[conf] = value
                                    db.set(module.name, "__config__", modcfg)
                                except (ValueError, TypeError):
                                    value = module.config.getdef(conf)
                        dict.__setitem__(module.config, conf, value)
                    except KeyError:
                        dict.__setitem__(
                            module.config, conf, module.config.getdef(conf)
                        )
            if isinstance(module.config, ModuleConfig):
                module.config.bind(db, module.name)
