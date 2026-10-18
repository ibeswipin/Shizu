"""Recognise bundled source files without trusting plugin names or flags."""

import os
from pathlib import Path

CORE_MODULES_PATH = Path(__file__).resolve().parents[1] / "modules" / "core"


def is_core_file(file_path: str) -> bool:
    if not file_path:
        return False
    path = Path(os.path.abspath(file_path))
    return (
        path.parent == CORE_MODULES_PATH
        and path.suffix == ".py"
        and not path.name.startswith("_")
        and path.is_file()
        and path.resolve() == path
    )


def touches_core(file_path: str) -> bool:
    if not file_path:
        return False
    path = Path(os.path.abspath(file_path))
    return CORE_MODULES_PATH in path.parents or CORE_MODULES_PATH in path.resolve().parents


def is_core_source(module_name: str, file_path: str, spec=None) -> bool:
    # A supplied spec may execute strings or a custom loader despite its origin.
    return (
        spec is None
        and is_core_file(file_path)
        and module_name == f"shizu.modules.{Path(file_path).stem}"
    )
