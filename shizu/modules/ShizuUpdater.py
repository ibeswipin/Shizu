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


import asyncio
import contextlib
import logging
import time
from subprocess import check_output

import git
from aiogram.types import CallbackQuery, InputFile
from pyrogram import Client, enums, types

from shizu import loader, utils
from shizu.version import branch


@loader.module(name="ShizuUpdater", author="shizu")
class UpdateMod(loader.Module):
    """Updates, restarts and notifies about new commits"""

    strings = {}
    m__telethon = False

    def __init__(self):
        self.config = loader.ModuleConfig(
            "enabled",
            True,
            lambda m: self.strings("cfg_doc_enable"),
            "check_interval",
            300,
            lambda m: self.strings("cfg_doc_check_interval"),
            "repo_owner",
            "ibeswipin",
            lambda m: self.strings("cfg_doc_repo_owner"),
            "repo_name",
            "Shizu",
            lambda m: self.strings("cfg_doc_repo_name"),
        )

    async def on_load(self, app):
        self.adopt_config("ShizuUpdateNotifier")

    @staticmethod
    def _pull() -> bool:
        """Stash local changes and pull; False when already up to date"""
        check_output("git stash", shell=True)
        return (
            "Already up to date." not in check_output("git pull", shell=True).decode()
        )

    def _restart_record(
        self, chat, message_id: int, kind: str, bot: bool = False
    ) -> None:
        self.db.set(
            "shizu.updater",
            "restart",
            {
                "chat": chat,
                "id": message_id,
                "start": time.time(),
                "type": kind,
                **({"bot": True} if bot else {}),
            },
        )

    @staticmethod
    def _chat_of(message):
        return (
            message.chat.username
            if message.chat.type == enums.ChatType.BOT
            else message.chat.id
        )

    @loader.command()
    async def update(self, app: Client, message: types.Message):
        """Updates itself"""
        try:
            await message.answer(self.strings("attempt_"))
            if not await asyncio.to_thread(self._pull):
                return await message.answer(self.strings("last_"))
            self._restart_record(self._chat_of(message), message.id, "update")
            await message.answer(self.strings("update_"))
            utils.restart()
        except Exception as error:
            await message.answer(f"An error occurred: {error}")

    @loader.command()
    async def restart(self, app: Client, message: types.Message):
        """Restart the userbot"""
        ms = await message.answer(self.strings("reboot_"))
        self._restart_record(self._chat_of(message), ms.id, "restart")
        utils.restart()

    def _commits_list(self, commits: list, limit: int) -> str:
        """Newest commits first, the rest folded so the text fits Telegram limits"""
        owner = self.config["repo_owner"]
        repo_name = self.config["repo_name"]
        lines, used = [], 0
        for commit in reversed(commits):
            sha = commit.get("sha", "")
            message = (
                commit.get("commit", {}).get("message", "No message").split("\n")[0]
            )
            if len(message) > 80:
                message = message[:79] + "…"
            used += len(message) + 12
            if used > limit and lines:
                lines.append(f"… +{len(commits) - len(lines)}")
                break
            lines.append(
                f"• <a href='https://github.com/{owner}/{repo_name}/commit/{sha}'>{sha[:7]}</a>"
                f" {utils.escape_html(message)}"
            )
        return "\n".join(lines)

    async def _missing_commits(self, owner: str, repo_name: str, branch_name: str):
        """Latest remote commit and the commits the running checkout does not have yet"""
        latest = await self._get_latest_commit(owner, repo_name, branch_name)
        if not latest or not latest.get("sha"):
            return None, []
        try:
            repo = git.Repo()
            local = repo.head.commit.hexsha
            if latest["sha"] == local or repo.is_ancestor(latest["sha"], local):
                return latest, []
        except Exception as e:
            logging.warning("Could not compare with the local checkout: %s", e)
            return latest, []
        commits = await self._get_commits_since(owner, repo_name, branch_name, local)
        return latest, commits or [latest]

    @staticmethod
    def _fetch(git_repo: "git.Repo", branch_name: str):
        """Fetch origin without ever prompting for credentials"""
        env = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": ""}
        try:
            with git_repo.git.custom_environment(**env):
                git_repo.remotes.origin.fetch(branch_name)
        except Exception as e:
            logging.warning("Fetch failed, using local refs: %s", e)

    async def _get_latest_commit(
        self, owner: str, repo_name: str, branch_name: str
    ) -> dict:
        """Get the latest commit from git repository"""
        try:
            git_repo = git.Repo()
            await asyncio.to_thread(self._fetch, git_repo, branch_name)

            try:
                latest_commit = next(
                    git_repo.iter_commits(f"origin/{branch_name}", max_count=1)
                )

                return {
                    "sha": latest_commit.hexsha,
                    "commit": {"message": latest_commit.message.strip()},
                }
            except (git.exc.GitCommandError, StopIteration):
                return None
        except Exception as e:
            logging.error("Error fetching commit: %s", e)
            return None

    async def _get_commits_since(
        self, owner: str, repo_name: str, branch_name: str, since_sha: str
    ) -> list:
        """Get all commits since a specific SHA"""
        try:
            git_repo = git.Repo()

            try:
                commits = list(
                    git_repo.iter_commits(f"{since_sha}..origin/{branch_name}")
                )

                result = []
                for commit in reversed(commits):
                    result.append(
                        {
                            "sha": commit.hexsha,
                            "commit": {"message": commit.message.strip()},
                        }
                    )

                return result
            except (git.exc.GitCommandError, ValueError):
                logging.warning(
                    f"Git command failed for {since_sha[:7]}...{branch_name}, trying alternative method"
                )

                try:
                    all_commits = list(
                        git_repo.iter_commits(f"origin/{branch_name}", max_count=30)
                    )

                    new_commits = []
                    for commit in all_commits:
                        if commit.hexsha == since_sha:
                            break
                        new_commits.append(
                            {
                                "sha": commit.hexsha,
                                "commit": {"message": commit.message.strip()},
                            }
                        )

                    if new_commits:
                        return list(reversed(new_commits))
                except Exception as e:
                    logging.error(f"Alternative method failed: {e}")

                return []
        except Exception as e:
            logging.error("Error fetching commits: %s", e)
            return []

    @loader.loop(interval="check_interval", autostart=True)
    async def check_updates_loop(self):
        """Periodically check for new commits"""
        if not self.config["enabled"]:
            return

        owner = self.config["repo_owner"]
        repo_name = self.config["repo_name"]
        branch_name = str(branch) if branch else "beta"

        latest, commits = await self._missing_commits(owner, repo_name, branch_name)
        if not latest:
            return

        commit_sha = latest["sha"]
        if not commits:
            self.db.set("shizu.update_notifier", "last_commit_sha", commit_sha)
            return
        if commit_sha == self.db.get("shizu.update_notifier", "last_commit_sha", ""):
            return

        logging.info(f"Found {len(commits)} new commit(s), sending notification")
        try:
            await self._send_update_notification(commits)
            self.db.set("shizu.update_notifier", "last_commit_sha", commit_sha)
            logging.info(
                f"Notification sent and last_commit_sha updated to {commit_sha[:7]}"
            )
        except Exception as e:
            logging.exception("Error sending update notification: %s", e)

    async def _send_update_notification(self, commits: list):
        """Send notification about new update"""
        try:
            text = self.strings("update_available").format(
                commits_list=self._commits_list(commits, 800),
                count=len(commits),
                branch=utils.escape_html(str(branch)),
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

            await self.bot.bot.send_photo(
                self.me.id,
                InputFile("assets/update.jpg"),
                caption=text,
                reply_markup=markup,
            )

        except Exception as e:
            logging.exception("Error sending update notification: %s", e)

    async def inline__update(self, call: CallbackQuery):
        """Handle update button click"""
        try:
            await call.answer(self.strings("updating"))
            if not await asyncio.to_thread(self._pull):
                return await call.message.edit_caption(self.strings("already_updated"))
            with contextlib.suppress(Exception):
                await call.message.delete()
            msg = await self.bot.bot.send_message(
                call.message.chat.id, self.strings("update_complete")
            )
            self._restart_record(msg.chat.id, msg.message_id, "update", bot=True)
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
        repo_name = self.config["repo_name"]
        branch_name = str(branch) if branch else "beta"

        latest, commits = await self._missing_commits(owner, repo_name, branch_name)
        if not latest:
            return await utils.answer(message, self.strings("fetch_error"))

        if not commits:
            return await utils.answer(message, self.strings("latest_version"))

        text = self.strings("update_available_manual").format(
            commits_list=self._commits_list(commits, 3000),
            count=len(commits),
            branch=utils.escape_html(str(branch)),
        )
        await utils.answer(message, text, disable_web_page_preview=True)
