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

"""Command access rules shared by the Pyrogram and Telethon dispatchers"""

import time
from collections import defaultdict, deque

OWNER = 1 << 0
SUDO = 1 << 1
SUPPORT = 1 << 2
GROUP_OWNER = 1 << 3
GROUP_ADMIN_ADD_ADMINS = 1 << 4
GROUP_ADMIN_CHANGE_INFO = 1 << 5
GROUP_ADMIN_BAN_USERS = 1 << 6
GROUP_ADMIN_DELETE_MESSAGES = 1 << 7
GROUP_ADMIN_PIN_MESSAGES = 1 << 8
GROUP_ADMIN_INVITE_USERS = 1 << 9
GROUP_ADMIN = 1 << 10
GROUP_MEMBER = 1 << 11
PM = 1 << 12
EVERYONE = 1 << 13

GROUP_ADMIN_ANY = (
    GROUP_ADMIN_ADD_ADMINS
    | GROUP_ADMIN_CHANGE_INFO
    | GROUP_ADMIN_BAN_USERS
    | GROUP_ADMIN_DELETE_MESSAGES
    | GROUP_ADMIN_PIN_MESSAGES
    | GROUP_ADMIN_INVITE_USERS
    | GROUP_ADMIN
)
DEFAULT_PERMISSIONS = OWNER | SUDO
ALL = (1 << 14) - 1

FLAGS = {
    "owner": OWNER,
    "sudo": SUDO,
    "support": SUPPORT,
    "group_owner": GROUP_OWNER,
    "group_admin_add_admins": GROUP_ADMIN_ADD_ADMINS,
    "group_admin_change_info": GROUP_ADMIN_CHANGE_INFO,
    "group_admin_ban_users": GROUP_ADMIN_BAN_USERS,
    "group_admin_delete_messages": GROUP_ADMIN_DELETE_MESSAGES,
    "group_admin_pin_messages": GROUP_ADMIN_PIN_MESSAGES,
    "group_admin_invite_users": GROUP_ADMIN_INVITE_USERS,
    "group_admin": GROUP_ADMIN,
    "group_member": GROUP_MEMBER,
    "pm": PM,
    "everyone": EVERYONE,
    "unrestricted": EVERYONE,
    "inline_everyone": EVERYONE,
}

TELETHON_RIGHTS = {
    GROUP_ADMIN_ADD_ADMINS: "add_admins",
    GROUP_ADMIN_CHANGE_INFO: "change_info",
    GROUP_ADMIN_BAN_USERS: "ban_users",
    GROUP_ADMIN_DELETE_MESSAGES: "delete_messages",
    GROUP_ADMIN_PIN_MESSAGES: "pin_messages",
    GROUP_ADMIN_INVITE_USERS: "invite_users",
}
PYROGRAM_RIGHTS = {
    GROUP_ADMIN_ADD_ADMINS: "can_promote_members",
    GROUP_ADMIN_CHANGE_INFO: "can_change_info",
    GROUP_ADMIN_BAN_USERS: "can_restrict_members",
    GROUP_ADMIN_DELETE_MESSAGES: "can_delete_messages",
    GROUP_ADMIN_PIN_MESSAGES: "can_pin_messages",
    GROUP_ADMIN_INVITE_USERS: "can_invite_users",
}

RATELIMIT_CALLS = 3
RATELIMIT_WINDOW = 10


def mask_of(func) -> int:
    """Permission bitmask declared on a command, 0 when none was declared"""
    target = getattr(func, "__func__", func)
    mask = 0
    for flag in getattr(target, "security", ()) or ():
        mask |= FLAGS.get(flag, 0)
    return mask


