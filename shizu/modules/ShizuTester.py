#    Sh1t-UB (telegram userbot by sh1tn3t)
#    Copyright (C) 2021-2022 Sh1tN3t

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.


# ---------------------------------------------------------------------------


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


import time
import io

import logging

from pyrogram import Client, types

from .. import loader, utils, logger


@loader.module(name="ShizuTester", author="shizu")
class TesterMod(loader.Module):
    """Execute activities based on userbot self-testing"""

    strings = {}

    @loader.command()
    async def logs(self, app: Client, message: types.Message):
        """To get logs. Usage: logs (verbosity level)"""

        args = message.get_args()

        lvl = 40

        if args and not (lvl := logger.get_valid_level(args)):
            return await message.answer(self.strings("invalid_verb"))

        handler = logging.getLogger().handlers[0]
        logs = ("\n".join(handler.dumps(lvl))).encode("utf-8")
        if not logs:
            return await message.answer(
                self.strings("no_logs_").format(
                    lvl,
                    logging.getLevelName(lvl),
                )
            )

        logs = io.BytesIO(logs)
        logs.name = "shizu.log"

        await message.delete()
        return await message.answer(
            logs,
            doc=True,
            caption=f"🐙 Shizu logs with verbosity {lvl} ({logging.getLevelName(lvl)})",
        )

    @loader.command()
    async def ping(self, app: Client, message: types.Message):
        """Checks the response rate of the user bot"""
        start = time.perf_counter_ns()

        ms = await message.answer("<emoji id=5267444331010074275>▫️</emoji>")

        ping = round((time.perf_counter_ns() - start) / 10**6, 3)

        await ms.edit(
            self.strings("ping").format(ping),
        )

    @loader.command()
    async def suspend(self, app: Client, message: types.Message):
        """Suspend the userbot for a certain time (n seconds)"""

        try:
            await message.answer(
                self.strings("suspend").format(int(message.get_args()))
            )
            time.sleep(int(message.get_args()))

        except ValueError:
            await message.answer(self.strings("suspend_invalid_time"))
