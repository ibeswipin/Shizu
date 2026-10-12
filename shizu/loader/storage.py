"""Persist reviewed local plugins separately from bundled source code."""

import logging
import os
import re
import tempfile
from pathlib import Path

CUSTOM_MODULES_PATH = Path(__file__).resolve().parents[1] / "modules" / "custom"


def ensure_directory(directory):
    path = Path(os.path.abspath(directory))
    path.mkdir(parents=True, exist_ok=True)
    if path.resolve() != path:
        raise OSError(f"Custom module directory must not be a symlink: {path}")
    return path


def save_module(directory, name: str, source: str) -> Path:
    directory = ensure_directory(directory)
    filename = re.sub(r"\W+", "_", name.lower()).strip("_") or "module"
    destination = directory / f"{filename}.py"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(source)
        # Replace the directory entry, never follow an existing file symlink.
        os.replace(temporary, destination)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def migrate_legacy_modules(legacy_directory, custom_directory, reserved_names):
    """Move old local plugins without overwriting custom files or moving core."""
    legacy = Path(legacy_directory)
    custom = ensure_directory(custom_directory)
    if legacy.resolve() == custom or not legacy.is_dir():
        return
    for source in sorted(legacy.glob("*.py")):
        if source.name.startswith("_"):
            continue
        if source.name in reserved_names:
            logging.warning("Skipped legacy copy of a core module: %s", source)
            continue
        if source.is_symlink() or not source.is_file():
            logging.warning("Skipped unsafe legacy module file: %s", source)
            continue
        destination = custom / source.name
        try:
            # Exclusive creation preserves existing files even during a race.
            os.link(source, destination, follow_symlinks=False)
            source.unlink()
        except FileExistsError:
            logging.warning("Custom module already exists; kept legacy file: %s", source)
        except OSError:
            logging.exception("Could not migrate local module %s", source)
        else:
            logging.info("Moved local module to %s", destination)
