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
import logging
import os
import re
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
from shizu.security import PrivateFiles, SecretRedactor
from shizu.telegram.device import TelegramDeviceProfile
from shizu.web.telethon_setup import TelethonSetupController

BASE_DIR = os.path.dirname(utils.get_base_dir())
logger = logging.getLogger(__name__)


class Web:
    def __init__(self, **kwargs):
        self.api_token = kwargs.pop("api_token")
        self.redirect_url = None
        super().__init__(**kwargs)
        self.app.router.add_get("/", self.root)
        self.app.router.add_get("/initialSetup", self.initial_setup)
        self.app.router.add_put("/setApi", self.set_tg_api)
        self.app.router.add_post("/sendTgCode", self.send_tg_code)
        self.app.router.add_post("/resendTgCode", self.resend_tg_code)
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
        self.sent_code = None
        self.code_resend_at = 0
        self._login_lock = asyncio.Lock()
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
        SecretRedactor.remember(api_hash)
        PrivateFiles.write_config("./config.ini", cfg)

        self.api_token = collections.namedtuple("api_token", ("ID", "HASH"))(
            api_id, api_hash
        )

        self.api_set.set()
        return web.Response()

    @staticmethod
    def normalize_phone(phone):
        """Keep the supplied country code; accept +CC, 00CC and bare CC."""
        if not isinstance(phone, str) or len(phone) > 64:
            raise ValueError("Invalid phone number")
        phone = re.sub(r"[\s().\-\u2010-\u2015]", "", phone)
        if phone.startswith("00"):
            phone = phone[2:]
        phone = "+" + phone.removeprefix("+")
        if not re.fullmatch(r"\+[1-9][0-9]{6,14}", phone):
            raise ValueError("Invalid phone number")
        return phone

    @staticmethod
    def code_error(error):
        """Return a useful failure without exposing RPC arguments or credentials."""
        logger.warning("Telegram setup code request failed: %s", type(error).__name__)
        if isinstance(error, errors.PhoneNumberInvalid):
            message, status = (
                "Invalid phone number. Include the country code, for example +48 for Poland.",
                400,
            )
        elif isinstance(error, errors.PhoneNumberBanned):
            message, status = "Telegram has banned this phone number.", 403
        elif isinstance(error, errors.FloodWait):
            seconds = max(1, int(error.value))
            return web.json_response(
                {
                    "error": f"Telegram limits login attempts. Try again in {seconds} seconds.",
                    "retry_after": seconds,
                },
                status=429,
            )
        elif isinstance(error, (errors.PhoneNumberFlood, errors.PhonePasswordFlood)):
            message, status = (
                "Telegram limits login attempts for this number. Try again later; repeated requests can extend the limit.",
                429,
            )
        elif isinstance(error, errors.PhoneNumberUnoccupied):
            message, status = (
                "This number has no Telegram account. Register it in the official Telegram app first.",
                400,
            )
        elif isinstance(
            error, (errors.SendCodeUnavailable, errors.SmsCodeCreateFailed)
        ):
            message, status = (
                "Telegram could not deliver a login code. Use QR login or try again later.",
                503,
            )
        elif isinstance(error, errors.UpdateAppToLogin):
            message, status = (
                "Telegram requires a different login flow. Use QR login.",
                409,
            )
        elif isinstance(error, (OSError, asyncio.TimeoutError)):
            message, status = (
                "Could not connect to Telegram. Check the server connection and try again.",
                503,
            )
        else:
            message, status = (
                "Telegram rejected the code request. Try QR login or try again later.",
                503,
            )
        return web.json_response({"error": message}, status=status)

    def _save_sent_code(self, phone, client, sent):
        delivery = getattr(getattr(sent, "type", None), "name", "")
        hints = {
            "APP": "Open Telegram on a device already signed in to this account. The code arrives in the Telegram service chat, not by SMS.",
            "SMS": "Telegram sent the code by SMS to this phone number.",
            "CALL": "Telegram will call this number and read out the login code.",
            "MISSED_CALL": "Enter the last digits of the number from Telegram's missed call.",
            "FRAGMENT_SMS": "Retrieve your login code from Fragment for this number.",
            "SMS_WORD": "Enter the word from Telegram's SMS.",
            "SMS_PHRASE": "Enter the phrase from Telegram's SMS.",
            "FIREBASE_SMS": "Telegram requires verification in its official mobile app before sending this SMS. Use QR login, or wait for another delivery method if available.",
            "EMAIL_CODE": "Telegram selected email verification, which this setup does not support. Use QR login.",
            "SETUP_EMAIL_REQUIRED": "Telegram requires a login email to be configured in its official app. Use QR login.",
            "FLASH_CALL": "Telegram selected flash-call verification. Use QR login.",
        }
        supported = delivery in {
            "APP",
            "SMS",
            "CALL",
            "MISSED_CALL",
            "FRAGMENT_SMS",
            "SMS_WORD",
            "SMS_PHRASE",
        }
        code_hash = getattr(sent, "phone_code_hash", None)
        if not code_hash:
            return web.json_response(
                {"error": "Telegram returned an unsupported login flow. Use QR login."},
                status=409,
            )
        self.phone_code_hash = code_hash
        self.sign_in_clients[phone] = client
        timeout = max(0, int(getattr(sent, "timeout", None) or 0))
        self.code_resend_at = time.monotonic() + timeout
        self.sent_code = {
            "phone": phone,
            "delivery": delivery,
            "message": hints.get(
                delivery,
                "Telegram selected an unsupported verification method. Use QR login.",
            ),
            "supported": supported,
            "numeric": delivery not in {"SMS_WORD", "SMS_PHRASE"},
            "can_resend": bool(getattr(sent, "next_type", None)),
            "timeout": timeout,
        }
        SecretRedactor.remember(code_hash)
        return web.json_response(self.sent_code)

    async def send_tg_code(self, request):
        try:
            phone = self.normalize_phone(await request.text())
        except ValueError:
            return web.json_response(
                {
                    "error": "Enter an international phone number with country code, for example +48 123 456 789."
                },
                status=400,
            )
        async with self._login_lock:
            if self.api_token is None or self.authenticated:
                return web.Response(status=400)
            try:
                client = await self.new_client()
                sent = await client.send_code(phone)
            except (errors.RPCError, OSError, asyncio.TimeoutError) as error:
                return self.code_error(error)
            return self._save_sent_code(phone, client, sent)

    async def resend_tg_code(self, request):
        try:
            phone = self.normalize_phone(await request.text())
        except ValueError:
            return web.Response(status=400)
        async with self._login_lock:
            if (
                self.authenticated
                or not self.sent_code
                or phone != self.sent_code["phone"]
                or self.client is not self.sign_in_clients.get(phone)
            ):
                return web.json_response(
                    {
                        "error": "This login attempt expired. Enter your phone number again."
                    },
                    status=409,
                )
            if not self.sent_code["can_resend"]:
                return web.json_response(
                    {
                        "error": "Telegram did not offer another code delivery method. Use QR login."
                    },
                    status=409,
                )
            remaining = self.code_resend_at - time.monotonic()
            if remaining > 0:
                seconds = int(remaining) + 1
                return web.json_response(
                    {
                        "error": f"Wait {seconds} seconds before requesting another code.",
                        "retry_after": seconds,
                    },
                    status=429,
                )
            try:
                sent = await self.client.resend_code(phone, self.phone_code_hash)
            except (errors.RPCError, OSError, asyncio.TimeoutError) as error:
                return self.code_error(error)
            return self._save_sent_code(phone, self.client, sent)

    async def new_client(self):
        if self.client is not None and self.client.is_connected:
            await self.client.disconnect()
        self.sign_in_clients.clear()
        self.phone_code_hash = None
        self.sent_code = None
        self.code_resend_at = 0
        self.qr = None
        self.client = pyrogram.client.Client(
            name="../shizu",
            api_id=self.api_token.ID,
            api_hash=self.api_token.HASH,
            **TelegramDeviceProfile.from_config().client_options(),
        )
        SecretRedactor.remember(self.api_token.HASH)
        PrivateFiles.secure_sqlite(self.client.storage.database)
        await self.client.connect()
        SecretRedactor.remember(await self.client.storage.auth_key())
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
        async with self._login_lock:
            return await self._qr_login(request)

    async def _qr_login(self, request):
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
        async with self._login_lock:
            return await self._qr_password(request)

    async def _qr_password(self, request):
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
        async with self._login_lock:
            return await self._tg_code(request)

    async def _tg_code(self, request):
        text = await request.text()
        if len(text) < 6:
            return web.Response(status=400)
        split = text.split("\n", 2)
        if len(split) not in (2, 3):
            return web.Response(status=400)
        code = split[0].strip()
        try:
            phone = self.normalize_phone(split[1])
        except ValueError:
            return web.Response(status=400)
        password = split[2] if len(split) == 3 else ""
        if self.client is None or phone not in self.sign_in_clients:
            return web.Response(status=400)
        if (
            not code
            or len(code) > 128
            or (
                self.sent_code
                and (
                    not self.sent_code["supported"]
                    or (
                        self.sent_code["numeric"]
                        and not re.fullmatch(r"[0-9]{4,10}", code)
                    )
                )
            )
        ):
            return web.Response(status=400)
        if not password:
            try:
                user = await self.client.sign_in(
                    phone, phone_code=code, phone_code_hash=self.phone_code_hash
                )
                if not user or isinstance(user, pyrogram.types.TermsOfService):
                    return web.json_response(
                        {
                            "error": "This number has no Telegram account. Register it in the official Telegram app first."
                        },
                        status=400,
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
