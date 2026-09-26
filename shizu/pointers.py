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

"""Lists and dicts that write themselves back to the database on every change"""

import collections.abc
import copy


class _Pointer:
    def __init__(self, db, module: str, key: str, default):
        self._db = db
        self._module = module
        self._key = key
        self._default = default

    def _load(self):
        value = self._db.get(self._module, self._key, None)
        return copy.deepcopy(self._default) if value is None else value

    def _save(self, value):
        self._db.set(self._module, self._key, value)


class PointerList(_Pointer, collections.abc.MutableSequence):
    """List stored under `module.key` in the database"""

    def __init__(self, db, module: str, key: str, default=None):
        super().__init__(db, module, key, list(default or []))

    @property
    def data(self) -> list:
        return list(self._load())

    def __getitem__(self, index):
        return self.data[index]

    def __setitem__(self, index, value):
        data = self.data
        data[index] = value
        self._save(data)

    def __delitem__(self, index):
        data = self.data
        del data[index]
        self._save(data)

    def __len__(self) -> int:
        return len(self.data)

    def insert(self, index, value):
        data = self.data
        data.insert(index, value)
        self._save(data)

    def clear(self):
        self._save([])

    def __eq__(self, other) -> bool:
        return self.data == list(other)

    def __repr__(self) -> str:
        return f"PointerList({self.data!r})"

    def tolist(self) -> list:
        return self.data


class PointerDict(_Pointer, collections.abc.MutableMapping):
    """Dict stored under `module.key` in the database"""

    def __init__(self, db, module: str, key: str, default=None):
        super().__init__(db, module, key, dict(default or {}))

    @property
    def data(self) -> dict:
        return dict(self._load())

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        data = self.data
        data[key] = value
        self._save(data)

    def __delitem__(self, key):
        data = self.data
        del data[key]
        self._save(data)

    def __iter__(self):
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def clear(self):
        self._save({})

    def __eq__(self, other) -> bool:
        return self.data == dict(other)

    def __repr__(self) -> str:
        return f"PointerDict({self.data!r})"

    def todict(self) -> dict:
        return self.data
