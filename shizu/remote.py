"""Pinned UTF-8 sources, before compatibility transformations or execution."""

import hashlib
import logging
import os
import posixpath
import re
import secrets
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests

from shizu import utils

logger = logging.getLogger(__name__)


class RemoteModuleError(ValueError):
    """The remote source cannot be safely loaded."""


class RemoteModuleIntegrityError(RemoteModuleError):
    def __init__(self, url: str, expected: str, actual: str):
        self.url, self.expected, self.actual = url, expected, actual
        super().__init__(
            f"SHA-256 mismatch for {url}: expected {expected}, received {actual}. "
            "The source was not loaded. Use updatemod to review an update."
        )


@dataclass(frozen=True)
class RemoteModuleSource:
    url: str
    sha256: str
    source: str
    resolved_url: str | None = None

    @classmethod
    def from_source(cls, url: str, source: str, resolved_url: str | None = None):
        return cls(
            url,
            hashlib.sha256(source.encode("utf-8")).hexdigest(),
            source,
            resolved_url,
        )


@dataclass(frozen=True)
class RemoteModuleUpdate:
    candidate: RemoteModuleSource
    previous_sha256: str
    expires: float


class RemoteModuleRegistry:
    SECTION = "shizu.loader"
    RECORDS = "remote_modules"
    UPDATE_TTL = 600

    def __init__(self, db, cache_dir: str | Path = "data/modules_cache"):
        self.db = db
        self.cache_dir = Path(cache_dir)
        self._updates: dict[str, RemoteModuleUpdate] = {}

    @staticmethod
    def is_remote(origin: str) -> bool:
        return bool(origin) and "://" in origin

    @staticmethod
    def validate_url(url: str) -> str:
        try:
            parsed = urlparse(url)
            _ = parsed.port
        except (ValueError, TypeError) as error:
            raise RemoteModuleError("Invalid module URL.") from error
        if parsed.scheme != "https" or not parsed.hostname:
            raise RemoteModuleError("Code may only be downloaded over https://.")
        if parsed.username is not None or parsed.password is not None:
            raise RemoteModuleError("Credentials in module URLs are not supported.")
        return url

    @staticmethod
    def _http_origin(url: str):
        parsed = urlparse(url)
        return parsed.scheme, parsed.hostname, parsed.port or 443

    def _get(self, url: str, headers: dict | None = None):
        url = self.validate_url(url)
        original = self._http_origin(url)
        for _ in range(6):
            response = requests.get(
                url,
                headers=headers if self._http_origin(url) == original else None,
                timeout=30,
                allow_redirects=False,
            )
            if response.status_code not in (301, 302, 303, 307, 308):
                return response
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise RemoteModuleError("The source returned an empty redirect.")
            # Validate before following: checking response.url permits an HTTP hop.
            url = self.validate_url(urljoin(url, location))
        raise RemoteModuleError("The source returned too many redirects.")

    async def request(self, url: str, headers: dict | None = None):
        self.validate_url(url)
        return await utils.run_sync(self._get, url, headers)

    async def _download(self, url: str, headers: dict | None = None):
        response = await self.request(url, headers)
        try:
            response.raise_for_status()
            if response.status_code != 200:
                raise requests.exceptions.HTTPError(
                    f"The source returned HTTP {response.status_code}, expected 200.",
                    response=response,
                )
            resolved_url = self.validate_url(getattr(response, "url", None) or url)
            return RemoteModuleSource.from_source(url, response.text, resolved_url)
        finally:
            response.close()

    def record(self, url: str) -> dict | None:
        record = self.db.get(self.SECTION, self.RECORDS, {}).get(url)
        if record is not None and not isinstance(record, dict):
            raise RemoteModuleError(f"Invalid stored module record for {url}.")
        if record and record.get("sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(record["sha256"])):
                raise RemoteModuleError(f"Invalid stored SHA-256 for {url}.")
            if record.get("url") != url:
                raise RemoteModuleError(f"Stored module URL does not match {url}.")
        return record

    def kind(self, url: str) -> str:
        return (self.record(url) or {}).get("kind", "module")

    def review_origin(self, url: str) -> str:
        origin = self.validate_url((self.record(url) or {}).get("resolved_url") or url)
        parsed = urlparse(origin)
        return parsed._replace(path=posixpath.normpath(unquote(parsed.path))).geturl()

    def verify(self, item: RemoteModuleSource, expected: str):
        if item.sha256 != expected:
            raise RemoteModuleIntegrityError(item.url, expected, item.sha256)

    def check_source(self, url: str, source: str) -> RemoteModuleSource:
        self.validate_url(url)
        item = RemoteModuleSource.from_source(url, source)
        record = self.record(url)
        if record and record.get("sha256"):
            self.verify(item, record["sha256"])
        return item

    def _cache_path(self, item: RemoteModuleSource) -> Path:
        return self.cache_dir / (item.sha256 + ".py")

    def _write_cache(self, item: RemoteModuleSource):
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.cache_dir, delete=False) as file:
                path = Path(file.name)
                file.write(item.source.encode("utf-8"))
                file.flush()
                os.fsync(file.fileno())
            os.replace(path, self._cache_path(item))
        finally:
            if path is not None:
                path.unlink(missing_ok=True)

    def _save(self, item: RemoteModuleSource, kind: str, *, previous=None):
        self._write_cache(item)
        records = dict(self.db.get(self.SECTION, self.RECORDS, {}))
        records[item.url] = {
            "url": item.url,
            "sha256": item.sha256,
            "source": item.source,
            "kind": kind,
            "resolved_url": item.resolved_url or self.review_origin(item.url),
        }
        if previous:
            records[item.url]["previous"] = previous
        self.db.set(self.SECTION, self.RECORDS, records)

    def remember(self, url: str, source: str, *, kind: str = "module"):
        item = self.check_source(url, source)
        self._save(item, kind, previous=(self.record(url) or {}).get("previous"))
        return item

    def install(self, url: str, source: str):
        self.remember(url, source)
        modules = self.db.get(self.SECTION, "modules", [])
        if url not in modules:
            self.db.set(self.SECTION, "modules", [*modules, url])
        self.complete_update(url)

    def complete_update(self, url: str):
        record = self.record(url)
        if record and "previous" in record:
            records = dict(self.db.get(self.SECTION, self.RECORDS, {}))
            records[url] = {
                key: value for key, value in record.items() if key != "previous"
            }
            self.db.set(self.SECTION, self.RECORDS, records)

    def rollback_update(self, url: str, sha256: str) -> bool:
        record = self.record(url)
        if not record or record.get("sha256") != sha256 or not record.get("previous"):
            return False
        previous = record["previous"]
        item = RemoteModuleSource.from_source(
            url, previous["source"], previous.get("resolved_url") or url
        )
        self.verify(item, previous["sha256"])
        self._save(item, previous.get("kind", "module"))
        logger.warning(
            "Restored previous pinned source for %s after a rejected update", url
        )
        return True

    async def resolve(self, url: str, headers: dict | None = None, *, kind="module"):
        self.validate_url(url)
        record = self.record(url)
        if record and record.get("sha256"):
            path = self.cache_dir / (record["sha256"] + ".py")
            try:
                data = path.read_bytes()
            except FileNotFoundError:
                item = await self._download(url, headers)
                self.verify(item, record["sha256"])
                self._write_cache(item)
                return item
            actual = hashlib.sha256(data).hexdigest()
            if actual != record["sha256"]:
                raise RemoteModuleIntegrityError(url, record["sha256"], actual)
            return RemoteModuleSource(
                url, actual, data.decode("utf-8"), record.get("resolved_url") or url
            )

        approved_sources = self.db.get("ShizuBeSafe", "sources", {})
        legacy = (
            bool(record)
            or url in self.db.get(self.SECTION, "modules", [])
            or (kind == "library" and url in approved_sources)
        )
        source = (record or {}).get("source")
        if legacy and source is None:
            source = approved_sources.get(url)
        item = (
            RemoteModuleSource.from_source(url, source)
            if isinstance(source, str)
            else await self._download(url, headers)
        )
        self.check_source(url, item.source)
        self._save(item, kind)
        if legacy:
            logger.warning(
                "TOFU: pinned existing module %s to SHA-256 %s", url, item.sha256
            )
        return item

    async def prepare_update(self, url: str, headers: dict | None = None):
        record = self.record(self.validate_url(url))
        if not record or not record.get("sha256"):
            raise RemoteModuleError("Install the module before requesting an update.")
        if record.get("previous"):
            raise RemoteModuleError(
                "Finish the pending BeSafe review before requesting another update."
            )
        item = await self._download(url, headers)
        now = time.monotonic()
        self._updates = {
            key: value for key, value in self._updates.items() if value.expires > now
        }
        token = secrets.token_urlsafe(24)
        update = RemoteModuleUpdate(item, record["sha256"], now + self.UPDATE_TTL)
        self._updates[token] = update
        return token, update

    def pending_update(self, token: str) -> RemoteModuleUpdate:
        update = self._updates.get(token)
        if update is None or update.expires <= time.monotonic():
            self._updates.pop(token, None)
            raise RemoteModuleError(
                "This update confirmation has expired. Run updatemod again."
            )
        record = self.record(update.candidate.url)
        if not record or record.get("sha256") != update.previous_sha256:
            self._updates.pop(token, None)
            raise RemoteModuleError(
                "The installed version changed. Run updatemod again."
            )
        return update

    def cancel_update(self, token: str):
        self._updates.pop(token, None)

    def confirm_update(self, token: str):
        update = self.pending_update(token)
        kind = self.kind(update.candidate.url)
        # Commit the reviewed bytes, not a second download after the click.
        self._save(update.candidate, kind, previous=self.record(update.candidate.url))
        self._updates.pop(token, None)
        logger.info(
            "Confirmed update of %s to SHA-256 %s",
            update.candidate.url,
            update.candidate.sha256,
        )
        return update.candidate

    def forget(self, url: str):
        records = dict(self.db.get(self.SECTION, self.RECORDS, {}))
        records.pop(url, None)
        self.db.set(self.SECTION, self.RECORDS, records)
        self.db.set(
            self.SECTION,
            "modules",
            [item for item in self.db.get(self.SECTION, "modules", []) if item != url],
        )

    def clear_modules(self):
        records = self.db.get(self.SECTION, self.RECORDS, {})
        self.db.set(
            self.SECTION,
            self.RECORDS,
            {
                url: record
                for url, record in records.items()
                if record.get("kind") == "library"
            },
        )
        self.db.set(self.SECTION, "modules", [])
        self._updates.clear()
