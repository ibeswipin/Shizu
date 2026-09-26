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
import json
import os
import re
import secrets
import shutil
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from aiohttp import web
from pyrogram import Client, types

from shizu import loader, utils


def web_page(name: str) -> str:
    path = os.path.join(os.path.dirname(utils.get_base_dir()), "web-resources", name)
    with open(path, encoding="utf-8") as f:
        return f.read()


@dataclass(frozen=True)
class ServiceRef:
    name: str
    user: bool = False

    NAME_RE = re.compile(r"^[A-Za-z0-9@._:-]+$")

    @classmethod
    def build(cls, raw: str, user: bool = False) -> Optional["ServiceRef"]:
        raw = raw.strip()
        if not raw or not cls.NAME_RE.match(raw) or raw.startswith("-"):
            return None
        if not re.search(r"\.(service|timer|socket|target|path|mount)$", raw):
            raw += ".service"
        return cls(raw, user)

    @property
    def short(self) -> str:
        return self.name[:-8] if self.name.endswith(".service") else self.name

    @property
    def key(self) -> str:
        return ("user:" if self.user else "") + self.name

    @classmethod
    def from_key(cls, key: str) -> "ServiceRef":
        return cls(key[5:], True) if key.startswith("user:") else cls(key, False)


@dataclass
class ServiceInfo:
    ref: ServiceRef
    props: Dict[str, str] = field(default_factory=dict)

    def _int(self, key: str) -> Optional[int]:
        v = self.props.get(key, "")
        if not v.isdigit() or int(v) >= 2**63:  # "[not set]" / UINT64_MAX
            return None
        return int(v)

    @property
    def exists(self) -> bool:
        return self.props.get("LoadState") not in (None, "", "not-found")

    @property
    def active(self) -> str:
        return self.props.get("ActiveState", "unknown")

    @property
    def sub(self) -> str:
        return self.props.get("SubState", "")

    @property
    def enabled(self) -> str:
        return self.props.get("UnitFileState", "") or "—"

    @property
    def emoji(self) -> str:
        return {
            "active": "🟢",
            "reloading": "🔵",
            "activating": "🟡",
            "deactivating": "🟠",
            "failed": "🔴",
            "inactive": "⚪️",
        }.get(self.active, "⚫️")

    @property
    def pid(self) -> Optional[int]:
        return self._int("MainPID") or None

    @property
    def uptime(self) -> Optional[float]:
        mono = self._int("ActiveEnterTimestampMonotonic")
        if self.active != "active" or not mono:
            return None
        return max(0.0, time.monotonic() - mono / 1e6)

    @property
    def memory(self) -> Optional[int]:
        return self._int("MemoryCurrent")

    @property
    def cpu_seconds(self) -> Optional[float]:
        ns = self._int("CPUUsageNSec")
        return ns / 1e9 if ns is not None else None

    @property
    def restarts(self) -> Optional[int]:
        return self._int("NRestarts")

    @property
    def tasks(self) -> Optional[int]:
        return self._int("TasksCurrent")

    @property
    def can_reload(self) -> bool:
        return self.props.get("CanReload") == "yes"

    def is_shizu(self) -> bool:
        """This service runs the userbot itself — stopping it kills Shizu"""
        return self.pid is not None and self.pid in (os.getpid(), os.getppid())


class CommandResult:
    def __init__(self, code: int, out: str, err: str):
        self.code, self.out, self.err = code, out, err

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def needs_password(self) -> bool:
        return (
            "password is required" in self.err or "a terminal is required" in self.err
        )

    @property
    def text(self) -> str:
        return (self.err or self.out).strip()


