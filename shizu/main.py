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

import logging
import os

import sys
import asyncio
import subprocess

import pyrogram
from pyrogram import types
from pyrogram.methods.utilities.idle import idle

from shizu import auth, database, loader, utils


async def main():
    """Main function"""

    me, app, tapp = await auth.Auth().authorize()

    await app.initialize()

    db = database.db

    modules = loader.ModulesManager(app, db, me)

    if utils.is_tl_enabled():
        asyncio.ensure_future(tapp.start())
        app.tl = tapp
    else:
        app.tl = "Not enabled"

    await modules.load(app)

    if not db.get("shizu.me", "me", None):
        id_ = (await app.get_me()).id
        db.set("shizu.me", "me", id_)

    await idle()

    logging.info("Shizu is shutting down...")
    return True
