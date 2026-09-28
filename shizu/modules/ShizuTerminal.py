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
import fcntl
import json
import os
import pty
import re
import secrets
import shlex
import signal
import struct
import termios
import time

from aiohttp import WSMsgType, web
from pyrogram import Client, types

from shizu import loader, utils
from shizu.web.core import TunnelManager

ANSI = re.compile(r"\x1b(\[[0-?]*[ -/]*[@-~]|\][^\x07]*\x07|[()][0-9A-Za-z]|[=>])")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

WEB_IDLE = 15 * 60
WEB_MAX_FAILS = 5


def web_page(name: str) -> str:
    path = os.path.join(os.path.dirname(utils.get_base_dir()), "web-resources", name)
    with open(path, encoding="utf-8") as f:
        return f.read()


def clean(raw: str) -> str:
    """Strips ANSI codes and applies carriage returns like a terminal would"""
    text = ANSI.sub("", raw).replace("\r\n", "\n")
    text = "\n".join(line.rsplit("\r", 1)[-1] for line in text.split("\n"))
    return CONTROL.sub("", text)


async def spawn_pty(cmd: str, term: str):
    """Runs cmd in a pseudo-terminal, returns (process, pty master fd)"""
    master, slave = pty.openpty()
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=utils.get_base_dir(),
        env={**os.environ, "TERM": term},
        start_new_session=True,
        preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0),
    )
    os.close(slave)
    return process, master

ANSI = re.compile(r"\x1b(\[[0-?]*[ -/]*[@-~]|\][^\x07]*\x07|[()][0-9A-Za-z]|[=>])")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(raw: str) -> str:
    """Strips ANSI codes and applies carriage returns like a terminal would"""
    text = ANSI.sub("", raw).replace("\r\n", "\n")
    text = "\n".join(line.rsplit("\r", 1)[-1] for line in text.split("\n"))
    return CONTROL.sub("", text)


async def spawn_pty(cmd: str, term: str = "dumb"):
    """Runs cmd in a pseudo-terminal, returns (process, pty master fd)"""
    master, slave = pty.openpty()
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=utils.get_base_dir(),
        env={**os.environ, "TERM": term},
        start_new_session=True,
        preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0),
    )
    os.close(slave)
    return process, master


