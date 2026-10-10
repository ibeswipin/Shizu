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


import inspect
import re
import subprocess
from urllib.parse import urlparse

from shizu import loader
from shizu.inter import inter

from .compiler import ModuleCompiler
from .dependencies import VALID_PIP_PACKAGES
from .models import Library, LoadError


class LibraryLoader:
    """Review, execute and initialise shared libraries, retaining manager-owned instances."""

    def __init__(self, manager):
        self.manager = manager

    async def load(self, url: str, *, suspend_on_error: bool = False) -> "Library":
        """Load a shared library from `url` once; later calls return the same instance"""
        manager = self.manager
        if url in manager._libraries:
            return manager._libraries[url]
        try:
            item = await manager._remote_source(url, kind="library")
            source = item.source
        except Exception as error:
            raise LoadError(f"Could not download library {url}: {error}") from error

        if manager.load_guard:
            verdict = await manager.load_guard(source, url)
            if verdict is not True:
                raise LoadError(f"Library {url} is not approved yet ({verdict})")

        manager.remote_modules.remember(url, source, kind="library")

        library = await manager._exec_library(url, inter.transform(source), source)
        manager._libraries[url] = library
        manager.remote_modules.complete_update(url)
        return library

    async def execute(
        self, url: str, code: str, source: str, retried: bool = False
    ) -> "Library":
        manager = self.manager
        name = "shizu.modules.__lib_" + re.sub(
            r"\W", "_", urlparse(url).path.rsplit("/", 1)[-1][:-3] or "lib"
        )
        spec = ModuleCompiler.source_spec(name, code, url)
        module = ModuleCompiler.create(spec)
        try:
            spec.loader.exec_module(module)
        except ImportError as error:
            match = VALID_PIP_PACKAGES.search(source)
            if retried or not match:
                raise LoadError(f"Library {url} failed to import: {error}") from error
            try:
                await loader._install_requirements(
                    [
                        item
                        for item in match[1].split()
                        if item[0] not in ("-", "_", ".")
                    ]
                )
            except (subprocess.CalledProcessError, OSError) as install_error:
                raise LoadError(
                    f"Could not install dependencies for library {url}: "
                    f"{manager._pip_error(install_error)[-1000:]}"
                ) from install_error
            return await manager._exec_library(url, code, source, True)

        classes = [
            value
            for value in vars(module).values()
            if inspect.isclass(value)
            and issubclass(value, Library)
            and value is not Library
        ]
        if not classes:
            raise LoadError(f"{url} does not define a library class")
        library = classes[0]()
        library.name = library.name or classes[0].__name__
        client = manager._module_client()
        library.client = library._client = client
        library.db = manager._db
        library.all_modules = library.allmodules = manager
        library.inline = manager.bot_manager
        library.tg_id = library._tg_id = manager.me.id
        library.lookup = manager._lookup
        library.source_url = url
        if hasattr(library, "config"):
            manager.config_reconfigure(library, manager._db)
        await library.init()
        return library

    async def review(self, source: str, url: str):
        manager = self.manager
        manager.remote_modules.remember(url, source, kind="library")
        # Existing modules retain their library objects until restart.
        if url in manager._libraries:
            manager.remote_modules.complete_update(url)
            return "LIBRARY_UPDATED"
        await manager.import_library(url)
        return "LIBRARY_READY"
