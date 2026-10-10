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


import json
from pathlib import Path
from typing import KT, VT

from lightdb import LightDB

from shizu.private_files import PrivateFiles
from shizu.redaction import SecretRedactor


class Database(LightDB):
    """Local database in the file"""

    def __init__(self, location):
        PrivateFiles.secure_existing(location)
        # A previous interrupted save may have left a plaintext temporary file.
        PrivateFiles.secure_existing(
            Path(location).with_name(Path(location).name + ".tmp")
        )
        super().__init__(location)
        SecretRedactor.remember_mapping(self)

    def __repr__(self):
        return object.__repr__(self)

    def save(self) -> None:
        """Save the current state of the database to a JSON file"""
        SecretRedactor.remember_mapping(self)
        self._write(self)

    def _write(self, data: dict) -> None:
        text = json.dumps(data, ensure_ascii=False, indent=4)
        PrivateFiles.write(self.location, text.encode("utf-8"))

    def replace(self, data: dict) -> None:
        """Keep the current database if serialization or disk replacement fails."""
        self._write(data)
        self.clear()
        self.update(data)
        SecretRedactor.remember_mapping(self)

    def set(self, name: str, key: KT, value: VT):
        self.setdefault(name, {})[key] = value

        return self.save()

    def get(self, name: str, key: KT, default: VT = None):
        try:
            return self[name][key]
        except KeyError:
            return default

    def pop(self, name: str, key: KT = None, default: VT = None):
        if not key:
            value = self[name].pop(name, default)
        else:
            try:
                value = self[name].pop(key, default)
            except KeyError:
                value = default

        self.save()

        return value if value is not None else default
