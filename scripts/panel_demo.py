"""Preview the dashboard on loopback with sample data and no Telegram connection."""

import argparse
import asyncio
import json
import time
from pathlib import Path

from aiohttp import web


class PanelDemo:
    def __init__(self, language="ru"):
        self.root = Path(__file__).resolve().parent.parent
        self.assets = self.root / "web-resources" / "panel"
        self.language = language
        self.prefixes = ["."]
        self.protection = True
        self.started = time.monotonic()
        self.modules = [
            {
                "name": "ShizuBackuper",
                "author": "hikamoru",
                "core": True,
                "config_count": 2,
                "commands": 4,
                "description": "Зашифрованные бэкапы базы данных и настроек модулей.",
            },
            {
                "name": "ShizuPanel",
                "author": "hikamoru",
                "core": True,
                "config_count": 0,
                "commands": 2,
                "description": "Управление юзерботом через Telegram и веб-панель.",
            },
            {
                "name": "ShizuLoader",
                "author": "hikamoru",
                "core": True,
                "config_count": 1,
                "commands": 8,
                "description": "Загрузка модулей с проверкой исходников и подтверждением BeSafe.",
            },
            {
                "name": "ShizuSettings",
                "author": "hikamoru",
                "core": True,
                "config_count": 0,
                "commands": 5,
                "description": "Настройки клиента и защита от слишком частых запросов.",
            },
            {
                "name": "ShizuOnload",
                "author": "hikamoru",
                "core": True,
                "config_count": 2,
                "commands": 0,
                "description": "Приветствие и сообщения при запуске Shizu.",
            },
            {
                "name": "Weather",
                "author": "demo",
                "core": False,
                "config_count": 2,
                "commands": 1,
                "description": "Прогноз погоды и температура в вашем городе.",
            },
            {
                "name": "Notes",
                "author": "demo",
                "core": False,
                "config_count": 0,
                "commands": 3,
                "description": "Быстрые заметки прямо в Telegram.",
            },
        ]
        self.configs = {
            "ShizuBackuper": [
                self.field("auto_backup", True, "Ежедневный бэкап в служебный чат."),
                self.field(
                    "backup_time",
                    "03:00",
                    "Время бэкапа по часовому поясу сервера, ЧЧ:ММ.",
                ),
            ],
            "ShizuLoader": [
                self.field(
                    "token",
                    None,
                    "Токен доступа к приватному репозиторию.",
                    hidden=True,
                )
            ],
            "ShizuOnload": [
                self.field(
                    "enable_start_text", True, "Отправлять сообщение при запуске."
                ),
                self.field(
                    "start_text", "Shizu готов к работе 🌿", "Текст приветствия."
                ),
            ],
            "Weather": [
                self.field("city", "Ташкент", "Город для прогноза погоды."),
                self.field("units", "°C", "Единицы температуры.", choices=["°C", "°F"]),
            ],
        }
        self.app = web.Application(middlewares=[self.headers], client_max_size=65536)
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/api/meta", self.meta)
        self.app.router.add_get("/api/session", self.session)
        self.app.router.add_get("/api/state", self.state)
        self.app.router.add_get("/api/server/metrics", self.metrics)
        self.app.router.add_get("/api/server/diagnostics", self.diagnostics)
        self.app.router.add_get("/api/permissions", self.permissions)
        self.app.router.add_get("/api/logs", self.logs)
        self.app.router.add_get("/api/modules/{name}/config", self.configuration)
        self.app.router.add_post("/api/settings", self.save_settings)
        self.app.router.add_post("/api/modules/{name}/config", self.save_config)
        self.app.router.add_post("/api/{path:.*}", self.unavailable)
        self.app.router.add_static("/", self.assets, show_index=False)

    @staticmethod
    def field(key, value, description, *, hidden=False, choices=None):
        return {
            "key": key,
            "value": value,
            "type": "boolean" if type(value) is bool else "string",
            "description": description,
            "hidden": hidden,
            "configured": hidden or value is not None,
            "editable": True,
            "choices": choices,
        }

    @web.middleware
    async def headers(self, request, handler):
        if (
            request.method == "POST"
            and request.headers.get("Origin") != f"http://{request.host}"
        ):
            return web.json_response({"message": "Demo origin rejected"}, status=403)
        response = await handler(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            }
        )
        return response

    def pack(self):
        return json.loads(
            (self.root / "shizu" / "langpacks" / f"{self.language}.json").read_text()
        )

    async def index(self, request):
        return web.FileResponse(self.assets / "index.html")

    async def meta(self, request):
        prefix = "shizu.web.panel."
        return web.json_response(
            {
                "demo": True,
                "language": self.language,
                "strings": {
                    key[len(prefix) :]: value
                    for key, value in self.pack().items()
                    if key.startswith(prefix)
                },
            }
        )

    async def session(self, request):
        return web.json_response({"csrf": "demo"})

    async def state(self, request):
        return web.json_response(
            {
                "account": {
                    "id": 100000,
                    "name": "Shizu Demo",
                    "username": "shizu_demo",
                    "has_avatar": False,
                },
                "settings": {
                    "prefixes": self.prefixes,
                    "language": self.language,
                    "api_protection": self.protection,
                    "bot": "shizu_demo_bot",
                },
                "modules": self.modules,
                "runtime": {
                    "version": "1.0.5",
                    "uptime": 9360 + int(time.monotonic() - self.started),
                },
                "backups": {
                    "key_path": "~/.config/shizu/backup.key",
                    "max_bytes": 64 * 1024 * 1024,
                    "available": True,
                    "auto_backup": self.configs["ShizuBackuper"][0]["value"],
                    "backup_time": self.configs["ShizuBackuper"][1]["value"],
                },
            }
        )

    async def metrics(self, request):
        gib = 1024**3
        return web.json_response(
            {
                "sampled_at": time.time(),
                "cpu_percent": 26.4,
                "cpu_count": 4,
                "load_average": [0.42, 0.37, 0.31],
                "memory": {
                    "total": 8 * gib,
                    "used": 3 * gib,
                    "available": 5 * gib,
                    "percent": 37.5,
                },
                "disk": {
                    "total": 80 * gib,
                    "used": 28 * gib,
                    "free": 52 * gib,
                    "percent": 35,
                },
                "swap": {"total": 2 * gib, "used": 0, "percent": 0},
                "process": {"memory": 128 * 1024**2, "threads": 6},
                "host_uptime": 345600,
                "shizu_uptime": 9360 + int(time.monotonic() - self.started),
                "history": [
                    17,
                    26,
                    32,
                    44,
                    31,
                    28,
                    38,
                    49,
                    57,
                    26,
                    21,
                    35,
                    42,
                    23,
                    27,
                    31,
                    54,
                    68,
                    84,
                    61,
                    42,
                    36,
                    29,
                    26.4,
                ],
            }
        )

    async def diagnostics(self, request):
        files = [
            {
                "kind": kind,
                "name": name,
                "status": "present",
                "bytes": size,
                "modified": time.time() - 1800,
                "mode": "0600",
                "private": True,
                "readable": True,
                "writable": True,
            }
            for kind, name, size in (
                ("database", "shizu.json", 32768),
                ("session_file", "shizu.session", 57344),
                ("backup_key", "backup.key", 44),
            )
        ]
        return web.json_response(
            {
                "python": "3.10.14",
                "system": "Linux",
                "architecture": "x86_64",
                "packages": {
                    "kurigram": "2.2.0",
                    "aiohttp": "3.13.0",
                    "psutil": "7.1.0",
                    "cryptography": "46.0.0",
                },
                "database_sections": 18,
                "files": files,
            }
        )

    async def permissions(self, request):
        def command(name, module="Weather", available=True, applies=True):
            return {
                "name": name,
                "module": module,
                "available": available,
                "grant_applies": applies,
            }

        weather = command("weather")
        notes = command("note", "Notes")
        return web.json_response(
            {
                "owner_mode": False,
                "users": [
                    {
                        "id": "100000",
                        "account_owner": True,
                        "additional_owner": False,
                        "owner_active": True,
                        "direct": [],
                        "groups": [],
                        "commands": [],
                    },
                    {
                        "id": "200001",
                        "account_owner": False,
                        "additional_owner": True,
                        "owner_active": False,
                        "direct": [weather],
                        "groups": [],
                        "commands": [weather],
                    },
                    {
                        "id": "300001",
                        "account_owner": False,
                        "additional_owner": False,
                        "owner_active": False,
                        "direct": [],
                        "groups": ["Helpers"],
                        "commands": [
                            weather,
                            notes,
                            command("oldcmd", "", False, False),
                        ],
                    },
                ],
                "groups": [
                    {
                        "name": "Helpers",
                        "commands": [
                            weather,
                            notes,
                            command("oldcmd", "", False, False),
                        ],
                        "users": ["300001"],
                    }
                ],
            }
        )

    async def configuration(self, request):
        name = request.match_info["name"]
        return web.json_response({"name": name, "fields": self.configs.get(name, [])})

    async def save_config(self, request):
        data = await request.json()
        for field in self.configs.get(request.match_info["name"], []):
            if field["key"] == data.get("key"):
                if not field["hidden"]:
                    field["value"] = data.get("value")
                return web.json_response({"ok": True})
        raise web.HTTPBadRequest()

    async def save_settings(self, request):
        data = await request.json()
        if data.get("language") not in ("en", "ru", "uz") or not isinstance(
            data.get("prefixes"), list
        ):
            raise web.HTTPBadRequest()
        self.language = data["language"]
        self.prefixes = data["prefixes"]
        self.protection = data.get("api_protection", True)
        return web.json_response({"ok": True})

    async def logs(self, request):
        records = [
            ("INFO", "[INFO] shizu.main: Shizu is ready"),
            ("INFO", "[INFO] shizu.loader: Core modules loaded"),
            ("INFO", "[INFO] shizu.backups: Encrypted backup created"),
            (
                "WARNING",
                "[WARNING] shizu.besafe: Weather is waiting for owner approval",
            ),
            ("INFO", "[INFO] shizu.redaction: bot_token=[REDACTED]"),
        ]
        levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        level = levels.get(request.query.get("level"), 20)
        return web.json_response(
            {"lines": [text for name, text in records if levels[name] >= level]}
        )

    async def unavailable(self, request):
        return web.json_response(
            {"message": self.pack()["shizu.web.panel.demo_readonly"]}, status=400
        )

    async def run(self, port):
        runner = web.AppRunner(self.app, access_log=None)
        await runner.setup()
        try:
            await web.TCPSite(runner, "127.0.0.1", port).start()
            print(f"Shizu demo: http://127.0.0.1:{port}", flush=True)
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    @classmethod
    def launch(cls):
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--port", type=int, default=8082)
        parser.add_argument("--language", choices=("en", "ru", "uz"), default="ru")
        args = parser.parse_args()
        try:
            asyncio.run(cls(args.language).run(args.port))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    PanelDemo.launch()