class SystemdClient:
    PROPS = (
        "Id,Description,LoadState,ActiveState,SubState,UnitFileState,MainPID,"
        "ActiveEnterTimestampMonotonic,MemoryCurrent,CPUUsageNSec,NRestarts,TasksCurrent,"
        "FragmentPath,Result,CanReload,ExecMainStatus"
    )
    ACTIONS = (
        "start",
        "stop",
        "restart",
        "reload",
        "enable",
        "disable",
        "reset-failed",
    )

    def __init__(self, use_sudo: bool):
        self._sudo = use_sudo and os.geteuid() != 0 and shutil.which("sudo") is not None

    async def _run(
        self, *args: str, privileged: bool = False, timeout: int = 30
    ) -> CommandResult:
        cmd = (["sudo", "-n"] if privileged and self._sudo else []) + list(args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "SYSTEMD_COLORS": "0", "SYSTEMD_PAGER": ""},
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return CommandResult(124, "", f"timeout {timeout}s")
        return CommandResult(
            proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")
        )

    @staticmethod
    def _scope(ref: ServiceRef) -> List[str]:
        return ["--user"] if ref.user else []

    async def info(self, ref: ServiceRef) -> ServiceInfo:
        r = await self._run(
            "systemctl",
            *self._scope(ref),
            "show",
            ref.name,
            f"--property={self.PROPS}",
            "--no-pager",
        )
        props = dict(line.split("=", 1) for line in r.out.splitlines() if "=" in line)
        return ServiceInfo(ref, props)

    async def action(self, ref: ServiceRef, verb: str) -> CommandResult:
        if verb not in self.ACTIONS:
            return CommandResult(2, "", f"unknown action {verb}")
        return await self._run(
            "systemctl",
            *self._scope(ref),
            verb,
            ref.name,
            "--no-pager",
            privileged=not ref.user,
        )

    async def logs(
        self, ref: ServiceRef, lines: int = 40, errors_only: bool = False
    ) -> CommandResult:
        args = [
            "journalctl",
            *self._scope(ref),
            "-u",
            ref.name,
            "-n",
            str(lines),
            "--no-pager",
            "-o",
            "short-iso",
        ]
        if errors_only:
            args += ["-p", "warning"]
        return await self._run(*args, privileged=not ref.user)

    async def cat(self, ref: ServiceRef) -> CommandResult:
        return await self._run(
            "systemctl", *self._scope(ref), "cat", ref.name, "--no-pager"
        )

    def follow_cmd(self, ref: ServiceRef, backlog: int = 200) -> List[str]:
        base = [
            "journalctl",
            *self._scope(ref),
            "-u",
            ref.name,
            "-f",
            "-n",
            str(backlog),
            "-o",
            "json",
            "--no-pager",
        ]
        return (["sudo", "-n"] if self._sudo and not ref.user else []) + base


class LiveLogServer:
    def __init__(self, client: SystemdClient):
        self._client = client
        self._sessions: Dict[str, Tuple[ServiceRef, float]] = {}
        self._runner: Optional[web.AppRunner] = None
        self.port: Optional[int] = None

    @property
    def running(self) -> bool:
        return self._runner is not None

    async def start(self) -> int:
        if self._runner:
            return self.port
        app = web.Application()
        app.router.add_get("/{token}/", self._page)
        app.router.add_get("/{token}/stream", self._stream)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        self.port = self._runner.addresses[0][1]
        return self.port

    async def stop(self):
        self._sessions.clear()
        if self._runner:
            await self._runner.cleanup()
        self._runner, self.port = None, None

    def open_session(self, ref: ServiceRef, ttl_min: int) -> str:
        token = secrets.token_urlsafe(24)
        self._sessions[token] = (ref, time.time() + ttl_min * 60)
        return token

    def close_sessions(self, ref: Optional[ServiceRef] = None):
        for t, (r, _) in list(self._sessions.items()):
            if ref is None or r == ref:
                del self._sessions[t]

    def purge_expired(self) -> int:
        now = time.time()
        for t, (_, exp) in list(self._sessions.items()):
            if exp < now:
                del self._sessions[t]
        return len(self._sessions)

    def _session(self, request: web.Request) -> ServiceRef:
        item = self._sessions.get(request.match_info["token"])
        if not item or item[1] < time.time():
            raise web.HTTPNotFound()
        return item[0]

    async def _page(self, request: web.Request) -> web.Response:
        ref = self._session(request)
        page = web_page("systemd_logs.html").replace(
            "__NAME__", utils.escape_html(ref.name)
        )
        return web.Response(text=page, content_type="text/html")

    async def _stream(self, request: web.Request) -> web.StreamResponse:
        ref = self._session(request)
        token = request.match_info["token"]
        resp = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            }
        )
        await resp.prepare(request)
        proc = await asyncio.create_subprocess_exec(
            *self._client.follow_cmd(ref),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            while token in self._sessions:
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), 15)
                except asyncio.TimeoutError:
                    await resp.write(b": ping\n\n")
                    continue
                if not line:
                    break
                event = self._event(line)
                if event:
                    await resp.write(
                        f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
                    )
        except ConnectionResetError:
            pass
        finally:
            if proc.returncode is None:
                proc.kill()
        return resp

    @staticmethod
    def _event(line: bytes) -> Optional[dict]:
        try:
            e = json.loads(line)
        except ValueError:
            return None
        msg = e.get("MESSAGE", "")
        if isinstance(msg, list):
            msg = bytes(msg).decode(errors="replace")
        ts = int(e.get("__REALTIME_TIMESTAMP", 0)) / 1e6
        return {
            "t": time.strftime("%d.%m %H:%M:%S", time.localtime(ts)),
            "p": int(e.get("PRIORITY", 6)),
            "m": str(msg),
        }


