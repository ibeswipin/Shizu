<div align="center">

<img src="assets/shizubanner.jpg" alt="Shizu">

<h1>Shizu</h1>

<p><b>Telegram userbot. Find joy in the little things.</b></p>

<a href="https://github.com/ibeswipin/Shizu/stargazers"><img src="https://img.shields.io/github/stars/ibeswipin/Shizu?style=flat" alt="Stars"></a>
<a href="https://github.com/ibeswipin/Shizu/issues"><img src="https://img.shields.io/github/issues/ibeswipin/Shizu?style=flat" alt="Issues"></a>
<a href="LICENSE"><img src="https://img.shields.io/github/license/ibeswipin/Shizu?style=flat" alt="License"></a>
<a href="https://t.me/shizu_talks"><img src="https://img.shields.io/badge/chat-@shizu__talks-2CA5E0?style=flat&logo=telegram" alt="Support chat"></a>

</div>

## Features

- **Modules**: load from a link or a file, unload, configure. Built-in modules cover help, backups, updates, languages and more.
- **Web setup**: first launch opens a web page. Log in with a QR code, or with your phone number and 2FA password, then pick your bot.
- **Bot control panel**: send `/panel` to your bot to restart or stop Shizu, change the prefix or the bot token.
- **BeSafe**: third-party modules load only after you review and approve them. Approval cards arrive in a separate chat.
- **Service chats**: Shizu creates `Shizu-logs`, `Shizu-backup` and `Shizu-besafe`, and puts them with your bot into a **Shizu** chat folder.
- **Inline bot**: inline forms, galleries and buttons for modules.
- **Web terminal and systemd control**: manage the server from Telegram.
- **Languages**: English, Russian, Uzbek.

## Installation

### Automatic (Linux, macOS)

```bash
git clone https://github.com/ibeswipin/Shizu
cd Shizu
bash install.sh
```

The installer gets Python 3.11 with [uv](https://docs.astral.sh/uv/), creates `.venv`, installs dependencies and walks you through the Telegram login. On Linux with systemd it offers to install a service that runs as your user. The service is enabled only after a successful login, and installing it needs `sudo`.

Run the installer as your normal user. Existing config and sessions are reused. You need `git` and `curl` or `wget`. If a dependency has to be compiled, install your build tools (`build-essential` on Debian/Ubuntu, Xcode Command Line Tools on macOS).

```bash
bash install.sh --no-start   # install dependencies only, no login or systemd
bash start.sh                # run manually
sudo systemctl restart shizu # restart the service
journalctl -u shizu -f       # follow the service logs
```

An existing `shizu.service` is never overwritten. After creating the service, keep the project at the same path.

### Manual

```bash
sudo apt update && sudo apt install -y git python3.11 python3.11-venv
git clone https://github.com/ibeswipin/Shizu
cd Shizu
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install .
python -m shizu
```

## First launch

Shizu prints a link to the setup page in the console, for example `https://….lhr.life`. The link is published through a [localhost.run](https://localhost.run) tunnel.

1. Enter your **API ID** and **API Hash** from [my.telegram.org/apps](https://my.telegram.org/apps).
2. Scan the QR code in Telegram (**Settings → Devices → Link Desktop Device**), or choose **Log in with phone number**.
3. Enter your 2FA password if your account has one.
4. Let Shizu create a bot for you, or paste the token of your own bot.

Shizu restarts and sends a start message to `Shizu-logs`.

| Flag | What it does |
| --- | --- |
| `--no-web` | Log in from the console instead of the web page |
| `--port 8080` | Port for the setup page |
| `--setup-only` | Log in and exit without starting the userbot |

## Commands

The default prefix is `.`. Change it with `.setprefix` or from `/panel`.

| Command | What it does |
| --- | --- |
| `.help` | List modules and commands |
| `.dlmod <link>` | Load a module from a link |
| `.loadmod` | Load a module from a replied file |
| `.unloadmod <name>` | Unload a module |
| `.restart` / `.update` / `.stop` | Restart / update / stop Shizu |
| `.checkupdate` | Show new commits without installing them |
| `.setprefix <prefix>` | Change the prefix |
| `.setbot <token>` | Change the bot token and restart |
| `.lang [code]` | Choose the language |
| `.backupdb` / `.restoredb` | Back up / restore the database |
| `.besafe` | BeSafe status, decisions and journal |
| `.owner [user]` | Owners panel, or add / remove an owner |
| `.alias [alias] [command]` | List, add or delete aliases |
| `.info` | Info card about your Shizu, with the support chat link |

In your bot:

| Command | What it does |
| --- | --- |
| `/panel` | Control panel: restart, stop, prefix, bot token |

## Support

Questions and bug reports: [@shizu_talks](https://t.me/shizu_talks) or [GitHub issues](https://github.com/ibeswipin/Shizu/issues). News: [@shizuhub](https://t.me/shizuhub).

Developer: [@hikamoru](https://t.me/hikamoru).

## License

[GNU GPLv3](LICENSE).
