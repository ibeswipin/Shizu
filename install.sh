#!/usr/bin/env bash
# Run from a checkout: bash install.sh
set -Eeuo pipefail
umask 077

if [[ -t 1 ]]; then
    BOLD=$'\e[1m' AMBER=$'\e[38;5;214m' RED=$'\e[31m' DIM=$'\e[2m' RESET=$'\e[0m'
else
    BOLD='' AMBER='' RED='' DIM='' RESET=''
fi
step() { printf '\n%s==>%s %s%s%s\n' "$AMBER" "$RESET" "$BOLD" "$1" "$RESET"; }
die() { printf '%sError:%s %s\n' "$RED" "$RESET" "$1" >&2; exit 1; }
trap 'printf "\n%sInstallation failed at line %s.%s Fix the error above and run bash install.sh again.\n" "$RED" "$LINENO" "$RESET" >&2' ERR

case "$(uname -s)" in
    Linux|Darwin) ;;
    *) die 'Only Linux and macOS are supported.' ;;
esac
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    echo 'Usage: bash install.sh [--no-start]'
    echo
    echo 'Installs Python and dependencies, logs in to Telegram'
    echo 'and on Linux offers to run Shizu as a systemd service.'
    echo
    echo '  --no-start   only install dependencies, skip login and systemd'
    exit 0
fi
[[ $# -eq 0 || ( $# -eq 1 && "$1" == --no-start ) ]] || die 'Unknown argument. See bash install.sh --help.'
command -v git >/dev/null || die 'git is required. Install it and run the installer again.'
if [[ $EUID -eq 0 ]]; then
    printf '%sWarning:%s running as root. Shizu files and the service will belong to root.\n' "$AMBER" "$RESET"
    printf '%sRun the installer as your normal user unless this is intended.%s\n' "$DIM" "$RESET"
fi

SHIZU_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SHIZU_ROOT"
SHIZU_PYTHON_VERSION="$(tr -d '[:space:]' < .python-version)"
[[ "$SHIZU_PYTHON_VERSION" =~ ^3\.11\.[0-9]+$ ]] || die '.python-version must contain a Python 3.11.x version.'

printf '%s静 Shizu installer%s %s(%s)%s\n' "$BOLD" "$RESET" "$DIM" "$SHIZU_ROOT" "$RESET"

if command -v uv >/dev/null; then
    SHIZU_UV="$(command -v uv)"
elif [[ -x "$SHIZU_ROOT/.installer/bin/uv" ]]; then
    SHIZU_UV="$SHIZU_ROOT/.installer/bin/uv"
else
    step 'Downloading uv'
    mkdir -p .installer/bin
    if command -v curl >/dev/null; then
        curl --fail --location --silent --show-error https://astral.sh/uv/install.sh -o .installer/uv-install.sh
    elif command -v wget >/dev/null; then
        wget -q https://astral.sh/uv/install.sh -O .installer/uv-install.sh
    else
        die 'curl or wget is required to download uv.'
    fi
    UV_UNMANAGED_INSTALL="$SHIZU_ROOT/.installer/bin" sh .installer/uv-install.sh
    SHIZU_UV="$SHIZU_ROOT/.installer/bin/uv"
fi
# Keep managed interpreters local; do not replace system Python or the old venv.
export UV_PYTHON_INSTALL_DIR="$SHIZU_ROOT/.installer/python"
export UV_CACHE_DIR="$SHIZU_ROOT/.installer/cache"

step "Installing Python ${SHIZU_PYTHON_VERSION}"
"$SHIZU_UV" python install --no-bin "$SHIZU_PYTHON_VERSION"
if [[ -e .venv ]]; then
    if ! .venv/bin/python -c 'import platform, sys; sys.exit(platform.python_version() != sys.argv[1])' "$SHIZU_PYTHON_VERSION"; then
        die ".venv uses another Python version or is broken. Rename it (mv .venv .venv.old) and run the installer again."
    fi
else
    "$SHIZU_UV" venv --managed-python --python "$SHIZU_PYTHON_VERSION" --seed .venv
fi

step 'Installing Shizu and dependencies'
"$SHIZU_UV" pip install --python "$SHIZU_ROOT/.venv/bin/python" --editable "$SHIZU_ROOT"
"$SHIZU_UV" pip check --python "$SHIZU_ROOT/.venv/bin/python"
exec "$SHIZU_ROOT/.venv/bin/python" "$SHIZU_ROOT/scripts/install.py" "$@"