class TunnelManager:
    """Public HTTPS address for a local port: cloudflared quick tunnel or localhost.run (ssh)"""

    def __init__(self):
        self._proc: Optional[asyncio.subprocess.Process] = None
        self.url: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def open(self, port: int, provider: str = "auto") -> str:
        if self.running and self.url:
            return self.url
        use_cf = provider == "cloudflared" or (
            provider == "auto" and shutil.which("cloudflared")
        )
        if use_cf:
            cmd = [
                "cloudflared",
                "tunnel",
                "--no-autoupdate",
                "--url",
                f"http://127.0.0.1:{port}",
            ]
            pattern = re.compile(r"(https://[a-z0-9-]+\.trycloudflare\.com)")
        else:
            cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ServerAliveInterval=30",
                "-R",
                f"80:127.0.0.1:{port}",
                "nokey@localhost.run",
            ]
            pattern = re.compile(r"(https://[^\s,]+)")
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self.url = await asyncio.wait_for(
            self._read_url(pattern, need_tunneled=not use_cf), 30
        )
        return self.url

    async def _read_url(self, pattern: re.Pattern, need_tunneled: bool) -> str:
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                raise RuntimeError("tunnel exited without giving an address")
            text = line.decode(errors="replace")
            if need_tunneled and "tunneled" not in text:
                continue
            if m := pattern.search(text):
                asyncio.ensure_future(self._drain())
                return m[1]

    async def _drain(self):
        while self.running and await self._proc.stdout.readline():
            pass

    async def close(self):
        if self.running:
            self._proc.terminate()
        self._proc, self.url = None, None


class ServiceFormatter:
    def __init__(self, strings: Callable[[str], str]):
        self.s = strings

    def duration(self, sec: Optional[float]) -> str:
        if sec is None:
            return "—"
        sec = int(sec)
        d, h, m = sec // 86400, sec % 86400 // 3600, sec % 3600 // 60
        if d:
            return self.s("dur_days").format(d, h)
        if h:
            return self.s("dur_hours").format(h, m)
        return self.s("dur_minutes").format(m, sec % 60)

    def size(self, b: Optional[int]) -> str:
        if b is None:
            return "—"
        units = self.s("size_units").split(",")
        for unit in units[:-1]:
            if b < 1024:
                return f"{b:.0f} {unit}" if unit == units[0] else f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} {units[-1]}"

    def list_line(self, s: ServiceInfo) -> str:
        tail = (
            f" · {self.duration(s.uptime)} · {self.size(s.memory)}"
            if s.active == "active"
            else ""
        )
        user = " <i>(user)</i>" if s.ref.user else ""
        return f"{s.emoji} <b>{utils.escape_html(s.ref.short)}</b>{user} — {s.active}/{s.sub}{tail}"

    def card(self, s: ServiceInfo, note: str = "") -> str:
        e = utils.escape_html
        na = lambda v: v if v is not None else "—"
        lines = [
            f"{s.emoji} <b>{e(s.ref.name)}</b>{' <i>(user)</i>' if s.ref.user else ''}",
            *(
                [f"<i>{e(s.props['Description'])}</i>"]
                if s.props.get("Description")
                else []
            ),
            "",
            self.s("card_state").format(s.active, s.sub)
            + (f" · {self.duration(s.uptime)}" if s.uptime else ""),
            self.s("card_autostart").format(e(s.enabled)),
            self.s("card_stats").format(
                s.pid or "—",
                self.size(s.memory),
                self.duration(s.cpu_seconds),
                na(s.tasks),
            ),
            self.s("card_restarts").format(na(s.restarts))
            + (
                self.s("card_result").format(e(s.props.get("Result")))
                if s.props.get("Result") not in (None, "success")
                else ""
            ),
            self.s("card_file").format(e(s.props.get("FragmentPath") or "—")),
        ]
        if s.is_shizu():
            lines.append("\n" + self.s("card_shizu"))
        if note:
            lines += ["", note]
        return "\n".join(lines)

    def code_block(self, title: str, text: str, limit: int = 3300) -> str:
        text = text.strip() or self.s("empty")
        if len(text) > limit:
            text = "…" + text[-limit:]
        return f"{title}\n<pre>{utils.escape_html(text)}</pre>"


