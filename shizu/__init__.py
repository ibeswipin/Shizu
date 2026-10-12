__license__ = "GNU Affero General Public License v3.0"
__copyright__ = "Copyright (C) 2026 Shizu"
__developer__ = "https://t.me/hikamoru"
__github__ = "https://github.com/ibeswipin/"

import importlib
import sys

from .integrity import runtime as _integrity

_integrity.install()

security = importlib.import_module(".security", __name__)

redaction = safemode = private_files = security
for _name in ("redaction", "safemode", "private_files"):
    sys.modules[f"{__name__}.{_name}"] = security

del _name
