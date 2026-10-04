"""Interactive account setup and optional Linux systemd installation."""

import argparse
import configparser
import getpass
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv/bin/python"
SERVICE = "shizu.service"
UNIT_PATH = Path("/etc/systemd/system") / SERVICE
DESCRIPTION = "Description=Shizu Telegram userbot"


def ask(question):
    while True:
        answer = input(question + " [y/N]: ").strip().lower()
        if answer in ("", "n", "no"):
            return False
        if answer in ("y", "yes"):
            return True


def run(*command):
    subprocess.run(command, cwd=ROOT, check=True)


def unit_quote(value):
    # systemd specifiers are expanded even inside quotes.
    value = str(value)
    if any(ord(c) < 32 for c in value):
        raise ValueError("The path contains control characters")
    return (
        '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'
    )


def unit_value(value):
    # User= and WorkingDirectory= take the raw value: quotes would become part of it.
    value = str(value)
    if any(ord(c) < 32 for c in value):
        raise ValueError("The path contains control characters")
    return value.replace("%", "%%")


def own_unit():
    try:
        text = UNIT_PATH.read_text(encoding="utf-8")
    except OSError:
        return False
    return DESCRIPTION in text and str(ROOT) in text


def service_text(username):
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\$?", username):
        raise ValueError(f"Unsupported user name for systemd: {username!r}")
    return f"""[Unit]
{DESCRIPTION}
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
User={username}
WorkingDirectory={unit_value(ROOT)}
ExecStart={unit_quote(PYTHON)} -u -m shizu --no-web
Environment=PYTHONUNBUFFERED=1
Environment={unit_quote("PATH=" + str(PYTHON.parent) + ":" + os.defpath)}
Restart=on-failure
RestartSec=10
TimeoutStopSec=30
UMask=0077

[Install]
WantedBy=multi-user.target
"""


def account_config():
    cfg = configparser.ConfigParser()
    path = ROOT / "config.ini"
    cfg.read(path)
    api_id = cfg.get("pyrogram", "api_id", fallback="")
    api_hash = cfg.get("pyrogram", "api_hash", fallback="")
    if (
        api_id.isdigit()
        and int(api_id) > 0
        and len(api_hash) == 32
        and all(c in "0123456789abcdefABCDEF" for c in api_hash)
    ):
        return
    print("\nEnter the API ID and API Hash from https://my.telegram.org/apps")
    while True:
        api_id = input("API ID: ").strip()
        if api_id.isdigit() and int(api_id) > 0:
            break
        print("API ID must be a positive number.")
    while True:
        api_hash = getpass.getpass("API Hash (hidden): ").strip()
        if len(api_hash) == 32 and all(c in "0123456789abcdefABCDEF" for c in api_hash):
            break
        print("API Hash must be 32 hexadecimal characters.")
    if not cfg.has_section("pyrogram"):
        cfg.add_section("pyrogram")
    cfg.set("pyrogram", "api_id", api_id)
    cfg.set("pyrogram", "api_hash", api_hash)
    with path.open("w", encoding="utf-8") as stream:
        cfg.write(stream)
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-start", action="store_true", help="Only install dependencies"
    )
    args = parser.parse_args()
    os.chdir(ROOT)
    os.umask(0o077)
    print("\nShizu is installed. Start it manually with: bash start.sh", flush=True)
    if args.no_start:
        return
    if not sys.stdin.isatty():
        raise RuntimeError(
            "An interactive terminal is required. Use --no-start to install without logging in"
        )
    systemd = (
        sys.platform.startswith("linux")
        and Path("/run/systemd/system").is_dir()
        and shutil.which("systemctl")
    )
    if (
        systemd
        and subprocess.run(["systemctl", "is-active", "--quiet", SERVICE]).returncode
        == 0
    ):
        raise RuntimeError(
            "The Shizu service is already running. Stop it first: sudo systemctl stop shizu"
        )
    use_service = bool(systemd) and ask(
        "Run Shizu as a systemd service that starts on boot? Requires sudo"
    )
    privileged = [] if os.geteuid() == 0 else ["sudo"]
    if use_service:
        if privileged and not shutil.which("sudo"):
            raise RuntimeError("sudo was not found. Choose manual start or set up sudo")
        if UNIT_PATH.exists() and not own_unit():
            raise RuntimeError(
                "shizu.service already exists and is not overwritten. Use it, or start manually with bash start.sh"
            )
        if privileged:
            run("sudo", "-v")
    elif sys.platform.startswith("linux") and not systemd:
        print("systemd was not found. Start Shizu manually with bash start.sh.")
    account_config()
    print(
        "\nTelegram login: log in with a QR code or your phone number, code and 2FA password.",
        flush=True,
    )
    run(str(PYTHON), "-u", "-m", "shizu", "--no-web", "--setup-only")
    if use_service:
        username = pwd.getpwuid(os.getuid()).pw_name
        with tempfile.TemporaryDirectory(prefix="shizu-service-") as folder:
            unit = Path(folder) / SERVICE
            unit.write_text(service_text(username), encoding="utf-8")
            run(*privileged, "install", "-m", "644", str(unit), str(UNIT_PATH))
        run(*privileged, "systemctl", "daemon-reload")
        run(*privileged, "systemctl", "enable", "--now", SERVICE)
        if (
            subprocess.run(["systemctl", "is-active", "--quiet", SERVICE]).returncode
            != 0
        ):
            subprocess.run(["systemctl", "--no-pager", "status", SERVICE])
            raise RuntimeError(
                "The Shizu service did not start. See the log: journalctl -u shizu -e"
            )
        print(
            "\nShizu runs as a service and starts on boot.\n  Logs:    journalctl -u shizu -f\n  Restart: sudo systemctl restart shizu\n  Stop:    sudo systemctl stop shizu\nOpen your bot and send /panel to control Shizu from Telegram.\n",
            flush=True,
        )
    else:
        print(
            "\nStarting Shizu. Press Ctrl+C to stop. Next time start it with: bash start.sh",
            flush=True,
        )
        os.execv(str(PYTHON), [str(PYTHON), "-u", "-m", "shizu", "--no-web"])


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print(
            "\nInstallation stopped. Run it again with: bash install.sh",
            file=sys.stderr,
        )
        sys.exit(130)
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"\nError: {error}", file=sys.stderr)
        sys.exit(1)