@loader.module(name="ShizuSystemd", author="shizu")
class SystemdMod(loader.Module):
    """Manage systemd services: status, start/stop/restart, logs and live logs in the browser"""

    strings = {}

    CONFIRM = {"stop", "disable"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            "USE_SUDO",
            True,
            lambda m: self.strings("cfg_sudo"),
            "WATCH",
            True,
            lambda m: self.strings("cfg_watch"),
            "LIVE_TTL",
            15,
            lambda m: self.strings("cfg_ttl"),
            "TUNNEL",
            "auto",
            lambda m: self.strings("cfg_tunnel"),
        )
        self.live: Optional[LiveLogServer] = None
        self.tunnel = TunnelManager()

    @property
    def client(self) -> SystemdClient:
        return SystemdClient(bool(self.config["USE_SUDO"]))

    @property
    def fmt(self) -> ServiceFormatter:
        return ServiceFormatter(self.strings)

    def _refs(self) -> List[ServiceRef]:
        return [ServiceRef.from_key(k) for k in self.db.get(self.name, "services", [])]

    def _save(self, refs: List[ServiceRef]):
        self.db.set(self.name, "services", [r.key for r in refs])

    @loader.command()
    async def sdadd(self, app: Client, message: types.Message):
        """[--user] <service> — add a service to the list"""
        args = (message.get_args_raw() or "").split()
        user = "--user" in args
        names = [a for a in args if a != "--user"]
        if not names:
            return await message.answer(self.strings("add_usage"))
        refs, report = self._refs(), []
        for raw in names:
            ref = ServiceRef.build(raw, user)
            if not ref:
                report.append(self.strings("bad_name").format(utils.escape_html(raw)))
                continue
            info = await self.client.info(ref)
            if not info.exists:
                report.append(self.strings("not_found").format(ref.name))
            elif ref in refs:
                report.append(self.strings("already").format(ref.name))
            else:
                refs.append(ref)
                report.append(f"✅ {self.fmt.list_line(info)}")
        self._save(refs)
        await message.answer("\n".join(report))

    @loader.command()
    async def sddel(self, app: Client, message: types.Message):
        """<service> — remove a service from the list (the service itself is untouched)"""
        raw = message.get_args_raw() or ""
        refs = self._refs()
        keep = [r for r in refs if raw not in (r.name, r.short, r.key)]
        self._save(keep)
        await message.answer(
            self.strings("removed" if len(keep) < len(refs) else "not_in_list")
        )

    @loader.command()
    async def systemd(self, app: Client, message: types.Message):
        """Service list and control panel"""
        text, markup = await self._list_view()
        await message.answer(text, reply_markup=markup)

    @loader.command()
    async def sdlogs(self, app: Client, message: types.Message):
        """<service> [lines] — last journal lines"""
        args = (message.get_args_raw() or "").split()
        ref = self._find(args[0]) if args else None
        if not ref:
            return await message.answer(self.strings("logs_usage"))
        n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 40
        r = await self.client.logs(ref, n)
        await message.answer(
            self.fmt.code_block(f"📜 <b>{ref.name}</b>", self._err_hint(r) or r.out)
        )

    async def systemd_inline_handler(self, app: Client, inline_query):
        """Service list and control panel"""
        text, markup = await self._list_view()
        uid = utils.rand(30)
        self.bot._forms[uid] = {
            "type": "form",
            "text": text,
            "buttons": markup,
            "force_me": True,
            "always_allow": [],
            "chat": None,
            "message_id": None,
            "uid": uid,
        }
        await inline_query.answer(
            [
                InlineQueryResultArticle(
                    id=utils.random_id(),
                    title="systemd",
                    description=self.strings("inline_desc"),
                    input_message_content=InputTextMessageContent(
                        text, "HTML", disable_web_page_preview=True
                    ),
                    reply_markup=self.bot._generate_markup(uid, for_inline_query=True),
                )
            ],
            cache_time=0,
        )

    async def _list_view(self) -> Tuple[str, list]:
        refresh = [{"text": self.strings("btn_refresh"), "callback": self.inline__list}]
        refs = self._refs()
        if not refs:
            return self.strings("list_empty"), [refresh]
        infos = await asyncio.gather(*(self.client.info(r) for r in refs))
        up = sum(i.active == "active" for i in infos)
        failed = sum(i.active == "failed" for i in infos)
        head = self.strings("list_head").format(up, len(infos))
        if failed:
            head += self.strings("list_failed").format(failed)
        text = head + "\n\n" + "\n".join(self.fmt.list_line(i) for i in infos)
        buttons = [
            {
                "text": f"{i.emoji} {i.ref.short}",
                "callback": self.inline__service,
                "args": (i.ref.key,),
            }
            for i in infos
        ]
        rows = [buttons[x : x + 2] for x in range(0, len(buttons), 2)]
        rows.append(refresh)
        return text, rows

    def _service_buttons(self, info: ServiceInfo) -> list:
        k = info.ref.key
        s = self.strings
        b = lambda text, action: {
            "text": s(text),
            "callback": self.inline__action,
            "args": (k, action),
        }
        running = info.active in ("active", "activating", "reloading")
        rows = [
            [
                b("btn_stop", "stop") if running else b("btn_start", "start"),
                b("btn_restart", "restart"),
            ]
        ]
        extra = []
        if info.can_reload and running:
            extra.append(b("btn_reload", "reload"))
        extra.append(
            b("btn_disable", "disable")
            if info.enabled == "enabled"
            else b("btn_enable", "enable")
        )
        if info.active == "failed":
            extra.append(b("btn_reset", "reset-failed"))
        rows.append(extra)
        rows.append(
            [
                {
                    "text": s("btn_logs"),
                    "callback": self.inline__logs,
                    "args": (k, False),
                },
                {
                    "text": s("btn_errors"),
                    "callback": self.inline__logs,
                    "args": (k, True),
                },
                {"text": s("btn_unit"), "callback": self.inline__unit, "args": (k,)},
            ]
        )
        rows.append(
            [{"text": s("btn_live"), "callback": self.inline__live, "args": (k,)}]
        )
        rows.append(
            [
                {
                    "text": s("btn_refresh"),
                    "callback": self.inline__service,
                    "args": (k,),
                },
                {"text": s("btn_back_list"), "callback": self.inline__list},
            ]
        )
        return rows

    def _back(self, key: str) -> dict:
        return {
            "text": self.strings("btn_back"),
            "callback": self.inline__service,
            "args": (key,),
        }

    async def inline__list(self, call):
        text, markup = await self._list_view()
        await call.edit(text, reply_markup=markup)

    async def inline__service(self, call, key: str, note: str = ""):
        info = await self.client.info(ServiceRef.from_key(key))
        await call.edit(
            self.fmt.card(info, note), reply_markup=self._service_buttons(info)
        )

    async def inline__action(
        self, call, key: str, action: str, confirmed: bool = False
    ):
        ref = ServiceRef.from_key(key)
        info = await self.client.info(ref)
        if (
            action in self.CONFIRM or (info.is_shizu() and action == "restart")
        ) and not confirmed:
            return await call.edit(
                self.fmt.card(info, self.strings("confirm").format(action)),
                reply_markup=[
                    [
                        {
                            "text": self.strings("btn_yes").format(action),
                            "callback": self.inline__action,
                            "args": (key, action, True),
                        },
                        {
                            "text": self.strings("btn_cancel"),
                            "callback": self.inline__service,
                            "args": (key,),
                        },
                    ]
                ],
            )
        if info.is_shizu() and action in ("restart", "stop"):
            await call.edit(self.strings("shizu_going").format(action, ref.name))
        r = await self.client.action(ref, action)
        await asyncio.sleep(1.2)
        if r.ok:
            note = self.strings("act_" + action.replace("-", "_"))
        else:
            note = self.strings("action_error").format(
                utils.escape_html(self._err_hint(r) or r.text)[:600]
            )
        await self.inline__service(call, key, note)

    async def inline__logs(self, call, key: str, errors_only: bool):
        ref = ServiceRef.from_key(key)
        r = await self.client.logs(ref, 60 if errors_only else 30, errors_only)
        title = self.strings(
            "logs_errors_title" if errors_only else "logs_recent_title"
        ).format(ref.short)
        await call.edit(
            self.fmt.code_block(title, self._err_hint(r) or r.out),
            reply_markup=[
                [
                    {
                        "text": self.strings("btn_again"),
                        "callback": self.inline__logs,
                        "args": (key, errors_only),
                    },
                    self._back(key),
                ]
            ],
        )

    async def inline__unit(self, call, key: str):
        ref = ServiceRef.from_key(key)
        r = await self.client.cat(ref)
        await call.edit(
            self.fmt.code_block(f"📄 <b>{ref.name}</b>", r.out or r.text),
            reply_markup=[[self._back(key)]],
        )

    async def inline__live(self, call, key: str):
        ref = ServiceRef.from_key(key)
        await call.edit(self.strings("live_opening").format(ref.short))
        try:
            if not self.live:
                self.live = LiveLogServer(self.client)
            port = await self.live.start()
            url = await self.tunnel.open(port, str(self.config["TUNNEL"]))
        except Exception as e:
            return await self.inline__service(
                call, key, self.strings("live_failed").format(utils.escape_html(str(e)))
            )
        ttl = int(self.config["LIVE_TTL"] or 15)
        token = self.live.open_session(ref, ttl)
        link = f"{url.rstrip('/')}/{token}/"
        await call.edit(
            self.strings("live_ready").format(ref.short, ttl),
            reply_markup=[
                [{"text": self.strings("btn_open_live"), "url": link}],
                [
                    {
                        "text": self.strings("btn_close_live"),
                        "callback": self.inline__live_close,
                        "args": (key,),
                    },
                    self._back(key),
                ],
            ],
        )

    async def inline__live_close(self, call, key: str):
        if self.live:
            self.live.close_sessions(ServiceRef.from_key(key))
            if not self.live.purge_expired():
                await self._shutdown_live()
        await self.inline__service(call, key, self.strings("live_closed"))

    async def _shutdown_live(self):
        await self.tunnel.close()
        if self.live:
            await self.live.stop()

    @loader.loop(interval=30, autostart=True)
    async def watchdog(self):
        if self.live and self.live.running and not self.live.purge_expired():
            await self._shutdown_live()
        if not self.config["WATCH"]:
            return
        last: Dict[str, str] = self.db.get(self.name, "last_state", {})
        for ref in self._refs():
            info = await self.client.info(ref)
            prev, now = last.get(ref.key), info.active
            last[ref.key] = now
            if (
                prev is None
                or prev == now
                or now in ("activating", "deactivating", "reloading")
            ):
                continue
            if now == "failed" or (prev == "active" and now == "inactive"):
                r = await self.client.logs(ref, 15)
                text = self.fmt.code_block(
                    self.strings("watch_down").format(ref.name, prev, now), r.out
                )
                await self._notify(text + "\n\n" + self.strings("watch_down_hint"))
            elif now == "active":
                await self._notify(self.strings("watch_up").format(ref.name))
        self.db.set(self.name, "last_state", last)

    async def _notify(self, text: str):
        try:
            await self.inline_bot.send_message(self.tg_id, text, parse_mode="HTML")
        except Exception:
            pass

    def _find(self, raw: str) -> Optional[ServiceRef]:
        return next((r for r in self._refs() if raw in (r.name, r.short, r.key)), None)

    def _err_hint(self, r: CommandResult) -> str:
        if r.needs_password:
            return self.strings("sudo_hint").format(os.environ.get("USER") or "shizu")
        if not r.ok and not r.out:
            return r.text
        return ""
