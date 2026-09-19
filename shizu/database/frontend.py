import json
import os

from lightdb import LightDB

from typing import KT, VT


class Database(LightDB):
    """Local database in the file"""

    def __repr__(self):
        return object.__repr__(self)

    def save(self) -> None:
        """Save the current state of the database to a JSON file"""
        tmp = self.location.with_name(self.location.name + ".tmp")

        with tmp.open("w", encoding="utf-8") as file:
            json.dump(self, file, ensure_ascii=False, indent=4)
            file.flush()
            os.fsync(file.fileno())

        os.replace(tmp, self.location)

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