class SecurityManager:
    """Decides whether a sender may run a command"""

    def __init__(self, db):
        self._db = db
        self._calls = defaultdict(deque)

    @property
    def _me(self) -> int:
        return self._db.get("shizu.me", "me", None)

    @property
    def _owner(self) -> list:
        owners = list(self._db.get("shizu.me", "owners", []))
        if not self._db.get("shizu.owner", "status", False):
            owners = []
        return [self._me, *owners] if self._me else owners

    @property
    def _sudo(self) -> list:
        users = {int(uid) for uid in self._db.get("shizu.permissions", "users", {})}
        users |= {int(uid) for uid in self._db.get("shizu.commandgroups", "user_groups", {})}
        return sorted(users)

    @property
    def _support(self) -> list:
        return []

    def has_command_access(self, user_id: int, command: str = None) -> bool:
        if user_id in self._owner:
            return True
        if not command:
            return False
        user = str(user_id)
        if command in self._db.get("shizu.permissions", "users", {}).get(user, []):
            return True
        groups = self._db.get("shizu.commandgroups", "groups", {})
        return any(
            command in groups.get(name, [])
            for name in self._db.get("shizu.commandgroups", "user_groups", {}).get(user, [])
        )

    def rate_limited(self, user_id: int, command: str) -> bool:
        now = time.monotonic()
        calls = self._calls[(user_id, command)]
        while calls and now - calls[0] > RATELIMIT_WINDOW:
            calls.popleft()
        if len(calls) >= RATELIMIT_CALLS:
            return True
        calls.append(now)
        return False

    async def check(self, message, func=None, command: str = None, client=None) -> bool:
        """True when the sender of `message` may run `func` (or a raw bitmask)"""
        info = _message_info(message)
        if info["out"] or (info["user_id"] and info["user_id"] == self._me):
            return True
        user_id = info["user_id"]
        if not user_id:
            return False

        mask = func if isinstance(func, int) else mask_of(func) if func else 0
        if not mask:
            return self.has_command_access(user_id, command)

        if mask & OWNER and user_id in self._owner:
            return True
        if mask & (SUDO | SUPPORT) and self.has_command_access(user_id, command):
            return True
        if mask & EVERYONE:
            return True
        if mask & PM and info["private"]:
            return True
        if info["private"]:
            return False
        if mask & GROUP_MEMBER:
            return True
        if mask & (GROUP_OWNER | GROUP_ADMIN_ANY):
            return await _group_rights_allow(
                mask, client or getattr(message, "_client", None), info["chat_id"], user_id
            )
        return False


def _message_info(message) -> dict:
    if hasattr(message, "sender_id") and hasattr(message, "is_private"):
        return {
            "out": bool(message.out),
            "user_id": message.sender_id,
            "private": bool(message.is_private),
            "chat_id": message.chat_id,
        }
    user = getattr(message, "from_user", None) or getattr(message, "sender_chat", None)
    chat = getattr(message, "chat", None)
    chat_type = getattr(getattr(chat, "type", None), "name", "")
    return {
        "out": bool(getattr(message, "outgoing", False)) or bool(getattr(user, "is_self", False)),
        "user_id": getattr(user, "id", None),
        "private": chat_type in ("PRIVATE", "BOT"),
        "chat_id": getattr(chat, "id", None),
    }


async def _group_rights_allow(mask: int, client, chat_id, user_id) -> bool:
    if client is None or chat_id is None:
        return False
    try:
        if hasattr(client, "get_permissions"):
            perms = await client.get_permissions(chat_id, user_id)
            if perms.is_creator:
                return True
            if not perms.is_admin:
                return False
            if mask & GROUP_ADMIN:
                return True
            return any(
                mask & bit and getattr(perms, right, False)
                for bit, right in TELETHON_RIGHTS.items()
            )
        member = await client.get_chat_member(chat_id, user_id)
        status = getattr(member.status, "name", "")
        if status == "OWNER":
            return True
        if status != "ADMINISTRATOR":
            return False
        if mask & GROUP_ADMIN:
            return True
        privileges = member.privileges
        return any(
            mask & bit and getattr(privileges, right, False)
            for bit, right in PYROGRAM_RIGHTS.items()
        )
    except Exception:
        return False
