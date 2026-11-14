# Yomu Note for beginners — a guided tour of the source

This guide explains not only **what** a piece of code does, but also **why it exists** and **what can break if you change it**. The codebase has an important split between the *data model* and the *Qt UI*. You can follow this guide without knowing advanced Python.

## 1. Basic Python terms

- **Module:** A `.py` file. Example: `notebook.py`.
- **Class:** A blueprint for objects. `Notebook` is a class; your current study notebook is one instance.
- **Method:** A function owned by a class. `notebook.save()` is a method.
- **Signal:** Qt's way to announce an event. A checkbox sends a signal when its state changes.
- **Slot/callback:** A function that reacts to a signal or an event.
- **Worker thread:** A separate execution lane for slow work such as copying PDFs. It must **not** directly update Qt widgets.
- **SQLite transaction:** An all-or-nothing group of database writes. If a step fails, the writes can roll back.
- **Manifest:** JSON metadata describing which tabs/pages exist and where their files live.
- **Undo command:** A reversible change with both `undo()` and `redo()` methods.

## 2. Follow the app from startup

```text
main.py
  -> creates QApplication (Qt's central event loop)
  -> constructs MainWindow (yomunote/window.py)
  -> opens a Notebook (yomunote/notebook.py)
  -> creates one ProjectPane per tab (window.py)
       -> Page navigator + Preview/annotations + NotesEditor
```

`QApplication.exec()` is a **loop** that responds to mouse/keyboard/timer events. It doesn't reach the next line until the app quits. Don't put long disk work inside a button callback; the UI would freeze.

## 3. What's in a notebook?

```text
YourCourse.yomunote              <- ONE SQLite database on disk
  meta('manifest')               <- Notebook name and tab IDs/order
  files                           <- Referenced tab assets as BLOBs

Temporary notebook WORKSPACE      <- an extracted working copy
  tabs/<tab-id>/project.json     <- each tab's page/notes/annotation model
  tabs/<tab-id>/originals/       <- full-quality source documents
  tabs/<tab-id>/pages/           <- internal page data, when needed
  tabs/<tab-id>/cache/           <- disposable previews (NOT shared)
```

`notebook.py`: `Notebook.load()` reads the SQLite container, checks paths/sizes, and extracts a workspace. `Notebook.save()` writes changed files into SQLite using bounded 1 MiB chunks and commits a transaction. In-memory `Notebook.tabs` is a list of *visible* tab entries. `Notebook.close()` cleans up its temporary workspace once workers are finished.

`project.py`: `Project.load()` validates the JSON for ONE tab: page IDs, notes, annotations, group hierarchy, rich text etc. **Never use PDF page numbers as unique IDs**: the same source PDF can be imported multiple times.

**Do not mix up two version fields:** `app_version` is informational and changes each release; `version=5` describes the storage schema and should not change without a migration.

## 4. The three-pane window

`window.py` is the largest module, because the UI coordinates multiple kinds of state. The most important pieces are:

- `MainWindow`: app menus, notebook lifecycle, tab bar, current workspace and notebook-level history.
- `ProjectPane`: the three-pane UI for ONE tab, page selection, reading state, preview, notes and per-tab history.
- `ImageCanvas`: Qt graphics scene for document image and vector annotation items.
- `NotesEditor` (in `editor.py`): rich text and formatting toolbar.
- `PageGroupsTree` (in `page_groups_ui.py`): nested chapter groups and navigator page selection.

**Crucial:** a page *visible in the preview* is not automatically *explicitly selected* in the navigator. Paste/import operations that need an insertion anchor must use the navigator's selection; otherwise they can insert content in surprising positions. This distinction is intentional and already tested.

## 5. Tab Exchange: how to safely share Week 4

```text
Student A exports Week 4
  1. User selects tab(s) via TabExchangeDialog
  2. export_tabs() opens the source READ-ONLY
  3. Select only referenced originals and project.json
  4. Stream those assets to a NEW SQLite container
  5. Verify SQLite and create the new filename exclusively

Student B imports Week 4
  1. inspect_notebook() reads source tab names and sizes
  2. User chooses tab(s)
  3. stage_import() validates every referenced file
  4. Each selected tab gets a NEW ID and a temporary copied project
  5. commit_import() adds all tabs together, then records one Undo
```

