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

    async def _get_commits_since(self, owner: str, repo: str, branch_name: str, since_sha: str) -> list:
        """Get all commits since a specific SHA"""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/compare/{since_sha}...{branch_name}"
            response = await utils.run_sync(requests.get, url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                commits = data.get("commits", [])
                return list(reversed(commits))
            return []
        except Exception as e:
            logging.error("Error fetching commits: %s", e)
            return []

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
                commits = await self._get_commits_since(owner, repo, branch_name, last_sha)
                if commits:
                    await self._send_update_notification(self.bot, commits)
            self.db.set("shizu.update_notifier", "last_commit_sha", commit_sha)
            self.db.save()

    async def _send_update_notification(self, bot: "bot.BotManager", commits: list):
        """Send notification about new update"""
        try:
            owner = self.config["repo_owner"]
            repo = self.config["repo_name"]
            
            commits_text = []
            for commit in commits:
                commit_sha = commit.get("sha", "")
                commit_sha_short = commit_sha[:7]
                commit_message = commit.get("commit", {}).get("message", "No message")
                commit_link = f"https://github.com/{owner}/{repo}/commit/{commit_sha}"
                
                message_line = utils.escape_html(commit_message.split(chr(10))[0])
                commits_text.append(
                    f"▫️ <a href='{commit_link}'>{commit_sha_short}</a> - {message_line}"
                )
            
            commits_list = "\n\n".join(commits_text)
            text = self.strings("update_available").format(commits_list=commits_list)

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

            await self.bot.bot.send_message(self.me.id, text, reply_markup=markup, disable_web_page_preview=True)

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
            if last_sha:
                commits = await self._get_commits_since(owner, repo, branch_name, last_sha)
            else:
                commits = [commit]
            
            if commits:
                owner = self.config["repo_owner"]
                repo = self.config["repo_name"]
                
                commits_text = []
                for commit_item in commits:
                    commit_sha_item = commit_item.get("sha", "")
                    commit_sha_short = commit_sha_item[:7]
                    commit_message = commit_item.get("commit", {}).get("message", "No message")
                    commit_link = f"https://github.com/{owner}/{repo}/commit/{commit_sha_item}"
                    
                    message_line = utils.escape_html(commit_message.split(chr(10))[0])
                    commits_text.append(
                        f"▫️ <a href='{commit_link}'>{commit_sha_short}</a> - {message_line}"
                    )
                
                commits_list = "\n\n".join(commits_text)
                text = self.strings("update_available_manual").format(commits_list=commits_list)
                await utils.answer(message, text)
