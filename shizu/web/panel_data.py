"""Dashboard operations use the same module and backup APIs as Telegram commands."""

import copy
import json
import logging
import re
from collections.abc import Mapping
from datetime import datetime

from shizu import loader, security, utils, version
from shizu.backups import EncryptedBackup
from shizu.loader.config import has_validator, unwrap_validator
from shizu.redaction import SecretRedactor


class PanelError(ValueError):
    def __init__(self, key, status=400, detail=""):
        super().__init__(key)
        self.key, self.status, self.detail = key, status, detail


class PanelData:
    def __init__(self, module):
        self.module = module
        self.db = module.db
        self.manager = module.all_modules
        self.backups = EncryptedBackup()

    def state(self):
        me = self.module.me
        backuper = next(
            (m for m in self.manager.modules if m.name == "ShizuBackuper"), None
        )
        backup_config = getattr(backuper, "config", {})
        return {
            "account": {
                "id": me.id,
                "name": " ".join(filter(None, [me.first_name, me.last_name])),
                "username": me.username or "",
                "has_avatar": bool(getattr(me, "photo", None)),
            },
            "settings": {
                "prefixes": self.db.get("shizu.loader", "prefixes", ["."]),
                "language": self.db.get("shizu.me", "lang", "en"),
                "api_protection": self.db.get("shizu.api", "protection", True),
                "bot": self.db.get("shizu.bot", "username", ""),
            },
            "modules": [self.module_info(module) for module in self.manager.modules],
            "runtime": {
                "version": ".".join(map(str, version.__version__)),
                "uptime": utils.uptime(),
            },
            "backups": {
                "key_path": str(self.backups.key_path),
                "max_bytes": self.backups.MAX_BYTES,
                "available": backuper is not None,
                "auto_backup": bool(backup_config.get("auto_backup", False)),
                "backup_time": str(backup_config.get("backup_time", "03:00")),
            },
        }

    def module_info(self, module):
        config = getattr(module, "config", {})
        return {
            "name": str(module.name),
            "author": str(getattr(module, "author", "")),
            "core": self.manager.is_core(module),
            "config_count": len(self.config_keys(config)),
            "commands": len(getattr(module, "command_handlers", {})),
            "description": SecretRedactor.text(module.__doc__ or ""),
        }

    def permissions(self):
        """Configured grants, including dormant owners and unloaded commands."""
        owner_id = str(self.module.me.id)
        owner_mode = bool(self.db.get("shizu.owner", "status", False))
        owners = {str(uid) for uid in self.db.get("shizu.me", "owners", [])}
        direct = {
            str(uid): commands
            for uid, commands in self.db.get("shizu.permissions", "users", {}).items()
        }
        assignments = {
            str(uid): groups
            for uid, groups in self.db.get(
                "shizu.commandgroups", "user_groups", {}
            ).items()
        }
        groups = self.db.get("shizu.commandgroups", "groups", {})
        handlers = getattr(self.manager, "command_handlers", {})

        def names(values):
            if not isinstance(values, (list, tuple, set)):
                return []
            return sorted({name for name in values if isinstance(name, str)})

        def command_info(name, user_id=None):
            handler = handlers.get(name)
            mask = security.mask_of(handler) if handler else 0
            is_owner = user_id == owner_id or (owner_mode and user_id in owners)
            grant_applies = handler is not None and (
                user_id == owner_id
                or not mask
                or bool(mask & (security.SUDO | security.SUPPORT | security.EVERYONE))
                or (is_owner and bool(mask & security.OWNER))
            )
            return {
                "name": SecretRedactor.text(name),
                "module": str(getattr(getattr(handler, "__self__", None), "name", "")),
                "available": handler is not None,
                "grant_applies": grant_applies,
            }

        users = []
        for uid in sorted({owner_id, *owners, *direct, *assignments}, key=str):
            assigned_groups = names(assignments.get(uid, []))
            commands = set(names(direct.get(uid, [])))
            for group in assigned_groups:
                commands.update(names(groups.get(group, [])))
            users.append(
                {
                    "id": uid,
                    "account_owner": uid == owner_id,
                    "additional_owner": uid in owners and uid != owner_id,
                    "owner_active": uid == owner_id or (owner_mode and uid in owners),
                    "direct": [
                        command_info(name, uid) for name in names(direct.get(uid, []))
                    ],
                    "groups": [SecretRedactor.text(name) for name in assigned_groups],
                    "commands": [command_info(name, uid) for name in sorted(commands)],
                }
            )
        return {
            "owner_mode": owner_mode,
            "users": users,
            "groups": [
                {
                    "name": SecretRedactor.text(name),
                    "commands": [command_info(command) for command in names(commands)],
                    "users": sorted(
                        uid for uid, items in assignments.items() if name in items
                    ),
                }
                for name, commands in sorted(groups.items())
            ],
        }

    def save_settings(self, data):
        prefixes = data.get("prefixes")
        if (
            not isinstance(prefixes, list)
            or not 1 <= len(prefixes) <= 10
            or any(
                not isinstance(p, str)
                or not p
                or len(p) > 16
                or any(c.isspace() for c in p)
                for p in prefixes
            )
        ):
            raise PanelError("invalid_prefixes")
        if (
            data.get("language") not in ("en", "ru", "uz")
            or type(data.get("api_protection")) is not bool
        ):
            raise PanelError("invalid_value")
        updated = copy.deepcopy(dict(self.db))
        updated.setdefault("shizu.loader", {})["prefixes"] = list(
            dict.fromkeys(prefixes)
        )
        updated.setdefault("shizu.me", {})["lang"] = data["language"]
        updated.setdefault("shizu.api", {})["protection"] = data["api_protection"]
        self.db.replace(updated)

    def find_module(self, name):
        module = next((m for m in self.manager.modules if m.name == name), None)
        if module is None:
            raise PanelError("module_missing", 404)
        return module

    @classmethod
    def hidden_validator(cls, validator):
        return has_validator(validator, loader.validators.Hidden)

    def config_keys(self, config):
        if hasattr(config, "visible_keys"):
            return config.visible_keys(utils.owner_premium(self.manager))
        return list(config)

    @classmethod
    def hidden_value(cls, value):
        if isinstance(value, Mapping):
            return any(
                SecretRedactor._key.search(str(key)) or cls.hidden_value(child)
                for key, child in value.items()
            )
        if isinstance(value, (list, tuple)):
            return any(cls.hidden_value(child) for child in value)
        return isinstance(value, str) and SecretRedactor.text(value) != value

    def field(self, config, key):
        descriptor = getattr(config, "_config_values", {}).get(key)
        validator = getattr(descriptor, "validator", None)
        value = config[key]
        hidden = (
            bool(SecretRedactor._key.search(str(key)))
            or self.hidden_validator(validator)
            or self.hidden_value(value)
        )
        if hidden:
            SecretRedactor.remember(value)
            SecretRedactor.remember_mapping(value)
        kind = (
            "boolean"
            if type(value) is bool
            else "number"
            if type(value) in (int, float)
            else "string"
            if isinstance(value, str)
            else "json"
        )
        if hidden and value is None:
            kind = "string"
        try:
            json.dumps(value, allow_nan=False)
            editable = True
        except (TypeError, ValueError, RecursionError):
            editable = False
        validator = unwrap_validator(validator)
        choices = (
            getattr(validator, "possible_values", None)
            if isinstance(validator, loader.validators.Choice)
            else None
        )
        return {
            "key": key,
            "label": SecretRedactor.text(config.getlabel(key))
            if hasattr(config, "getlabel")
            else key,
            "type": kind,
            "hidden": hidden,
            "configured": value not in (None, ""),
            "editable": editable,
            "value": value if editable and not hidden else None,
            "choices": choices
            if not hidden and not self.hidden_value(choices)
            else None,
            "description": SecretRedactor.text(config.getdoc(key))
            if hasattr(config, "getdoc")
            else "",
        }

    def configuration(self, name):
        module = self.find_module(name)
        config = getattr(module, "config", {})
        return {
            "name": module.name,
            "fields": [self.field(config, key) for key in self.config_keys(config)],
        }

    def save_config(self, name, key, value):
        module = self.find_module(name)
        config = getattr(module, "config", {})
        if (
            not isinstance(key, str)
            or key not in self.config_keys(config)
            or not self.field(config, key)["editable"]
        ):
            raise PanelError("invalid_value")
        hidden = self.field(config, key)["hidden"]
        if hidden:
            SecretRedactor.remember(value)
            SecretRedactor.remember_mapping(value)
        if name == "ShizuBackuper":
            if key == "auto_backup" and type(value) is not bool:
                raise PanelError("invalid_value")
            if key == "backup_time" and (
                not isinstance(value, str)
                or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value)
            ):
                raise PanelError("invalid_time")
        old_value = copy.deepcopy(config[key])
        old_db = copy.deepcopy(dict(self.db))
        try:
            json.dumps(value, allow_nan=False)
            config[key] = value
            if not getattr(config, "_storage", None):
                stored = dict(self.db.get(name, "__config__", {}))
                stored[key] = config[key]
                self.db.set(name, "__config__", stored)
        except (ValueError, TypeError) as error:
            # Hidden validators can include the submitted credential in their errors.
            dict.__setitem__(config, key, old_value)
            self.db.clear()
            self.db.update(old_db)
            detail = "" if hidden else SecretRedactor.text(error)
            raise PanelError("invalid_value", detail=detail) from None
        except OSError:
            dict.__setitem__(config, key, old_value)
            self.db.clear()
            self.db.update(old_db)
            raise

    async def install(self, url):
        if (
            not isinstance(url, str)
            or len(url) > 2048
            or not url.startswith("https://")
        ):
            raise PanelError("https_only")
        item = await self.manager._remote_source(url, self.manager._remote_headers(url))
        result = await self.manager.load_module(item.source, item.url)
        if result == "PENDING":
            return "module_pending"
        if isinstance(result, str) and result not in (
            "DENIED",
            "NFA",
            "OTL",
            "PREMIUM_REQUIRED",
        ):
            module = self.manager.find_module_strict(result)
            if module:
                await self.manager.call_hook(module, "on_dlmod")
                return "module_loaded"
        raise PanelError(
            {
                "DENIED": "module_denied",
                "NFA": "module_account",
                "OTL": "module_telethon",
                "PREMIUM_REQUIRED": "module_premium",
            }.get(str(result), "module_failed"),
            detail=getattr(self.manager, "get_load_error", lambda *_: "")(
                item.source, item.url
            )
            if result is False
            else "",
        )

    def unload(self, name):
        module = self.find_module(name)
        if self.manager.is_core(module):
            raise PanelError("core_locked", 403)
        if not self.manager.unload_module(name):
            raise PanelError("module_failed")

    @staticmethod
    def logs(level):
        levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        if level not in levels:
            raise PanelError("invalid_value")
        for handler in logging.getLogger().handlers:
            if type(handler).__name__ == "MemoryHandler":
                handler.acquire()
                try:
                    records = list(handler.handled_buffer) + list(handler.buffer)
                finally:
                    handler.release()
                return [
                    SecretRedactor.text(handler.target.format(record))
                    for record in records
                    if record.levelno >= levels[level]
                ][-200:]
        return []

    def archive(self):
        name = f"shizu-{datetime.now().strftime('%d-%m-%Y-%H-%M')}.shizu-backup"
        return name, self.backups.encrypt(self.db, self.module.me.id)

    async def restart(self):
        await self.module.dashboard.stop()
        utils.restart()
