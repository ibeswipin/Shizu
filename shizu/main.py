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

import logging
import os

import sys
import asyncio
import subprocess

import pyrogram
from pyrogram import types
from pyrogram.methods.utilities.idle import idle

from shizu import auth, database, loader
from shizu.besafe import BeSafe
from shizu.ratelimit import ApiLimiter
from shizu.version import __version__


async def main():
    """Main function"""

    me, app, tapp = await auth.Auth().authorize()

    if auth.args.setup_only:
        if tapp is not None:
            await tapp.disconnect()
        await app.disconnect()
        logging.info("Account authorization completed. Shizu is ready to start.")
        return True

    try:
        await app.initialize()
        db = database.db
        ApiLimiter(db).attach(app)
        modules = loader.ModulesManager(app, db, me)
        guard = BeSafe()
        await guard.protect_secrets(app, tapp)
        guard.install()
        guard.attach(app, "invoke", 0)

        if tapp is not None:
            guard.attach(tapp, "_call", 1)
            app.tl = tapp
        else:
            app.tl = "Not enabled"

        await modules.load(app)

        if not db.get("shizu.me", "me", None):
            id_ = (await app.get_me()).id
            db.set("shizu.me", "me", id_)

        await idle()
    finally:
        if tapp is not None:
            await tapp.disconnect()
        if getattr(app, "telethon_connections", None):
            await app.telethon_connections.close()
        if app.is_initialized:
            await app.stop()
        elif app.is_connected:
            await app.disconnect()

    logging.info("Shizu is shutting down...")
    return True
