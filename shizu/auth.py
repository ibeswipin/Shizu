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


import argparse
import asyncio
import base64
import configparser as cp
import logging
import random
import sys
from datetime import datetime
from getpass import getpass
from typing import NoReturn

from pyrogram import Client, errors, raw, types
from pyrogram.raw.functions.auth.export_login_token import ExportLoginToken
from pyrogram.session.session import Session
from qrcode.main import QRCode

from shizu import database, utils
from shizu.health import Reporter, reporter
from shizu.private_files import PrivateFiles
from shizu.redaction import SecretRedactor
from shizu.telegram.device import TelegramDeviceProfile
from shizu.telegram.exceptions import (
    AccountMismatch,
    TelegramConnectionError,
    TelethonSessionInvalid,
)
from shizu.telegram.services import TelegramConnectionService

try:
    from .web import core
except ImportError:
    web_available = False
    logging.exception("Unable to import web")
else:
    web_available = True

Session.notice_displayed = True

loop = asyncio.get_event_loop()


def colored_input(prompt: str = "", hide: bool = False) -> str:
    frame = sys._getframe(1)
    return (getpass if hide else input)(
        "\x1b[32m{time:%Y-%m-%d %H:%M:%S}\x1b[0m | "
        "\x1b[1m{level: <8}\x1b[0m | "
        "\x1b[36m{name}\x1b[0m:\x1b[36m{function}\x1b[0m:\x1b[36m{line}\x1b[0m - \x1b[1m{prompt}\x1b[0m".format(
            time=datetime.now(),
            level="INPUT",
            name=frame.f_globals["__name__"],
            function=frame.f_code.co_name,
            line=frame.f_lineno,
            prompt=prompt,
        )
    )


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Shizu - A modular Telegram userbot",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        usage="python3 -m shizu -[option]",
    )

    parser.add_argument(
        "--no-web", action="store_false", help="Disable web interface", dest="web"
    )
    parser.add_argument("--port", type=int, help="Port for web interface", dest="port")
    parser.add_argument(
        "--setup-only", action="store_true", help="Authorize the account and exit"
    )

    return parser.parse_args()


args = argument_parser()


