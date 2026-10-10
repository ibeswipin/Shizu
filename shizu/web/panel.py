"""An on-demand dashboard, separate from the initial Telegram login server."""

import asyncio
import html
import json
import logging
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import web

from shizu import utils
from shizu.backups import BackupError, EncryptedBackup
from shizu.translator import Translator
from shizu.web.core import TunnelManager
from shizu.web.panel_auth import PanelAuth
from shizu.web.panel_data import PanelData, PanelError

logger = logging.getLogger(__name__)


class DashboardServer(TunnelManager):
    CALLBACK_PREFIX = "shizu_web:"
    PUBLIC = {
        "/",
        "/panel.js",
        "/panel.css",
        "/sakura.svg",
        "/api/meta",
        "/api/auth/start",
        "/api/auth/status",
    }

    def __init__(self, module):
        super().__init__()
        self.module = module
        self.auth = PanelAuth(module.me.id)
        self.data = PanelData(module)
        self.translator = Translator(module.app, module.db)
        self.runner = None
        self.local_url = None
        self._restart_task = None
        self._mutation_lock = asyncio.Lock()
        self.resources = Path(utils.get_base_dir()).parent / "web-resources" / "panel"
        self.app = web.Application(
            middlewares=[self.middleware], client_max_size=EncryptedBackup.MAX_BYTES
        )
        self._routes()

    def _routes(self):
        routes = self.app.router
        routes.add_get("/", self.page)
        routes.add_get("/panel.js", self.javascript)
        routes.add_get("/panel.css", self.stylesheet)
        routes.add_get("/sakura.svg", self.sakura)
        routes.add_get("/fonts/{name}", self.font)
        routes.add_get("/api/meta", self.meta)
        routes.add_post("/api/auth/start", self.auth_start)
        routes.add_get("/api/auth/status", self.auth_status)
        routes.add_get("/api/session", self.session)
        routes.add_post("/api/logout", self.logout)
        routes.add_get("/api/state", self.state)
        routes.add_post("/api/settings", self.settings)
        routes.add_get("/api/modules/{name}/config", self.module_config)
        routes.add_post("/api/modules/{name}/config", self.module_save)
        routes.add_post("/api/modules/load", self.module_load)
        routes.add_post("/api/modules/{name}/unload", self.module_unload)
        routes.add_get("/api/logs", self.logs)
        routes.add_post("/api/backups/download", self.backup_download)
        routes.add_post("/api/backups/inspect", self.backup_inspect)
        routes.add_post("/api/backups/restore", self.backup_restore)

    def text(self, key):
        return self.translator.gettext("shizu.web.panel." + key)

    async def notify(self, key, *values, reply_markup=None):
        try:
            await asyncio.wait_for(
                self.module.bot.bot.send_message(
                    self.module.me.id,
                    self.module.strings(key).format(
                        *(html.escape(str(value)) for value in values)
                    ),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=reply_markup,
                ),
                timeout=8,
            )
        except Exception:
            logger.warning("Could not deliver dashboard notification to its owner")

    def error(self, key, status=400, detail=""):
        return web.json_response(
            {"error": key, "message": self.text(key), "detail": detail}, status=status
        )

    @property
    def origins(self):
        return {url.rstrip("/") for url in (self.url, self.local_url) if url}

    @web.middleware
    async def middleware(self, request, handler):
        try:
            if request.host not in {urlsplit(url).netloc for url in self.origins}:
                raise PanelError("forbidden", 403)
            if (
                request.method not in ("GET", "HEAD")
                and request.headers.get("Origin") not in self.origins
            ):
                raise PanelError("forbidden", 403)
            if request.path not in self.PUBLIC and not request.path.startswith(
                "/fonts/"
            ):
                session = self.auth.session(
                    request.cookies.get(PanelAuth.SESSION_COOKIE)
                )
                if session is None:
                    raise PanelError("unauthorized", 401)
                request["session"] = session
                if request.method not in ("GET", "HEAD"):
                    csrf = request.headers.get("X-CSRF-Token", "")
                    if not secrets.compare_digest(csrf, session["csrf"]):
                        raise PanelError("forbidden", 403)
                    async with self._mutation_lock:
                        if (
                            self.auth.session(
                                request.cookies.get(PanelAuth.SESSION_COOKIE)
                            )
                            is not session
                        ):
                            raise PanelError("unauthorized", 401)
                        if self._restart_task:
                            raise PanelError("restore_done", 409)
                        response = await handler(request)
                else:
                    response = await handler(request)
            else:
                response = await handler(request)
        except PanelError as error:
            response = self.error(error.key, error.status, error.detail)
        except BackupError as error:
            message = self.translator.gettext(
                "shizu.modules.ShizuBackuper." + error.code
            )
            response = web.json_response(
                {"error": error.code, "message": message}, status=400
            )
        except web.HTTPException as error:
            response = self.error(
                "too_large" if error.status == 413 else "request_failed", error.status
            )
        except (ValueError, TypeError, KeyError):
            response = self.error("invalid_value")
        except OSError:
            response = self.error("write_failed", 500)
        except Exception:
            logger.exception("Dashboard operation failed")
            response = self.error("request_failed", 500)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        return response

    async def start(self, *, tunnel=True, port=None):
        if self.runner:
            return self.url
        self.runner = web.AppRunner(self.app, access_log=None)
        try:
            await self.runner.setup()
            selected_port = (
                int(os.environ.get("SHIZU_PANEL_PORT", "0")) if port is None else port
            )
            site = web.TCPSite(self.runner, "127.0.0.1", selected_port)
            await site.start()
            bound_port = self.runner.addresses[0][1]
            self.local_url = self.url = f"http://127.0.0.1:{bound_port}"
            if tunnel:
                try:
                    await self.open_tunnel(bound_port, provider="cloudflare")
                except OSError as error:
                    await self.close_tunnel()
                    logger.warning(
                        "Cloudflare Quick Tunnel could not start; dashboard is local only: %s",
                        error,
                    )
            await self.notify("web_opened", self.url)
            return self.url
        except BaseException:
            await self.stop()
            raise

    async def stop(self):
        was_running = self.runner is not None and self.local_url is not None
        self.auth.clear()
        await self.close_tunnel()
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        if was_running:
            await self.notify("web_closed")

    def invitation(self):
        return f"{self.url}/#invite={self.auth.invite()}"

    def _cookie(self, response, request, name, token, max_age):
        secure = request.headers.get("Origin", self.url).startswith("https://")
        response.set_cookie(
            name,
            token,
            max_age=max_age,
            httponly=True,
            secure=secure,
            samesite="Strict",
            path="/",
        )

    async def _json(self, request):
        if request.content_type != "application/json":
            raise PanelError("invalid_value")
        body = bytearray()
        async for chunk in request.content.iter_chunked(8192):
            body.extend(chunk)
            if len(body) > 65536:
                raise PanelError("too_large", 413)
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError
            json.dumps(data, allow_nan=False)
            return data
        except (ValueError, UnicodeError, RecursionError):
            raise PanelError("invalid_value") from None

    async def page(self, request):
        return web.Response(
            text=self.resources.joinpath("index.html").read_text(),
            content_type="text/html",
        )

    async def javascript(self, request):
        return web.Response(
            text=self.resources.joinpath("panel.js").read_text(),
            content_type="application/javascript",
        )

    async def stylesheet(self, request):
        return web.Response(
            text=self.resources.joinpath("panel.css").read_text(),
            content_type="text/css",
        )

    async def font(self, request):
        name = request.match_info["name"]
        if name not in {"Movement.ttf", "Hubballi-Regular.ttf", "Roboto.ttf"}:
            raise web.HTTPNotFound()
        return web.Response(
            body=self.resources.joinpath("fonts", name).read_bytes(),
            content_type="font/ttf",
        )

    async def sakura(self, request):
        return web.Response(
            body=self.resources.joinpath("sakura.svg").read_bytes(),
            content_type="image/svg+xml",
        )

    async def meta(self, request):
        prefix = "shizu.web.panel."
        keys = self.translator._load_langpack("en")
        return web.json_response(
            {
                "language": self.translator._get_lang(),
                "strings": {
                    key[len(prefix) :]: self.translator.gettext(key)
                    for key in keys
                    if key.startswith(prefix)
                },
            }
        )

    async def auth_start(self, request):
        data = await self._json(request)
        pending = self.auth.begin(data.get("invite"))
        if pending is None:
            raise PanelError("invite_expired", 403)
        token, item = pending
        markup = InlineKeyboardMarkup().row(
            InlineKeyboardButton(
                self.module.strings("web_allow"),
                callback_data=f"{self.CALLBACK_PREFIX}{item['id']}:allow",
            ),
            InlineKeyboardButton(
                self.module.strings("web_deny"),
                callback_data=f"{self.CALLBACK_PREFIX}{item['id']}:deny",
            ),
        )
        try:
            await self.module.bot.bot.send_message(
                self.module.me.id,
                self.module.strings("web_approve").format(item["code"]),
                reply_markup=markup,
                parse_mode="HTML",
            )
        except Exception:
            self.auth.pending.pop(token, None)
            logger.exception("Could not send dashboard login approval")
            raise PanelError("telegram_failed", 503) from None
        response = web.json_response({"status": "pending", "code": item["code"]})
        self._cookie(
            response, request, PanelAuth.PENDING_COOKIE, token, PanelAuth.INVITE_TTL
        )
        return response

    async def auth_status(self, request):
        token = request.cookies.get(PanelAuth.PENDING_COOKIE)
        item = self.auth.status(token)
        if not item:
            return web.json_response({"status": "expired"})
        if item["status"] != "approved":
            return web.json_response({"status": item["status"], "code": item["code"]})
        session_token, session = self.auth.complete(token)
        response = web.json_response({"status": "approved", "csrf": session["csrf"]})
        secure = request.host == urlsplit(self.url).netloc and self.url.startswith(
            "https://"
        )
        response.set_cookie(
            PanelAuth.SESSION_COOKIE,
            session_token,
            max_age=PanelAuth.SESSION_TTL,
            httponly=True,
            secure=secure,
            samesite="Strict",
            path="/",
        )
        response.del_cookie(PanelAuth.PENDING_COOKIE, path="/")
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                self.module.strings("web_revoke"),
                callback_data=f"{self.CALLBACK_PREFIX}{session['id']}:revoke",
            )
        )
        await self.notify("web_login_notice", item["code"], reply_markup=markup)
        return response

    async def revoke_session(self, session_id, owner_id):
        async with self._mutation_lock:
            return self.auth.revoke(session_id, owner_id)

    async def session(self, request):
        return web.json_response({"csrf": request["session"]["csrf"]})

    async def logout(self, request):
        self.auth.sessions.pop(request.cookies.get(PanelAuth.SESSION_COOKIE), None)
        response = web.json_response({"ok": True})
        response.del_cookie(PanelAuth.SESSION_COOKIE, path="/")
        await self.notify("web_logout_notice")
        return response

    async def state(self, request):
        return web.json_response(self.data.state())

    async def settings(self, request):
        self.data.save_settings(await self._json(request))
        await self.notify("web_settings_notice")
        return web.json_response({"ok": True})

    async def module_config(self, request):
        return web.json_response(self.data.configuration(request.match_info["name"]))

    async def module_save(self, request):
        data = await self._json(request)
        if "value" not in data:
            raise PanelError("invalid_value")
        self.data.save_config(
            request.match_info["name"], data.get("key"), data["value"]
        )
        await self.notify("web_config_notice", request.match_info["name"], data["key"])
        return web.json_response({"ok": True})

    async def module_load(self, request):
        data = await self._json(request)
        result = await self.data.install(data.get("url"))
        await self.notify("web_module_notice", self.text(result))
        return web.json_response({"message": self.text(result)})

    async def module_unload(self, request):
        self.data.unload(request.match_info["name"])
        await self.notify("web_unload_notice", request.match_info["name"])
        return web.json_response({"ok": True})

    async def logs(self, request):
        return web.json_response(
            {"lines": self.data.logs(request.query.get("level", "INFO"))}
        )

    async def backup_download(self, request):
        name, archive = self.data.archive()
        await self.notify("web_backup_notice")
        return web.Response(
            body=archive,
            content_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    async def backup_inspect(self, request):
        archive = await request.read()
        decoded = self.data.backups.decrypt(
            archive, self.module.me.id, allow_legacy=request.query.get("legacy") == "1"
        )
        preview_id = secrets.token_urlsafe(24)
        request["session"]["restore"] = {
            "id": preview_id,
            "expires": time.monotonic() + 120,
            "data": decoded,
        }
        return web.json_response(
            {
                "preview_id": preview_id,
                "sections": len(decoded),
                "modules": len(decoded.get("shizu.loader", {}).get("modules", [])),
            }
        )

    async def backup_restore(self, request):
        data = await self._json(request)
        preview = request["session"].get("restore")
        if (
            not preview
            or preview["expires"] <= time.monotonic()
            or data.get("preview_id") != preview["id"]
        ):
            raise PanelError("preview_expired", 409)
        self.module.db.replace(preview["data"])
        request["session"].pop("restore", None)
        await self.notify("web_restore_notice")
        self._restart_task = asyncio.create_task(self._restart())
        return web.json_response({"ok": True, "message": self.text("restore_done")})

    async def _restart(self):
        await asyncio.sleep(2)
        await self.data.restart()
