# Модули Shizu: от первой команды до готового примера

[English](modules.en.md) · [На главную](../Readme.md)

Это практическое руководство для **Pyrogram**. Сначала загрузите небольшой
модуль, затем добавьте настройки, хранение данных и кнопки. В конце есть
[полный Notes.py](#example), который можно сразу установить.

| Нужно сделать | Раздел |
| --- | --- |
| Написать и загрузить первый модуль | [Быстрый старт](#start) |
| Прочитать аргументы и ответить на реплай | [Команды и сообщения](#commands) |
| Добавить настройки и переводы | [Конфиг](#config) · [Переводы](#translations) |
| Сохранить данные после перезапуска | [Хранение](#storage) |
| Сделать меню, таблицу или галерею | [Кнопки и rich text](#inline) |
| Обрабатывать сообщения и запускать задачи | [Вотчеры](#watchers) · [Задачи](#tasks) |
| Настроить зависимости и ограничения | [Загрузка и доступ](#loading) |

<a id="start"></a>

## 1. Первый модуль

Сохраните код в файл `Hello.py`:

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

1. Отправьте файл в **Shizu-Expiriments** или другой обычный чат.
2. Ответьте на файл командой `.loadmod`.
3. Если BeSafe запросит подтверждение, проверьте код и одобрите его в **Shizu-besafe**.
4. Выполните `.hello Shizu`. Ответ: **Hello, Shizu!**

Для загрузки по ссылке используйте `.dlmod <ссылка>`. Ссылки GitHub `/blob/`
поддерживаются. `.unloadmod Hello` выгрузит модуль.

| Часть кода | Зачем она нужна |
| --- | --- |
| `@loader.module(...)` | Задаёт имя модуля, автора и версию |
| `class HelloMod(loader.Module)` | Подключает методы и состояние Shizu |
| `@loader.command()` | Регистрирует метод как команду `.hello` |
| `async def hello(self, app, message)` | Получает экземпляр модуля, клиент и сообщение команды |
| `message.get_args_raw()` | Читает текст после имени команды |
| `utils.escape_html(name)` | Показывает пользовательский текст без превращения в HTML-теги |
| `message.answer(...)` | Отправляет ответ или редактирует ваше сообщение команды |

Держите один класс модуля в файле и ставьте `@loader.module(...)` над ним.
Имя модуля должно быть уникальным: повторная загрузка того же модуля заменяет
его. Описания класса и команд показываются в `.help`.

> Далее методы и поля с отступом добавляются **внутрь класса модуля**.
> Импорты остаются в начале файла. Примеры можно пробовать по отдельности.

<a id="commands"></a>

## 2. Команды, аргументы и ответы

### Проверка аргументов

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

Команду можно вызвать как `.greet Anna` или `.hi Anna`. Без имени она покажет
подсказку. `aliases` задаёт дополнительные названия, а `ru_doc` — русское
описание команды в `.help`.

| Вызов | Результат для `.greet New York` |
| --- | --- |
| `message.get_args_raw()` | `"New York"`; сохраняет исходные пробелы |
| `message.get_args()` | `"New York"`; объединяет слова одиночными пробелами |
| `message.get_args_html()` | Аргументы с форматированием в HTML |

### Работа с реплаем

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

У сообщения с медиа текст может быть в `caption`, поэтому проверяйте оба поля.
В этом примере исходное оформление намеренно заменяется на цитату с обычным
текстом. Для HTML исходного сообщения используйте `reply.text.html` или
`reply.caption.html`, когда соответствующее поле присутствует.

`message.answer` принимает HTML: `<b>`, `<i>`, `<code>`, `<a>` и другие
поддерживаемые теги. Это тот же помощник, что `utils.answer(message, text)`.
Для прямого вызова Telegram API доступен `app`, например
`await app.send_message("me", "Hello")`.

<a id="config"></a>

## 3. Конфиг с понятными названиями

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

Откройте `.config <имя модуля>`. Пользователь увидит кнопки **City** и
**API token**, а в коде вы будете читать `self.config["city"]` и
`self.config["api_key"]`.

| Параметр | Значение в примере |
| --- | --- |
| `key` | `city`: постоянный ключ хранения, который использует код |
| `default` | `London`: значение до первой настройки |
| `doc` | Описание, которое помогает пользователю выбрать значение |
| `validator` | Проверка и преобразование введённого значения |
| `label` | Короткий заголовок кнопки, отдельно от ключа |

Присваивание `self.config["city"] = "Paris"` проходит валидацию и сохраняется.
`Hidden` скрывает секрет в интерфейсе конфигурации; сам модуль получает его
обычное значение.

<details>
<summary><b>Часто используемые валидаторы</b></summary>

| Валидатор | Для чего |
| --- | --- |
| `Integer(minimum=1, maximum=20)` | Целое число в диапазоне |
| `Float(minimum=0)` | Число с дробной частью |
| `Boolean()` | Переключатель |
| `String(min_len=2, max_len=100)` | Текст заданной длины |
| `Choice(["light", "dark"])` | Одно значение из списка |
| `Series(validator=loader.validators.Link())` | Список ссылок |
| `Link()` | Формат HTTP(S)-ссылки |
| `RegExp(r"^[a-z]+$")` | Текст по регулярному выражению |
| `Hidden(loader.validators.String())` | Скрытое текстовое значение |

Валидаторы находятся в `loader.validators`. `Series` принимает JSON-список
или значения через запятую. Проверка формата ссылки не проверяет доступность сайта.

</details>

<a id="translations"></a>

## 4. Тексты и переводы

```python
    strings = {"greeting": "Hello, <b>{}</b>!", "city_label": "City"}
    strings_ru = {"greeting": "Привет, <b>{}</b>!", "city_label": "Город"}

    @loader.command()
    async def welcome(self, app: Client, message: types.Message):
        """Greet someone in the selected interface language."""
        name = utils.escape_html(message.get_args_raw() or "Shizu")
        await message.answer(self.strings("greeting").format(name))
```

`strings` задаёт базовые тексты, `strings_ru` — русские. Можно добавить
`strings_uz` и другие языки. Shizu выбирает язык интерфейса; отсутствующий
перевод берётся из `strings`.

Для конфигов передавайте функции, чтобы подписи менялись вместе с языком:
`label=lambda: self.strings("city_label")`. Описание `doc` переводится так же.
Вызов функции происходит после загрузки переводов, поэтому используйте именно
`lambda`, а не `self.strings(...)` прямо в `__init__`.

<a id="storage"></a>

## 5. Данные и жизненный цикл

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

`on_load` вызывается, когда модулю уже назначены клиент, база, переводы и
сохранённый конфиг. Здесь удобно подготовить состояние для команд.

| API | Что сохраняет |
| --- | --- |
| `self.get("key", default)` | Читает значение из раздела этого модуля |
| `self.set("key", value)` | Записывает JSON-совместимое значение |
| `self.pointer("items", {})` | Словарь с сохранением изменений верхнего уровня |
| `self.pointer("items", [])` | Список с сохранением добавлений и удалений |

Данные останутся после перезапуска. Внутри метода для вложенного словаря измените копию
и присвойте её обратно; само изменение вложенного объекта не вызывает сохранение:

```python
item = dict(self.items["profile"])
item["name"] = "Shizu"
self.items["profile"] = item
```

В последнем фрагменте предполагается, что ключ `profile` уже содержит словарь.

<details>
<summary><b>Доступные свойства и хуки</b></summary>

| Свойство или хук | Назначение |
| --- | --- |
| `self.app`, `self.me` | Pyrogram-клиент и аккаунт владельца |
| `self.inline`, `self.bot` | Менеджер инлайн-бота |
| `self.db` | База данных Shizu |
| `self.get_prefix()` | Первый текущий префикс команд |
| `self.lookup("Name")` | Другой загруженный модуль, либо `False` |
| `on_load(self, app)` | Подготовка состояния |
| `client_ready(self, client, db)` | Дополнительный хук после `on_load` |
| `on_unload(self)` | Освобождение ресурсов при выгрузке |

Для отказа от загрузки с понятной причиной поднимите `loader.LoadError("reason")`
в `on_load`. При выгрузке Shizu останавливает циклы и убирает обработчики.

</details>

<a id="inline"></a>

## 6. Кнопки, rich text и галереи

### Меню с кнопками

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

`reply_markup` — список строк клавиатуры. `args` передаёт значение `"ready"`
в `check_cb(call, status)`. Ссылочная кнопка открывает URL, а callback-кнопка
вызывает ваш метод.

| Вызов или параметр | Что делает |
| --- | --- |
| `call.answer(text, show_alert=True)` | Показывает уведомление о нажатии |
| `call.edit(text, reply_markup=rows)` | Обновляет текст и кнопки формы |
| `call.delete()` | Удаляет сообщение формы; возвращает результат удаления |
| `force_me=True` | Оставляет кнопки доступными владельцу и разрешённым owners |
| `always_allow=[123456]` | Даёт доступ указанным пользователям |
| `ttl=600` | Через десять минут кнопки истекают; сообщение само не удаляется |

После перезапуска старые callback-кнопки могут истечь: вызовите команду снова.
Форма с callback-кнопками использует инлайн-бота для обработки нажатий.

### Rich text и таблицы

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

`utils.send_table` строит rich-таблицу и имеет текстовый fallback. Для своего
HTML используйте `await message.answer("<h2>Status</h2><p>Ready</p>", rich=True)`.
Параметр `rich_message` отделяет rich-разметку от текста fallback:

```python
await message.answer(
    "Status: ready",
    rich_message={"html": "<h2>Status</h2><p>Ready</p>"},
)
```

Shizu выбирает отправителя по **Telegram Premium владельца аккаунта**:
rich-сообщение отправляется напрямую для Premium, через инлайн-бота — без него.
Формы с callback/input-кнопками используют бота независимо от Premium.

<details>
<summary><b>Кнопка прямо в rich-тексте</b></summary>

Этот метод использует `check_cb` и `close_cb` из примера меню выше:

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

`ref="check"` связывает тег с кнопкой в `reply_markup`. Подпись берётся из
текста внутри тега. Кнопки без `ref` остаются под сообщением.
Полный отдельный модуль: [RichButtons.py](examples/RichButtons.py).

</details>

<details>
<summary><b>Страницы и галерея</b></summary>

Внутри команды:

```python
await self.inline.list(message, ["First page", "Second page"])

await self.inline.gallery(
    message,
    ["https://example.com/first.png", "https://example.com/second.png"],
    caption="Gallery",
)
```

В галерее Close стоит снизу и удаляет сообщение. Вместо списка можно передать
функцию, которая возвращает URL или список URL для следующих изображений.

</details>

<a id="watchers"></a>

## 7. Вотчеры и доступ к командам

```python
    @loader.watcher("in", "only_groups", "only_messages", no_commands=True)
    async def activity_watcher(self, app: Client, message: types.Message):
        if message.from_user and not message.from_user.is_bot:
            self.set("last_sender", message.from_user.id)
```

Этот вотчер запоминает отправителя входящего текстового сообщения в группе.
Он пропускает команды и сообщения ботов. Строковые теги соединяются условием
**«и»**. При использовании тегов явно добавляйте `only_messages`, если
обработчику нужен текст или подпись.

По умолчанию команды доступны вам, owners и пользователям, которым вы выдали
доступ. Для публичной команды явно задайте разрешение:

```python
    @loader.command()
    @loader.everyone
    @loader.ratelimit
    async def ping(self, app: Client, message: types.Message):
        """Check whether the module responds."""
        await message.answer("Pong.")
```

`@loader.everyone` открывает команду всем, а `@loader.ratelimit` ограничивает
чужие вызовы до трёх за десять секунд на команду. Для отдельных случаев есть
`@loader.group_admin`, `@loader.group_owner`, `@loader.group_member` и `@loader.pm`.
Разрешение доступа и фильтр сообщений — разные проверки: `only_groups` ограничивает
тип чата, но само по себе не открывает команду другим людям.

<details>
<summary><b>Короткая справка по фильтрам</b></summary>

| Фильтр | Какие сообщения проходят |
| --- | --- |
| `in` / `out` | Входящие / исходящие |
| `only_pm` / `only_groups` | Личные чаты / группы |
| `only_messages` | Сообщения с текстом или подписью |
| `only_reply` / `no_reply` | С реплаем / без реплая |
| `only_media` / `no_media` | С медиа / без медиа |
| `only_photos`, `only_videos`, `only_docs` | Соответствующий тип медиа |
| `no_commands` | Без префикса команды |
| `contains="Shizu"`, `startswith="!"` | Проверка текста |
| `regex=r"^!hello"` | Поиск регулярным выражением |
| `from_id=123456`, `chat_id=-1001234567890` | Проверка отправителя или чата |

Для команд используйте `@loader.tag("only_groups", "only_reply")`.
Для вотчеров те же фильтры передаются в `@loader.watcher(...)`.

</details>

В Logs, Backups и BeSafe сообщения пользователей удаляются до обработки
команд и вотчеров. Проверяйте примеры в **Shizu-Expiriments** или обычном чате.

<a id="tasks"></a>

## 8. Фоновые задачи

### Повторяющийся цикл

```python
    @loader.loop(interval=600, autostart=True, wait_before=True)
    async def heartbeat(self):
        self.set("heartbeat_count", self.get("heartbeat_count", 0) + 1)
```

Цикл увеличивает сохранённый счётчик каждые десять минут. `wait_before=True`
откладывает первый запуск. Остановить его можно через
`await self.heartbeat.stop()`, запустить — через `self.heartbeat.start()`.
Вместо секунд допускается ключ конфига: `interval="refresh_seconds"`.

Для запуска по часам используйте `time="09:00"` или список времени.
Это **время сервера**; задавайте только один параметр: `time` или `interval`.

### Однократная задача с сохранением

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

`self.schedule` сохраняет задачу в базе и вызовет указанный метод с `payload`.
Она переживает перезапуск; для выполнения модуль должен быть загружен.
`when` принимает задержку в секундах, `timedelta` или `datetime`.
`self.unschedule(task_id)` отменяет задачу, `self.scheduled()` показывает очередь модуля.

Для блокирующей операции используйте `await utils.run_sync(func, *args)`.
Не вызывайте `time.sleep` или синхронный HTTP-запрос прямо в обработчике.

<a id="loading"></a>

## 9. Зависимости, репозитории и Premium

### Зависимости

В начале файла можно указать пакеты и нужные версии:

```python
# requires: alphabet-detector googletrans==4.0.0-rc1
```

`# required:` тоже поддерживается. Заголовок используется, когда импорт при
загрузке завершился ошибкой. Версии сохраняются, `bs4` преобразуется в
`beautifulsoup4`, модули стандартной библиотеки вроде `urllib` пропускаются.
Без заголовка Shizu пробует установить пакет для отсутствующего импорта.
Ошибка установки приходит в логи; для несовместимого API пакета может понадобиться
исправление кода или явная версия зависимости.

### Несколько репозиториев

В `.config ShizuLoader` укажите список GitHub-ссылок в `additional_repos`.
`.dlmod` покажет каталог, `.dlmod <имя>` найдёт модуль. Если нет `all.txt`,
Shizu собирает `.py` через GitHub API, включая вложенные папки.
Для вложенного файла используется `.dlmod folder/Module`.

<details>
<summary><b>Приватные репозитории и обновления</b></summary>

`private_repos` — список репозиториев, у каждого свой токен с доступом `Contents: read`:

```json
[
  {"url": "https://github.com/owner/first", "token": "TOKEN_1"},
  {"url": "https://github.com/owner/second", "token": "TOKEN_2"}
]
```

Поле скрыто в конфиге. Обнаруженное обновление установленного модуля приходит
в личный чат бота с diff и запросом подтверждения. Проверка не устанавливает
обновление автоматически. Настройки: `notify_updates` и `update_check_interval`.

</details>

### Telegram Premium

Здесь `is_premium` означает **Telegram Premium владельца аккаунта**, а не
платную подписку на модуль. Для отдельного пункта конфига:

```python
loader.ConfigValue(
    "premium_feature",
    False,
    "Enable a feature that requires Telegram Premium.",
    validator=loader.validators.IsPremium(loader.validators.Boolean()),
    label="Premium feature",
)
```

Вставьте этот `ConfigValue` в `ModuleConfig`. Без Premium пункт скрыт в
конфиге и веб-панели. Для команды:

```python
    @loader.command(is_premium=True)
    async def premiumcheck(self, app: Client, message: types.Message):
        """A command available when the account owner has Telegram Premium."""
        await message.answer("Telegram Premium is available.")
```

Для всего модуля используйте `@loader.module("Name", is_premium=True)`.
Также поддерживается тег `@loader.tag("is_premium")` на классе или команде.

<details>
<summary><b>Совместимость и общие библиотеки</b></summary>

Модули Telethon используют `(self, message)` и требуют `.enabletlmode`.
Для новых модулей используйте стиль Pyrogram из этого руководства; совместимость
с Hikka не означает поддержку всех её API.

Общий код можно вынести в класс `loader.Library` с методом `async def init(self)`
и загрузить через `await self.import_lib(url)`. Библиотека тоже проходит проверку BeSafe.

</details>

<a id="example"></a>

## 10. Полный пример: заметки

[Скачать Notes.py](examples/Notes.py)

Модуль сохраняет короткие заметки, показывает меню удаления и переводит
сообщения и конфиг на русский. Внешние зависимости не нужны.

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

| Часть | Что происходит |
| --- | --- |
| `strings` / `strings_ru` | Все подписи и сообщения хранятся отдельно от логики |
| `__init__` | Создаёт лимит заметок с валидатором и переведённой кнопкой |
| `on_load` | Подключает `saved_notes` к словарю `notes` в базе |
| `note` | Проверяет текст и лимит, сохраняет заметку с постоянным номером |
| `_notes_text` | Собирает HTML и экранирует пользовательский текст |
| `_note_buttons` | Делает кнопку удаления для каждой заметки и Close снизу |
| `delete_note` | Удаляет данные и обновляет текст и клавиатуру |
| `close_menu` | Удаляет сообщение, сохраняя сами заметки |

Попробуйте после загрузки:

```text
.note Buy tea
.note Read the module guide
.notes
.config Notes
```

Заметки ограничены 120 символами, их лимит — от 1 до 20. Форма активна десять
минут; сами заметки сохраняются после закрытия меню и перезапуска.

<a id="troubleshooting"></a>

## Если что-то не работает

| Симптом | Что проверить |
| --- | --- |
| Модуль не загрузился | Декоратор класса, импорт зависимостей и карточку BeSafe |
| Команда работает только у вас | Разрешения; для публичной команды нужен явный декоратор |
| Код не реагирует в служебной группе | Перенесите тест в Shizu-Expiriments |
| `Unknown string` | Наличие ключа в базовом `strings` |
| Изменение данных не сохранилось | Присвойте вложенный объект обратно в pointer |
| Кнопка истекла | Отправьте новую форму после перезапуска или истечения `ttl` |

Ошибка команды и traceback приходят в логи. `.logs` позволяет получить файл лога.
BeSafe проверяет загрузку стороннего кода; не отправляйте секреты или файлы сессии
в сообщениях и используйте `Hidden` для токенов в конфиге.
