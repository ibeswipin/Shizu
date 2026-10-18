#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
    echo 'Shizu is not installed yet. Run: bash install.sh' >&2
    exit 1
fi
exec .venv/bin/python -u -m shizu "$@"
