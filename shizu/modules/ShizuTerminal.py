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
from pyrogram import Client, types

from .. import loader, utils


@loader.module(name="ShizuTerminal", author="shizu")
class TerminalMod(loader.Module):
    """Terminal"""
    
    strings = {}


    @loader.command(aliases=["t"])
    async def terminal(self, app: Client, message: types.Message):
        args = message.get_args_raw()

        if not args:
            return await message.answer(self.strings("no_args"))

        message = await message.answer(self.strings("wait"))
        output = await self.run_command(args)

        await message.answer(
            f"⌨️ <b>Command:</b> <pre language='shell'>{args.strip()}</pre>\n"
            f"💾 <b>Output:</b>\n<code>"
            f"<pre language='shell'>{output}</pre>"
            f"</code>",
        )

    async def run_command(self, cmd):
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
            cwd=utils.get_base_dir(),
        )
        stdout, stderr = await process.communicate()
        return str(stdout.decode().strip()) + str(stderr.decode().strip())
