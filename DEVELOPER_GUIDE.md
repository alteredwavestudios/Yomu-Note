# v0.4.4 architecture — read before changing notebook storage

**Main contract:** `Notebook` (`yomunote/notebook.py`) owns exactly one portable
`.yominote` **SQLite FILE**, containing a format v5 manifest and a mapping of
`tabs/<uuid>/project.json`, `tabs/<uuid>/originals/...` and
`tabs/<uuid>/pages/...` to SQLite file BLOBs. Each internal tab uses the
existing v4 `Project` and `ProjectPane` unmodified where possible. Generated
`cache/` paths are NEVER copied into SQLite or backed up.

`Notebook.create` and `.load` allocate a temporary working directory for
file-based import/render backends. `Notebook.save` compares per-file mtime and
size and updates **only changed entries**, using `sqlite3.blobopen` in 1 MiB
chunks, enclosed in an atomic transaction (synchronous=FULL). Do not replace
this with `Path.read_bytes()` on large PDFs or recreating a ZIP each keystroke.
The working directory may temporarily use considerable disk space for large
originals; it is not a persistent render cache.

Migrations: `Notebook.load(path_to_v2_v3_v4_folder)` first validates its old
`Project`, creates a NEW `.yominote` file beside the legacy folder, and copies
only `originals/`, `pages/` and `project.json`. It never edits the legacy
folder. The outer format is v5, the inner tab manifests remain v4. Old apps
cannot read v5 files. Do not remove `Project.load` v2-v4 validation.

`MainWindow` now has one `self.notebook` and uses `QTabWidget` only for internal
tabs. `ProjectPane.on_container_save` commits its manifest via Notebook
without calling `QTextEdit.setHtml`, which would destroy text Undo history.
Inactive panes call `deactivate()` and stop image timers, clear at most 20
in-memory thumbnail icons, clear displayed preview/temporary bicubic pixmaps
and cancel stale async rendering tokens. The tab-delete Undo stack is separate
from Qt text-undo and page/annotation histories, avoiding shortcut conflicts.

Delete tab commands exclude the removed tab from the saved container but retain
its temporary source files for in-session Undo. Physical temp-folder cleanup
happens when the notebook closes. Page copy/move transfers original file paths
between project tab folders, never cache images, and copies a shared PDF only
once per selected group.

Backup timer: every 600,000 ms, *if changed*, `Notebook.backup` snapshots the
current committed SQLite database via SQLite's backup API to a timestamped
filename, excluding all raster caches by design. Rotation respects
`backupCount` (default 30) **and** the 2 GiB per-project total cap (always
keeps newest). Backup folder defaults to the writable per-user app-data area
(e.g., `%LOCALAPPDATA%\Yomu Note\Backups`), NOT Windows' admin-protected
`Program Files\Common Files`. Restore creates a NEW file with a new project
identifier, and refuses to overwrite an existing file.

**Do not change:** importers.py PDF 12 MP cap, thumb 20-pixmap cap, lazy page
rendering, adaptive preview 12 MiB / 3 files, enlarged thumbnail 8 MiB / 20
files, per-page clipping/annotations, or v4 validation while implementing UI
features. A multi-tab container is not permission to cache pages for inactive
tabs.

To run: `python -m pytest -q`. GUI tests in
`tests/test_stage2_notebook_gui.py` skip when PySide6 isn't installed and
should be repeated on Windows/macOS before distributing a binary build.

---

## Stage 1 notes (v0.3.4e)

* Keep `yomunote/importers.py` cache quotas and `yomunote/project.py` format version unchanged. The new `resampling.py` is a pure in-memory Pillow helper for a **visible viewport crop**. Never use it for full-page rendering or disk cache creation.
* Autosave is scheduled in `ProjectPane.schedule_save`: an idle 2000 ms timer resets on every change, while a separate 20000 ms maximum timer starts only on the first dirty edit. Only `ProjectPane.save` clears these timers after a successful atomic manifest save; Qt document contents are never reset by autosave.
* Annotation commands use `AnnotationChangeCommand` and page IDs instead of row positions. The `QUndoStack` is capped at 75 commands. Any future annotation tools must be implemented as undoable commands, not one-way mutations.
* Viewport-only bicubic is a best-effort post-gesture enhancement, not a PDF rerender. Keep worker threads free from Qt GUI objects and do not remove the source/target pixel caps.
* For GUI smoke tests: set `QT_QPA_PLATFORM=offscreen` if supported; `python -m pytest tests/test_stage1_gui.py -q`. Also test physically on Windows/macOS for icon alignment, QPainter Multiply composition, font caret height, and scrollbar/trackpad performance.

# Yomu Note — beginner-friendly guide to the source code

Yomu Note uses **Python** to describe the app, **PySide6 (Qt)** to draw windows and respond to clicks, **PDFium** to render PDF pages, and **Pillow** to process images. Code is organised into modules rather than one giant script so individual features are easier to change without breaking unrelated ones.