class Auth:
    def __init__(self, session_name: str = "../shizu") -> None:
        self._check_api_tokens()

        cfg = cp.ConfigParser()
        PrivateFiles.secure_existing("config.ini")
        cfg.read("./config.ini")

        device = TelegramDeviceProfile.from_config(cfg)
        api_id = cfg.get("pyrogram", "api_id", fallback="123")
        api_hash = cfg.get("pyrogram", "api_hash", fallback="hash")
        SecretRedactor.remember(api_hash)

        self.app = Client(
            name=session_name,
            api_id=api_id,
            api_hash=api_hash,
            **device.client_options(),
        )

        self.tapp = None
        self.connections = None

    async def _telethon_invalidated(self, user_id: int) -> None:
        """Handle a user rejecting the separate device, without signing in silently."""
        database.db.set("shizu.telethon", "enabled", False)
        database.db.set("shizu.telethon", "status", "invalid")
        self.app.is_tl_enabled = False
        reporter.problem(
            "telethon_revoked",
            "Telethon отключён в Telegram. Для переподключения используйте <code>.enabletlmode</code>.",
        )

    async def restore_telethon(self, user_id: int) -> None:
        """Restore only an existing encrypted authorization during startup."""
        try:
            self.connections = TelegramConnectionService.from_environment(
                self.app.api_id,
                self.app.api_hash,
                on_invalid=self._telethon_invalidated,
            )
            self.tapp = await self.connections.restore(user_id)
            self.app.telethon_connections = self.connections
        except (TelethonSessionInvalid, AccountMismatch) as error:
            logging.warning("Telethon startup: %s", error.status)
            await self._telethon_invalidated(user_id)
        except TelegramConnectionError as error:
            logging.warning(
                "Telethon startup temporarily unavailable: %s", error.status
            )
            database.db.set("shizu.telethon", "status", "unavailable")
            self.app.is_tl_enabled = False

    def _check_api_tokens(self) -> bool:
        cfg = cp.ConfigParser()
        return bool(cfg.read("./config.ini"))

    async def send_code(self) -> tuple[str, str]:
        while True:
            error_text: str = ""
            try:
                phone = colored_input("Enter phone number: ")
                return phone, (await self.app.send_code(phone)).phone_code_hash
            except errors.PhoneNumberInvalid:
                error_text = "Invalid phone number, please try again"
            except errors.PhoneNumberBanned:
                error_text = "Phone number is banned"
            except errors.PhoneNumberFlood:
                error_text = "Too many attempts for this phone number, try again later"
            except errors.PhoneNumberUnoccupied:
                error_text = "Phone number is not registered"
            except errors.BadRequest as error:
                error_text = f"An unknown error occurred: {error}"
            if error_text:
                logging.error(error_text)

    async def enter_code(self, phone: str, phone_code_hash: str) -> types.User | bool:
        try:
            code = colored_input("Enter confirmation code: ")
            return await self.app.sign_in(phone, phone_code_hash, code)
        except errors.SessionPasswordNeeded:
            return False

    async def enter_2fa(self) -> types.User:
        while True:
            try:
                passwd = colored_input(
                    "Enter two-factor authentication password: ", True
                )
                return await self.app.check_password(passwd)
            except errors.BadRequest:
                logging.error("Incorrect password, please try again")

    async def authorize(self) -> tuple[types.User, Client] | NoReturn:
        PrivateFiles.secure_sqlite(self.app.storage.database)
        await self.app.connect()
        SecretRedactor.remember(await self.app.storage.auth_key())

        try:
            me = await self.app.get_me()
        except errors.AuthKeyUnregistered:
            if args.web and web_available:
                await self.web_auth()
            await Reporter.notify_owner_by_token(
                Reporter.SESSION_ENDED + Reporter.LOGIN_CONSOLE, "session_notice"
            )
            await self.handle_auth_key_unregistered()
            me = await self.app.get_me()
        except errors.SessionRevoked:
            await Reporter.notify_owner_by_token(
                Reporter.SESSION_ENDED + Reporter.LOGIN_CONSOLE, "session_notice"
            )
            await self.handle_session_revoked()
            return sys.exit(64)

        if utils.is_tl_configured():
            await self.restore_telethon(me.id)
        return me, self.app, self.tapp

    async def handle_auth_key_unregistered(self) -> None:
        cfg = cp.ConfigParser()
        cfg.read("config.ini")

        api_id = cfg.get("pyrogram", "api_id", fallback="") or colored_input(
            "Enter API ID: "
        )
        api_hash = cfg.get("pyrogram", "api_hash", fallback="") or colored_input(
            "Enter API hash: "
        )

        if not cfg.has_section("pyrogram"):
            cfg.add_section("pyrogram")
        cfg.set("pyrogram", "api_id", api_id)
        cfg.set("pyrogram", "api_hash", api_hash)
        SecretRedactor.remember(api_hash)
        if not cfg.get("pyrogram", "device_model", fallback="").strip():
            cfg.set("pyrogram", "device_model", self.app.device_model)

        PrivateFiles.write_config("config.ini", cfg)

        qr = colored_input("Log in with a QR code? y/n: ").strip().lower()
        if qr in ("y", "yes"):
            await self.login_with_qr_code(cfg)
        else:
            phone, phone_code_hash = await self.send_code()
            logged = await self.enter_code(phone, phone_code_hash)
            if logged:
                await self.app.get_me()
            else:
                await self.enter_2fa()

    async def handle_session_revoked(self) -> None:
        logging.error(
            "Session has been revoked. Delete the session file and run the start command again"
        )
        await self.app.disconnect()

    async def login_with_qr_code(self, cfg: cp.ConfigParser) -> None:
        api_id = int(cfg.get("pyrogram", "api_id"))
        api_hash = cfg.get("pyrogram", "api_hash")
        tries = 0
        while True:
            try:
                r = await self.app.invoke(
                    ExportLoginToken(api_id=api_id, api_hash=api_hash, except_ids=[])
                )
            except errors.exceptions.unauthorized_401.SessionPasswordNeeded:
                print("2FA is enabled, please enter your password")
                passwd = colored_input(
                    "Enter two-factor authentication password: ", True
                )
                await self.app.check_password(passwd)
                await self.app.get_me()
                break
            if isinstance(r, raw.types.auth.login_token_success.LoginTokenSuccess):
                break
            if isinstance(r, raw.types.auth.login_token.LoginToken) and tries % 30 == 0:
                print("Scan the QR code below:")
                qr = QRCode(error_correction=1)
                qr.add_data(
                    f"tg://login?token={base64.urlsafe_b64encode(r.token).decode('utf-8').rstrip('=')}"
                )
                qr.make(fit=True)
                qr.print_ascii()
            tries += 1
            await asyncio.sleep(1)

    async def web_auth(self) -> NoReturn:
        """Start the web interface for authentication"""

        if args.web and web_available:
            if web := (
                core.Web(
                    api_token=None,
                )
            ):
                web.port = args.port or random.randint(2000, 9999)

                await web.start(web.port)

                logging.info(f"🌐 Web interface available at: {web.url}")
                await Reporter.notify_owner_by_token(
                    Reporter.SESSION_ENDED + Reporter.LOGIN_WEB.format(web.url),
                    "session_notice",
                )

                await web.wait_for_api_token_setup()
                await web.wait_for_clients_setup()

                return utils.restart()
