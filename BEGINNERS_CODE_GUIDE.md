# Yomu Note: a beginner's guide to the source code

This guide assumes you have never programmed before.

It is intended to stay readable when your code editor
occupies less than half the screen. Most explanatory lines
are kept below about 74 characters in length.

## 1. What is a Python module?

A Python file ending in `.py` is called a **module**.
It contains instructions for the computer.

A module can include:

- **Variables:** names for values or objects.
- **Functions:** reusable sets of instructions.
- **Classes:** blueprints for objects with behaviour.
- **Comments:** explanations that Python ignores.
- **Imports:** tools from another module or library.

A line beginning with `#` is a comment.
A description enclosed in triple quotes is a *docstring*.

## 2. Where to start exploring

The most useful places to start are:

| File | What it does |
|---|---|
| `main.py` | Starts the application. |
| `yomunote/window.py` | Builds the main window and its panels. |
| `yomunote/editor.py` | The rich-text notes editor. |
| `yomunote/notebook.py` | Saves and opens `.yominote` files. |
| `yomunote/project.py` | Validates the contents of each tab. |
| `yomunote/importers.py` | Imports documents and draws PDF previews. |
| `yomunote/ocr_engine.py` | Extracts text with local OCR. |
| `yomunote/pdfium_guard.py` | Prevents unsafe PDF processing overlap. |
| `yomunote/tasks.py` | Runs slower jobs without freezing the UI. |
| `yomunote/diagnostics.py` | Records error details locally. |
| `tests/` | Small programs that check expected behaviour. |

Start with the **docstring** at the beginning of each file.
Then look for a function whose name describes your interest.

## 3. A tiny example: why a lock is necessary

Imagine that PDFium is one shared printing machine.
Two workers must not operate its controls simultaneously.

A **lock** is like a sign saying "machine in use".

```python
with PDFIUM_LOCK:
    document = pdfium.PdfDocument(str(source))
    try:
        count = len(document)
    finally:
        document.close()
```

`with` obtains the lock and releases it automatically.

`try` and `finally` tell Python to close the PDF,
even if an error occurs while counting the pages.

This is important because a broken background worker
must not leave a PDF handle open or corrupt another job.

## 4. What is a notebook file?

A `.yominote` file is a **SQLite database**.

A database is a structured place for saving information.
A database *table* resembles a spreadsheet:
rows hold individual records and columns hold fields.

Yomu Note keeps two main tables:

- `meta`: the notebook's identity and list of tabs.
- `files`: project files and imported source materials.

The original PDF files can be quite large.
Yomu Note copies them to SQLite in small pieces,
so a gigabyte-sized PDF does not need a second
one-gigabyte buffer in memory.

## 5. Why deleted files need special treatment

When you delete a page, Undo must still work.

That creates two separate questions:

1. Is the source still needed *in this editing session*?
2. Is the source still needed *in the saved notebook*?

Yomu Note keeps temporary source files during the session
so Undo can restore a page.

When saving, it stores only files referenced by pages
that still exist in the notebook.

A database might retain unused internal space.
The **Export Clean Notebook for Sharing** command uses
SQLite's `VACUUM INTO` operation to build a fresh copy.
This is safer to share than an older, repeatedly edited file.

**Important:** old backups are separate documents.
Cleaning one notebook does not delete its backups.

## 6. How safe recovery works

A bad annotation should not destroy good study notes.

If a notebook cannot open, Yomu Note can offer recovery.
It first makes a **separate copy** of the original.

Only that copy is allowed to skip invalid annotations
or reset cosmetic settings such as broken panel widths.

A damaged path or notebook structure is still rejected.
This stops recovery from accepting deliberately unsafe files.

Always check recovered notes before using the copy.

## 7. What is a background task?

A normal Python function runs in order, one step at a time.
But a slow operation can freeze the app if it runs on
the main interface thread.

Yomu Note uses `start_task()` to run work elsewhere.

The worker handles file and image processing.
When it finishes, Qt delivers the result back to the
main window thread, where widgets may be updated safely.

**Rule:** never change a Qt widget from a worker thread.

## 8. How error logs help

An *exception* means something unexpected happened.

The short error message appears in Yomu Note.
A more detailed traceback can be saved locally to:

- Windows: `%LOCALAPPDATA%/Yomu Note/Logs/errors.log`
- macOS: `~/Library/Logs/Yomu Note/errors.log`
- Linux: `~/.local/state/yomu-note/logs/errors.log`

Logs do not upload themselves to any service.
They may mention filenames, so review them before sharing.

## 9. How to test a change

From the project folder, run:

```powershell
python -m pytest -q
```

A result like `183 passed` means those checks succeeded.

Some tests require **PySide6**, the Qt interface library.
They may be skipped if Qt is unavailable on that machine.

A passing test does **not** guarantee that every
screen, operating system, or document works perfectly.
Always try important changes in a spare test notebook.

## 10. How to add readable comments

Prefer this:

```python
# Keep this file in the temporary workspace.
# An Undo command may still need it later.
# It must NOT be included in the shared notebook
# once no live page refers to it.
```

Avoid extremely long comments that require horizontal
scrolling. Aim for about 70 to 78 characters per line.