## Where to start

1. `main.py` creates `QApplication`, sets global resource limits and starts the main window.
2. `yomunote/window.py` lays out the three columns, project tabs and toolbar actions.
3. `yomunote/editor.py` implements the rich-text editor and keyboard shortcuts.
4. `yomunote/project.py` opens/saves projects, validates paths, and migrates formats.
5. `yomunote/importers.py` imports original files and renders page images when necessary.
6. `yomunote/tasks.py` runs CPU/disk work away from the interface thread.
7. `yomunote/ui.py` supplies small reusable UI controls, animations and icons.

## `main.py`: startup

`main()` creates one Qt application instance. Applications need this before widgets exist. `QThreadPool.globalInstance().setMaxThreadCount(2)` limits background jobs to avoid exhausting smaller machines. `QPixmapCache.setCacheLimit(4096)` limits *Qt's global cache* to 4 MB; the active image remains held separately. `_font_warning_filter(...)` ignores **only** a known repetitive Qt warning for the GB18030 Bitmap fallback font; other Qt messages still go to stderr.

## `project.py`: data structures, safety and saving

`Project` is a `dataclass`, meaning it stores related fields (name, pages, note HTML, colour, annotations and paths) with convenient automatic initialization. `Project.create()` makes a `.yominote` folder with its required subdirectories; `Project.load()` reads and validates `project.json`. `Project.save()` writes a new manifest to a temporary filename, then replaces the existing one: interruption during writing is less likely to destroy the current manifest. `validate_relpath()` rejects filenames that could escape the project directory. `asset_path()` uses that validation and resolves symlinks to avoid reading other files. `duplicate_to()` copies a project without disposable caches.

**Do not change the `FORMAT_VERSION` without a migration plan.** Version 4 reads older v2 and v3 manifests, makes a backup before saving, and retains old `sumi://page/` links. New data is marked `yomu-note` and gets a per-project `highlight_color` field.

## `importers.py` and `tasks.py`: don't block the window

An imported PDF is indexed first, not immediately turned into hundreds of giant images. `image_for_page()` renders images as they're requested: small JPEG thumbnails for the left-hand column, and larger JPEGs for reading. `Task` wraps a function that runs on Qt's background worker pool. `TaskSignals` passes completion/errors back to the main GUI thread; `GuiReceiver` ensures that Qt widgets are never modified directly from a background worker.

**Qt rule:** `QPixmap` and widget operations belong on the GUI thread. The worker may read/write files, decode with Pillow or use PDFium, but should return a filename or result to the GUI.

## `window.py`: the three columns

`MainWindow` owns the window, project tabs, File/Edit/View/Settings menus, preferences, theme and About popup. `ProjectPane` is one tab's contents: page shelf, main preview, notes editor and autosave. `DropPageList` is a list with selection, reordering and a fading plus sign between pages. `ImageCanvas` is a Qt `QGraphicsView`: it displays one image and overlays non-destructive translucent rectangular highlights.

`ProjectPane.update_visible_thumbnails()` is critical for performance: it determines which page rows are on screen, loads only their icons, and clears icons from rows that have scrolled away. The active view is capped at 20 thumbnail pixmaps. When a tab is inactive, `deactivate()` releases its UI images; the original documents remain on disk. Avoid creating one full-resolution Qt bitmap for every page or making all pages visible at once.

The preview has two trackpad event paths: `viewportEvent()` handles gestures sent to its child viewport; `event()` handles native gestures delivered directly to `QGraphicsView`. `zoom()` applies the scale with upper/lower limits and keeps the pointer anchored. Page navigation shortcuts belong to the shelf or preview, not to the notes editor, to avoid breaking text editing.

## `editor.py`: hyperlinks and formatting

`LinkTextEdit` subclasses Qt's `QTextEdit`. Its `keyPressEvent()` receives key presses before the normal editor. On macOS, **Qt reports Command as `ControlModifier`** for cross-platform shortcut consistency; `MetaModifier` is not the correct test for Command here. `NotesEditor` wraps the text widget with formatting toolbar controls. Qt stores text formatting as `QTextCharFormat` objects, including font family, size, boldness and link state.

`insert_link()` first **copies** the `QTextCharFormat` at the caret. It enables a URL anchor on a *copy* for just the inserted text, then restores an explicitly *unlinked* format to the typing caret. The old implementation created an empty formatting object, resetting the font and leaving following text linked. `insert_page_link()` uses a single `↗` symbol and an internal `yomu://page/ID` address. `open_link()` still reads old `sumi://page/ID` links from v0.3 projects.

