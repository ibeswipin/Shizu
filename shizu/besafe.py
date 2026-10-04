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
import base64
import contextvars
import functools
import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from urllib.parse import unquote

from pyrogram import Client
from pyrogram.methods.messages.inline_session import get_session
from pyrogram.session import Session
from pyrogram.storage.sqlite_storage import SQLiteStorage
from pyrogram.storage.storage import Storage
from telethon import TelegramClient
from telethon.client.telegrambaseclient import TelegramBaseClient
from telethon.network.mtprotosender import MTProtoSender
from telethon.sessions.memory import MemorySession
from telethon.sessions.sqlite import SQLiteSession
from telethon.sessions.string import StringSession

from shizu.health import reporter

logger = logging.getLogger(__name__)


class BeSafe:
    """Defense in depth for plugins; arbitrary in-process Python is not isolated.

    Install before plugin execution. Core trust is captured at startup and
    plugin namespaces are registered before their top-level code executes.
    """

    _core = frozenset()
    _library_namespaces = frozenset()
    _namespaces = {}

    @classmethod
    def register_namespace(cls, module, *, trusted=False):
        namespace = module.__dict__
        name = module.__name__.rsplit(".", 1)[-1]
        cls._namespaces[id(namespace)] = (namespace, None if trusted else name)

    BLOCKED = {
        "ExportAuthorization",
        "ImportAuthorization",
        "ExportLoginToken",
        "ImportLoginToken",
        "AcceptLoginToken",
        "ResetAuthorizations",
        "ResetAuthorization",
        "ResetWebAuthorizations",
        "ResetWebAuthorization",
        "ChangeAuthorizationSettings",
        "DeleteAccount",
        "SendChangePhoneCode",
        "ChangePhone",
        "GetPasswordSettings",
        "UpdatePasswordSettings",
        "GetTmpPassword",
        "ResetPassword",
        "GetAuthorizations",
        "GetWebAuthorizations",
        "GetPassword",
        "RequestPasswordRecovery",
        "RecoverPassword",
        "CheckPassword",
        "SendCode",
        "ResendCode",
        "CancelCode",
        "SignIn",
        "SignUp",
        "LogOut",
        "BindTempAuthKey",
        "DestroyAuthKey",
    }
    origin = contextvars.ContextVar("shizu_besafe_origin", default=None)
    NOTICE = (
        "🛡 <b>Blocked</b> <code>{}</code> <b>from module</b> <code>{}</code>.\n"
        "Third-party modules may not call account takeover methods. "
        "If you did not expect this, remove the module."
    )

    class Forbidden(PermissionError):
        pass

    @classmethod
    def method_name(cls, query) -> str:
        return type(query).__name__.removesuffix("Request")

    @classmethod
    def culprit(cls, frame):
        core = cls._core
        inherited = cls.origin.get()
        if inherited:
            return inherited
        while frame:
            registered = cls._namespaces.get(id(frame.f_globals))
            if registered is not None:
                if registered[1]:
                    return registered[1]
                frame = frame.f_back
                continue
            name = frame.f_globals.get("__name__", "")
            if name.startswith("shizu.modules."):
                module = name.rsplit(".", 1)[1]
                if module.startswith("__lib_") or module not in core:
                    return module
            frame = frame.f_back
        return None

    @classmethod
    def sensitive_message(cls, message):
        for obj in (message, getattr(message, "message", None)):
            if obj is None:
                continue
            for field in ("chat_id", "sender_id", "user_id", "peer"):
                if getattr(obj, field, None) == 777000:
                    return True
            for field in (
                "chat",
                "from_user",
                "peer",
                "peer_id",
                "from_id",
                "from_peer",
                "to_peer",
            ):
                peer = getattr(obj, field, None)
                if (
                    getattr(peer, "id", None) == 777000
                    or getattr(peer, "user_id", None) == 777000
                ):
                    return True
        return False

    @classmethod
    def allow_handler(cls, handler, message):
        func = getattr(handler, "__func__", handler)
        name = getattr(func, "__module__", "")
        namespace = getattr(func, "__globals__", None)
        registered = cls._namespaces.get(id(namespace))
        external = (
            bool(registered[1])
            if registered is not None
            else (
                name.startswith("shizu.modules.")
                and (name.rsplit(".", 1)[1] not in cls._core or ".__lib_" in name)
            )
        )
        return not (external and cls.sensitive_message(message))

    async def protect_secrets(self, app, tapp=None):
        self._session_inodes = set()
        paths = (
            getattr(app.storage, "database", None),
            getattr(getattr(tapp, "session", None), "filename", None),
        )
        for path in paths:
            if path and path != ":memory:":
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                self._session_inodes.add((stat.st_dev, stat.st_ino))
        self._secrets = set()
        key = await app.storage.auth_key()
        if key:
            self._secrets.update(
                (
                    key,
                    key.hex().encode(),
                    base64.b64encode(key),
                    base64.urlsafe_b64encode(key),
                )
            )
        session = await app.storage.export_session_string()
        if session:
            self._secrets.add(session.encode())
        if tapp is not None:
            key = getattr(getattr(tapp.session, "auth_key", None), "key", None)
            if key:
                self._secrets.update(
                    (
                        key,
                        key.hex().encode(),
                        base64.b64encode(key),
                        base64.urlsafe_b64encode(key),
                    )
                )

            session = StringSession.save(tapp.session)
            if session:
                self._secrets.add(session.encode())

    def check_payload(self, value, seen=None):
        seen = set() if seen is None else seen
        if id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, str):
            value = value.encode()
        if isinstance(value, (bytes, bytearray, memoryview)):
            data = bytes(value)
            if any(secret in data for secret in getattr(self, "_secrets", ())):
                raise self.Forbidden(
                    "Third-party code may not transmit session credentials"
                )
        elif isinstance(value, dict):
            for item in value.values():
                self.check_payload(item, seen)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.check_payload(item, seen)
        elif type(value).__module__.startswith(("pyrogram.raw.", "telethon.tl.")):
            fields = getattr(value, "__dict__", None)
            if fields is not None:
                self.check_payload(fields, seen)
            for base in type(value).__mro__:
                slots = getattr(base, "__slots__", ())
                if isinstance(slots, str):
                    slots = (slots,)
                for field in slots:
                    self.check_payload(getattr(value, field, None), seen)

    @classmethod
    def contains_sensitive(cls, value, seen=None):
        seen = set() if seen is None else seen
        if id(value) in seen:
            return False
        seen.add(id(value))
        if cls.sensitive_message(value):
            return True
        if isinstance(value, (list, tuple)):
            return any(cls.contains_sensitive(item, seen) for item in value)
        for field in ("message", "messages", "update", "updates"):
            child = getattr(value, field, None)
            if child is not None and cls.contains_sensitive(child, seen):
                return True
        return False

    def _protect_handlers(self):
        original_add = Client.add_handler

        def add_handler(client, handler, *args, **kwargs):
            module = self.culprit(sys._getframe(1))
            if module:
                callback = handler.callback
                original_check = handler.check

                async def guarded_check(client, update):
                    if self.contains_sensitive(update):
                        return False
                    token = self.origin.set(module)
                    try:
                        return await original_check(client, update)
                    finally:
                        self.origin.reset(token)

                handler.check = guarded_check

                @functools.wraps(callback)
                async def guarded(*cb_args, **cb_kwargs):
                    if any(self.contains_sensitive(value) for value in cb_args):
                        return
                    token = self.origin.set(module)
                    try:
                        return await callback(*cb_args, **cb_kwargs)
                    finally:
                        self.origin.reset(token)

                handler.callback = guarded
            return original_add(client, handler, *args, **kwargs)

        Client.add_handler = add_handler
        original_add_tl = TelegramClient.add_event_handler
        original_remove_tl = TelegramClient.remove_event_handler
        callbacks = {}

        def add_event_handler(client, callback, *args, **kwargs):
            module = self.culprit(sys._getframe(1))
            if module:
                key = (client, callback)
                guarded = callbacks.get(key)
                if guarded is None:

                    @functools.wraps(callback)
                    async def guarded(event):
                        if self.contains_sensitive(event):
                            return
                        token = self.origin.set(module)
                        try:
                            return await callback(event)
                        finally:
                            self.origin.reset(token)

                    callbacks[key] = guarded
                callback = guarded
            offset = len(client._event_builders)
            result = original_add_tl(client, callback, *args, **kwargs)
            if module:
                for builder, _ in client._event_builders[offset:]:
                    original_filter = builder.filter

                    async def guarded_filter(event, _filter=original_filter):
                        if self.contains_sensitive(event):
                            return False
                        token = self.origin.set(module)
                        try:
                            result = _filter(event)
                            if asyncio.iscoroutine(result):
                                result = await result
                            return result
                        finally:
                            self.origin.reset(token)

                    builder.filter = guarded_filter
            return result

        def remove_event_handler(client, callback, *args, **kwargs):
            guarded = callbacks.get((client, callback), callback)
            result = original_remove_tl(client, guarded, *args, **kwargs)
            if not any(
                registered is guarded for registered, _ in client.list_event_handlers()
            ):
                callbacks.pop((client, callback), None)
            return result

        TelegramClient.add_event_handler = add_event_handler
        TelegramClient.remove_event_handler = remove_event_handler

    def _context(self, context=None):
        context = context.copy() if context is not None else contextvars.copy_context()
        module = self.culprit(sys._getframe(1))
        if module:
            context.run(self.origin.set, module)
        return context

    @classmethod
    def _internal_caller(cls, frame):
        while frame and frame.f_globals.get("__name__", "") == __name__:
            frame = frame.f_back
        if not frame or id(frame.f_globals) in cls._namespaces:
            return False
        return id(frame.f_globals) in cls._library_namespaces

    def _protect_attributes(self, cls, names):
        """Deny direct access, while library internals can maintain the connection."""
        original_get = cls.__getattribute__
        original_set = cls.__setattr__

        def check(name, frame):
            if (
                name in names
                and not self._internal_caller(frame)
                and self.culprit(frame)
            ):
                raise self.Forbidden(
                    "Third-party code may not access session credentials"
                )

        def guarded_get(obj, name):
            check(name, sys._getframe(1))
            return original_get(obj, name)

        def guarded_set(obj, name, value):
            check(name, sys._getframe(1))
            return original_set(obj, name, value)

        cls.__getattribute__ = guarded_get
        cls.__setattr__ = guarded_set
        # Also guard explicit Class.property.fget(instance) calls.
        for name in names:
            descriptor = cls.__dict__.get(name)
            if not isinstance(descriptor, property) or descriptor.fget is None:
                continue

            def getter(obj, _get=descriptor.fget, _name=name):
                check(_name, sys._getframe(1))
                return _get(obj)

            setter = descriptor.fset
            if setter is not None:

                def setter(obj, value, _set=setter, _name=name):
                    check(_name, sys._getframe(1))
                    return _set(obj, value)

            setattr(
                cls, name, property(getter, setter, descriptor.fdel, descriptor.__doc__)
            )

    def _protect_export(self, cls, name, *, internal=False):
        original = getattr(cls, name)

        def check():
            frame = sys._getframe(2)
            if self.culprit(frame) and not (internal and self._internal_caller(frame)):
                raise self.Forbidden(
                    "Third-party code may not access session credentials"
                )

        if asyncio.iscoroutinefunction(original):

            @functools.wraps(original)
            async def guarded(*args, **kwargs):
                check()
                return await original(*args, **kwargs)

        else:

            @functools.wraps(original)
            def guarded(*args, **kwargs):
                check()
                return original(*args, **kwargs)

        setattr(cls, name, guarded)

    def _protect_scheduling(self, loop):
        # Capture the caller before callbacks / worker threads lose their stack.
        for name in ("call_soon", "call_soon_threadsafe", "call_at"):
            original = getattr(loop, name)

            def guarded(*args, context=None, _original=original, _name=name):
                callback = args[1] if _name == "call_at" else args[0]
                owner = getattr(callback, "__self__", None)
                # Task wakeups carry the waiting task's own context. Do not
                # taint an unrelated caller when a module task completes.
                if isinstance(owner, (asyncio.Task, asyncio.Future)):
                    return _original(*args, context=context)
                return _original(*args, context=self._context(context))

            setattr(loop, name, guarded)
        original_executor = loop.run_in_executor

        def executor(executor, func, *args):
            context = self._context()
            if context.get(self.origin) is None:
                return original_executor(executor, func, *args)
            if isinstance(executor, ProcessPoolExecutor):
                raise self.Forbidden(
                    "Module provenance cannot be preserved in a process pool"
                )
            return original_executor(executor, context.run, func, *args)

        loop.run_in_executor = executor

    def _protect_session_api(self):

        self._protect_attributes(
            SQLiteStorage,
            {
                "auth_key",
                "session_string",
                "conn",
                "_conn",
                "_get",
                "_set",
                "_accessor",
            },
        )
        self._protect_attributes(Session, {"auth_key"})
        self._protect_attributes(
            MemorySession, {"auth_key", "_auth_key", "tmp_auth_key", "_tmp_auth_key"}
        )
        self._protect_attributes(SQLiteSession, {"_conn", "_cursor"})
        self._protect_attributes(MTProtoSender, {"auth_key"})
        for name in ("auth_key", "_get", "_set", "_accessor"):
            self._protect_export(SQLiteStorage, name, internal=True)
        self._protect_export(Storage, "export_session_string")
        self._protect_export(StringSession, "save")

    def install(self):
        """Install once, before executing third-party code. Not a Python sandbox."""
        if getattr(self, "_installed", False):
            return
        self._installed = True
        manager = getattr(sys.modules.get("shizu.loader"), "_manager", None)
        type(self)._core = frozenset(manager.cmodules) if manager else frozenset()
        loop = asyncio.get_running_loop()
        previous = loop.get_task_factory()

        def factory(loop, coro, context=None):
            context = self._context(context)
            if previous:
                return previous(loop, coro, context=context)
            return asyncio.Task(coro, loop=loop, context=context)

        loop.set_task_factory(factory)
        self._protect_scheduling(loop)
        self._protect_session_api()
        self._protect_handlers()

        def audit(event, args):
            if event not in ("open", "sqlite3.connect") or not args:
                return
            if not self.culprit(sys._getframe(1)):
                return
            path = args[0]
            if not isinstance(path, (str, bytes, os.PathLike)):
                return
            path = unquote(os.fsdecode(path).split("?", 1)[0])
            if path.startswith("file:"):
                path = path[5:]
            paths = (path.lower(), os.path.realpath(path).lower())
            protected = any(".session" in name for name in paths)
            if not protected:
                try:
                    stat = os.stat(path)
                except OSError:
                    pass
                else:
                    protected = (stat.st_dev, stat.st_ino) in getattr(
                        self, "_session_inodes", ()
                    )
            if protected:
                raise self.Forbidden("Third-party code may not open session storage")

        sys.addaudithook(audit)

        self._media_codes = {
            Client.get_session.__code__,
            get_session.__code__,
            TelegramBaseClient._create_exported_sender.__code__,
        }

        self.attach(Session, "invoke", 1)
        self.attach(Session, "send", 1)
        self.attach(MTProtoSender, "send", 1)
        type(self)._library_namespaces = frozenset(
            id(vars(module))
            for name, module in tuple(sys.modules.items())
            if module is not None and name.startswith(("pyrogram.", "telethon."))
        )

    def check(self, query, frame) -> None:
        queries = list(query) if isinstance(query, (list, tuple)) else [query]
        seen = set()
        module = self.culprit(frame)
        if not module:
            return
        while queries:
            item = queries.pop()
            if id(item) in seen:
                continue
            seen.add(id(item))
            inner = getattr(item, "query", None)
            if inner is not None:
                queries.append(inner)
            method = self.method_name(item)
            self.check_payload(item)
            if module and self.sensitive_message(item):
                raise self.Forbidden("Third-party code may not access login-code chat")
            internal_media = False
            if method in ("ExportAuthorization", "ImportAuthorization"):
                current = frame
                while current:
                    if current.f_code in getattr(self, "_media_codes", ()):
                        internal_media = True
                        break
                    current = current.f_back
            if method in self.BLOCKED and module and not internal_media:
                logger.warning("BeSafe blocked %s from %s", method, module)
                reporter.problem(
                    f"besafe_{module}_{method}", self.NOTICE.format(method, module)
                )
                raise self.Forbidden(f"{method} is not allowed for third-party modules")
        return

    def _filter_result(self, result):
        if isinstance(result, (list, tuple)):
            return type(result)(self._filter_result(item) for item in result)
        if not isinstance(result, asyncio.Future):
            if self.contains_sensitive(result):
                raise self.Forbidden(
                    "Third-party code may not read login-code messages"
                )
            return result
        filtered = asyncio.get_running_loop().create_future()

        def completed(source):
            if filtered.cancelled():
                if not source.cancelled():
                    source.exception()
                return
            if source.cancelled():
                filtered.cancel()
                return
            try:
                value = source.result()
                if self.contains_sensitive(value):
                    raise self.Forbidden(
                        "Third-party code may not read login-code messages"
                    )
            except Exception as error:
                filtered.set_exception(error)
            else:
                filtered.set_result(value)

        def cancelled(future):
            if future.cancelled() and not result.done():
                result.cancel()

        result.add_done_callback(completed)
        filtered.add_done_callback(cancelled)
        return filtered

    def attach(self, client, method: str, query_index: int) -> None:
        original = getattr(client, method)

        def check(args, kwargs):
            query = (
                args[query_index]
                if len(args) > query_index
                else kwargs.get("query", kwargs.get("request", kwargs.get("data")))
            )
            if query is not None:
                self.check(query, sys._getframe(2))

        if asyncio.iscoroutinefunction(original):

            @functools.wraps(original)
            async def guarded(*args, **kwargs):
                check(args, kwargs)
                module = self.culprit(sys._getframe(1))
                result = await original(*args, **kwargs)
                if module and self.contains_sensitive(result):
                    raise self.Forbidden(
                        "Third-party code may not read login-code messages"
                    )
                return result

        else:

            @functools.wraps(original)
            def guarded(*args, **kwargs):
                check(args, kwargs)
                module = self.culprit(sys._getframe(1))
                result = original(*args, **kwargs)
                return self._filter_result(result) if module else result

        setattr(client, method, guarded)
