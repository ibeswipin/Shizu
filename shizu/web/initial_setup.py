#    Friendly Telegram (telegram userbot)
#    Copyright (C) 2018-2022 The Authors

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

# ----------------------------------------------------------------------------------

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


import asyncio
import base64
import collections
import configparser as cp
import os
import secrets
import string
import time

import aiohttp_jinja2
import pyrogram
import qrcode
import qrcode.image.svg
from aiohttp import web
from pyrogram import errors, raw

from shizu import utils
from shizu.bot.token_manager import TokenManager
from shizu.telegram.device import TelegramDeviceProfile
from shizu.web.telethon_setup import TelethonSetupController

BASE_DIR = os.path.dirname(utils.get_base_dir())


class Web:
    def __init__(self, **kwargs):
        self.api_token = kwargs.pop("api_token")
        self.redirect_url = None
        super().__init__(**kwargs)
        self.app.router.add_get("/", self.root)
        self.app.router.add_get("/initialSetup", self.initial_setup)
        self.app.router.add_put("/setApi", self.set_tg_api)
        self.app.router.add_post("/sendTgCode", self.send_tg_code)
        self.app.router.add_post("/tgCode", self.tg_code)
        self.app.router.add_post("/finishLogin", self.finish_login)
        self.app.router.add_post("/qrLogin", self.qr_login)
        self.app.router.add_post("/qrPassword", self.qr_password)
        self.telethon = TelethonSetupController(self)
        self.app.router.add_post("/telethonPrepare", self.telethon.prepare)
        self.app.router.add_post("/telethonConnect", self.telethon.connect)
        self.app.router.add_post("/telethonSkip", self.telethon.skip)
        self.app.router.add_post("/telethonDisconnect", self.telethon.disconnect)
        self.app.on_cleanup.append(self.telethon.close)
        self.telethon_choice = None
        self.setup_owner = None
        self.api_set = asyncio.Event()
        self.sign_in_clients = {}
        self.clients = []
        self.client = None
        self.authenticated = False
        self.phone_code_hash = None
        self.qr = None
        self.clients_set = asyncio.Event()
        self.root_redirected = asyncio.Event()

    async def root(self, request):
        if self.redirect_url:
            self.root_redirected.set()
            return web.Response(status=302, headers={"Location": self.redirect_url})

        return await self.initial_setup(request)

    @aiohttp_jinja2.template("initial_root.jinja2")
    async def initial_setup(self, request):
        if (
            self.authenticated
            and request.cookies.get("shizu_setup") != self.setup_owner
        ):
            raise web.HTTPForbidden()
        return {
            "api_done": self.api_token is not None,
            "tg_done": self.authenticated or bool(self.client_data),
            "telethon_done": self.telethon_choice is not None,
        }

    def wait_for_api_token_setup(self):
        return self.api_set.wait()

    def wait_for_clients_setup(self):
        return self.clients_set.wait()

    async def set_tg_api(self, request):
        if self.authenticated:
            return web.Response(status=409)
        text = await request.text()
        if len(text) < 36:
            return web.Response(status=400)
        api_id = text[32:]
        api_hash = text[:32]
        if any(c not in string.hexdigits for c in api_hash) or any(
            c not in string.digits for c in api_id
        ):
            return web.Response(status=400)

        cfg = cp.ConfigParser()
        cfg["pyrogram"] = {
            "api_id": api_id,
            "api_hash": api_hash,
            "device_model": await utils.run_sync(utils.get_random_smartphone),
        }
        with open("./config.ini", "w", encoding="utf-8") as file:
            cfg.write(file)

        self.api_token = collections.namedtuple("api_token", ("ID", "HASH"))(
            api_id, api_hash
        )

        self.api_set.set()
        return web.Response()

    async def send_tg_code(self, request):
        phone = await request.text()
        if not phone:
            return web.Response(status=400)
        if self.api_token is None or self.authenticated:
            return web.Response(status=400)
        client = await self.new_client()
        while True:
            phone_hash = (await self.client.send_code(phone)).phone_code_hash
            self.phone_code_hash = phone_hash
            self.sign_in_clients[phone] = client
            return web.Response()

    async def new_client(self):
        if self.client is not None:
            await self.client.disconnect()
        self.sign_in_clients.clear()
        self.qr = None
        self.client = pyrogram.client.Client(
            name="../shizu",
            api_id=self.api_token.ID,
            api_hash=self.api_token.HASH,
            **TelegramDeviceProfile.from_config().client_options(),
        )
        await self.client.connect()
        return self.client

    async def migrate_dc(self, dc_id):
        client = self.client
        dc_option = await client.get_dc_option(dc_id, ipv6=client.ipv6)
        await client.session.stop()
        client.session = await client.get_session(
            dc_id=dc_id,
            server_address=dc_option.ip_address,
            port=dc_option.port,
            export_authorization=False,
            temporary=True,
        )
        await client.storage.dc_id(dc_id)
        await client.storage.server_address(dc_option.ip_address)
        await client.storage.port(dc_option.port)
        await client.storage.auth_key(client.session.auth_key)

    def _authorize_browser(self, response, request=None):
        """Bind subsequent setup writes to the browser that completed login."""
        self.setup_owner = secrets.token_urlsafe(32)
        response.set_cookie(
            "shizu_setup",
            self.setup_owner,
            httponly=True,
            samesite="Strict",
            secure=bool(
                getattr(request, "secure", False)
                or str(getattr(self, "url", "")).startswith("https://")
            ),
        )
        return response

    async def qr_authorized(self, user_id, request=None):
        await self.client.storage.user_id(user_id)
        await self.client.storage.is_bot(False)
        self.qr = None
        self.authenticated = True
        return self._authorize_browser(web.json_response({"done": True}), request)

    async def qr_login(self, request):
        if self.api_token is None or self.authenticated:
            return web.Response(status=400)
        if self.qr is None:
            await self.new_client()
            self.qr = {"expires": 0}
        try:
            r = await self.client.invoke(
                raw.functions.auth.ExportLoginToken(
                    api_id=int(self.api_token.ID),
                    api_hash=self.api_token.HASH,
                    except_ids=[],
                )
            )
            if isinstance(r, raw.types.auth.LoginTokenMigrateTo):
                await self.migrate_dc(r.dc_id)
                r = await self.client.invoke(
                    raw.functions.auth.ImportLoginToken(token=r.token)
                )
        except errors.exceptions.SessionPasswordNeeded:
            self.qr["password"] = True
            return web.Response(status=401)
        except errors.exceptions.FloodWait:
            return web.Response(status=421)
        if isinstance(r, raw.types.auth.LoginTokenSuccess):
            return await self.qr_authorized(r.authorization.user.id, request)
        if self.qr["expires"] - time.time() < 5:
            url = "tg://login?token=" + base64.urlsafe_b64encode(
                r.token
            ).decode().rstrip("=")
            svg = qrcode.make(
                url, image_factory=qrcode.image.svg.SvgPathImage, border=1
            )
            self.qr = {"expires": r.expires, "svg": svg.to_string(encoding="unicode")}
        return web.json_response({"svg": self.qr["svg"]})

    async def qr_password(self, request):
        if self.authenticated or not (self.qr or {}).get("password"):
            return web.Response(status=400)
        password = await request.text()
        if not password:
            return web.Response(status=400)
        try:
            user = await self.client.check_password(password)
        except errors.exceptions.PasswordHashInvalid:
            return web.Response(status=403)
        except errors.exceptions.FloodWait:
            return web.Response(status=421)
        return await self.qr_authorized(user.id, request)

    async def tg_code(self, request):
        text = await request.text()
        if len(text) < 6:
            return web.Response(status=400)
        split = text.split("\n", 2)
        if len(split) not in (2, 3):
            return web.Response(status=400)
        code = split[0]
        phone = split[1]
        password = split[2] if len(split) == 3 else ""
        if self.client is None or phone not in self.sign_in_clients:
            return web.Response(status=400)
        if (
            (len(code) != 5 and not password)
            or any(c not in string.digits for c in code)
            or not phone
        ):
            return web.Response(status=400)
        if not password:
            try:
                await self.client.sign_in(
                    phone, phone_code=code, phone_code_hash=self.phone_code_hash
                )
            except errors.exceptions.SessionPasswordNeeded:
                return web.Response(status=401)  # Requires 2FA login
            except errors.exceptions.PhoneCodeExpired:
                return web.Response(status=404)
            except errors.exceptions.PhoneCodeInvalid:
                return web.Response(status=403)
            except errors.exceptions.FloodWait:
                return web.Response(status=421)
        else:
            try:
                await self.client.check_password(password)
            except errors.exceptions.PasswordHashInvalid:
                return web.Response(status=403)  # Invalid 2FA password
            except errors.exceptions.FloodWait:
                return web.Response(status=421)
        del self.sign_in_clients[phone]
        self.authenticated = True
        return self._authorize_browser(web.Response(), request)

    async def finish_login(self, request):
        if self.clients_set.is_set():
            return web.Response(status=409)
        if not self.authenticated:
            return web.Response(status=401)
        if (
            getattr(self, "setup_owner", None)
            and request.cookies.get("shizu_setup") != self.setup_owner
        ):
            return web.Response(status=401)
        if getattr(self, "telethon_choice", False) is None:
            return web.json_response(
                {"error": "Choose whether to connect Telethon first."}, status=409
            )
        token = (await request.text()).strip()
        if token:
            try:
                username = await TokenManager.check_token(token)
            except ValueError as e:
                return web.json_response({"error": str(e)}, status=400)
            TokenManager.save_token(token, username)
        self.clients_set.set()
        return web.Response()
