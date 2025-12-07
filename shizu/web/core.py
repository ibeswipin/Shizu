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


import os
import re
import asyncio
import inspect

import aiohttp_jinja2
import jinja2
from aiohttp import web

from shizu.web import initial_setup


class TunnelManager:
    def __init__(self):
        self.url = None

    async def open_tunnel(self, port):
        ssh_command = f"ssh -o StrictHostKeyChecking=no -R 80:localhost:{port} nokey@localhost.run"
        process = await asyncio.create_subprocess_shell(
            ssh_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        url = await self._extract_tunnel_url(process.stdout)
        self.url = url or f"https://localhost:{port}"
        return self.url

    async def _extract_tunnel_url(self, stdout):
        event = asyncio.Event()
        url = None

        async def read_output():
            nonlocal url
            while True:
                line = await stdout.readline()
                if not line:
                    break
                decoded_line = line.decode()
                match = re.search(r"tunneled.*?(https:\/\/.+)", decoded_line)
                if match:
                    url = match[1]
                    break
            event.set()

        await read_output()
        await event.wait()
        return url


class Web(initial_setup.Web, TunnelManager):
    def __init__(self, **kwargs):
        self.runner = None
        self.port = None
        self.running = asyncio.Event()
        self.ready = asyncio.Event()
        self.client_data = {}
        self.app = web.Application()
        aiohttp_jinja2.setup(
            self.app,
            filters={"getdoc": inspect.getdoc, "ascii": ascii},
            loader=jinja2.FileSystemLoader("web-resources"),
        )
        super().__init__(**kwargs)

        self.app["static_root_url"] = "/static"
        self.app.router.add_get("/favicon.ico", self.favicon)
        self.app.router.add_static("/static", "web-resources/static")

    async def start_if_ready(self, total_count, port):
        if total_count <= len(self.client_data):
            if not self.running.is_set():
                await self.start(port)
            self.ready.set()

    async def start(self, port):
        self.runner = web.AppRunner(self.app)

        await self.runner.setup()

        self.port = os.environ.get("PORT", port)

        site = web.TCPSite(self.runner, None, self.port)
        await site.start()

        await self.open_tunnel(self.port)

        self.running.set()


    async def stop(self):
        await self.runner.shutdown()
        await self.runner.cleanup()
        self.running.clear()
        self.ready.clear()

    @staticmethod
    async def favicon(request):
        return web.Response(
            status=301, headers={"Location": "https://i.imgur.com/j0OPQso.jpeg"}
        )
