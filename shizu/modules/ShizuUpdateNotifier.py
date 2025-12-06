# Shizu Copyright (C) 2023-2024  AmoreForever
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
from datetime import datetime

import requests
from aiogram.types import CallbackQuery
from pyrogram import Client, types

from .. import loader, utils
from ..version import branch


@loader.module("ShizuUpdateNotifier", "hikamoru")
class UpdateNotifier(loader.Module):
    """Notifies about new commits in the repository"""

    strings = {}

    def __init__(self):
        self.config = loader.ModuleConfig(
            "enabled",
            True,
            lambda m: self.strings("cfg_doc_enable"),
            "check_interval",
            300,
            lambda m: self.strings("cfg_doc_check_interval"),
            "repo_owner",
            "AmoreForever",
            lambda m: self.strings("cfg_doc_repo_owner"),
            "repo_name",
            "Shizu",
            lambda m: self.strings("cfg_doc_repo_name"),
        )

    async def _get_latest_commit(self, owner: str, repo: str, branch_name: str) -> dict:
        """Get the latest commit from GitHub API"""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch_name}"
            response = await utils.run_sync(requests.get, url, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logging.error("Error fetching commit: %s", e)
            return None

    @loader.loop(interval=60, autostart=True)
    async def check_updates_loop(self):
        """Periodically check for new commits"""
        if not self.config["enabled"]:
            return

        owner = self.config["repo_owner"]
        repo = self.config["repo_name"]
        branch_name = str(branch) if branch else "beta"

        commit = await self._get_latest_commit(owner, repo, branch_name)
        if not commit:
            return

        commit_sha = commit.get("sha", "")
        last_sha = self.db.get("shizu.update_notifier", "last_commit_sha", "")

        if commit_sha and commit_sha != last_sha:
            if last_sha:
                await self._send_update_notification(self.bot, commit)
            self.db.set("shizu.update_notifier", "last_commit_sha", commit_sha)
            self.db.save()

    async def _send_update_notification(self, bot: "bot.BotManager", commit: dict):
        """Send notification about new update"""
        try:
            commit_message = commit.get("commit", {}).get("message", "No message")
            commit_author = (
                commit.get("commit", {}).get("author", {}).get("name", "Unknown")
            )
            commit_date = commit.get("commit", {}).get("author", {}).get("date", "")
            commit_url = commit.get("html_url", "")
            commit_sha_short = commit.get("sha", "")[:7]

            if commit_date:
                try:
                    dt = datetime.fromisoformat(commit_date.replace("Z", "+00:00"))
                    commit_date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, AttributeError):
                    commit_date_str = commit_date
            else:
                commit_date_str = "Unknown"

            text = self.strings("update_available").format(
                commit_sha_short=commit_sha_short,
                commit_author=utils.escape_html(commit_author),
                commit_date=commit_date_str,
                commit_message=utils.escape_html(commit_message.split(chr(10))[0]),
                commit_url=commit_url,
            )

            markup = self.bot._generate_markup(
                [
                    [
                        {
                            "text": self.strings("button_update"),
                            "callback": self.inline__update,
                        },
                        {
                            "text": self.strings("button_close"),
                            "callback": self.inline__close,
                        },
                    ]
                ]
            )

            await self.bot.bot.send_message(self.me.id, text, reply_markup=markup)

        except Exception as e:
            logging.exception("Error sending update notification: %s", e)

    async def inline__update(self, call: CallbackQuery):
        """Handle update button click"""
        try:
            await call.answer(self.strings("updating"))
            from subprocess import check_output

            check_output("git stash", shell=True).decode()
            output = check_output("git pull", shell=True).decode()

            if "Already up to date." in output:
                await call.edit(self.strings("already_updated"))
            else:
                self.db.set(
                    "shizu.updater",
                    "restart",
                    {
                        "chat": call.message.chat.id,
                        "id": call.message.message_id,
                        "start": str(round(datetime.now().timestamp())),
                        "type": "update",
                    },
                )
                await call.edit(self.strings("update_complete"))
                utils.restart()
        except Exception as e:
            logging.exception("Error updating: %s", e)
            await call.answer(
                self.strings("update_error").format(error=str(e)), show_alert=True
            )

    async def inline__close(self, call: CallbackQuery):
        """Handle close button click"""
        try:
            await call.answer()
            await call.message.delete()
        except Exception as e:
            logging.debug("Error closing notification: %s", e)

    @loader.command()
    async def checkupdate(self, _app: Client, message: types.Message):
        """Manually check for updates"""
        await utils.answer(message, self.strings("checking"))

        owner = self.config["repo_owner"]
        repo = self.config["repo_name"]
        branch_name = str(branch) if branch else "beta"

        commit = await self._get_latest_commit(owner, repo, branch_name)
        if not commit:
            return await utils.answer(message, self.strings("fetch_error"))

        commit_sha = commit.get("sha", "")
        last_sha = self.db.get("shizu.update_notifier", "last_commit_sha", "")

        if commit_sha == last_sha:
            await utils.answer(message, self.strings("latest_version"))
        else:
            commit_message = commit.get("commit", {}).get("message", "No message")
            commit_sha_short = commit.get("sha", "")[:7]
            text = self.strings("update_available_manual").format(
                commit_sha_short=commit_sha_short,
                commit_message=utils.escape_html(commit_message.split(chr(10))[0]),
            )
            await utils.answer(message, text)
