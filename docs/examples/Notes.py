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
