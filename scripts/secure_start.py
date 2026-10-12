"""Verify signed installation sources before importing the userbot."""

import sys

if not sys.flags.isolated:
    import os

    os.execv(sys.executable, [sys.executable, "-I", __file__, *sys.argv[1:]])

import importlib.util
import hashlib
import json
import os
import runpy
import stat
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PUBLIC_KEY_HEX = "3803e376267ae17b2445fa21c7a521717069d3cce57840f6dd3c116adc5e6c6d"

ROOT = Path(__file__).resolve().parent.parent


def read_bootstrap(filename, *, repair_permissions=False):
    directory = os.open(ROOT / "shizu", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptor = None
    try:
        descriptor = os.open(
            filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or (info.st_mode & 0o022 and not repair_permissions)
            or info.st_size > 4 * 1024 * 1024
        ):
            raise RuntimeError("Unsafe release bootstrap file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            data = stream.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise RuntimeError("Release bootstrap file is too large")
        return data
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


def main():
    repair_permissions = sys.argv[1:] == ["--fix-permissions"]
    if "--fix-permissions" in sys.argv[1:] and not repair_permissions:
        raise RuntimeError("Use --fix-permissions without other arguments")
    # Authenticate the verifier before executing any code from the checkout.
    public = bytes.fromhex(PUBLIC_KEY_HEX)
    manifest = read_bootstrap("core-manifest.json", repair_permissions=repair_permissions)
    Ed25519PublicKey.from_public_bytes(public).verify(
        read_bootstrap("core-manifest.sig", repair_permissions=repair_permissions), manifest
    )
    payload = json.loads(manifest)
    source = read_bootstrap("integrity.py", repair_permissions=repair_permissions)
    if hashlib.sha256(source).hexdigest() != payload["files"].get("shizu/integrity.py"):
        raise RuntimeError("The release verifier was modified")
    # Execute the exact authenticated source, avoiding pre-existing .pyc files.
    name = "shizu.integrity"
    filename = ROOT / "shizu/integrity.py"
    spec = importlib.util.spec_from_file_location(name, filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(source, str(filename), "exec"), module.__dict__)
    if repair_permissions:
        module.ReleaseFiles(ROOT).secure_permissions()
        module.Release(ROOT, public).verify_tree()
        print("Protected file permissions secured; release signature and hashes verified.")
        return
    release = module.Release(ROOT, public)
    sys.path.insert(0, str(ROOT))
    module.runtime.install(release)
    sys.argv[0] = str(ROOT / "shizu/__main__.py")
    runpy.run_module("shizu", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, InvalidSignature, ValueError, KeyError, TypeError) as error:
        if isinstance(error, InvalidSignature):
            error = "Release signature is invalid"
        print(f"Shizu startup blocked: {error}", file=sys.stderr)
        sys.exit(1)
