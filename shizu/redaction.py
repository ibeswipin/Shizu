"""Shared credential masking for diagnostic output, independent of the database."""

import html
import re
import threading
import traceback
from collections.abc import Mapping


class SecretRedactor:
    MASK = "[REDACTED]"
    _secrets = set()
    _lock = threading.RLock()
    _key = re.compile(
        r"(?:token|password|passwd|secret|api_hash|auth_key|session_string|"
        r"encryption_key|phone_code(?:_hash)?)",
        re.I,
    )
    _bot = re.compile(r"\b\d{5,}:[A-Za-z0-9_-]{30,}")
    _session = re.compile(r"(?<![\w-])[A-Za-z0-9_-]{200,}={0,2}(?![\w-])")
    _labelled = re.compile(
        r"(?P<label>(?:[\"']|&quot;|&#(?:x27|39);)?(?:[\w.-]*(?:token|password|passwd|secret|api_hash|"
        r"auth_key|session_string|encryption_key|phone_code(?:_hash)?))"
        r"(?:[\"']|&quot;|&#(?:x27|39);)?\s*[:=]\s*)"
        r"(?:\[REDACTED\]|&quot;[^\n]*?&quot;|&#(?:x27|39);[^\n]*?&#(?:x27|39);|"
        r"\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|"
        r"(?:&(?:\w+|#\d+|#x[\da-f]+);|[^\s,;<>}\]\"'])+)",
        re.I,
    )

    @classmethod
    def remember(cls, value) -> None:
        if isinstance(value, bytes):
            cls.remember(value.hex())
            cls.remember(repr(value))
            try:
                value = value.decode("utf-8")
            except UnicodeError:
                return
        if isinstance(value, str) and len(value) >= 8:
            with cls._lock:
                cls._secrets.add(value)

    @classmethod
    def remember_mapping(cls, value) -> None:
        pending, seen = [value], set()
        while pending:
            item = pending.pop()
            if not isinstance(item, (Mapping, list, tuple)) or id(item) in seen:
                continue
            seen.add(id(item))
            if isinstance(item, Mapping):
                for key, child in item.items():
                    if cls._key.search(str(key)):
                        cls.remember(child)
                    pending.append(child)
            else:
                pending.extend(item)

    @classmethod
    def text(cls, value) -> str:
        text = str(value)
        with cls._lock:
            secrets = sorted(cls._secrets, key=len, reverse=True)
        for secret in secrets:
            for variant in (secret, html.escape(secret)):
                text = text.replace(variant, cls.MASK)
        text = cls._bot.sub(cls.MASK, text)
        text = cls._session.sub(cls.MASK, text)
        return cls._labelled.sub(lambda m: m["label"] + cls.MASK, text)

    @classmethod
    def loguru_record(cls, record) -> None:
        text = record["message"]
        if exception := record["exception"]:
            text += "\n" + "".join(traceback.format_exception(*exception))
            # Do not hand raw frames to sinks which may enable diagnose=True.
            record["exception"] = None
        record["message"] = cls.text(text)
        record["extra"] = {
            key: cls.MASK if cls._key.search(str(key)) else cls.text(value)
            for key, value in record["extra"].items()
        }
