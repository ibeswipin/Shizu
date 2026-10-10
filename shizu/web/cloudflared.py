"""A verified user-local cloudflared installation without root privileges."""

import asyncio
import hashlib
import io
import os
import platform
import shutil
import stat
import tarfile
import time
from pathlib import Path

import requests

from shizu import utils
from shizu.private_files import PrivateFiles


class CloudflaredInstaller:
    VERSION = "2026.10.0"
    MAX_BYTES = 100 * 1024 * 1024
    _lock = asyncio.Lock()
    ASSETS = {
        ("Linux", "x86_64"): (
            "cloudflared-linux-amd64",
            "d33ff2d14475178d2012c2c56beba87389ac5ded27649519f198a7d3134a99db",
        ),
        ("Linux", "aarch64"): (
            "cloudflared-linux-arm64",
            "e6422b9d4f72d3194bc5a38676f13667c06666523217b842a877d72a80b5ac08",
        ),
        ("Linux", "armv7l"): (
            "cloudflared-linux-armhf",
            "236afbc341625f5af0a8c461577d9da8aa66e3fd123a5b34e801d18a8a5a4d95",
        ),
        ("Linux", "armv6l"): (
            "cloudflared-linux-arm",
            "1dbe8e4ec17e74bb7f49cf91db6a4903bd0f9fe41984556c7503e40b765fd099",
        ),
        ("Linux", "i686"): (
            "cloudflared-linux-386",
            "f6fbd789e6ce9c824d4d560cbbfad2753d55ce398ece16b4c9fbf17271dceab3",
        ),
        ("Darwin", "x86_64"): (
            "cloudflared-darwin-amd64.tgz",
            "903845b81828c8cb3c5d13d816a2de71c06a3da5785469df8eb0e1b736d92f9f",
        ),
        ("Darwin", "arm64"): (
            "cloudflared-darwin-arm64.tgz",
            "a2f79ff7b9420aa537d74af239f376da170bbabeb529aec416002adac6a72e70",
        ),
    }

    def __init__(self, directory=None):
        self.directory = (
            Path(directory)
            if directory
            else Path(utils.get_base_dir()).parent / "data" / "bin"
        )

    async def ensure(self):
        if binary := shutil.which("cloudflared"):
            return binary
        async with self._lock:
            return await asyncio.to_thread(self._install)

    def _asset(self):
        system, machine = platform.system(), platform.machine().lower()
        machine = (
            {"amd64": "x86_64", "arm64": "aarch64", "i386": "i686"}.get(
                machine, machine
            )
            if system == "Linux"
            else machine
        )
        try:
            return self.ASSETS[(system, machine)]
        except KeyError:
            raise OSError(
                f"Automatic cloudflared installation is unavailable for {system}/{machine}"
            ) from None

    def _install(self):
        name, checksum = self._asset()
        binary = self.directory / f"cloudflared-{self.VERSION}"
        digest_path = binary.with_name(binary.name + ".sha256")
        if self._cached(
            binary, digest_path, checksum if not name.endswith(".tgz") else None
        ):
            return str(binary)
        data = self._download(name)
        if hashlib.sha256(data).hexdigest() != checksum:
            raise OSError("cloudflared release checksum mismatch")
        if name.endswith(".tgz"):
            data = self._unpack(data)
        PrivateFiles.directory(self.directory)
        PrivateFiles.write(binary, data)
        binary.chmod(0o700)
        PrivateFiles.write(digest_path, hashlib.sha256(data).hexdigest().encode())
        return str(binary)

    def _cached(self, binary, digest_path, checksum):
        try:
            if not stat.S_ISREG(binary.lstat().st_mode):
                raise OSError("cloudflared cache must be a regular file")
            expected = checksum or PrivateFiles.read(digest_path).decode()
            if binary.stat().st_size > self.MAX_BYTES:
                return False
            if hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
                return False
            return os.access(binary, os.X_OK)
        except (FileNotFoundError, UnicodeError):
            return False

    def _download(self, name):
        url = f"https://github.com/cloudflare/cloudflared/releases/download/{self.VERSION}/{name}"
        started = time.monotonic()
        try:
            with requests.get(url, stream=True, timeout=(10, 30)) as response:
                response.raise_for_status()
                if not response.url.startswith("https://"):
                    raise OSError("cloudflared download must use HTTPS")
                data = bytearray()
                for chunk in response.iter_content(256 * 1024):
                    data.extend(chunk)
                    if len(data) > self.MAX_BYTES or time.monotonic() - started > 120:
                        raise OSError(
                            "cloudflared download exceeded its size or time limit"
                        )
                return bytes(data)
        except requests.RequestException as error:
            raise OSError(
                "Could not download the official cloudflared release"
            ) from error

    def _unpack(self, data):
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                member = next(
                    (
                        item
                        for item in archive
                        if item.name in ("cloudflared", "./cloudflared")
                    ),
                    None,
                )
                if not member or not member.isfile() or member.size > self.MAX_BYTES:
                    raise OSError("Invalid cloudflared archive")
                with archive.extractfile(member) as stream:
                    return stream.read(self.MAX_BYTES + 1)
        except tarfile.TarError as error:
            raise OSError("Invalid cloudflared archive") from error
