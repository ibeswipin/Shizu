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
import contextlib
import inspect
import os
import re

import aiohttp_jinja2
import jinja2
from aiohttp import web

from shizu.web import initial_setup
from shizu.web.cloudflared import CloudflaredInstaller


class TunnelManager:
    def __init__(self):
        self.url = None
        self.process = None
        self._drain_task = None

    async def open_tunnel(self, port, *, provider="localhost.run"):
        await self.close_tunnel()
        command = self._tunnel_command(port, provider)
        if provider == "cloudflare":
            command[0] = await CloudflaredInstaller().ensure()
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self.process = process

        try:
            url = await asyncio.wait_for(
                self._extract_tunnel_url(process.stdout, provider), 30
            )
        except asyncio.TimeoutError:
            url = None
        except BaseException:
            await self.close_tunnel()
            raise
        if not url:
            await self.close_tunnel()
        self.url = url or f"http://127.0.0.1:{port}"
        return self.url

    @staticmethod
    def _tunnel_command(port, provider):
        if provider == "cloudflare":
            return [
                "cloudflared",
                "tunnel",
                "--no-autoupdate",
                "--protocol",
                "http2",
                "--url",
                f"http://127.0.0.1:{int(port)}",
            ]
        if provider != "localhost.run":
            raise ValueError("Unknown tunnel provider")
        return [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ExitOnForwardFailure=yes",
            "-R",
            f"80:127.0.0.1:{int(port)}",
            "nokey@localhost.run",
        ]

    async def close_tunnel(self):
        if self._drain_task:
            self._drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._drain_task
            self._drain_task = None
        process, self.process = self.process, None
        if process and process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 3)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()

    async def _extract_tunnel_url(self, stdout, provider="localhost.run"):
        url = None
        async for line in stdout:
            text = line.decode(errors="replace")
            pattern = (
                r"https://[a-z0-9-]+\.trycloudflare\.com\b"
                if provider == "cloudflare"
                else r"tunneled.*?(https://[\w.-]+)"
            )
            match = re.search(pattern, text)
            if match:
                url = match[0] if provider == "cloudflare" else match[1]
            # Cloudflare prints the hostname before establishing its connection.
            if url and (
                provider != "cloudflare" or "Registered tunnel connection" in text
            ):
                self._drain_task = asyncio.create_task(self._drain(stdout))
                return url
        return None

    @staticmethod
    async def _drain(stdout):
        async for _ in stdout:
            pass


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
        await self.close_tunnel()
        await self.runner.shutdown()
        await self.runner.cleanup()
        self.running.clear()
        self.ready.clear()

    @staticmethod
    async def favicon(request):
        return web.Response(
            status=301, headers={"Location": "https://i.imgur.com/j0OPQso.jpeg"}
        )