@loader.module(name="ShizuTerminal", author="shizu")
class TerminalMod(loader.Module):
    """Terminal"""

    strings = {}

    def __init__(self):
        self._procs = {}
        self._web = None

    @loader.command(aliases=["t"])
    async def terminal(self, app: Client, message: types.Message):
        args = message.get_args_raw()

        if not args:
            return await message.answer(self.strings("no_args"))

        sender = message.from_user.id if message.from_user else None
        message = await message.answer(self.strings("wait"))

        process, master = await spawn_pty(args, "dumb")
        output = bytearray()
        loop = asyncio.get_running_loop()

        def on_read():
            try:
                data = os.read(master, 4096)
            except OSError:
                data = b""

            if not data:
                return loop.remove_reader(master)

            output.extend(data)
            del output[:-65536]

        loop.add_reader(master, on_read)
        key = (message.chat.id, message.id)
        self._procs[key] = (master, sender)

        wait = asyncio.ensure_future(process.wait())
        shown = None
        try:
            while True:
                done, _ = await asyncio.wait({wait}, timeout=3)
                if done:
                    await asyncio.sleep(0.3)

                text = self._render(args, output, process.returncode if done else None)
                if text != shown:
                    with contextlib.suppress(Exception):
                        await message.answer(text)
                    shown = text

                if done:
                    break
        finally:
            self._procs.pop(key, None)
            loop.remove_reader(master)
            os.close(master)

    def _render(self, cmd: str, output: bytearray, code) -> str:
        out = utils.escape_html(clean(output.decode(errors="replace")).strip()[-3500:])
        status = (
            self.strings("running") if code is None else self.strings("done").format(code)
        )
        return (
            f"⌨️ <b>Command:</b> <pre language='shell'>{utils.escape_html(cmd.strip())}</pre>\n"
            f"💾 <b>Output:</b>\n<pre language='shell'>{out or '...'}</pre>\n"
            f"{status}"
        )

    @loader.watcher(only_messages=True, no_commands=True)
    async def terminal_input_watcher(self, app: Client, message: types.Message):
        """Replies to a running command message go to its stdin"""
        proc = self._procs.get((message.chat.id, message.reply_to_message_id))
        if not proc or not message.from_user or message.from_user.id != proc[1]:
            return

        text = message.text or ""
        os.write(
            proc[0],
            {"^C": b"\x03", "^D": b"\x04"}.get(text, (text + "\n").encode()),
        )

        with contextlib.suppress(Exception):
            await message.delete()

    @loader.command()
    async def webterm(self, app: Client, message: types.Message):
        """Web terminal through a tunnel - <code>.webterm [stop]</code>"""
        if message.get_args_raw().strip() == "stop":
            if not self._web:
                return await message.answer(self.strings("web_not_running"))

            await self._web_stop(self.strings("web_closed"))
            return await message.answer(self.strings("web_closed"))

        if self._web:
            return await message.answer(
                self.strings("web_running").format(self._web["url"])
            )

        message = await message.answer(self.strings("web_starting"))
        if not (w := await self._web_start()):
            return await message.answer(self.strings("web_tunnel_error"))

        w["password_msg"] = await app.send_message(
            "me",
            self.strings("web_password").format(w["url"], w["password"]),
            disable_web_page_preview=True,
        )
        self._web = w
        asyncio.ensure_future(self._web_watchdog(w))
        await message.answer(self.strings("web_ready").format(w["url"]))

    async def _web_start(self):
        w = {
            "password": secrets.token_urlsafe(12),
            "tokens": set(),
            "sockets": set(),
            "fails": 0,
            "last": time.time(),
            "tunnel": TunnelManager(),
        }

        webapp = web.Application()
        webapp.router.add_get("/", self._web_index)
        webapp.router.add_post("/login", self._web_login)
        webapp.router.add_get("/ws", self._web_ws)

        w["runner"] = web.AppRunner(webapp)
        await w["runner"].setup()
        await web.TCPSite(w["runner"], "127.0.0.1", 0).start()

        with contextlib.suppress(asyncio.TimeoutError):
            w["url"] = await asyncio.wait_for(
                w["tunnel"].open_tunnel(w["runner"].addresses[0][1]), 30
            )

        if not w.get("url") or w["url"].startswith("https://localhost"):
            if w["tunnel"].process:
                w["tunnel"].process.kill()
            await w["runner"].cleanup()
            return None

        asyncio.ensure_future(w["tunnel"].process.stdout.read())
        return w

    async def _web_stop(self, notice: str):
        w, self._web = self._web, None
        if not w:
            return

        w["tunnel"].process.kill()
        for ws in list(w["sockets"]):
            await ws.close()

        await w["runner"].cleanup()

        with contextlib.suppress(Exception):
            await w["password_msg"].edit_text(notice)

    async def _web_watchdog(self, w: dict):
        while self._web is w:
            await asyncio.sleep(60)
            if (
                self._web is w
                and not w["sockets"]
                and time.time() - w["last"] > WEB_IDLE
            ):
                await self._web_stop(self.strings("web_idle"))

    def _web_authed(self, request: web.Request) -> bool:
        return bool(self._web) and request.cookies.get("shizu_term") in self._web["tokens"]

    async def _web_index(self, request: web.Request):
        page = (
            web_page("terminal.html")
            if self._web_authed(request)
            else web_page("terminal_login.html").replace("{error}", "")
        )
        return web.Response(text=page, content_type="text/html")

    async def _web_login(self, request: web.Request):
        if not (w := self._web):
            return web.Response(status=404)

        password = str((await request.post()).get("password", ""))
        if not secrets.compare_digest(password.encode(), w["password"].encode()):
            w["fails"] += 1
            if w["fails"] >= WEB_MAX_FAILS:
                asyncio.ensure_future(self._web_stop(self.strings("web_locked")))

            return web.Response(
                text=web_page("terminal_login.html").replace(
                    "{error}", "<p>Wrong password</p>"
                ),
                content_type="text/html",
                status=401,
            )

        token = secrets.token_urlsafe(32)
        w["tokens"].add(token)
        response = web.Response(status=302, headers={"Location": "/"})
        response.set_cookie(
            "shizu_term", token, httponly=True, secure=True, samesite="Strict"
        )
        return response

    async def _web_ws(self, request: web.Request):
        if not self._web_authed(request):
            return web.Response(status=403)

        w = self._web
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        w["sockets"].add(ws)

        shell = shlex.quote(os.environ.get("SHELL", "/bin/bash"))
        process, master = await spawn_pty(f"exec {shell} -l", "xterm-256color")
        loop = asyncio.get_running_loop()

        def on_read():
            try:
                data = os.read(master, 65536)
            except OSError:
                data = b""

            if not data:
                loop.remove_reader(master)
                asyncio.ensure_future(ws.close())
                return

            asyncio.ensure_future(ws.send_bytes(data))

        loop.add_reader(master, on_read)
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue

                data = json.loads(msg.data)
                if "input" in data:
                    os.write(master, data["input"].encode())
                elif "resize" in data:
                    cols, rows = data["resize"]
                    fcntl.ioctl(
                        master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0)
                    )
        finally:
            w["sockets"].discard(ws)
            w["last"] = time.time()
            loop.remove_reader(master)
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGHUP)
            os.close(master)

        return ws
