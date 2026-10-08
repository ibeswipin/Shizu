# Как писать модули для Shizu

🇬🇧 [English version](modules.en.md)

Это руководство описывает всё, что может модуль Shizu: команды, вотчеры,
конфиг, хранение данных, переводы, инлайн-бот, циклы и правила безопасности,
по которым работает любой сторонний модуль. Все примеры написаны для режима
Pyrogram, который включён по умолчанию.

- [Быстрый старт](#быстрый-старт)
- [Устройство файла модуля](#устройство-файла-модуля)
- [Команды](#команды)
- [Ответ на сообщение](#ответ-на-сообщение)
- [Кто может запускать команду](#кто-может-запускать-команду)
- [Вотчеры](#вотчеры)
- [Фильтры сообщений](#фильтры-сообщений)
- [Конфиг](#конфиг)
- [Хранение данных](#хранение-данных)
- [Строки и переводы](#строки-и-переводы)
- [Хуки жизненного цикла](#хуки-жизненного-цикла)
- [Циклы](#циклы)
- [Инлайн-бот](#инлайн-бот)
- [Диалоги](#диалоги)
- [Зависимости и условия загрузки](#зависимости-и-условия-загрузки)
- [Общие библиотеки](#общие-библиотеки)
- [Утилиты](#утилиты)
- [Модули Telethon и Hikka](#модули-telethon-и-hikka)
- [Правила безопасности](#правила-безопасности)
- [Полный пример](#полный-пример)
- [Частые проблемы](#частые-проблемы)

## Быстрый старт

```python
from pyrogram import Client, types

from shizu import loader


@loader.module(name="Hello", author="you", version=1.0)
class HelloMod(loader.Module):
    """Здоровается"""

    @loader.command()
    async def hello(self, app: Client, message: types.Message):
        """Поприветствовать. Использование: hello <имя>"""
        name = message.get_args_raw() or "мир"
        await message.answer(f"👋 Привет, <b>{name}</b>!")
```

Установить модуль можно тремя способами:

| Способ | Как |
|---|---|
| Из файла | отправьте `Hello.py` в любой чат и ответьте на него `.loadmod` |
| По ссылке | `.dlmod https://example.com/Hello.py` |
| Локально | положите файл в `shizu/modules/` и перезапустите Shizu |

Затем выполните `.hello Shizu`. Удалить модуль: `.unloadmod Hello`. Получить
обратно его файл или ссылку: `.ml Hello`. Модули, установленные по ссылке,
скачиваются заново при каждом запуске.

## Устройство файла модуля

```python
# required: requests beautifulsoup4

from pyrogram import Client, types

from shizu import loader, utils


@loader.module(name="Weather", author="you", version=1.2)
class WeatherMod(loader.Module):
    """Текущая погода в любом городе"""

    strings = {...}
    strings_ru = {...}

    def __init__(self):
        self.config = loader.ModuleConfig(...)

    async def on_load(self, app: Client): ...

    @loader.command()
    async def weather(self, app: Client, message: types.Message): ...
```

Правила, на которые опирается загрузчик:

- **`@loader.module(...)` должен стоять прямо над строкой с классом.**
  Загрузчик ищет `@loader.module(...)`, за которым сразу идёт `class Name(`.
  Без этого модуль из файла или по ссылке не загрузится.
- Класс наследуется от `loader.Module`. Его docstring служит описанием модуля
  в `.help`.
- `name` — имя модуля, которое видят пользователи, и одновременно имя его
  раздела в базе данных. Оно не должно совпадать с именем системного модуля
  (`ShizuHelp`, `ShizuLoader` и т. д.). Если загрузить модуль с тем же именем
  класса или тем же `name`, что у уже установленного, новый заменит старый.
- `author` и `version` необязательны.
- В одном файле — один класс модуля.

Атрибуты, которые Shizu добавляет каждому модулю:

| Атрибут | Что это |
|---|---|
| `self.app` | Pyrogram `Client` аккаунта |
| `self.db` | база данных (см. [Хранение данных](#хранение-данных)) |
| `self.inline` | менеджер инлайн-бота (см. [Инлайн-бот](#инлайн-бот)) |
| `self.bot` | тот же менеджер; `self.inline_bot` — «голый» aiogram `Bot` |
| `self.me` | ваш аккаунт как Pyrogram `User`; `self.tg_id` — его ID |
| `self.all_modules` | менеджер модулей: `get_module(name)`, `modules`, `commands` |
| `self.prefix` | список префиксов команд; `self.get_prefix()` возвращает первый |
| `self.strings` | переведённые строки (см. [Строки](#строки-и-переводы)) |
| `self.lookup(name)` | другой загруженный модуль по имени или `False` |
| `self.tl`, `self.client` | клиент Telethon, только если включён режим Telethon |

## Команды

Команда — это async-метод с декоратором `@loader.command()`:

```python
@loader.command(aliases=["w"], hidden=False)
async def weather(self, app: Client, message: types.Message):
    """Показать погоду. Использование: weather <город>"""
```

- Имя команды — имя метода в нижнем регистре: `weather` вызывается как
  `.weather`.
- Метод, имя которого оканчивается на `cmd`, тоже становится командой даже
  без декоратора: `weathercmd` — это `.weather`.
- `aliases` задаёт дополнительные имена. Пользователи могут добавлять и свои
  алиасы.
- `hidden=True` скрывает команду из `.help`.
- Docstring — описание команды в `.help`. Пишите туда и способ использования.
- Сигнатура всегда `(self, app, message)`.
- Команда срабатывает и тогда, когда вы редактируете сообщение в команду.

Аргументы:

| Вызов | Для `.weather New York` вернёт |
|---|---|
| `message.get_args_raw()` | `"New York"` (текст после команды как есть; `False`, если у сообщения нет текста) |
| `message.get_args()` | `"New York"` (слова через один пробел) |
| `message.get_args_html()` | аргументы с форматированием в виде HTML |
| `utils.get_args_split_by(message, ",")` | список, разделённый по разделителю |

Сообщение, на которое ответили, лежит в `message.reply_to_message`.
`await utils.get_user(message)` возвращает пользователя из ответа или первого
аргумента, `await utils.get_target(message)` — его ID.

Исключения внутри команды перехватываются: трейсбек отправляется в чат и в
чат логов. Оборачивать весь обработчик в try/except не нужно.

## Ответ на сообщение

Используйте `message.answer(...)` (или `utils.answer(message, ...)`). Метод
редактирует ваше сообщение или отвечает на чужое и сам справляется с длинным
текстом:

```python
await message.answer("✅ <b>Готово</b>")
await message.answer(file_bytes, doc=True, caption="logs")
await message.answer("https://example.com/cat.jpg", photo_=True)
await message.answer("Выберите:", reply_markup=[{"text": "OK", "callback": self.ok}])
```

- По умолчанию разметка — HTML.
- Текст длиннее 4096 символов превращается в инлайн-список со страницами,
  а если это не удалось, отправляется файлом `output.txt`.
- С `reply_markup` ответ уходит инлайн-формой (см. [Инлайн-бот](#инлайн-бот)).
- Кастомные эмодзи: `<emoji id=5372892693024218813>🥶</emoji>`.
- Пользовательский ввод экранируйте через `utils.escape_html(text)`.
- Таблицы: `await utils.send_table(message, rows, header=[...], title="...")`.

Всё остальное — обычный Pyrogram: `await app.send_message(...)`,
`await message.delete()`, `await app.get_chat(...)` и так далее.

## Кто может запускать команду

По умолчанию команду могут запускать:

- вы сами (исходящие сообщения разрешены всегда);
- владельцы, добавленные через `.owner`;
- пользователи, которым эту команду выдали через `.permissions`.

Декораторы расширяют доступ, их можно сочетать:

```python
@loader.command()
@loader.group_admin_ban_users
@loader.pm
async def ban(self, app, message): ...
```

| Декоратор | Кому разрешено |
|---|---|
| `@loader.owner` | владельцам |
| `@loader.sudo`, `@loader.support` | тем, кому команду выдали через `.permissions` |
| `@loader.everyone` (`unrestricted`, `inline_everyone`) | всем |
| `@loader.pm` | всем в личных сообщениях |
| `@loader.group_member` | любому участнику группы |
| `@loader.group_owner` | создателю группы |
| `@loader.group_admin` | любому админу группы |
| `@loader.group_admin_ban_users` | админам с правом банить |
| `@loader.group_admin_delete_messages` | админам с правом удалять сообщения |
| `@loader.group_admin_pin_messages` | админам с правом закреплять |
| `@loader.group_admin_invite_users` | админам с правом приглашать |
| `@loader.group_admin_change_info` | админам с правом менять информацию о чате |
| `@loader.group_admin_add_admins` | админам с правом назначать админов |

Другие декораторы команд:

- `@loader.ratelimit` ограничивает других пользователей тремя вызовами
  команды за 10 секунд. Ваши собственные вызовы не ограничиваются.
- `@loader.on(filters.private)` добавляет фильтр Pyrogram: команда сработает,
  только если фильтр пройден. Подойдёт и обычная функция с сигнатурой
  `(flt, app, message)`.
- `@loader.tag(...)` запускает команду только для подходящих сообщений по
  [фильтрам сообщений](#фильтры-сообщений):

```python
@loader.command()
@loader.tag("only_groups", "only_reply")
async def warn(self, app, message): ...
```

Проверить права пользователя из кода можно так:
`await self.all_modules.check_security(message, self.some_command)`.

## Вотчеры

Вотчер получает каждое новое и отредактированное сообщение, которое видит
аккаунт:

```python
@loader.watcher(only_messages=True, no_commands=True)
async def watcher(self, app: Client, message: types.Message):
    if "shizu" in message.text.lower():
        await message.reply("👀")
```

- Метод становится вотчером, если у него есть `@loader.watcher(...)` или если
  в его имени есть `watcher`. Имена, начинающиеся с `_`, пропускаются.
- Сигнатура: `(self, app, message)` или `(self, message)`.
- Переключатели-аргументы:

| Аргумент | По умолчанию | Действие |
|---|---|---|
| `only_messages` | `True` | пропускать сообщения без текста и подписи |
| `no_commands` | `False` | пропускать сообщения, начинающиеся с префикса команд |
| `no_stickers`, `no_docs`, `no_audios`, `no_videos`, `no_photos` | `False` | пропускать этот тип медиа |
| `no_forwards` | `False` | пропускать пересланные сообщения |

- Вотчер также принимает [фильтры сообщений](#фильтры-сообщений):

```python
@loader.watcher("out", "only_groups", regex=r"^!\w+")
async def bang_watcher(self, app, message): ...
```

- Если передан хотя бы один строковый тег, `only_messages` выключается, пока
  вы не укажете его явно: `@loader.watcher("only_pm", "only_messages")`.
- Вотчер видит и ваши сообщения, включая саму команду вашего модуля. Если они
  не нужны, сразу выходите из функции.
- Вотчеры должны работать быстро: они вызываются на каждое сообщение.
  Медленную работу выносите в `utils.spawn(coro)`.
- Исключение в одном вотчере попадает в лог и не мешает остальным.

## Фильтры сообщений

`@loader.tag(...)` и `@loader.watcher(...)` принимают одинаковые фильтры.
Должны совпасть все. Теги — это строки:

| Тег | Что пропускает |
|---|---|
| `out` / `in` | ваши сообщения / сообщения других |
| `only_pm` / `no_pm` | личные чаты (включая ботов) |
| `only_groups` / `no_groups` | группы и супергруппы |
| `only_channels` / `no_channels` | каналы |
| `only_media` / `no_media` | любые медиа |
| `only_photos` / `no_photos` | фото |
| `only_videos` / `no_videos` | видео |
| `only_audios` / `no_audios` | аудиофайлы и голосовые |
| `only_docs` / `no_docs` | документы |
| `only_stickers` / `no_stickers` | стикеры |
| `only_forwards` / `no_forwards` | пересланные сообщения |
| `only_reply` / `no_reply` | ответы на сообщения |
| `only_inline` / `no_inline` | сообщения, отправленные через бота |
| `mention` / `no_mention` | сообщения с упоминанием вас |
| `only_commands` / `no_commands` | сообщения, начинающиеся с префикса команд |
| `editable` | ваши сообщения, которые не являются пересланными |

Фильтры-аргументы:

| Фильтр | Срабатывает, когда |
|---|---|
| `startswith="!"` | текст (или подпись) начинается со значения |
| `endswith="?"` | текст заканчивается значением |
| `contains="shizu"` | текст содержит значение |
| `regex=r"\d+"` | `re.search` находит шаблон в тексте |
| `from_id=123` | ID отправителя равен значению |
| `chat_id=-100123` | ID чата равен значению |
| `filter=func` | `func(message)` возвращает истинное значение |

Тег можно передать и аргументом: `@loader.tag(only_pm=True)` — то же самое,
что `@loader.tag("only_pm")`.

## Конфиг

Значения конфига пользователь меняет через `.config`, они сохраняются
автоматически.

```python
def __init__(self):
    self.config = loader.ModuleConfig(
        loader.ConfigValue(
            "city",
            "London",
            "Город по умолчанию",
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
            "API-ключ с openweathermap.org",
            validator=loader.validators.Hidden(loader.validators.String()),
        ),
    )
```

Прочитать значение: `self.config["city"]`. Присваивание
`self.config["city"] = "Paris"` проверяет значение валидатором и сохраняет его.

- Описание может быть строкой или функцией, возвращающей строку, — так его
  можно перевести.
- Пока значение ни разу не меняли через `.config`, его можно задать
  переменной окружения `ИмяМодуля.ключ` (например, `Weather.city`).
- Сохранённое значение, которое перестало проходить валидатор, заменяется
  значением по умолчанию.
- Работает и старая короткая форма
  `loader.ModuleConfig("key", default, "doc", "key2", default2, "doc2")`,
  но без валидаторов.

Валидаторы (`loader.validators.*`):

| Валидатор | Что принимает |
|---|---|
| `Integer(minimum=, maximum=)` | целые числа |
| `Float(minimum=, maximum=)` | числа |
| `Boolean()` | `true/false`, `1/0`, `yes/no`, `on/off` |
| `String(length=, min_len=, max_len=)` | текст |
| `RegExp(pattern, description=, flags=)` | текст, подходящий под регулярное выражение |
| `Choice([...])` | одно из перечисленных значений |
| `MultiChoice([...])` | список из перечисленных значений |
| `Series(validator=, min_len=, max_len=, fixed_len=)` | список; принимает JSON или текст через запятую |
| `Link()` | ссылку http(s) |
| `TelegramID()` | числовой Telegram ID |
| `EntityLike()` | ID, `@username` или ссылку `t.me` |
| `Emoji(length=, min_len=, max_len=)` | только эмодзи |
| `Union(v1, v2, ...)` | первый подошедший валидатор |
| `NoneType()` | `None` |
| `Hidden(validator)` | то же, что внутренний валидатор; для секретов |

Чтобы отклонить значение, валидатор выбрасывает `ValueError`. Свой валидатор —
это любой объект с методом `validate(value)`, который возвращает очищенное
значение.

Если вы переименовали модуль, вызовите `self.adopt_config("OldName")` в
`on_load`, чтобы перенести сохранённые значения.

## Хранение данных

У каждого модуля свой раздел в базе с именем `name`:

```python
self.set("last_city", "Berlin")
city = self.get("last_city", "London")
```

Для списков и словарей используйте pointer — он сохраняется при каждом
изменении:

```python
self.history = self.pointer("history", [])
self.history.append("Berlin")

self.cache = self.pointer("cache", {})
self.cache["Berlin"] = 12
```

Pointer замечает только изменения, сделанные через него самого. Если вы
изменили вложенный объект (`self.cache["Berlin"]["temp"] = 12`), присвойте
его заново: `self.cache["Berlin"] = value`.

Сама база доступна как `self.db`: `self.db.get(section, key, default)`,
`self.db.set(section, key, value)`, `self.db.pop(section, key)`. Значения
должны сериализоваться в JSON. Не пишите в разделы других модулей и в разделы
`shizu.*`.

## Строки и переводы

Держите тексты для пользователя в `strings` и добавьте словарь на каждый язык:

```python
strings = {
    "done": "✅ Saved {}",
}

strings_ru = {
    "done": "✅ Сохранено {}",
}
```

`self.strings("done")` (или `self.strings["done"]`) возвращает текст на языке,
выбранном через `.lang`, а если перевода нет — из `strings`. Имя атрибута —
`strings_<код>`: `strings_ru`, `strings_uz`, `strings_de` и т. д. Для
отсутствующего ключа возвращается `"Unknown string"`.

## Хуки жизненного цикла

```python
async def on_load(self, app):
    """После загрузки модуля и восстановления конфига"""

async def client_ready(self, client, db):
    """Сразу после on_load; получает клиент и базу"""

async def on_unload(self):
    """При выгрузке или замене модуля"""

async def on_dlmod(self, client, db):
    """Один раз, после установки модуля по ссылке"""
```

Все хуки необязательны и могут принимать меньше аргументов. При выгрузке
модуля его циклы останавливаются, а обработчики удаляются.

Чтобы прервать загрузку с сообщением, выбросите `loader.LoadError("причина")`
из `on_load` или `client_ready`. Чтобы тихо выгрузиться — `loader.SelfUnload()`.
Любое другое исключение в хуке попадает в лог, а модуль остаётся загруженным.

## Циклы

```python
@loader.loop(interval=600, autostart=True)
async def refresh(self):
    await self.update_cache()

@loader.loop(time=["09:00", "21:00"], autostart=True)
async def digest(self):
    await self.app.send_message("me", "📰 Дайджест")
```

- Укажите что-то одно: `interval` (секунды) или `time` (`"HH:MM"` или список,
  время сервера).
- Оба параметра могут быть ключом конфига: `interval="refresh_seconds"`
  берёт значение из `self.config`, и пользователь может его менять.
- `autostart=True` запускает цикл при загрузке модуля.
- `wait_before=True` — пауза перед каждым запуском, а не после.
- Управление из кода: `self.refresh.start()`, `await self.refresh.stop()`,
  `self.refresh.status`.
- Чтобы остановить цикл изнутри, выбросьте `loader.StopLoop`.

## Инлайн-бот

У каждой установки Shizu есть свой бот. Через `self.inline` модули отправляют
от вашего аккаунта сообщения с кнопками.

### Формы

```python
await self.inline.form(
    text="🌤 <b>Погода</b>",
    message=message,
    reply_markup=[
        [
            {"text": "🔄 Обновить", "callback": self.refresh_cb, "args": (city,)},
            {"text": "🌐 Сайт", "url": "https://openweathermap.org"},
        ],
        [{"text": "✖️ Закрыть", "callback": self.close_cb}],
    ],
)
```

`message` — это `Message` (форма заменит его или ответит на него) или ID чата.
`form()` возвращает ID формы или `False`.

`reply_markup` — список рядов, каждый ряд — список кнопок. Можно передать и
одну кнопку или один ряд. Ключи кнопки:

| Ключ | Значение |
|---|---|
| `text` | надпись на кнопке |
| `callback` | метод, который вызывается при нажатии |
| `args`, `kwargs` | дополнительные аргументы для `callback` (или `handler`) |
| `url` | кнопка-ссылка |
| `data` | «сырые» callback-данные; обрабатывайте их в callback-обработчике |
| `input` + `handler` | просит пользователя ввести текст, затем вызывает `handler(call, text, *args)` |

Callback получает нажатие кнопки:

```python
async def refresh_cb(self, call, city: str):
    await call.answer("Обновляю…")
    await call.edit(
        f"🌤 {city}: 21°C",
        reply_markup=[{"text": "✖️ Закрыть", "callback": self.close_cb}],
    )

async def close_cb(self, call):
    await call.delete()
```

- `call.edit(text, reply_markup=None)` меняет форму; без `reply_markup`
  кнопки исчезают.
- `call.delete()` удаляет форму.
- `call.answer(text, show_alert=False)` показывает всплывающее уведомление.
- `call.from_user` — кто нажал; `call.form` — сохранённая форма.

Другие параметры `form()`:

| Параметр | Значение |
|---|---|
| `force_me=True` | нажимать кнопки можете только вы и владельцы |
| `always_allow=[ids]` | кому ещё можно нажимать кнопки |
| `disable_security=True` | нажимать кнопки может любой |
| `ttl=секунды` | через сколько форма перестанет работать |
| `photo=`, `video=`, `gif=`, `audio=` | URL медиа, которое отправится вместе с текстом |
| `msg_id=` | ID сообщения, на которое ответить |
| `silent=True` | без заглушки «Loading inline form...» |
| `rich=True` | rich-сообщение с кнопками внутри текста, см. ниже |
| `rich_message={...}` | «сырой» объект `InputRichMessage` из Bot API |

### Кнопки внутри текста (rich-формы)

С `rich=True` кнопка с ключом `ref` встаёт прямо в текст, а не в клавиатуру:

```python
await self.inline.form(
    text='Модуль обновлён. <tg-button ref="log">показать лог</tg-button>',
    message=message,
    rich=True,
    reply_markup=[
        {"ref": "log", "callback": self.show_log, "style": "link"},
        {"text": "Закрыть", "callback": self.close_cb},
    ],
)
```

- Надпись — это текст между тегами. У кнопки должен быть `url`, `callback`
  или `data`.
- `style` — `danger`, `success`, `primary` или `link`. `link` работает только
  у callback-кнопок и выглядит как обычная ссылка.
- Кнопки без `ref` остаются в клавиатуре под сообщением.
- Если Telegram не примет rich-сообщение, форма уйдёт обычным текстом, а
  надписи кнопок останутся простым текстом.
- Rich-сообщения в Telegram могут отправлять только боты, поэтому они всегда
  идут через инлайн-бота; через `app.send_message` их не отправить.
- Rich-формы используют Bot API 10.3. Приложения Telegram, которые ещё не
  поддерживают rich-сообщения, могут показывать их иначе.

### Списки и галереи

```python
await self.inline.list(message, ["страница 1", "страница 2", "страница 3"])

await self.inline.gallery(
    message,
    ["https://.../1.jpg", "https://.../2.jpg"],
    caption="Котики",
)
```

Вместо списка `gallery` принимает и функцию (обычную или async). Она должна
возвращать URL или список URL и вызывается за новыми фото, пока пользователь
листает галерею.

### Инлайн-команды

Инлайн-команда срабатывает, когда кто-то набирает `@ваш_бот name args`:

```python
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

@loader.inline_handler()
async def weather_inline_handler(self, app, inline_query, args):
    """Погода в инлайн-режиме"""
    await inline_query.answer(
        [
            InlineQueryResultArticle(
                id=utils.random_id(),
                title=f"Погода: {args or 'London'}",
                input_message_content=InputTextMessageContent("🌤 21°C"),
            )
        ],
        cache_time=0,
    )
```

- Имя команды — имя метода без `_inline_handler` или имя, переданное в
  `@loader.inline_handler("name")`.
- Метод, имя которого оканчивается на `_inline_handler`, работает и без
  декоратора.
- Сигнатура: `(app, inline_query, args)` или `(app, inline_query)`; аргументы
  также лежат в `inline_query.args`.
- Пользоваться инлайн-командами могут только вы и владельцы. Чтобы открыть
  команду всем, добавьте `@loader.everyone`.
- `inline_query` — объект aiogram 2.

### События бота

- `@loader.callback_handler()` на методе (или имя, оканчивающееся на
  `_callback_handler`) получает **каждое** нажатие кнопок бота как `(call)`.
  Проверяйте `call.data` и сразу выходите, если кнопка чужая. Используйте это
  для кнопок с `data`.
- Метод `<name>_message_handler(self, app, message)` получает сообщения,
  которые пишут боту в личку, по умолчанию только ваши. Чтобы принимать
  сообщения от других, добавьте `@loader.on_bot(lambda self, app, message: True)`.
- `self.inline.ss(user_id, state)` и `self.inline.gs(user_id)` хранят простое
  состояние пользователя для диалогов с ботом.

## Диалоги

Для пошагового общения с другим ботом используйте `fsm.Conversation`:

```python
from shizu import fsm

async with fsm.Conversation(app, "@BotFather", purge=True) as conv:
    await conv.ask("/mybots")
    reply = await conv.get_response(timeout=30)
```

`purge=True` удаляет сообщения диалога после завершения. `ask_media(path, "photo")`
отправляет файл.

## Зависимости и условия загрузки

Специальные комментарии в начале файла:

| Комментарий | Действие |
|---|---|
| `# required: requests bs4` | pip-пакеты: ставятся, если импорт не удался, после чего модуль загружается снова |
| `# only: 123456,789012` | модуль загрузится только на аккаунтах с этими ID |
| `# tl-only` | модуль загрузится только при включённом режиме Telethon |

Пакеты ставятся в виртуальное окружение, а если Shizu запущен без него — в
`.module_dependencies`. Об установке пакетов пишется в чат логов.

Тяжёлые или необязательные пакеты импортируйте внутри функций, если модуль
должен загружаться и без них.

## Общие библиотеки

Код, который нужен нескольким модулям, можно вынести в библиотеку:

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

В модуле:

```python
async def on_load(self, app):
    self.lib = await self.import_lib("https://example.com/weather_lib.py")
```

Библиотека скачивается один раз на URL и общая для всех модулей. У неё есть
`self.client`, `self.db`, `self.inline`, `self.get/set/pointer` (свой раздел
в базе), и она поддерживает `# required:`. Библиотеки проходят то же
одобрение, что и модули.

## Утилиты

`from shizu import utils`:

| Функция | Назначение |
|---|---|
| `escape_html(text)` | экранировать `<`, `>`, `&` |
| `remove_html(text)` | убрать теги |
| `answer(message, text, ...)` | то же, что `message.answer` |
| `answer_file(message, file, caption=)` | отправить файл |
| `send_table(message, rows, header=, title=)` | таблица rich-сообщением, при неудаче — `<pre>` |
| `get_user(message)` / `get_target(message)` | пользователь / его ID из ответа или аргументов |
| `get_chat_id(message)` | ID чата |
| `get_display_name(entity)` | имя пользователя или название чата |
| `get_message_link(message)`, `get_entity_url(entity)` | ссылки |
| `run_sync(func, *args)` | выполнить блокирующий код в потоке |
| `spawn(coro)` | безопасно запустить фоновую задачу |
| `chunks(list, n)` | разбить список на части по `n` |
| `rand(n)` / `random_id()` | случайные строки |
| `formatted_uptime()` | время работы юзербота |

Методы модуля на `self`:

| Метод | Назначение |
|---|---|
| `await self.invoke("help", "Notes", message=message)` | выполнить другую команду |
| `await self.animate(message, frames, interval)` | прокрутить сообщение по кадрам |
| `await self.request_join(peer, reason)` | спросить вас в чате с ботом, вступить ли в чат |
| `self.all_modules.get_module("Name")` | другой модуль |

## Модули Telethon и Hikka

При включённом режиме Telethon (`.enabletlmode`) Shizu загружает и модули на
Telethon, в том числе большинство модулей Hikka/Heroku. Они распознаются по
импортам и сигнатурам (`async def cmd(self, message)`, `@loader.tds`,
`from .. import`) и преобразуются при загрузке. В таких модулях:

- обработчики принимают `(self, message)` с сообщением Telethon;
- `self.client` — клиент Telethon;
- [фильтры сообщений](#фильтры-сообщений) работают так же;
- `@loader.raw_handler(UpdateType)` получает «сырые» обновления Telethon.

Без режима Telethon такие модули не загружаются. Новые модули лучше писать
в стиле Pyrogram, описанном выше.

## Правила безопасности

Сторонние модули выполняются внутри процесса Shizu, но для них действуют
защиты:

- **Одобрение.** Модуль из неизвестного источника не запустится, пока вы не
  одобрите его в боте: придёт карточка с его импортами, хостами и опасными
  вызовами. Ссылки из официального репозитория ShizuMods считаются
  доверенными. Изменённый код нужно одобрить заново.
- **Заблокированные методы.** Вызовы, через которые можно угнать аккаунт,
  отклоняются: экспорт и импорт авторизаций, токены входа, список и сброс
  сессий, пароль и 2FA, смена номера, удаление аккаунта, вход и выход.
- **Файлы сессий.** Модули не могут открыть файлы `*.session` и хранилище
  сессий.
- **Коды входа.** Обработчики сторонних модулей никогда не получают сообщения
  от служебного аккаунта Telegram (777000).

Вызов заблокированного метода выбрасывает `BeSafe.Forbidden`, а вам приходит
уведомление с именем модуля. Не пытайтесь обойти эти проверки: такой модуль
уберут из доверенных.

Общие советы:

- Никогда не пишите в лог и никуда не отправляйте токены, `config.ini` и
  содержимое базы.
- Для секретов в конфиге используйте `validators.Hidden`.
- Блокирующие сетевые и дисковые операции запускайте через `run_sync`, чтобы
  юзербот не зависал.

## Полный пример

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

## Частые проблемы

| Проблема | Причина |
|---|---|
| Модуль не загрузился, ошибки нет | `@loader.module(...)` стоит не прямо над `class`, или модуль ждёт одобрения в боте |
| `NFA` при загрузке | в `# only:` нет вашего аккаунта |
| `OTL` при загрузке | модулю нужен режим Telethon (`.enabletlmode`) |
| Команда не отвечает другим людям | по умолчанию доступ есть только у вас, владельцев и через `.permissions`; добавьте декоратор доступа |
| Вотчер с тегами получает и медиа без текста | строковые теги выключают `only_messages`; добавьте тег `"only_messages"` |
| Изменение в pointer не сохранилось | изменён вложенный объект; присвойте ключ заново |
| `Unknown string` | ключа нет в `strings` |
| Кнопки пишут «This button has expired» | форма пропала после перезапуска или по `ttl`; отправьте новую |
| Модуль не грузится после установки пакетов | имя пакета в `# required:` отличается от имени импорта |

Логи: `.logs` присылает файл лога, ошибки команд также приходят в чат логов.
