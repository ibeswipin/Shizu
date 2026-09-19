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
import contextlib
import fcntl
import os
import pty
import re
import termios

from pyrogram import Client, types

from shizu import loader, utils

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

    @loader.command(aliases=["t"])
    async def terminal(self, app: Client, message: types.Message):
        args = message.get_args_raw()

        if not args:
            return await message.answer(self.strings("no_args"))

        sender = message.from_user.id if message.from_user else None
        message = await message.answer(self.strings("wait"))

        process, master = await spawn_pty(args)
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