Useful comments explain **why something is necessary**,
not just repeat what the next line already says.

Whenever you change unfamiliar code:

1. Read the module's opening docstring.
2. Find the relevant function.
3. Check which other functions call it.
4. Make one small change.
5. Run tests.
6. Keep the previous working build until verified.

Yomu Note is being documented gradually, starting with
the safety-critical modules in this release. This guide
does not mean every older function is documented yet.

## 9. How the rich-text notes editor stores formatting

Yomu Note uses a Qt widget called `QTextEdit`.
This provides an editable text area with fonts and paragraphs.

The text itself lives inside a `QTextDocument`.
A **document** is the whole body of notes being edited.

A `QTextBlock` is one paragraph in that document.
A single paragraph may wrap across several visible lines.
Wrapping does not create extra blocks or new list items.

A `QTextCursor` is a position or selection in that document.
Code can use a cursor to apply formatting to one block.

A `QTextBlockFormat` stores settings such as margins,
heading level and line spacing for a paragraph.

A `QTextCharFormat` stores character formatting such as
font size, bold, italics, text colour or highlighting.

These two format types are different on purpose:
changing one heading must not move the neighbouring bullets.

### What does 0 pt paragraph spacing mean?

The app has a default amount of space after paragraphs.
But sometimes you want *no* gap after a particular paragraph.

Earlier code could confuse those two situations:

- No personal spacing setting: inherit the default.
- Explicitly set 0 pt: make the gap zero.

Yomu now records an explicit override on the actual block.
The number is saved in typographic **points** rather than
on-screen **pixels** so the setting travels more reliably.

See `yomunote/notes_spacing.py` for the storage helper.
It contains explanations above the related functions.

### Why does Yomu have its own Undo history?

Qt already knows how to undo typing and text formatting.
But Yomu also handles page moves, PDF annotations and tabs.

`yomunote/history.py` coordinates all of those operations.
The editor's right-click Undo now uses that coordinator too.
This stops a context-menu Undo from silently skipping it.

Page Setup is special because it affects two places:

1. The actual paragraph formatting in Qt.
2. The default settings saved in the notebook.

When undoing Page Setup, both must return to matching values.
Otherwise the visible page and saved settings disagree.

### How to test an editor change

After making changes, run:

```powershell
python -m pytest -q
```

Some tests need the desktop Qt library (`PySide6`).
When it is missing they are marked as skipped.
A skipped test does **not** mean the interface was verified.

For on-screen tests, build the app and check the features
in both a light theme and a dark theme.


---

## New in v0.6.6: tables inside the notes editor

Start with `yomunote/notes_tables.py`.

A **module** is a Python file. This module holds the table tools,
so the very large `editor.py` does not need to manage everything.

A **class** groups related functions and information.
For example, `TableTools` has functions for inserting tables,
adding rows and columns, and changing borders.

A **function** is a named set of steps. When you see
`def add_row_below(self):`, it means the steps following that
line are run when the Add Row Below action is selected.

A **QTextTable** is Qt's actual table object. Each cell contains
editable text. We do not type spaces or use a fake marker to
create rows and columns: Qt handles the grid structure.

`QTextCursor` represents a position inside the text document.
It is used to insert a table, move to a cell and edit its
contents. A cursor in code does not mean the mouse pointer.

A **callback** is a function passed to another function to be
run later. Here, a callback groups a table edit into one
Undo operation while keeping the same reading position.

`beginEditBlock()` and `endEditBlock()` tell Qt that several
small changes belong to ONE history action. This is why
adding a row should not require five separate Undo presses.

A **temporary overlay** is drawn over the editor but is not
stored with the words. Our table guides are a good example:
`paint_table_guides()` draws grey dashed lines, while the
real border setting remains zero. Once you click elsewhere,
the guides disappear, but your words and cell structure stay.

A **signal** is how one Qt part announces that something
happened. A menu action has a signal called `triggered`.
Connecting that signal to a function makes the button work.

The ten extra colour palettes live in `window.py` under
`THEMES.update({...})`. Each palette uses the same named
colours (`paper`, `ink`, `accent`, etc.), so existing menus
and dialogs inherit those colours without special handling.

### Testing a change safely

- Copy the project folder before making major edits.
- Make one small change at a time and run the tests.
- `python -m pytest -q` runs all included checks.
- GUI tests need PySide6 and a working Qt application.
- Keep a known working build while testing a candidate.


## v0.6.6a: Why table guides are not document borders

A **table** stores text in actual rows and columns.

The temporary dashed lines are just a drawing on screen.
They must never be stored as real document content.

The old code used the typing cursor to guess where a
column started. But centring text moves that cursor.
It does **not** move the actual table column.

The new code reads percentage widths from the real table
format instead. It then draws guides at those positions.

A **merged cell** covers several squares of a grid.
We check which real cell owns each square before drawing
a border or deleting a row or column.

An **Undo transaction** groups changes into one step.
After a row is deleted, Qt can restore its contents using
Undo while the editor remains open. The saved HTML only
contains the cells still present in the document.

See `yomunote/table_grid.py` for small calculations
that are readable even without knowing anything about Qt.