Why are IDs regenerated? Two notebooks might both have a `Week 4`, but they must never share their internal identity. IDs, unlike names, are stable even if users rename tabs.

Why a staging folder? An unexpected disk error on page 49 should not leave half of a classmate's tab installed. Only after the entire batch has passed validation do we change the current notebook.

Why exclude files not referenced by living pages? A deleted page may still exist in SQLite storage or old backups; transferring those can accidentally disclose private notes.

## 6. Undo and Redo are not the same as saving

`history.py`: `UnifiedHistory` keeps a bounded sequence of reversible **operations**. For a Tab Exchange import, one history entry owns the *batch*, not one entry per page. Undo removes the imported tabs from the visible notebook and saved manifest, while their temporary working files remain available to Redo. They are cleaned up on notebook close.

`NotesEditor` also relies on `QTextDocument` for native text typing Undo. Destroying the Qt document while Undo still refers to it causes crashes; keep referenced documents alive until their histories are cleared.

## 7. Qt signals and why thread ownership matters

`tasks.py`: `Task` runs slow file operations in a `QThreadPool`; `GuiReceiver` delivers the results back to the main thread using a queued Qt signal. Widgets belong to that main thread. If a background task finishes after the user closes a tab, its handler must check whether the tab still exists before touching it.

`import_review_dialog.py`: Never delete/rebuild the chapter tree *inside its own* `itemChanged` callback. The callback is running on an item which Qt still owns. In-place checkbox updates with blocked nested signals fixed a real crash in v0.8.0a.

## 8. Other modules by feature

| Module | What it does | One thing to preserve |
| --- | --- | --- |
| `importers.py` | Imports originals and indexes PDF pages | Index lazily; don't rasterise a whole 600-page PDF |
| `import_selection.py` | Parses page ranges and chapter/page intersection | Physical source page numbers remain stable |
| `import_review_dialog.py` | GUI for editing chapters/import plan | No recursive tree rebuilds on checkbox clicks |
| `page_groups.py` | Pure-Python chapter group hierarchy | A page belongs to one stable flat order |
| `page_groups_ui.py` | Navigator tree, selection and drag/drop | Preview ≠ explicit selection |
| `vector_marks.py` | Validation and transforms for annotations | Reject invalid marks before drawing |
| `ocr_engine.py` | Crops images and invokes local Tesseract | OCR is off the UI thread and offline |
| `ocr_runtime.py` | Finds bundled OCR executable and language data | Prefer private app-bundle paths |
| `pdfium_guard.py` | One shared lock for native PDFium calls | Avoid unsafe simultaneous native PDF access |
| `import_staging.py` | Cleans aborted imports | Don't delete referenced originals/Undo data |
| `reading_progress.py` | Pure data for completion counters | Count each page only once |
| `reading_rewards.py` | Optional celebratory feedback | Don't trigger fireworks during reload/Undo |
| `notes_tables.py` | Rich-text table editing helpers | Keep native Ctrl+Z behaviour intact |
| `notes_layout.py` | Page margins and paragraph layout | Preserve rich-text HTML formatting |
| `ui.py` | Wrapping toolbar controls, icons, Pomodoro | Keep small-window responsiveness |
| `lifecycle.py` | Retires closed notebook workspaces | Wait for outstanding workers before cleanup |
| `diagnostics.py` | Local application error log | Never log private document/OCR content |

## 9. How to make a safe change

1. Make a fresh copy of the current source and notebooks.
2. Locate the smallest function that owns the behaviour; avoid unrelated refactors.
3. Add a test reproducing the error **before** changing the logic.
4. If a Qt callback crashes, look for object deletion, signal recursion or stale worker completions.
5. Run `python -m pytest -q` and `python -m compileall -q main.py yomunote ocr_packaging tests`.
6. Test Windows/Mac app behaviour with real PDFs; many Qt tests can't run in a headless environment.
7. Update the changelog and app version, but do **not** bump the notebook *schema* just because the app release changed.

For existing design context, see `DEVELOPER_GUIDE.md` and `BEGINNERS_CODE_GUIDE.md`.
