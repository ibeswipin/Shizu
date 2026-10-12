# Shizu modules: from a first command to a complete example

[Русский](modules.ru.md) · [Back to README](../Readme.md)

This is a practical guide for **Pyrogram**. Start with a small module, then add
settings, persistent data and buttons. The [complete Notes.py](#example) at the
end is ready to install.

| What you want to build | Section |
| --- | --- |
| Your first installable module | [Quick start](#start) |
| Arguments and reply handling | [Commands and messages](#commands) |
| Settings and translated text | [Config](#config) · [Translations](#translations) |
| Data that survives a restart | [Storage](#storage) |
| A menu, table or gallery | [Buttons and rich text](#inline) |
| Message handlers and background work | [Watchers](#watchers) · [Tasks](#tasks) |
| Dependencies and restrictions | [Loading and access](#loading) |

<a id="start"></a>

## 1. Your first module

Save this as `Hello.py`:

```python
from pyrogram import Client, types

from shizu import loader, utils


@loader.module(name="Hello", author="you", version=1.0)
class HelloMod(loader.Module):
    """A greeting command."""

    @loader.command()
    async def hello(self, app: Client, message: types.Message):
        """Say hello: hello <name>."""
        name = message.get_args_raw() or "world"
        await message.answer(f"Hello, <b>{utils.escape_html(name)}</b>!")
```

1. Send the file to **Shizu-Expiriments** or another regular chat.
2. Reply to the file with `.loadmod`.
3. If BeSafe asks, review the code and approve it in **Shizu-besafe**.
4. Run `.hello Shizu`. The response is **Hello, Shizu!**

Use `.dlmod <link>` to install from a URL. GitHub `/blob/` links are supported.
`.unloadmod Hello` unloads the module.

| Code | Why it is there |
| --- | --- |
| `@loader.module(...)` | Sets the module name, author and version |
| `class HelloMod(loader.Module)` | Provides Shizu's module methods and state |
| `@loader.command()` | Registers the method as `.hello` |
| `async def hello(self, app, message)` | Receives the module, client and command message |
| `message.get_args_raw()` | Reads text after the command name |
| `utils.escape_html(name)` | Displays user input without treating it as HTML tags |
| `message.answer(...)` | Sends a response or edits your outgoing command |

Use one module class per file, with `@loader.module(...)` above it. Choose a
unique module name: loading the same module again replaces it. Class and command
docstrings appear in `.help`.

> Indented methods and fields below belong **inside your module class**.
> Imports stay at the top of the file. You can try the examples independently.

<a id="commands"></a>

## 2. Commands, arguments and responses

### Validate the arguments

```python
    @loader.command(aliases=["hi"], ru_doc="Поздороваться: greet <имя>.")
    async def greet(self, app: Client, message: types.Message):
        """Say hello: greet <name>."""
        name = message.get_args_raw()
        if not name:
            return await message.answer(
                f"Usage: <code>{self.get_prefix()}greet name</code>"
            )
        await message.answer(f"Hello, <b>{utils.escape_html(name)}</b>!")
```

Run `.greet Anna` or `.hi Anna`. Without a name, the command shows its usage.
`aliases` provides alternative names; `ru_doc` supplies Russian command help.

| Call | Result for `.greet New York` |
| --- | --- |
| `message.get_args_raw()` | `"New York"`; preserves the original spacing |
| `message.get_args()` | `"New York"`; joins words with single spaces |
| `message.get_args_html()` | Arguments with formatting represented as HTML |

### Read a reply

```python
    @loader.command()
    async def quote(self, app: Client, message: types.Message):
        """Show the text of the replied-to message."""
        reply = message.reply_to_message
        if reply is None:
            return await message.answer("Reply to a message first.")
        text = reply.text or reply.caption or "No text in this message."
        await message.answer(f"<blockquote>{utils.escape_html(text)}</blockquote>")
```

Media messages may keep their text in `caption`, so check both fields. This
example displays plain source text inside a quote. To use the source formatting
as HTML, read `reply.text.html` or `reply.caption.html` when that field exists.

`message.answer` accepts supported HTML tags such as `<b>`, `<i>`, `<code>` and
`<a>`. It is the same helper as `utils.answer(message, text)`. Use `app` for direct
Telegram calls, for example `await app.send_message("me", "Hello")`.

<a id="config"></a>

## 3. Config with readable labels

```python
    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "city",
                "London",
                "Default city for the command.",
                validator=loader.validators.String(min_len=2),
                label="City",
            ),
            loader.ConfigValue(
                "api_key",
                None,
                "Token for the external service.",
                validator=loader.validators.Hidden(loader.validators.String()),
                label="API token",
            ),
        )
```

Open `.config <module name>`. Users see **City** and **API token** buttons, while
your code reads `self.config["city"]` and `self.config["api_key"]`.

| Parameter | Meaning in this example |
| --- | --- |
| `key` | `city`: the stable storage key used by your code |
| `default` | `London`: the value before configuration |
| `doc` | A description that helps the user choose a value |
| `validator` | Checks and converts user input |
| `label` | A short button title, separate from the storage key |

Assigning `self.config["city"] = "Paris"` validates and saves the value. `Hidden`
masks a secret in the config interface; the module still receives its actual value.

<details>
<summary><b>Common validators</b></summary>

| Validator | Use |
| --- | --- |
| `Integer(minimum=1, maximum=20)` | An integer in a range |
| `Float(minimum=0)` | A number with a fractional part |
| `Boolean()` | A toggle |
| `String(min_len=2, max_len=100)` | Text with length bounds |
| `Choice(["light", "dark"])` | One of the listed values |
| `Series(validator=loader.validators.Link())` | A list of links |
| `Link()` | An HTTP(S) URL format |
| `RegExp(r"^[a-z]+$")` | Text matching a regular expression |
| `Hidden(loader.validators.String())` | A masked text value |

Validators live in `loader.validators`. `Series` accepts JSON lists or
comma-separated values. URL format validation does not check site availability.

</details>

<a id="translations"></a>

## 4. Text and translations

```python
    strings = {"greeting": "Hello, <b>{}</b>!", "city_label": "City"}
    strings_ru = {"greeting": "Привет, <b>{}</b>!", "city_label": "Город"}

    @loader.command()
    async def welcome(self, app: Client, message: types.Message):
        """Greet someone in the selected interface language."""
        name = utils.escape_html(message.get_args_raw() or "Shizu")
        await message.answer(self.strings("greeting").format(name))
```

`strings` contains base text; `strings_ru` supplies Russian translations. You can
add `strings_uz` or other languages. Shizu selects the interface language and
falls back to `strings` for missing translations.

For translated config labels, pass a function:
`label=lambda: self.strings("city_label")`. Use the same pattern for `doc`.
The function is evaluated after translations are set up, so use `lambda` rather
than calling `self.strings(...)` directly in `__init__`.

<a id="storage"></a>

## 5. Data and lifecycle

```python
    async def on_load(self, app: Client):
        self.items = self.pointer("items", {})

    @loader.command()
    async def save(self, app: Client, message: types.Message):
        """Save text in the module database."""
        text = message.get_args_raw()
        if not text:
            return await message.answer("Pass some text to save.")
        self.items["latest"] = text
        self.set("saved_count", self.get("saved_count", 0) + 1)
        await message.answer("Saved.")
```

`on_load` runs after Shizu assigns the client, database, translations and restored
config. Initialize the state your commands need here.

| API | Purpose |
| --- | --- |
| `self.get("key", default)` | Read from this module's database section |
| `self.set("key", value)` | Save a JSON-compatible value |
| `self.pointer("items", {})` | A dict that saves top-level changes |
| `self.pointer("items", [])` | A list that saves insertions and deletions |

Data survives restarts. Inside a method, change a copy of a nested dict and assign it back;
mutating the nested object itself does not trigger a save:

```python
item = dict(self.items["profile"])
item["name"] = "Shizu"
self.items["profile"] = item
```

This last fragment assumes `profile` already holds a dict.

<details>
<summary><b>Properties and hooks</b></summary>

| Property or hook | Purpose |
| --- | --- |
| `self.app`, `self.me` | The Pyrogram client and owner account |
| `self.inline`, `self.bot` | The inline bot manager |
| `self.db` | Shizu's database |
| `self.get_prefix()` | The first current command prefix |
| `self.lookup("Name")` | A loaded module, or `False` |
| `on_load(self, app)` | Initialize module state |
| `client_ready(self, client, db)` | An additional hook after `on_load` |
| `on_unload(self)` | Release resources when unloading |

Raise `loader.LoadError("reason")` in `on_load` to abort loading with a clear
reason. Unloading stops the module's loops and removes its handlers.

</details>

<a id="inline"></a>

## 6. Buttons, rich text and galleries

### A button menu

```python
    @loader.command()
    async def menu(self, app: Client, message: types.Message):
        """Open a menu with a callback and a link."""
        await self.inline.form(
            text="<b>Module menu</b>",
            message=message,
            reply_markup=[
                [
                    {"text": "Check", "callback": self.check_cb, "args": ("ready",)},
                    {"text": "Source", "url": "https://github.com/ibeswipin/Shizu"},
                ],
                [{"text": "Close", "callback": self.close_cb}],
            ],
            force_me=True,
            ttl=600,
        )

    async def check_cb(self, call, status: str):
        await call.answer(f"Status: {status}", show_alert=True)

    async def close_cb(self, call):
        if not await call.delete():
            return await call.answer("Could not delete the message.", show_alert=True)
        await call.answer()
```

`reply_markup` is a list of keyboard rows. `args` passes `"ready"` to
`check_cb(call, status)`. A URL button opens a link; a callback button invokes
one of your methods.

| Call or option | Purpose |
| --- | --- |
| `call.answer(text, show_alert=True)` | Acknowledge the press with a notification |
| `call.edit(text, reply_markup=rows)` | Update the form text and buttons |
| `call.delete()` | Delete the form message; returns the deletion result |
| `force_me=True` | Restrict buttons to the account owner and configured owners |
| `always_allow=[123456]` | Allow additional users |
| `ttl=600` | Expire buttons after ten minutes; does not delete the message |

Old callback buttons may expire after a restart: run the command again.
Forms with callback buttons use the inline bot to process presses.

### Rich text and tables

```python
    @loader.command()
    async def status(self, app: Client, message: types.Message):
        """Show a rich table."""
        await utils.send_table(
            message,
            [["State", "Ready"], ["Notes", str(self.get("saved_count", 0))]],
            header=["Item", "Value"],
            title="Module status",
        )
```

`utils.send_table` builds a rich table with a text fallback. For your own HTML,
use `await message.answer("<h2>Status</h2><p>Ready</p>", rich=True)`.
`rich_message` supplies rich markup separately from fallback text:

```python
await message.answer(
    "Status: ready",
    rich_message={"html": "<h2>Status</h2><p>Ready</p>"},
)
```

Shizu routes rich messages using the **account owner's Telegram Premium** status:
Premium accounts send directly; other accounts use the inline bot. Forms with
callback or input buttons use the bot regardless of Premium.

<details>
<summary><b>A button inside rich text</b></summary>

This method uses `check_cb` and `close_cb` from the menu example above:

```python
    @loader.command()
    async def richmenu(self, app: Client, message: types.Message):
        """Place a callback button inside the text."""
        await self.inline.form(
            text='Module is ready. <tg-button ref="check">Check status</tg-button>',
            message=message,
            rich=True,
            reply_markup=[
                {"ref": "check", "callback": self.check_cb, "args": ("ready",), "style": "link"},
                {"text": "Close", "callback": self.close_cb},
            ],
        )
```

`ref="check"` connects the text tag to its `reply_markup` entry. The tag's content
is the button label. Buttons without `ref` stay below the message.
Complete standalone module: [RichButtons.py](examples/RichButtons.py).

</details>

<details>
<summary><b>Pages and a gallery</b></summary>

Inside a command:

```python
await self.inline.list(message, ["First page", "Second page"])

await self.inline.gallery(
    message,
    ["https://example.com/first.png", "https://example.com/second.png"],
    caption="Gallery",
)
```

The gallery's Close button sits below the other controls and deletes the message.
Instead of a list, you can pass a function returning a URL or a list of URLs
for the next images.

</details>

<a id="watchers"></a>

## 7. Watchers and command access

```python
    @loader.watcher("in", "only_groups", "only_messages", no_commands=True)
    async def activity_watcher(self, app: Client, message: types.Message):
        if message.from_user and not message.from_user.is_bot:
            self.set("last_sender", message.from_user.id)
```

This watcher remembers the sender of an incoming text message in a group. It skips
commands and bot messages. String tags are combined with **and**. When using tags,
include `only_messages` explicitly if you require text or a caption.

Commands are available to you, configured owners and users granted access by
default. Declare wider permissions for a public command:

```python
    @loader.command()
    @loader.everyone
    @loader.ratelimit
    async def ping(self, app: Client, message: types.Message):
        """Check whether the module responds."""
        await message.answer("Pong.")
```

`@loader.everyone` opens the command to anyone; `@loader.ratelimit` limits other
users to three calls per ten seconds per command. Other access decorators include
`@loader.group_admin`, `@loader.group_owner`, `@loader.group_member` and `@loader.pm`.
Access permissions and message filters are separate checks: `only_groups` limits
the chat type but does not grant other people command access.

<details>
<summary><b>Compact filter reference</b></summary>

| Filter | Messages that pass |
| --- | --- |
| `in` / `out` | Incoming / outgoing |
| `only_pm` / `only_groups` | Private chats / groups |
| `only_messages` | Text or caption present |
| `only_reply` / `no_reply` | With / without a reply |
| `only_media` / `no_media` | With / without media |
| `only_photos`, `only_videos`, `only_docs` | The corresponding media type |
| `no_commands` | No command prefix |
| `contains="Shizu"`, `startswith="!"` | Text checks |
| `regex=r"^!hello"` | Regular expression search |
| `from_id=123456`, `chat_id=-1001234567890` | Sender or chat checks |

For commands, use `@loader.tag("only_groups", "only_reply")`. For watchers,
pass the same filters to `@loader.watcher(...)`.

</details>

User messages in Logs, Backups and BeSafe are removed before commands or watchers
run. Try your examples in **Shizu-Expiriments** or a regular chat.

<a id="tasks"></a>

## 8. Background tasks

### A repeating loop

```python
    @loader.loop(interval=600, autostart=True, wait_before=True)
    async def heartbeat(self):
        self.set("heartbeat_count", self.get("heartbeat_count", 0) + 1)
```

The loop increments a stored counter every ten minutes. `wait_before=True` delays
the first run. Stop it with `await self.heartbeat.stop()` and start it with
`self.heartbeat.start()`. A config key can supply the interval:
`interval="refresh_seconds"`.

For a daily schedule, use `time="09:00"` or a list of times. These are in
**server time**. Specify either `time` or `interval`, never both.

### A persistent one-off task

```python
    @loader.command()
    async def remind(self, app: Client, message: types.Message):
        """Send a reminder in one minute: remind <text>."""
        text = message.get_args_raw()
        if not text:
            return await message.answer("Pass reminder text.")
        task_id = self.schedule(
            60, "deliver_reminder", {"chat_id": message.chat.id, "text": text}
        )
        await message.answer(f"Reminder scheduled: <code>{task_id}</code>")

    async def deliver_reminder(self, payload):
        await self.app.send_message(
            payload["chat_id"], utils.escape_html(payload["text"])
        )
```

`self.schedule` saves a task in the database and calls the named method with
`payload`. It survives restarts; the module must be loaded to execute it.
`when` accepts a delay in seconds, a `timedelta` or a `datetime`.
`self.unschedule(task_id)` cancels a task; `self.scheduled()` lists the module's queue.

Use `await utils.run_sync(func, *args)` for blocking operations. Avoid `time.sleep`
and synchronous HTTP calls inside handlers.

<a id="loading"></a>

## 9. Dependencies, repositories and Premium

### Dependencies

Declare package names and versions at the top of the file:

```python
# requires: alphabet-detector googletrans==4.0.0-rc1
```

`# required:` also works. The header is used when an import fails during loading.
Version constraints are preserved, `bs4` maps to `beautifulsoup4`, and standard
library modules such as `urllib` are skipped. Without a header, Shizu attempts
to install the package for a missing import. Installation errors reach the logs;
an incompatible package API may need code changes or an explicit dependency version.

### Multiple repositories

Add GitHub links as a list in `additional_repos` under `.config ShizuLoader`.
`.dlmod` shows the catalog; `.dlmod <name>` finds a module. Without `all.txt`,
Shizu discovers `.py` files through the GitHub API, including nested folders.
Use `.dlmod folder/Module` for a nested file.

<details>
<summary><b>Private repositories and updates</b></summary>

`private_repos` is a list with a separate token per repository, each with
`Contents: read` access:

```json
[
  {"url": "https://github.com/owner/first", "token": "TOKEN_1"},
  {"url": "https://github.com/owner/second", "token": "TOKEN_2"}
]
```

The field is masked in config. An installed module update triggers a private bot
message with a diff and an approval request. Checking does not install updates
automatically. Configure `notify_updates` and `update_check_interval` to control it.

</details>

### Telegram Premium

Here, `is_premium` means **the account owner's Telegram Premium**, not a paid
module subscription. To restrict one config option:

```python
loader.ConfigValue(
    "premium_feature",
    False,
    "Enable a feature that requires Telegram Premium.",
    validator=loader.validators.IsPremium(loader.validators.Boolean()),
    label="Premium feature",
)
```

Place this `ConfigValue` inside `ModuleConfig`. Without Premium, the option is
hidden in config and the web panel. To restrict one command:

```python
    @loader.command(is_premium=True)
    async def premiumcheck(self, app: Client, message: types.Message):
        """A command available when the account owner has Telegram Premium."""
        await message.answer("Telegram Premium is available.")
```

For the whole module, use `@loader.module("Name", is_premium=True)`.
The `@loader.tag("is_premium")` tag also works on a class or command.

<details>
<summary><b>Compatibility and shared libraries</b></summary>

Telethon modules use `(self, message)` and require `.enabletlmode`. Prefer the
Pyrogram style in this guide for new modules; Hikka compatibility does not imply
support for every Hikka API.

Shared code can live in a `loader.Library` class with `async def init(self)`.
Load it with `await self.import_lib(url)`. Libraries also go through BeSafe review.

</details>

<a id="example"></a>

## 10. Complete example: notes

[Download Notes.py](examples/Notes.py)

This module saves short notes, provides a delete menu, and translates messages and
config into Russian. No external dependencies are needed.

```python
from pyrogram import Client, types

from shizu import loader, utils


@loader.module(name="Notes", author="Shizu example", version=1.0)
class NotesMod(loader.Module):
    """Save short notes and delete them from an inline menu."""

    strings = {
        "usage": "Usage: <code>{}note text</code>",
        "too_long": "Keep a note within 120 characters.",
        "limit": "The note limit is reached. Delete a note first.",
        "saved": "Note <b>#{}</b> saved.",
        "empty": "No notes yet.",
        "title": "<b>Your notes</b>",
        "deleted": "Deleted",
        "missing": "This note has already been deleted.",
        "delete": "Delete #{}",
        "close": "Close",
        "cant_close": "Could not delete the message.",
        "cfg_limit": "Maximum number of stored notes.",
        "cfg_limit_label": "Note limit",
    }

    strings_ru = {
        "usage": "Использование: <code>{}note текст</code>",
        "too_long": "В заметке должно быть не больше 120 символов.",
        "limit": "Достигнут лимит заметок. Сначала удалите одну.",
        "saved": "Заметка <b>#{}</b> сохранена.",
        "empty": "Заметок пока нет.",
        "title": "<b>Ваши заметки</b>",
        "deleted": "Удалено",
        "missing": "Эта заметка уже удалена.",
        "delete": "Удалить #{}",
        "close": "Закрыть",
        "cant_close": "Не удалось удалить сообщение.",
        "cfg_limit": "Максимальное количество сохранённых заметок.",
        "cfg_limit_label": "Лимит заметок",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "max_notes",
                10,
                lambda: self.strings("cfg_limit"),
                validator=loader.validators.Integer(minimum=1, maximum=20),
                label=lambda: self.strings("cfg_limit_label"),
            )
        )

    async def on_load(self, app: Client):
        self.saved_notes = self.pointer("notes", {})

    @loader.command()
    async def note(self, app: Client, message: types.Message):
        """Save a note: note <text>."""
        text = message.get_args_raw()
        if not text:
            return await message.answer(self.strings("usage").format(self.get_prefix()))
        if len(text) > 120:
            return await message.answer(self.strings("too_long"))
        if len(self.saved_notes) >= self.config["max_notes"]:
            return await message.answer(self.strings("limit"))

        note_id = str(self.get("next_id", 1))
        self.saved_notes[note_id] = text
        self.set("next_id", int(note_id) + 1)
        await message.answer(self.strings("saved").format(note_id))

    @loader.command()
    async def notes(self, app: Client, message: types.Message):
        """Show saved notes and their delete buttons."""
        await self.inline.form(
            text=self._notes_text(),
            message=message,
            reply_markup=self._note_buttons(),
            force_me=True,
            ttl=600,
        )

    def _notes_text(self):
        if not self.saved_notes:
            return self.strings("empty")
        lines = [
            f"<b>#{note_id}</b> {utils.escape_html(text)}"
            for note_id, text in self.saved_notes.items()
        ]
        return self.strings("title") + "\n\n" + "\n".join(lines)

    def _note_buttons(self):
        rows = [
            [
                {
                    "text": self.strings("delete").format(note_id),
                    "callback": self.delete_note,
                    "args": (note_id,),
                }
            ]
            for note_id in self.saved_notes
        ]
        rows.append([{"text": self.strings("close"), "callback": self.close_menu}])
        return rows

    async def delete_note(self, call, note_id: str):
        if self.saved_notes.pop(note_id, None) is None:
            return await call.answer(self.strings("missing"), show_alert=True)
        await call.answer(self.strings("deleted"))
        await call.edit(self._notes_text(), reply_markup=self._note_buttons())

    async def close_menu(self, call):
        if not await call.delete():
            return await call.answer(self.strings("cant_close"), show_alert=True)
        await call.answer()
```

| Part | What it does |
| --- | --- |
| `strings` / `strings_ru` | Keep labels and messages separate from logic |
| `__init__` | Defines a validated note limit with a translated button |
| `on_load` | Connects `saved_notes` to the stored `notes` dict |
| `note` | Checks the text and limit, then saves a note with a stable ID |
| `_notes_text` | Builds HTML while escaping user text |
| `_note_buttons` | Adds a delete button per note and Close at the bottom |
| `delete_note` | Removes the data and updates the text and keyboard |
| `close_menu` | Deletes the menu message while keeping the notes |

After installing it, try:

```text
.note Buy tea
.note Read the module guide
.notes
.config Notes
```

Notes are limited to 120 characters each, with a configurable count from 1 to 20.
The form stays active for ten minutes; notes survive closing the menu and restarting.

<a id="troubleshooting"></a>

## If something fails

| Symptom | What to check |
| --- | --- |
| Module did not load | The class decorator, dependency imports and BeSafe card |
| Only you can use the command | Access permissions; public commands need an explicit decorator |
| Nothing happens in a service group | Move the test to Shizu-Expiriments |
| `Unknown string` | The key exists in base `strings` |
| Data change did not persist | Assign the nested object back to its pointer |
| A button expired | Send a new form after a restart or `ttl` expiry |

Command errors and tracebacks reach the logs. `.logs` sends the log file.
BeSafe reviews third-party code loading. Keep secrets and session files out of
messages, and use `Hidden` for config tokens.
