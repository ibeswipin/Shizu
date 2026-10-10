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


import os
import sys
from importlib.abc import SourceLoader
from importlib.machinery import ModuleSpec
from importlib.util import module_from_spec, spec_from_file_location
from typing import Any

from shizu.besafe import BeSafe


class StringLoader(SourceLoader):
    """Loads the module from the line"""

    def __init__(self, data: str, origin: str) -> None:
        self.data = data.encode("utf-8")
        self.origin = origin

    def get_code(self, full_name: str) -> Any | None:
        if source := self.get_source(full_name):
            return compile(source, self.origin, "exec", dont_inherit=True)
        return None

    def get_filename(self, _: str) -> str:
        return self.origin

    def get_data(self, _: str) -> str:
        return self.data


class ModuleCompiler:
    """Build import specs and record BeSafe provenance before executing code."""

    @staticmethod
    def source_spec(name: str, source: str, origin: str, *, has_location=False):
        spec = ModuleSpec(name, StringLoader(source, origin), origin=origin)
        spec.has_location = has_location
        return spec

    @staticmethod
    def create(spec, *, trusted=False):
        module = module_from_spec(spec)
        sys.modules[module.__name__] = module
        BeSafe.register_namespace(module, trusted=trusted)
        return module

    @classmethod
    def execute_module(cls, module_name: str, file_path: str = "", spec=None):
        spec = spec or spec_from_file_location(module_name, file_path)
        short_name = module_name.rsplit(".", 1)[-1]
        core_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "modules", short_name + ".py"
        )
        trusted = (
            short_name in BeSafe._core
            and bool(file_path)
            and os.path.realpath(file_path) == os.path.realpath(core_path)
        )
        module = cls.create(spec, trusted=trusted)
        spec.loader.exec_module(module)
        return module
