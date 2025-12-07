
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


import asyncio
import collections
import os
import string

import aiohttp_jinja2
import pyrogram

import configparser as cp
from aiohttp import web

from pyrogram import errors

from shizu import utils

BASE_DIR =  os.path.dirname(utils.get_base_dir())

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
        self.api_set = asyncio.Event()
        self.sign_in_clients = {}
        self.clients = []
        self.client = None
        self.clients_set = asyncio.Event()
        self.root_redirected = asyncio.Event()

    async def root(self, request):
        if self.redirect_url:
            self.root_redirected.set()
            return web.Response(status=302, headers={"Location": self.redirect_url})
        
        return await self.initial_setup(request)

    @aiohttp_jinja2.template("initial_root.jinja2")
    async def initial_setup(self, request):
        return {
            "api_done": self.api_token is not None,
            "tg_done": bool(self.client_data),
        }

    def wait_for_api_token_setup(self):
        return self.api_set.wait()

    def wait_for_clients_setup(self):
        return self.clients_set.wait()

    async def set_tg_api(self, request):
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
            "device_model": utils.get_random_smartphone(),
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
        
        client = pyrogram.client.Client(
            name="../shizu",
            api_id=self.api_token.ID,
            api_hash=self.api_token.HASH,
            device_model=utils.get_random_smartphone(),
        )

        self.client = client

        await self.client.connect()
        while True:
            phone_hash = (await self.client.send_code(phone)).phone_code_hash
            self.api_token = collections.namedtuple("api_token", ("phone_hash"))(phone_hash=phone_hash)
            self.sign_in_clients[phone] = client
            return web.Response()
        
    async def tg_code(self, request):
        text = await request.text()
        if len(text) < 6:
            return web.Response(status=400)
        split = text.split("\n", 2)
        if len(split) not in (2, 3):
            return web.Response(status=400)
        code = split[0]
        phone = split[1]
        password = split[2]
        if (
            (len(code) != 5 and not password)
            or any(c not in string.digits for c in code)
            or not phone
        ):
            return web.Response(status=400)
        if not password:
            try:
                await self.client.sign_in(phone, phone_code=code, phone_code_hash=self.api_token.phone_hash)
            except errors.exceptions.SessionPasswordNeeded:
                return web.Response(status=401)  # Requires 2FA login
            except errors.exceptions.PhoneCodeExpired:
                return web.Response(status=404)
            except errors.exceptions.PhoneCodeInvalid:
                return web.Response(status=403)
            except errors.exceptions.FloodWait as e:
                return web.Response(status=421)
        else:
            try:
                await self.client.check_password(password)
                await self.client.sign_in(phone, phone_code_hash=self.api_token.phone_hash, phone_code=code)
            except errors.exceptions.PasswordHashInvalid:
                return web.Response(status=403)  # Invalid 2FA password
            except errors.exceptions.FloodWait as e:
                return web.Response(status=421)
        del self.sign_in_clients[phone]
        
        return web.Response()

    async def finish_login(self, request):
        self.clients_set.set()
        return web.Response()
