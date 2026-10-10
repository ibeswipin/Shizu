"""Short-lived browser credentials, approved by the Telegram account owner."""

import secrets
import time


class PanelAuth:
    INVITE_TTL = 300
    SESSION_TTL = 8 * 60 * 60
    PENDING_COOKIE = "shizu_panel_pending"
    SESSION_COOKIE = "shizu_panel_session"

    def __init__(self, owner_id):
        self.owner_id = owner_id
        self.invites = {}
        self.pending = {}
        self.sessions = {}

    def prune(self):
        now = time.monotonic()
        for items in (self.invites, self.pending, self.sessions):
            for key, item in list(items.items()):
                if item["expires"] <= now:
                    del items[key]
                elif item.get("restore", {}).get("expires", float("inf")) <= now:
                    item.pop("restore", None)

    def _insert(self, items, token, item, limit):
        self.prune()
        while len(items) >= limit:
            del items[next(iter(items))]
        items[token] = item

    def invite(self):
        token = secrets.token_urlsafe(32)
        self._insert(
            self.invites, token, {"expires": time.monotonic() + self.INVITE_TTL}, 16
        )
        return token

    def begin(self, invite):
        self.prune()
        if not isinstance(invite, str) or invite not in self.invites:
            return None
        del self.invites[invite]
        token = secrets.token_urlsafe(32)
        item = {
            "id": secrets.token_hex(12),
            "code": f"{secrets.randbelow(1000000):06d}",
            "status": "pending",
            "expires": time.monotonic() + self.INVITE_TTL,
        }
        self._insert(self.pending, token, item, 16)
        return token, item

    def decide(self, challenge_id, owner_id, allow):
        self.prune()
        if owner_id != self.owner_id:
            return False
        for item in self.pending.values():
            if item["id"] == challenge_id and item["status"] == "pending":
                item["status"] = "approved" if allow else "denied"
                return True
        return False

    def status(self, token):
        self.prune()
        return self.pending.get(token)

    def complete(self, pending_token):
        item = self.status(pending_token)
        if not item or item["status"] != "approved":
            return None
        del self.pending[pending_token]
        token = secrets.token_urlsafe(32)
        session = {
            "csrf": secrets.token_urlsafe(32),
            "expires": time.monotonic() + self.SESSION_TTL,
        }
        self._insert(self.sessions, token, session, 8)
        return token, session

    def session(self, token):
        self.prune()
        return self.sessions.get(token)

    def clear(self):
        self.invites.clear()
        self.pending.clear()
        self.sessions.clear()
