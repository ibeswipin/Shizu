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


import importlib
import os
import re
import site
import subprocess
import sys

from shizu import utils

VALID_URL = r"[-[\]_.~:/?#@!$&'()*+,;%<=>a-zA-Z0-9]+"
VALID_PIP_PACKAGES = re.compile(
    rf"^\s*# requi(?:red|res):(?: ?)((?:{VALID_URL} )*(?:{VALID_URL}))\s*$",
    re.MULTILINE,
)


MODULE_DEPENDENCIES = os.environ.get("SHIZU_DEPS_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".module_dependencies",
)


class DependencyInstaller:
    """Install plugin requirements and refresh the interpreter search path."""

    @staticmethod
    def activate(target=MODULE_DEPENDENCIES):
        if os.path.isdir(target):
            site.addsitedir(target)

    @staticmethod
    async def install(requirements, target=MODULE_DEPENDENCIES):
        """Install dependencies into SHIZU_DEPS_DIR, the venv or a project-local directory."""
        local = bool(os.environ.get("SHIZU_DEPS_DIR")) or sys.prefix == sys.base_prefix
        if importlib.util.find_spec("pip") is None:
            await utils.run_sync(
                subprocess.run,
                [sys.executable, "-m", "ensurepip"],
                check=True,
                capture_output=True,
                text=True,
            )
        await utils.run_sync(
            subprocess.run,
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                *(["--target", target] if local else []),
                *requirements,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        if local:
            site.addsitedir(target)
        importlib.invalidate_caches()

    @staticmethod
    def error_output(error: Exception) -> str:
        """pip's own error output, or the exception text when there is none"""
        output = (
            getattr(error, "stderr", None) or getattr(error, "stdout", None) or ""
        ).strip()
        return output or str(error)
