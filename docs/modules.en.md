# Writing Shizu modules

🇷🇺 [Русская версия](modules.ru.md)

This guide covers everything a module can do in Shizu: commands, watchers,
config, storage, translations, the inline bot, loops and the safety rules every
third-party module runs under. All examples target the default Pyrogram mode.

- [Quick start](#quick-start)
- [Module file layout](#module-file-layout)
- [Commands](#commands)
- [Replying to messages](#replying-to-messages)
- [Who can run a command](#who-can-run-a-command)
- [Watchers](#watchers)
- [Message filters](#message-filters)
- [Config](#config)
- [Storing data](#storing-data)
- [Strings and translations](#strings-and-translations)
- [Lifecycle hooks](#lifecycle-hooks)
- [Loops](#loops)
- [Inline bot](#inline-bot)
- [Conversations](#conversations)
- [Dependencies and load conditions](#dependencies-and-load-conditions)
- [Shared libraries](#shared-libraries)
- [Utilities](#utilities)
- [Telethon and Hikka modules](#telethon-and-hikka-modules)
- [Security rules](#security-rules)
- [Full example](#full-example)
- [Troubleshooting](#troubleshooting)

## Quick start

```python
from pyrogram import Client, types

from shizu import loader


@loader.module(name="Hello", author="you", version=1.0)
class HelloMod(loader.Module):
    """Says hello"""

    @loader.command()
    async def hello(self, app: Client, message: types.Message):
        """Greet someone. Usage: hello <name>"""
        name = message.get_args_raw() or "world"
        await message.answer(f"👋 Hello, <b>{name}</b>!")
```

Install it in one of these ways:

| Way | Command |
|---|---|
| From a file | send `Hello.py` to any chat, reply to it with `.loadmod` |
| From a link | `.dlmod https://example.com/Hello.py` |
| Locally | put the file into `shizu/modules/` and restart |

Then run `.hello Shizu`. Use `.unloadmod Hello` to remove it and `.ml Hello`
to get its file or link back. Modules installed by link are downloaded again
on every start.

## Module file layout

```python
# required: requests beautifulsoup4

from pyrogram import Client, types

from shizu import loader, utils


@loader.module(name="Weather", author="you", version=1.2)
class WeatherMod(loader.Module):
    """Current weather for any city"""

    strings = {...}
    strings_ru = {...}

    def __init__(self):
        self.config = loader.ModuleConfig(...)

    async def on_load(self, app: Client): ...

    @loader.command()
    async def weather(self, app: Client, message: types.Message): ...
```

Rules the loader relies on:

- **`@loader.module(...)` must stand directly above the class line.** The
  loader looks for `@loader.module(...)` followed by `class Name(`. Without it
  a module loaded by file or link is rejected.
- The class inherits `loader.Module`. Its docstring is the module description
  in `.help`.
- `name` is the module name users see and the database section of the module.
  It must not clash with a core module (`ShizuHelp`, `ShizuLoader`, ...).
  Loading a module with the same class name or `name` as an installed one
  replaces it.
- `author` and `version` are optional.
- One module class per file.

Attributes Shizu sets on every module:

| Attribute | What it is |
|---|---|
| `self.app` | Pyrogram `Client` of the account |
| `self.db` | database (see [Storing data](#storing-data)) |
| `self.inline` | inline bot manager (see [Inline bot](#inline-bot)) |
| `self.bot` | same manager; `self.inline_bot` is the raw aiogram `Bot` |
| `self.me` | your account as a Pyrogram `User`; `self.tg_id` is its ID |
| `self.all_modules` | modules manager: `get_module(name)`, `modules`, `commands` |
| `self.prefix` | list of command prefixes; `self.get_prefix()` gives the first |
| `self.strings` | translated strings (see [Strings](#strings-and-translations)) |
| `self.lookup(name)` | another loaded module by name, `False` when missing |
| `self.tl`, `self.client` | Telethon client, only when Telethon mode is enabled |

## Commands

A command is an async method with `@loader.command()`:

```python
@loader.command(aliases=["w"], hidden=False)
async def weather(self, app: Client, message: types.Message):
    """Show the weather. Usage: weather <city>"""
```

- The command name is the method name in lower case: `weather` runs with
  `.weather`.
- A method whose name ends with `cmd` also becomes a command without the
  decorator: `weathercmd` is `.weather`.
- `aliases` adds extra names. Users can add their own aliases too.
- `hidden=True` hides the command from `.help`.
- The docstring is the description shown in `.help`. Put the usage there.
- The signature is always `(self, app, message)`.
- Commands also fire when you edit a message into a command.

Reading arguments:

| Call | `.weather New York` gives |
|---|---|
| `message.get_args_raw()` | `"New York"` (raw text after the command, `False` for an empty message) |
| `message.get_args()` | `"New York"` (words joined by single spaces) |
| `message.get_args_html()` | arguments with formatting as HTML |
| `utils.get_args_split_by(message, ",")` | list split by a separator |

The replied-to message is `message.reply_to_message`. `await utils.get_user(message)`
returns the user from the reply or the first argument, and
`await utils.get_target(message)` returns their ID.

Errors raised in a command are caught. The traceback is sent to the chat and
to the log chat, so you don't need a try/except around the whole handler.

## Replying to messages

Use `message.answer(...)` (or `utils.answer(message, ...)`). It edits your own
message or replies to someone else's, and handles long texts:

```python
await message.answer("✅ <b>Done</b>")
await message.answer(file_bytes, doc=True, caption="logs")
await message.answer("https://example.com/cat.jpg", photo_=True)
await message.answer("Choose:", reply_markup=[{"text": "OK", "callback": self.ok}])
```

- HTML is the default parse mode.
- Text longer than 4096 characters becomes an inline list with pages; if that
  fails, it is sent as `output.txt`.
- With `reply_markup` the answer is sent as an inline form (see
  [Inline bot](#inline-bot)).
- Custom emoji: `<emoji id=5372892693024218813>🥶</emoji>`.
- Escape user input with `utils.escape_html(text)`.
- Tables: `await utils.send_table(message, rows, header=[...], title="...")`.

Everything else is plain Pyrogram: `await app.send_message(...)`,
`await message.delete()`, `await app.get_chat(...)` and so on.

## Who can run a command

By default a command runs for:

- you (outgoing messages are always allowed);
- the owners set with `.owner`;
- users who were granted this command with `.permissions`.

Decorators widen access. Combine as many as needed:

```python
@loader.command()
@loader.group_admin_ban_users
@loader.pm
async def ban(self, app, message): ...
```

| Decorator | Allows |
|---|---|
| `@loader.owner` | owners |
| `@loader.sudo`, `@loader.support` | users granted the command with `.permissions` |
| `@loader.everyone` (`unrestricted`, `inline_everyone`) | anyone |
| `@loader.pm` | anyone in private chats |
| `@loader.group_member` | any member of a group |
| `@loader.group_owner` | the group creator |
| `@loader.group_admin` | any group admin |
| `@loader.group_admin_ban_users` | admins who can ban |
| `@loader.group_admin_delete_messages` | admins who can delete messages |
| `@loader.group_admin_pin_messages` | admins who can pin |
| `@loader.group_admin_invite_users` | admins who can invite |
| `@loader.group_admin_change_info` | admins who can change chat info |
| `@loader.group_admin_add_admins` | admins who can add admins |

Other command decorators:

- `@loader.ratelimit` limits other users to 3 calls per 10 seconds per command.
  Your own calls are never limited.
- `@loader.on(filters.private)` adds a Pyrogram filter. The command runs only
  when the filter passes. A plain function works too, with the signature
  `(flt, app, message)`.
- `@loader.tag(...)` runs the command only for matching messages, using the
  [message filters](#message-filters):

```python
@loader.command()
@loader.tag("only_groups", "only_reply")
async def warn(self, app, message): ...
```

Inside your code you can check a user with
`await self.all_modules.check_security(message, self.some_command)`.

## Watchers

A watcher receives every new and edited message the account sees:

```python
@loader.watcher(only_messages=True, no_commands=True)
async def watcher(self, app: Client, message: types.Message):
    if "shizu" in message.text.lower():
        await message.reply("👀")
```

- A method becomes a watcher through `@loader.watcher(...)` or through a name
  containing `watcher`. Names starting with `_` are ignored.
- The signature is `(self, app, message)` or `(self, message)`.
- Keyword switches:

| Argument | Default | Effect |
|---|---|---|
| `only_messages` | `True` | skip messages without text or caption |
| `no_commands` | `False` | skip messages starting with a command prefix |
| `no_stickers`, `no_docs`, `no_audios`, `no_videos`, `no_photos` | `False` | skip that media type |
| `no_forwards` | `False` | skip forwarded messages |

- The watcher also accepts the [message filters](#message-filters):

```python
@loader.watcher("out", "only_groups", regex=r"^!\w+")
async def bang_watcher(self, app, message): ...
```

- Once you pass any string tag, `only_messages` is off unless you list it:
  `@loader.watcher("only_pm", "only_messages")`.
- A watcher sees your own messages too, including the command that triggered
  your module. Return early when you don't need them.
- Keep watchers fast: they run for every message. Move slow work into
  `utils.spawn(coro)`.
- An exception in one watcher is logged and doesn't stop the others.

## Message filters

`@loader.tag(...)` and `@loader.watcher(...)` take the same filters. All of
them must match. Tags are strings:

| Tag | Matches |
|---|---|
| `out` / `in` | your messages / messages from others |
| `only_pm` / `no_pm` | private chats (including bots) |
| `only_groups` / `no_groups` | groups and supergroups |
| `only_channels` / `no_channels` | channels |
| `only_media` / `no_media` | any media |
| `only_photos` / `no_photos` | photos |
| `only_videos` / `no_videos` | videos |
| `only_audios` / `no_audios` | audio files and voice messages |
| `only_docs` / `no_docs` | documents |
| `only_stickers` / `no_stickers` | stickers |
| `only_forwards` / `no_forwards` | forwarded messages |
| `only_reply` / `no_reply` | replies |
| `only_inline` / `no_inline` | messages sent via a bot |
| `mention` / `no_mention` | messages that mention you |
| `only_commands` / `no_commands` | messages starting with a command prefix |
| `editable` | your own messages that aren't forwarded |

Keyword filters:

| Filter | Matches when |
|---|---|
| `startswith="!"` | the text (or caption) starts with the value |
| `endswith="?"` | the text ends with the value |
| `contains="shizu"` | the text contains the value |
| `regex=r"\d+"` | `re.search` finds the pattern in the text |
| `from_id=123` | the sender ID equals the value |
| `chat_id=-100123` | the chat ID equals the value |
| `filter=func` | `func(message)` returns a true value |

A tag can also be passed as a keyword: `@loader.tag(only_pm=True)` is the same
as `@loader.tag("only_pm")`.

## Config

Config values are edited by users with `.config` and saved automatically.

```python
def __init__(self):
    self.config = loader.ModuleConfig(
        loader.ConfigValue(
            "city",
            "London",
            "Default city",
            validator=loader.validators.String(min_len=2),
        ),
        loader.ConfigValue(
            "units",
            "metric",
            lambda: self.strings("units_doc"),
            validator=loader.validators.Choice(["metric", "imperial"]),
        ),
        loader.ConfigValue(
            "api_key",
            None,
            "API key from openweathermap.org",
            validator=loader.validators.Hidden(loader.validators.String()),
        ),
    )
```

Read a value with `self.config["city"]`. Assigning `self.config["city"] = "Paris"`
validates and saves it.

- The description may be a string or a function returning one, which lets you
  translate it.
- Before the first `.config` change, a value can come from the environment
  variable `ModuleName.key` (for example `Weather.city`).
- A stored value that no longer passes the validator falls back to the default.
- The short legacy form `loader.ModuleConfig("key", default, "doc", "key2", default2, "doc2")`
  also works but has no validators.

Validators (`loader.validators.*`):

| Validator | Accepts |
|---|---|
| `Integer(minimum=, maximum=)` | integers |
| `Float(minimum=, maximum=)` | numbers |
| `Boolean()` | `true/false`, `1/0`, `yes/no`, `on/off` |
| `String(length=, min_len=, max_len=)` | text |
| `RegExp(pattern, description=, flags=)` | text matching a regex |
| `Choice([...])` | one of the given values |
| `MultiChoice([...])` | a list of the given values |
| `Series(validator=, min_len=, max_len=, fixed_len=)` | a list; accepts JSON or comma-separated text |
| `Link()` | an http(s) URL |
| `TelegramID()` | a numeric Telegram ID |
| `EntityLike()` | an ID, `@username` or `t.me` link |
| `Emoji(length=, min_len=, max_len=)` | emoji only |
| `Union(v1, v2, ...)` | the first validator that passes |
| `NoneType()` | `None` |
| `Hidden(validator)` | same as the inner validator, for secrets |

A validator raises `ValueError` to reject a value. To write your own, make any
object with a `validate(value)` method that returns the cleaned value.

When you rename a module, call `self.adopt_config("OldName")` in `on_load`
to carry over saved values.

## Storing data

Every module has its own database section named after `name`:

```python
self.set("last_city", "Berlin")
city = self.get("last_city", "London")
```

For lists and dicts use a pointer. It saves itself on every change:

```python
self.history = self.pointer("history", [])
self.history.append("Berlin")

self.cache = self.pointer("cache", {})
self.cache["Berlin"] = 12
```

A pointer only notices changes made through it. After changing a nested object
(`self.cache["Berlin"]["temp"] = 12`), assign it again:
`self.cache["Berlin"] = value`.

The raw database is `self.db`: `self.db.get(section, key, default)`,
`self.db.set(section, key, value)`, `self.db.pop(section, key)`. Values must be
JSON-serialisable. Don't write into other modules' sections or the `shizu.*`
sections.

## Strings and translations

Keep user-facing text in `strings` and add a dict per language:

```python
strings = {
    "done": "✅ Saved {}",
}

strings_ru = {
    "done": "✅ Сохранено {}",
}
```

`self.strings("done")` (or `self.strings["done"]`) returns the text in the
language chosen with `.lang`, falling back to `strings`. The attribute name
is `strings_<code>`: `strings_ru`, `strings_uz`, `strings_de` and so on. A
missing key returns `"Unknown string"`.

## Lifecycle hooks

```python
async def on_load(self, app):
    """After the module is loaded and its config is restored"""

async def client_ready(self, client, db):
    """Right after on_load; gets the client and the database"""

async def on_unload(self):
    """When the module is unloaded or replaced"""

async def on_dlmod(self, client, db):
    """Once, after the module is installed by link"""
```

All hooks are optional and may take fewer arguments. Unloading also stops the
module's loops and removes its handlers.

To stop loading with a message, raise `loader.LoadError("reason")` from
`on_load` or `client_ready`. To unload quietly, raise `loader.SelfUnload()`.
Any other exception in a hook is logged and the module stays loaded.

## Loops

```python
@loader.loop(interval=600, autostart=True)
async def refresh(self):
    await self.update_cache()

@loader.loop(time=["09:00", "21:00"], autostart=True)
async def digest(self):
    await self.app.send_message("me", "📰 Digest")
```

- Give exactly one of `interval` (seconds) or `time` (`"HH:MM"` or a list,
  server time).
- Either can be a config key: `interval="refresh_seconds"` reads the value
  from `self.config`, so users can change it.
- `autostart=True` starts the loop when the module loads.
- `wait_before=True` sleeps before each run instead of after.
- Control it from code: `self.refresh.start()`, `await self.refresh.stop()`,
  `self.refresh.status`.
- Raise `loader.StopLoop` inside the loop to stop it.

## Inline bot

Every Shizu install has its own bot. Modules use it to send messages with
buttons from your account, through `self.inline`.

### Forms

```python
await self.inline.form(
    text="🌤 <b>Weather</b>",
    message=message,
    reply_markup=[
        [
            {"text": "🔄 Refresh", "callback": self.refresh_cb, "args": (city,)},
            {"text": "🌐 Site", "url": "https://openweathermap.org"},
        ],
        [{"text": "✖️ Close", "callback": self.close_cb}],
    ],
)
```

`message` is a `Message` (the form replaces or answers it) or a chat ID.
`form()` returns the form ID or `False`.

`reply_markup` is a list of rows; each row is a list of buttons. A single
button or a single row also works. Button keys:

| Key | Meaning |
|---|---|
| `text` | button label |
| `callback` | method called when the button is pressed |
| `args`, `kwargs` | extra arguments for `callback` (or `handler`) |
| `url` | link button |
| `data` | raw callback data; handle it in a callback handler |
| `input` + `handler` | asks the user for text, then calls `handler(call, text, *args)` |

A callback receives the button press:

```python
async def refresh_cb(self, call, city: str):
    await call.answer("Updating…")
    await call.edit(
        f"🌤 {city}: 21°C",
        reply_markup=[{"text": "✖️ Close", "callback": self.close_cb}],
    )

async def close_cb(self, call):
    await call.delete()
```

- `call.edit(text, reply_markup=None)` changes the form; without
  `reply_markup` the buttons are removed.
- `call.delete()` deletes the form.
- `call.answer(text, show_alert=False)` shows a toast.
- `call.from_user` is who pressed it; `call.form` is the stored form.

Other `form()` options:

| Option | Meaning |
|---|---|
| `force_me=True` | only you and owners may press buttons |
| `always_allow=[ids]` | extra users who may press buttons |
| `disable_security=True` | anyone may press buttons |
| `ttl=seconds` | the form expires after this time |
| `photo=`, `video=`, `gif=`, `audio=` | URL of media to send with the text |
| `msg_id=` | message ID to reply to |
| `silent=True` | no "Loading inline form..." placeholder |
| `rich=True` | rich message with buttons inside the text, see below |
| `rich_message={...}` | raw Bot API `InputRichMessage` payload |

### Buttons inside the text (rich forms)

With `rich=True` a button that has a `ref` key is placed inside the text
instead of the keyboard:

```python
await self.inline.form(
    text='Module updated. <tg-button ref="log">show log</tg-button>',
    message=message,
    rich=True,
    reply_markup=[
        {"ref": "log", "callback": self.show_log, "style": "link"},
        {"text": "Close", "callback": self.close_cb},
    ],
)
```

- The label is the text between the tags; the button needs `url`,
  `callback` or `data`.
- `style` is `danger`, `success`, `primary` or `link`; `link` works only for
  callback buttons and looks like an ordinary link.
- Buttons without `ref` stay in the keyboard under the message.
- If Telegram rejects the rich message, the form is sent as plain text with
  the labels left as text.
- Telegram lets only bots send rich messages, so they always go through the
  inline bot; `app.send_message` can't send them.
- Rich forms use Bot API 10.3. Telegram apps that don't support rich
  messages yet may show them differently.

### Lists and galleries

```python
await self.inline.list(message, ["page 1", "page 2", "page 3"])

await self.inline.gallery(
    message,
    ["https://.../1.jpg", "https://.../2.jpg"],
    caption="Cats",
)
```

`gallery` also accepts a function (sync or async) instead of a list; it must
return a URL or a list of URLs and is called for more photos as the user
scrolls.

### Inline commands

Inline commands run when someone types `@your_bot name args`:

```python
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

@loader.inline_handler()
async def weather_inline_handler(self, app, inline_query, args):
    """Weather in inline mode"""
    await inline_query.answer(
        [
            InlineQueryResultArticle(
                id=utils.random_id(),
                title=f"Weather in {args or 'London'}",
                input_message_content=InputTextMessageContent("🌤 21°C"),
            )
        ],
        cache_time=0,
    )
```

- The command name is the method name without `_inline_handler`, or the name
  passed to `@loader.inline_handler("name")`.
- A method ending with `_inline_handler` works without the decorator.
- The signature is `(app, inline_query, args)` or `(app, inline_query)`;
  `inline_query.args` holds the arguments too.
- Only you and owners can use inline commands; add `@loader.everyone` to open
  one to everybody.
- `inline_query` is an aiogram 2 object.

### Bot updates

- `@loader.callback_handler()` on a method (or a name ending with
  `_callback_handler`) receives **every** button press of the bot as
  `(call)`. Check `call.data` and return early for foreign buttons. Use it
  for `data` buttons.
- A method named `<name>_message_handler(self, app, message)` receives
  messages sent to the bot in private, by default only yours. Add
  `@loader.on_bot(lambda self, app, message: True)` to accept others.
- `self.inline.ss(user_id, state)` and `self.inline.gs(user_id)` keep a
  simple per-user state for bot dialogs.

## Conversations

To talk to another bot step by step, use `fsm.Conversation`:

```python
from shizu import fsm

async with fsm.Conversation(app, "@BotFather", purge=True) as conv:
    await conv.ask("/mybots")
    reply = await conv.get_response(timeout=30)
```

`purge=True` deletes the dialog messages afterwards. `ask_media(path, "photo")`
sends a file.

## Dependencies and load conditions

Special comments at the top of the file:

| Comment | Effect |
|---|---|
| `# required: requests bs4` | pip packages installed when an import fails, then the module loads again |
| `# only: 123456,789012` | loads only on these account IDs |
| `# tl-only` | loads only when Telethon mode is enabled |

Packages go into the virtualenv, or into `.module_dependencies` when Shizu
runs without one. Set the `SHIZU_DEPS_DIR` environment variable to install
them into another directory instead, for example a Docker volume, so they
survive container rebuilds. Install time is shown in the log chat; if pip
fails, its error is sent there too.

Import heavy or optional packages inside functions if the module should load
without them.

## Shared libraries

Code shared by several modules can live in a library:

```python
from shizu import loader


class WeatherLib(loader.Library):
    name = "WeatherLib"
    developer = "you"
    version = 1

    async def init(self):
        self.session = ...

    async def fetch(self, city: str) -> dict: ...
```

In a module:

```python
async def on_load(self, app):
    self.lib = await self.import_lib("https://example.com/weather_lib.py")
```

A library is downloaded once per URL and shared between modules. It has
`self.client`, `self.db`, `self.inline`, `self.get/set/pointer` (its own
section) and supports `# required:`. Libraries go through the same approval
as modules.

## Utilities

`from shizu import utils`:

| Function | Purpose |
|---|---|
| `escape_html(text)` | escape `<`, `>`, `&` |
| `remove_html(text)` | strip tags |
| `answer(message, text, ...)` | same as `message.answer` |
| `answer_file(message, file, caption=)` | send a file |
| `send_table(message, rows, header=, title=)` | table as a rich message, falls back to `<pre>` |
| `get_user(message)` / `get_target(message)` | user / user ID from reply or arguments |
| `get_chat_id(message)` | chat ID |
| `get_display_name(entity)` | name of a user or title of a chat |
| `get_message_link(message)`, `get_entity_url(entity)` | links |
| `run_sync(func, *args)` | run blocking code in a thread |
| `spawn(coro)` | start a background task safely |
| `chunks(list, n)` | split a list into parts of `n` |
| `rand(n)` / `random_id()` | random strings |
| `formatted_uptime()` | userbot uptime |

Module helpers on `self`:

| Method | Purpose |
|---|---|
| `await self.invoke("help", "Notes", message=message)` | run another command |
| `await self.animate(message, frames, interval)` | edit a message through frames |
| `await self.request_join(peer, reason)` | ask you in the bot chat to join a chat |
| `self.all_modules.get_module("Name")` | another module |

## Telethon and Hikka modules

When Telethon mode is enabled (`.enabletlmode`), Shizu also loads Telethon
modules, including most Hikka/Heroku modules. They are detected by their
imports and signatures (`async def cmd(self, message)`, `@loader.tds`,
`from .. import`) and converted on load. In these modules:

- handlers take `(self, message)` with a Telethon message;
- `self.client` is the Telethon client;
- [message filters](#message-filters) work the same way;
- `@loader.raw_handler(UpdateType)` receives raw Telethon updates.

Without Telethon mode such modules don't load. For new modules prefer the
Pyrogram style described above.

## Security rules

Third-party modules run inside Shizu's process, but these guards apply:

- **Approval.** A module from an unknown source isn't run until you approve
  it in the bot: you get a card with its imports, hosts and risky calls. Links
  from the official ShizuMods repository are trusted. Updated code needs
  approval again.
- **Blocked methods.** Calls that can take over the account are refused:
  exporting or importing authorizations, login tokens, sessions list and
  reset, password and 2FA, phone change, account deletion, sign-in and
  log out.
- **Session files.** Modules can't open `*.session` files or the session
  storage.
- **Login codes.** Handlers of third-party modules never receive messages
  from Telegram's service account (777000).

Calling a blocked method raises `BeSafe.Forbidden`, and you get a notice
naming the module. Don't try to work around these checks: such a module will
be removed from the trusted list.

General advice:

- Never log or send tokens, `config.ini` or database contents.
- Use `validators.Hidden` for secrets in config.
- Use `run_sync` for blocking network or disk calls so the userbot doesn't
  freeze.

## Full example

```python
# required: humanize

import time

import humanize
from pyrogram import Client, types

from shizu import loader, utils


@loader.module(name="Notes", author="you", version=1.0)
class NotesMod(loader.Module):
    """Personal notes with an inline menu"""

    strings = {
        "saved": "📝 Note <b>{}</b> saved",
        "empty": "📭 No notes yet",
        "no_args": "❌ Usage: <code>{}note name text</code>",
        "deleted": "🗑 Deleted",
    }

    strings_ru = {
        "saved": "📝 Заметка <b>{}</b> сохранена",
        "empty": "📭 Заметок пока нет",
        "no_args": "❌ Использование: <code>{}note имя текст</code>",
        "deleted": "🗑 Удалено",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "max_notes",
                50,
                "Maximum number of notes",
                validator=loader.validators.Integer(minimum=1, maximum=500),
            ),
            loader.ConfigValue(
                "cleanup_hours",
                24,
                "Delete notes older than this many hours",
                validator=loader.validators.Integer(minimum=1),
            ),
        )

    async def on_load(self, app: Client):
        self.notes = self.pointer("notes", {})

    @loader.command(aliases=["n"])
    async def note(self, app: Client, message: types.Message):
        """Save a note. Usage: note <name> <text>"""
        args = message.get_args_raw()
        if not args or len(args.split(maxsplit=1)) < 2:
            return await message.answer(
                self.strings("no_args").format(self.get_prefix())
            )

        name, text = args.split(maxsplit=1)
        if len(self.notes) >= self.config["max_notes"]:
            self.notes.pop(next(iter(self.notes)))
        self.notes[name] = {"text": text, "at": time.time()}
        await message.answer(self.strings("saved").format(utils.escape_html(name)))

    @loader.command()
    async def notes(self, app: Client, message: types.Message):
        """Show all notes"""
        if not self.notes:
            return await message.answer(self.strings("empty"))

        lines = [
            f"▫️ <b>{utils.escape_html(name)}</b> · "
            f"{humanize.naturaltime(time.time() - note['at'])}"
            for name, note in self.notes.items()
        ]
        await self.inline.form(
            text="\n".join(lines),
            message=message,
            reply_markup=[
                [
                    {
                        "text": f"🗑 {name}",
                        "callback": self.delete_note,
                        "args": (name,),
                    }
                    for name in list(self.notes)[:3]
                ]
            ],
        )

    async def delete_note(self, call, name: str):
        self.notes.pop(name, None)
        await call.edit(self.strings("deleted"))

    @loader.watcher(only_messages=True, no_commands=True)
    async def watcher(self, app: Client, message: types.Message):
        if message.outgoing and message.text == "!notes":
            await message.answer(", ".join(self.notes) or self.strings("empty"))

    @loader.loop(interval=3600, autostart=True)
    async def cleanup(self):
        border = time.time() - self.config["cleanup_hours"] * 3600
        for name in [n for n, note in self.notes.items() if note["at"] < border]:
            del self.notes[name]
```

## Troubleshooting

| Problem | Cause |
|---|---|
| Module isn't loaded, no error | `@loader.module(...)` isn't directly above `class`; or the module waits for approval in the bot |
| `NFA` on load | `# only:` doesn't list your account |
| `OTL` on load | the module needs Telethon mode (`.enabletlmode`) |
| Command doesn't respond to others | default access is you, owners and `.permissions`; add a security decorator |
| Watcher with tags also gets media without text | string tags turn `only_messages` off; add the `"only_messages"` tag |
| Pointer change isn't saved | a nested object was changed; assign the key again |
| `Unknown string` | the key is missing from `strings` |
| Buttons say "This button has expired" | the form was dropped after a restart or `ttl`; send a new one |
| Loading fails after installing packages | the package name in `# required:` differs from the import name |

Logs: `.logs` sends the log file; command errors also go to the log chat.
