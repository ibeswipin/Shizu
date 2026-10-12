"""Keep bundled modules importable under their existing public namespace."""

from pathlib import Path

# Existing imports and translation keys use shizu.modules.<name>.
__path__.insert(0, str(Path(__file__).resolve().parent / "core"))
__path__.append(str(Path(__file__).resolve().parent / "custom"))
