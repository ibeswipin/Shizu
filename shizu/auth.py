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


import configparser as cp
import asyncio
import logging
import random
import base64
import sys
import argparse

from datetime import datetime
from getpass import getpass
from typing import NoReturn, Tuple, Union

from pyrogram import Client, errors, types, raw
from pyrogram.session.session import Session
from pyrogram.raw.functions.auth.export_login_token import ExportLoginToken

from telethon import TelegramClient

from qrcode.main import QRCode
from . import utils

try:
    from .web import core
except ImportError as e:
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

    return parser.parse_args()


args = argument_parser()


class Auth:
    def __init__(self, session_name: str = "../shizu") -> None:

        self._check_api_tokens()

        cfg = cp.ConfigParser()
        cfg.read("./config.ini")

        device_model = cfg.get(
            "pyrogram", "device_model", fallback=utils.get_random_smartphone()
        )
        api_id = cfg.get("pyrogram", "api_id", fallback="123")
        api_hash = cfg.get("pyrogram", "api_hash", fallback="hash")

        self.app = Client(
            name=session_name,
            api_id=api_id,
            api_hash=api_hash,
            device_model=device_model,
        )

        if utils.is_tl_enabled():
            self.tapp = TelegramClient(
                "shizu-tl",
                api_id=cfg.get("pyrogram", "api_id"),
                api_hash=cfg.get("pyrogram", "api_hash"),
                device_model="MacBook Pro",
                app_version="11.12.0",
                system_version="14.0",
                lang_code="en",
                system_lang_code="en-US"
            )

    def _check_api_tokens(self) -> bool:
        cfg = cp.ConfigParser()
        return bool(cfg.read("./config.ini"))

    async def send_code(self) -> Tuple[str, str]:
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
                error_text = "Phone number is flood protected"
            except errors.PhoneNumberUnoccupied:
                error_text = "Phone number is not registered"
            except errors.BadRequest as error:
                error_text = f"An unknown error occurred: {error}"
            if error_text:
                logging.error(error_text)

    async def enter_code(
        self, phone: str, phone_code_hash: str
    ) -> Union[types.User, bool]:
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

    async def authorize(self) -> Union[Tuple[types.User, Client], NoReturn]:
        await self.app.connect()

        try:
            me = await self.app.get_me()
        except errors.AuthKeyUnregistered:
            if args.web and web_available:
                await self.web_auth()
            await self.handle_auth_key_unregistered()
        except errors.SessionRevoked:
            await self.handle_session_revoked()
            return sys.exit(64)

        if utils.is_tl_enabled():
            return me, self.app, self.tapp

        return me, self.app, None

    async def handle_auth_key_unregistered(self) -> None:
        cfg = cp.ConfigParser()
        cfg.read("config.ini")

        api_id = colored_input("Enter API ID: ")
        api_hash = colored_input("Enter API hash: ")

        cfg["pyrogram"] = {
            "api_id": api_id,
            "api_hash": api_hash,
            "device_model": utils.get_random_smartphone(),
        }

        with open("config.ini", "w", encoding="utf-8") as file:
            cfg.write(file)

        qr = colored_input("Login with QR-CODE? y/n").lower().split()
        if qr[0] == "y":
            await self.login_with_qr_code(cfg)
        else:
            phone, phone_code_hash = await self.send_code()
            logged = await self.enter_code(phone, phone_code_hash)
            me: types.User = (
                await self.app.get_me() if logged else await self.enter_2fa()
            )

    async def handle_session_revoked(self) -> None:
        logging.error(
            "Session has been revoked, delete the session and run the start command again"
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
                me = await self.app.get_me()
                break
            if isinstance(r, raw.types.auth.login_token_success.LoginTokenSuccess):
                break
            if isinstance(r, raw.types.auth.login_token.LoginToken) and tries % 30 == 0:
                print("Scan QR code below:")
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

                await web.wait_for_api_token_setup()
                await web.wait_for_clients_setup()

                return utils.restart()
