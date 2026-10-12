<div align="center">

<img src="assets/shizubanner.png" alt="Shizu — Find joy in the little things" width="960">

<h1>Shizu</h1>

<p>A modular Telegram userbot with a web dashboard and tools for everyday use.</p>

<p>
<a href="https://github.com/ibeswipin/Shizu/stargazers"><img src="https://img.shields.io/github/stars/ibeswipin/Shizu?style=flat-square&color=8b9cf7" alt="GitHub stars"></a>
<a href="https://github.com/ibeswipin/Shizu/issues"><img src="https://img.shields.io/github/issues/ibeswipin/Shizu?style=flat-square&color=8b9cf7" alt="GitHub issues"></a>
<a href="LICENSE"><img src="https://img.shields.io/github/license/ibeswipin/Shizu?style=flat-square&color=8b9cf7" alt="GPLv3 license"></a>
<a href="https://t.me/shizu_talks"><img src="https://img.shields.io/badge/Telegram-Support-5baeb8?style=flat-square&logo=telegram" alt="Telegram support"></a>
</p>

<p>
<a href="#installation">Install</a> ·
<a href="#first-launch">First launch</a> ·
<a href="#commands">Commands</a> ·
<a href="#writing-modules">Write a module</a>
</p>

</div>

## What you get

| Feature | What it does |
| --- | --- |
| Modules | Install from links or files, browse repository catalogs, configure modules and manage aliases. Multiple public and private repositories are supported. |
| Web dashboard | Configure Shizu, manage modules, view logs, and download or restore encrypted backups. Browser access requires the account owner's approval. |
| Telegram control panel | Open `/panel` in your bot to manage startup, the prefix, the bot token and the dashboard. |
| BeSafe | Review third-party code before loading it. Approval cards arrive in a dedicated chat; dangerous account requests are blocked by default. |
| Inline and rich messages | Forms, galleries, buttons and rich layouts for modules. |
| Backups | Encrypted database backups with a configurable daily schedule and a separate recovery key. |
| Languages | English, Russian and Uzbek for the interface, with translated module settings. |

Shizu uses **Pyrogram** and supports **Telethon** through an optional separate login.
Enable it during setup or with `.enabletlmode`; `.disabletlmode` revokes the session.
Telethon sessions are encrypted, with a key generated automatically or supplied through
`SHIZU_SESSION_KEY`.

## Installation

### Linux and macOS

```bash
git clone https://github.com/ibeswipin/Shizu
cd Shizu
bash install.sh
```

The installer uses `uv` to prepare Python 3.11 and a virtual environment, installs
Shizu, and walks you through Telegram login. Existing configuration and sessions
are reused.

Run it as your normal user. You need **Git** and **curl or wget**. If a dependency
needs compilation, install your platform's build tools.

On Linux with systemd, the installer can create a service that runs as your user.
Service setup requires `sudo` and happens only after a successful login. An existing
`shizu.service` is preserved; keep the checkout at the same path once installed.

<details>
<summary><b>Manual installation</b></summary>

With Git and Python 3.11 installed:

```bash
git clone https://github.com/ibeswipin/Shizu
cd Shizu
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install .
python -m shizu
```

</details>

<details>
<summary><b>Startup and service commands</b></summary>

| Command | Purpose |
| --- | --- |
| `bash install.sh --no-start` | Install dependencies without login or service setup |
| `bash start.sh` | Run Shizu manually |
| `sudo systemctl restart shizu` | Restart the Linux service |
| `journalctl -u shizu -f` | Follow the service logs |

</details>

## First launch

Open the setup URL printed in the console. The web setup page is exposed through
a localhost.run tunnel.

1. Enter your **API ID** and **API Hash** from [my.telegram.org/apps](https://my.telegram.org/apps).
2. Scan the QR code in Telegram: **Settings → Devices → Link Desktop Device**. You can also log in with your phone number.
3. Enter your **2FA password** if your account has one.
4. Let Shizu create a bot, or provide the token for your own bot.

After setup, Shizu restarts and posts its status in **Shizu-logs**.
Use `.help` in a regular chat or in **Shizu-Expiriments** to get started.

| Startup flag | Purpose |
| --- | --- |
| `--no-web` | Use console login |
| `--port 8080` | Set the web setup port |
| `--setup-only` | Log in and exit without starting the userbot |

## Commands

The default prefix is **`.`**. Change it with `.setprefix` or through `/panel`.

| Command | Purpose |
| --- | --- |
| `.help` / `.help <module or command>` | Browse modules and command help |
| `.dlmod` / `.dlmod <name or link>` | Browse repository catalogs or install a module |
| `.loadmod` | Install a module from the file you reply to |
| `.unloadmod <name>` | Unload a module |
| `.config [module]` | Open module settings |
| `.web` / `.web stop` | Open the dashboard or close it and revoke browser sessions |
| `.restart` / `.update` / `.stop` | Restart, update or stop Shizu |
| `.checkupdate` | Check for new commits without installing them |
| `.setprefix <prefix>` / `.setbot <token>` | Change the command prefix or bot token |
| `.lang [code]` | Choose the interface language |
| `.backupdb` / `.restoredb` | Create or restore a database backup |
| `.autobackup` / `.backupkey` | Toggle daily backups or show the recovery key path |
| `.besafe` / `.apiprotect` | View BeSafe decisions or toggle API flood protection |
| `.owner [user]` | Open the owners panel or add/remove an owner |
| `.alias [alias] [command]` | List, add or delete command aliases |
| `.info` | Show your Shizu info card |

Send **`/panel`** to your bot to open its control panel.
Daily backup time is set in `.config ShizuBackuper`.

## Your Shizu folder

Shizu creates a **Shizu** chat folder containing your bot and these groups:

| Chat | Purpose |
| --- | --- |
| Shizu-logs | Logs, startup status and error reports |
| Shizu-backup | Encrypted database backups |
| Shizu-besafe | Module approval cards and security confirmations |
| Shizu-Expiriments | Messages, commands and module experiments |

While Shizu is running, user messages are automatically deleted from Logs,
Backups and BeSafe before commands or watchers run. Service messages and approval
buttons remain available. Use **Shizu-Expiriments** for your own messages and commands.

## Recovering a backup

Database backups are encrypted before they are sent to Telegram. The recovery key
is created on the first backup at `~/.config/shizu/backup.key`, outside the repository
and database. `.backupkey` shows its path without sending the key.

**Keep a separate copy of the key.** To restore on another server, copy the original
key there first. `SHIZU_BACKUP_KEY_FILE` lets you choose a different key file path.

## Writing modules

Build your own commands, watchers and inline interfaces with the module guides:

**[English](docs/modules.en.md) · [Русский](docs/modules.ru.md)**

The guides cover configuration, storage, translations, lifecycle hooks, loops,
shared libraries, Telethon compatibility and BeSafe, with complete examples.

## Community

[Support chat](https://t.me/shizu_talks) ·
[News](https://t.me/shizuhub) ·
[Report a bug](https://github.com/ibeswipin/Shizu/issues) ·
[Developer](https://t.me/hikamoru)

Licensed under [GNU GPLv3](LICENSE).