`setup_shortcuts()` creates editor-scoped `QShortcut` objects, so page navigation keys don't unexpectedly fire while writing. `make_list()`, `indent()`, `change_heading()` and `change_font_size()` operate using a `QTextCursor`. The tiny buttons are created using `WrapBar.addIconAction()` and grouped menus with `WrapBar.addMenuButton()`.

## `ui.py`: drawing and motion

`FlowLayout` positions widgets left-to-right, then wraps them when the pane gets too narrow. `WrapBar` uses this to prevent controls disappearing behind an overflow indicator. `line_icon()` draws crisp vector SVG line icons for controls without downloading an icon font.

`YomuWordmark` paints the two-line logo itself. It **caches the chosen installed font family in `__init__`** rather than querying all system fonts on every repaint. When the pointer enters the logo, an on-demand timer advances the gradient about 30 frames per second. The timer stops when the pointer leaves. Clicking emits a Qt `Signal` that `MainWindow` connects to its About popup.

`SoftButtonMotion` is an application-wide *event filter*: it observes mouse-enter, leave and left-click events on ordinary buttons. Each visited button receives a short shadow animation, **not** an always-running loop. `ColourDotButton` is a custom highlight button: its normal left-click toggles annotation, while right-click emits `colourRequested`, allowing a separate colour-picker dialog. `SaveToast` fades in at the bottom only when explicitly saving. `FocusTimer` uses `time.monotonic()` and a single one-second Qt timer to avoid time drift and avoid idle redraws.

## Debugging checklist

- Start by running the app from Terminal so genuine Python tracebacks remain visible.
- If a change affects saved data, add a migration and test under `tests/` before modifying real projects.
- If UI performance slows, search for unexpected `QPixmap` loading or repeated `QFontDatabase.families()` calls inside paint events.
- If text changes fonts after adding a link, inspect `insert_link()` and the restored `QTextCharFormat` at the cursor.
- If a shortcut misfires on Mac, remember the Command/Control mapping and the `QShortcut`'s `ShortcutContext`.
- When developing new animations, limit timers to an actively hovered/pressed element and respect the Reduce animations preference.
- Test on macOS for native trackpad gestures, focus/keyboard behaviour, and popup handling; static Python compilation cannot verify those interactions.


## v0.3.4d — movable pane headers and adaptive, bounded rendering

`ProjectPane` still contains one `QSplitter`, one `NotesEditor`, one `ImageCanvas`,
and one `DropPageList`. `ReorderGrip` starts a Qt drag containing a private
per-pane token and panel key. `PanelDropHeader` accepts only drags from the
same project tab, shows a before/after insertion marker and emits
`moveRequested`. `ProjectPane.apply_panel_order` calls `QSplitter.insertWidget`
with the EXISTING widgets; it never rebuilds any one of them. Pane sizes follow
their role. The View → Workspace Layout menu is a fallback if platform drag
behaviour differs. The NotesEditor already has a heading, so its grip is
inserted into that heading rather than creating a new title row.

`Project.panel_order` is an OPTIONAL validated list stored in the v4 manifest;
older v4 manifests default to classic order. `Project.splitter_sizes` remains
in the classic `[pages, preview, notes]` role order even when panes are reordered,
so older Yomu builds can still read the widths. `Project.duplicate_to()` omits
all `cache` folders and preserves the new layout field.

The normal page raster is still loaded before the optional adaptive one and
provides stable graphics scene coordinates for highlights. `_on_preview_zoom`
coalesces requests with a 260 ms timer. When zoom settles below 100% (taking
Qt high-DPI device scale into account), `_update_adaptive_quality` chooses a
ceiling 5% raster-size bucket and calls `image_for_page(level=...)` in a worker.
A supersampled PDFium bitmap is downscaled with Pillow Lanczos, converted to a
JPEG and stored in a tiny strict LRU cache. `replace_quality_image()` changes
only the image item's pixmap and its scale. Qt scene geometry, annotations,
zoom transform and scroll anchor remain stable. At or above 100%, Yomu uses
the normal page image with Qt SmoothPixmapTransform, no larger PDF raster.

The navigator measures `self.shelf.width()`, not `splitter.sizes()[0]`.
After resizing, `_thumbnail_width_for_view()` maps the icon width to a bounded
bucket. Only currently visible rows may generate an enlarged thumb; when rows
scroll away their icons are cleared as before. Never remove `THUMB_LIMIT` or
load enlarged thumbs for all document pages. Adaptive-preview files are
restricted to ≤3 and 12 MiB; responsive-thumb files to ≤20 and 8 MiB.

Old hi-res and fixed-tier cache JPEGs are removed once on project activation.
**No original source files, annotations or rich-text HTML are changed.**

GUI smoke tests in `tests/test_gui_workspace.py` and
`tests/test_render_gui_quality.py` can be run on Windows/macOS with PySide6;
they are skipped where Qt is unavailable. macOS gestures and cross-platform
visual layout must be tested on physical devices.
