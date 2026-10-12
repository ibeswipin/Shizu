"""Signed release verification and source-only imports for trusted code.

The bootstrap and pinned public key must themselves come from a trusted
installation. This is not an isolation boundary for arbitrary in-process Python.
"""

import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PUBLIC_KEY_HEX = "3803e376267ae17b2445fa21c7a521717069d3cce57840f6dd3c116adc5e6c6d"

MANIFEST_NAME = "shizu/core-manifest.json"
SIGNATURE_NAME = "shizu/core-manifest.sig"
RELEASE_FILES = (
    "pyproject.toml",
    "start.sh",
    "install.sh",
    "scripts/install.py",
    "scripts/secure_start.py",
)
MAX_FILE_BYTES = 4 * 1024 * 1024


class IntegrityError(RuntimeError):
    """Protected code failed verification; do not execute or auto-repair it."""


class ReleaseFiles:
    """Discover and safely read protected files from one installation."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    @staticmethod
    def is_protected(relative: str) -> bool:
        path = PurePosixPath(relative)
        if relative in RELEASE_FILES:
            return True
        if not relative.startswith("shizu/") or path.suffix != ".py":
            return False
        if relative.startswith("shizu/downloads/"):
            return False
        if relative.startswith("shizu/modules/"):
            return (
                relative == "shizu/modules/__init__.py"
                or relative.startswith("shizu/modules/core/")
            )
        return True

    def paths(self) -> tuple[str, ...]:
        """Discover protected source files, without importing or following symlinks."""
        root = self.root
        paths = []
        for folder, directories, files in os.walk(root / "shizu", followlinks=False):
            relative = Path(folder).relative_to(root).as_posix()
            if relative == "shizu/modules":
                directories[:] = [name for name in directories if name == "core"]
            else:
                directories[:] = [name for name in directories if name != "__pycache__"]
                if relative == "shizu":
                    directories[:] = [name for name in directories if name != "downloads"]
            for directory in directories:
                if (Path(folder) / directory).is_symlink():
                    raise IntegrityError(f"Symlink in protected directory: {relative}/{directory}")
            for filename in files:
                candidate = f"{relative}/{filename}"
                if self.is_protected(candidate):
                    paths.append(candidate)
        paths.extend(relative for relative in RELEASE_FILES if (root / relative).exists())
        return tuple(sorted(paths))

    def read(self, relative: str) -> bytes:
        """Open each path component with no-follow and execute only regular files."""
        parts = PurePosixPath(relative).parts
        if (
            not parts
            or PurePosixPath(relative).is_absolute()
            or any(part in (".", "..") for part in parts)
            or PurePosixPath(relative).as_posix() != relative
            or "\\" in relative
        ):
            raise IntegrityError(f"Invalid protected path: {relative!r}")
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
        directory = None
        descriptor = None
        try:
            directory = os.open(self.root, flags)
            if os.fstat(directory).st_mode & 0o022:
                raise IntegrityError("The installation directory is writable by others")
            for part in parts[:-1]:
                child = os.open(part, flags, dir_fd=directory)
                os.close(directory)
                directory = child
                if os.fstat(directory).st_mode & 0o022:
                    raise IntegrityError(f"Protected directory is writable by others: {relative}")
            descriptor = os.open(
                parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
            )
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_mode & 0o022
                or info.st_size > MAX_FILE_BYTES
            ):
                raise IntegrityError(f"Unsafe protected file: {relative}")
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = None
                data = stream.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise IntegrityError(f"Protected file is too large: {relative}")
            return data
        except OSError as error:
            raise IntegrityError(f"Cannot safely read protected file: {relative}") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory is not None:
                os.close(directory)


class Release:
    """An authenticated immutable snapshot of the expected release hashes."""

    def __init__(self, root: Path, public_key: bytes):
        self._sources = ReleaseFiles(root)
        self.root = self._sources.root
        self.public_key = public_key
        manifest = self._sources.read(MANIFEST_NAME)
        signature = self._sources.read(SIGNATURE_NAME)
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(signature, manifest)
            payload = json.loads(manifest, object_pairs_hook=self._unique_object)
        except (InvalidSignature, ValueError, TypeError) as error:
            raise IntegrityError("Release manifest signature is invalid") from error
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema", "files"}
            or type(payload["schema"]) is not int
            or payload["schema"] != 1
            or not isinstance(payload["files"], dict)
            or not payload["files"]
        ):
            raise IntegrityError("Invalid release manifest schema")
        for relative, digest in payload["files"].items():
            if (
                not self._sources.is_protected(relative)
                or PurePosixPath(relative).as_posix() != relative
                or ".." in PurePosixPath(relative).parts
                or "\\" in relative
                or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
            ):
                raise IntegrityError(f"Invalid release entry: {relative!r}")
        self.files = MappingProxyType(payload["files"])

    @staticmethod
    def _unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise IntegrityError("Duplicate key in release manifest")
            result[key] = value
        return result

    def read(self, relative: str) -> bytes:
        expected = self.files.get(relative)
        if expected is None:
            raise IntegrityError(f"Unsigned protected file: {relative}")
        data = self._sources.read(relative)
        if hashlib.sha256(data).hexdigest() != expected:
            raise IntegrityError(f"Protected file was modified: {relative}")
        return data

    def verify_tree(self):
        actual = set(self._sources.paths())
        expected = set(self.files)
        if actual != expected:
            extra = sorted(actual - expected)
            missing = sorted(expected - actual)
            raise IntegrityError(
                f"Release file set changed; unsigned={extra}, missing={missing}"
            )
        for relative in self.files:
            self.read(relative)

    def spec(self, fullname: str, relative: str):
        source = self.read(relative)
        filename = str(self.root / relative)
        loader = VerifiedSourceLoader(filename, source, relative.endswith("/__init__.py"))
        spec = importlib.util.spec_from_loader(fullname, loader, origin=filename)
        spec.has_location = True
        if loader.package:
            spec.submodule_search_locations = [str(Path(filename).parent)]
        return spec


class VerifiedSourceLoader(importlib.abc.Loader):
    """Compile the exact authenticated bytes; never consult a bytecode cache."""

    def __init__(self, filename: str, source: bytes, package: bool = False):
        self.filename = filename
        self.source = source
        self.package = package

    def create_module(self, spec):
        return None

    def is_package(self, fullname):
        return self.package

    def get_filename(self, fullname):
        return self.filename

    def get_source(self, fullname):
        return importlib.util.decode_source(self.source)

    def get_code(self, fullname):
        return compile(self.source, self.filename, "exec", dont_inherit=True)

    def exec_module(self, module):
        guard = getattr(sys.modules.get("shizu.besafe"), "BeSafe", None)
        if guard is not None and module.__name__.startswith("shizu.modules."):
            guard.register_namespace(module, trusted=True)
        exec(self.get_code(module.__name__), module.__dict__)
        guard = getattr(sys.modules.get("shizu.besafe"), "BeSafe", None)
        if guard is not None and module.__name__.startswith("shizu.modules."):
            guard.register_namespace(module, trusted=True)


class ModuleAliasLoader(importlib.abc.Loader):
    def __init__(self, canonical: str):
        self.canonical = canonical

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        sys.modules[module.__name__] = importlib.import_module(self.canonical)


class ReleaseFinder(importlib.abc.MetaPathFinder):
    ALIASES = MappingProxyType({
        "shizu.log": "shizu.logger",
        "shizu.translations": "shizu.translator",
    })

    def __init__(self, release: Release):
        self.release = release
        self.core = {
            PurePosixPath(path).stem: path
            for path in release.files
            if path.startswith("shizu/modules/core/")
            and len(PurePosixPath(path).parts) == 4
            and not PurePosixPath(path).name.startswith("_")
        }

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "shizu" and not fullname.startswith("shizu."):
            return None
        if canonical := self.ALIASES.get(fullname):
            return importlib.util.spec_from_loader(fullname, ModuleAliasLoader(canonical))
        short = fullname.removeprefix("shizu.modules.")
        if short in self.core:
            return self.release.spec(fullname, self.core[short])
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.origin is None:
            return spec
        origin = Path(os.path.abspath(spec.origin))
        try:
            relative = origin.relative_to(self.release.root).as_posix()
        except ValueError as error:
            raise IntegrityError(f"Protected import escaped the installation: {fullname}") from error
        if relative in self.release.files:
            return self.release.spec(fullname, relative)
        if relative.startswith("shizu/modules/") and not relative.startswith(
            "shizu/modules/core/"
        ) and relative != "shizu/modules/__init__.py":
            return spec
        raise IntegrityError(f"Unsigned protected import: {fullname}")


class IntegrityManager:
    """Own the pinned release cache and install verified imports."""

    def __init__(self, root: Path, public_key: bytes):
        self.root = root.resolve()
        self.public_key = public_key
        self._release: Release | None = None

    def get_release(self) -> Release:
        if self._release is None:
            release = Release(self.root, self.public_key)
            release.verify_tree()
            self._release = release
        return self._release

    def install(self, release: Release | None = None) -> None:
        release = release or self.get_release()
        if release.root != self.root or release.public_key != self.public_key:
            raise IntegrityError("Release does not match the pinned installation")
        release.verify_tree()
        if not any(isinstance(finder, ReleaseFinder) for finder in sys.meta_path):
            sys.meta_path.insert(0, ReleaseFinder(release))
        self._release = release


runtime = IntegrityManager(
    Path(__file__).resolve().parent.parent, bytes.fromhex(PUBLIC_KEY_HEX)
)
get_release = runtime.get_release
install = runtime.install
