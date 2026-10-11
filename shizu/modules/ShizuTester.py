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


import contextlib
import datetime
import html
import io
import logging
import time

from aiogram.types import CallbackQuery
from aiogram.utils.exceptions import TelegramAPIError
from pyrogram import Client, types

from shizu import loader, logger
from shizu.diagnostics import profiler, reports


@loader.module(name="ShizuTester", author="shizu")
class TesterMod(loader.Module):
    """Userbot self-testing tools"""

    strings = {}
    REPORT_PREFIX = "shizu_report:"

    @loader.command()
    async def logs(self, app: Client, message: types.Message):
        """Get logs. Usage: logs (verbosity level)"""

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
        """Check the userbot response time"""
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

    @loader.command()
    async def perf(self, app: Client, message: types.Message):
        """Show the slowest and failing commands and watchers. Usage: perf (reset)"""
        if message.get_args().strip() == "reset":
            profiler.reset()
            return await message.answer(self.strings("perf_reset"))

        top = profiler.top()
        if not top:
            return await message.answer(self.strings("perf_empty"))

        uptime = datetime.timedelta(seconds=round(time.time() - profiler.started))
        lines = [self.strings("perf_title").format(uptime)]
        for stats in top:
            errors = (
                self.strings("perf_errors").format(stats.errors) if stats.errors else ""
            )
            lines.append(
                self.strings("perf_line").format(
                    html.escape(stats.module),
                    html.escape(stats.handler),
                    self.strings(f"perf_{stats.kind}"),
                    stats.calls,
                    round(stats.total / stats.calls * 1000),
                    round(stats.slowest * 1000),
                    round(stats.total, 1),
                    errors,
                )
            )
        await message.answer("\n\n".join(lines))

    async def report_callback_handler(self, call: CallbackQuery):
        data = call.data or ""
        if not data.startswith(self.REPORT_PREFIX):
            return
        if call.from_user.id != self.me.id:
            return await call.answer(self.strings("report_owner_only"), show_alert=True)

        action, _, report_id = data[len(self.REPORT_PREFIX) :].rpartition(":")
        report = reports.get(report_id)
        if not report:
            return await call.answer(self.strings("report_expired"), show_alert=True)
        support, text = report

        if not action:
            await call.answer()
            return await self._bot.send_message(
                call.message.chat.id,
                self.strings("report_preview").format(html.escape(support))
                + "\n\n"
                + text,
                reply_to_message_id=call.message.message_id,
                reply_markup=self.bot._generate_markup(
                    [
                        [
                            {
                                "text": self.strings("btn_report_send"),
                                "data": f"{self.REPORT_PREFIX}send:{report_id}",
                            },
                            {
                                "text": self.strings("btn_report_cancel"),
                                "data": f"{self.REPORT_PREFIX}cancel:{report_id}",
                            },
                        ]
                    ]
                ),
            )

        if action == "send":
            try:
                await self.app.send_message(support, text)
            except Exception as error:
                return await call.answer(
                    self.strings("report_failed").format(error), show_alert=True
                )
            reports.pop(report_id)
            await call.answer(self.strings("report_sent"))
            status = self.strings("report_sent")
        else:
            reports.pop(report_id)
            await call.answer()
            status = self.strings("report_cancelled")

        with contextlib.suppress(TelegramAPIError):
            await call.message.edit_text(status)
