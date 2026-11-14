# Earlier README and release history

The following is preserved verbatim from the v0.8.1 source. The top-level README is now a focused entry point for new contributors.

---

# Yomu Note v0.8.1 — Tab Exchange (source candidate)

**New:** File → Import Tabs from Notebook… and File → Export Selected Tabs as Notebook…, with a selection review, drag-and-drop of `.yomunote` files, isolated copies of complete tabs, and a single Undo/Redo action for each imported batch. The receiving notebook and the source notebook remain independent. See [`RELEASE_081_TAB_EXCHANGE.md`](history/RELEASE_081_TAB_EXCHANGE.md) and [`TEST_WINDOWS_MAC_V081.md`](testing/TEST_WINDOWS_MAC_V081.md).

This ZIP provides full **source**, not a prebuilt `.exe` or `.app`. Keep a backup of v0.8.0a until you test the new native app. Application version is **0.8.1**, notebook format remains **5**.

---

# Yomu Note v0.8 — Smart Import 3.0 (source candidate)

The next feature release adds **selective PDF page ranges and bookmark/chapter inclusion** to the existing non-destructive import review. All pages and chapters are included by default. Non-contiguous ranges, nested chapter selection, optional front matter and intersection filtering are supported. This also works for ordinary multi-page imports. The application version in About and notebook saves is `0.8`, while the notebook schema stays at v5.

**Start with [`RELEASE_080_SMART_IMPORT_3.md`](history/RELEASE_080_SMART_IMPORT_3.md) and [`TEST_WINDOWS_MAC_V080.md`](testing/TEST_WINDOWS_MAC_V080.md).** This ZIP contains the full source and build scripts, **not** a prebuilt Windows installer or macOS application. Keep backups before testing. OCR packaging, one-minute autosave, notes editing and older annotations are retained.

---

**Current source candidate: v0.7.6a — Integrated Offline OCR.**
The packaged Windows installer and macOS app include Tesseract and its English
OCR language data; end users need no separate OCR installation. **Build**
computers must have a trusted Tesseract distribution, which the revised
PyInstaller scripts collect automatically and verify. Run the normal build
script and see `OCR_BUILD_GUIDE.md` and `TEST_WINDOWS_MAC_V076A.md`.
This is a cross-platform *source candidate*, not a verified compiled Windows
installer or macOS app. Previous autosave, project format and UI remain intact.

**Current source candidate: v0.7.6a — Integrated Offline OCR (based on v0.7.6 stability).**

Compiled Windows and macOS packages now bundle local OCR when built with the platform scripts. The build machine needs Tesseract, but end users of the resulting application do not. See `AUDIT_076A.md` and `TEST_WINDOWS_MAC_V076A.md` for limitations and clean-computer verification.
Autosave now runs once around 60 seconds after the first unsaved change, not
on every 2-second typing pause. Manual saves and close/tab-switch protection
remain immediate; automatic recovery snapshots still use the existing
10-minute schedule. Closed or replaced notebook workspaces are released once
any background page/OCR tasks finish; deleted tabs stay available for Undo
until the notebook itself closes. No notebook format changes.

See `RELEASE_076_MEMORY_AUTOSAVE.txt`, `AUDIT_076.md` and
`TEST_WINDOWS_MAC_V076.md` before testing with your important notebooks.
This source was tested without a PySide6 GUI runtime; desktop checks remain.

**Current source candidate: v0.7.4 — Notes Pages & Navigator Stability.**
Each tab now supports independent named rich-text notes pages (add, rename,
cycle and undoable remove), while old single-page notes are preserved as the
first page with their original formatting and links. New notebooks use
`.yomunote`; old `.yominote` files open and produce a separate modern-extension
copy, leaving the original untouched. The Groups navigator now retains labels
without thumbnails or a wide sidebar, offers right-click page removal, and
uses measured non-overlapping progress counters. Includes tab-close spacing,
"Individual" navigator naming, and more comfortable group margins.

**Read `RELEASE_074_NOTES_PAGES_NAVIGATOR_POLISH.txt`, `AUDIT_074.md`, and
`TEST_WINDOWS_V074.md` before using this candidate on an important notebook.**
The Qt GUI tests could not run in the source-testing environment; Windows
validation and a backup are essential before making this your main build.

**Current source candidate: v0.7.3a Smart Import hotfix.** Newly imported groups and subgroups default to collapsed (switchable in Smart Import options), and custom [chapter]/{chapter} page labels use final reviewed chapter boundaries. See `RELEASE_073A_SMART_IMPORT_COLLAPSE_CHAPTER_LABELS.txt` and `TEST_WINDOWS_V073A.md`.

# Yomu Note v0.7.3 — Smart Import 2.0 (source candidate)

Smart Import now has explicit root/nested-group destinations, one understandable grouping control, and a non-destructive **Review Structure** window. PDFs with bookmarks provide page-accurate chapters/subsections; converted documents are used only when their PDF output preserves bookmarks. Review can rename, split, merge, indent and adjust page boundaries with its own temporary Undo/Redo. Read `RELEASE_073_SMART_IMPORT_2.txt` and `TEST_WINDOWS_V073.md` before testing the new build. Existing notebook files are compatible.

# Yomu Note v0.7.2b — Responsive Navigator & Kawaii Themes (source candidate)

Builds directly on v0.7.2a. Larger checkbox click targets, responsive compact
Groups navigator, six brighter themes, Playful celebrations by default, and a
fix for repeated KawaiiNotice Qt stylesheet warnings. Crisp contrast remains
the default for users without an explicitly saved preview preference.

See `RELEASE_072B_NAVIGATOR_THEMES.txt` and `TEST_WINDOWS_V072B.md`.
The full Windows/macOS GUI still needs testing before a stable release.

# Yomu Note v0.7.1 — Reading Progress & Smart Import (source test candidate)

**New in v0.7.1:** Read/unread checkmarks for individual pages and entire
nested groups, group and tab completion bars, and a notebook-wide status
indicator. Import and Smart Import now offer safe, configurable page-label
presets; Smart Import can create a group per document or combine selected
images into a single folder. Whole folders can be dragged and reordered,
including their nested pages, as one per-tab Undo action. Long PDF names no
longer become unsafe internal asset paths.

See `RELEASE_071_READING_PROGRESS_SMART_IMPORT.txt` and
`TEST_WINDOWS_V071.md` for details.

**Introduced in v0.7.0:** A collapsible Groups tree alongside the original
thumbnail navigator, nested folders, manual grouping, drag-to-reorder,
rename/ungroup/delete actions, and per-tab Undo for changes.

The original flat page order and page IDs remain authoritative for
next/previous navigation, annotations and rendering. A grouped page
still belongs to exactly one position in that list.

Older notebooks without group data load with all pages at the top level.

See `RELEASE_070_PAGE_GROUPS.txt` and `PAGE_GROUPS_BEGINNERS_GUIDE.md`.

This version builds on the v0.6.7b mouse-release safety hotfix.
It adds whole-table left/right indentation, a labelled **Edit Table**
right-click submenu, keyboard row/column deletion, and reliable
Delete on a corner-selected table. See
`RELEASE_067C_FINAL_TABLE_POLISH.txt`.

# Yomu Note v0.6.7b — Table Mouse Release & Deletion Safety

This candidate builds on v0.6.7a and fixes a serious input bug:
`LinkTextEdit.mouseReleaseEvent` was accidentally defined TWICE.
Python kept only the later definition, so table drags never ended.
Explicit `grabMouse()` then left Windows stuck in resize mode.

This build merges the handlers, removes mouse grabbing, adds
a missed-release watchdog, and introduces **Delete entire table**
with safe Undo. Older tables can opt into proportional widths.

See `RELEASE_067B_TABLE_MOUSE_RELEASE_DELETE.txt` and
`TEST_WINDOWS_TABLE_RELEASE_067B.md` for tests and limitations.

# Yomu Note v0.6.7 — Resizable Tables & Shortcuts

This source candidate builds on the table-integrity changes
from v0.6.6a. It adds draggable column widths, row extra
height, a corner selection handle, Table Properties, and
keyboard shortcuts for inserting tables, rows and columns.

The original PDFs, notes engine, OCR and notebook format
are unchanged. See `RELEASE_067_RESIZABLE_TABLES.txt`.

**Note:** Windows/macOS GUI behaviour requires local testing.

---

## Previous v0.6.6a notes

This candidate builds directly on v0.6.6.

- Avoid alignment-sensitive column guides and duplicate boundaries.
- Keep screen-only guides away from merged-cell interiors.
- Delete just the chosen row/column in one native Qt Undo step.
- Prevent partial deletion through merged cells.
- Move the caret into a surviving cell after deletion.
- Preserve proportional widths while adding/removing columns.
- Confirm current saved HTML excludes deleted cell content;
  clean exports exclude old database pages.

See `RELEASE_066A_TABLE_INTEGRITY.txt` and
`BEGINNERS_CODE_GUIDE.md`.

---

# Yomu Note v0.6.6 — Native Tables & Additional Themes

**Complete source candidate based on v0.6.5a.**

New: editable borderless tables in the notes editor, including a
3×2 insertion dialog, temporary editing guides, Tab / Shift+Tab
cell navigation, row and column tools, permanent border toggle,
cell padding options, merged cells, and table editing context menu.

Five light and five dark themes have also been added.
Existing notebook formats, OCR and vector annotations remain unchanged.

See `RELEASE_066_TABLES_THEMES.txt` for tests, limitations and
instructions. Start with `BEGINNERS_CODE_GUIDE.md` for explanations
of the new table module written for someone new to programming.

---

# Yomu Note v0.6.5a — List, Heading & Dialog Theme Hotfix

**This source test candidate builds on v0.6.5.**

This release addresses list alignment and new-item scroll jumps,
adds proper solid / hollow / square nested bullet styles, fixes
repeated indentation and synchronises the heading dropdown with
actual selected text. Dialog input widgets now inherit the selected
light or dark theme from one shared palette and stylesheet.

See `RELEASE_065A_LIST_HEADING_THEME_HOTFIX.txt` for details,
build commands and testing instructions.

The existing OCR, notebooks, annotations and formatting workflows
are unchanged. Keep v0.6.5 available until this candidate is
verified in the Windows desktop application.

For beginner-friendly code explanations, see `BEGINNERS_CODE_GUIDE.md`.

---

# Yomu Note v0.6.5 — Rich-Text Editor Reliability (source test candidate)

This release builds on **v0.6.4** and focuses on safe editing.
Selected paragraphs now receive their heading text formatting together,
clear formatting inherits theme ink, explicit zero-gap spacing remains
intact, and page setup is connected to notebook Undo/Redo.

See `RELEASE_065_EDITOR_RELIABILITY.txt` for the precise scope,
installation steps, testing and limitations.

For educational comments in narrow editor windows, start with
`BEGINNERS_CODE_GUIDE.md` and `yomunote/notes_spacing.py`.

---

# Yomu Note v0.6.4 — Stability & Data Protection (source test candidate)

**This release focuses on keeping notebooks safe.** It shares one PDFium lock
across OCR, imports and previews; protects saved notebooks from unused deleted
assets; offers a clean, compact copy for sharing; and introduces opt-in recovery
copies for damaged annotations or cosmetic settings. Errors now have local
traceback logs, and the code includes a beginner-friendly learning guide.

See `RELEASE_064_SAFETY_AND_BEGINNER_COMMENTS.txt` for details and limitations.
Start with `BEGINNERS_CODE_GUIDE.md` if you're new to programming.

## Previously added in v0.6.3

Adds a **per-project document page setup** (four margins, default line spacing,
paragraph-after gap), a **Line & Paragraph Spacing** toolbar menu, an optional
**Jump to Edit Position** button, and improved notes reflow anchoring.
Qt's native QTextBlock/QTextList data model and HTML storage remain in place.
Existing projects without page setup retain their earlier margins until you
choose **Settings → Notes Page Setup…**. New projects default to 72pt / 1in
margins, 1.15× line spacing, 8pt paragraph-after at 13pt base font, with
quarter-inch list nesting and no between-item gap.

**Use:** **Settings → Notes Page Setup…** for document-wide settings, or the
new spacing button in the notes toolbar to apply before/after and line spacing
to exactly the current/selected paragraphs. Enable **Jump to Edit Position**
in Preferences → Notes style, or use the More menu.

See `RELEASE_063_PAGE_SETUP_SCROLL_SPACING.txt` for details and test instructions.

---

# Yomu Note v0.6.2 — Notes View Anchoring & List Marker Rebuild (source test candidate)

This candidate builds on v0.6.1, preserving the OCR workflow and annotation tools. It rebuilds the note-list handling around explicit selected blocks, preserves the note view during indent/undo/resize, and stabilises list markers. See `RELEASE_062_NOTES_ANCHOR_LIST_MARKERS.txt`.

**New:** multi-rectangle selection directly over the existing PDF/image page preview,
mouse-wheel/trackpad and edge auto-scrolling on long pages, 300 DPI source
clipped-render OCR (200/400/600 optional), local Tesseract engine, per-region
reading order, clipboard copying, editable text review, installed language
selection, and the contextual freehand pen thickness slider.

**Important:** Tesseract is a **separate system installation**; it is not bundled
into this source ZIP or its Windows installer. Read
`RELEASE_060_OCR_TEXT_EXTRACTION.txt` for the install links, usage instructions,
current limitations and Windows manual smoke-test checklist. Original PDF and
image sources are recognised directly, not the pixelated preview or UI overlay.
The v0.4 notebook format, preview renderer, editor and existing annotations are
unchanged. Retain the working v0.5.4c as rollback while testing this candidate.

---

# Yomu Note v0.5.2a — Selection & Colour UI Hotfix (Source Candidate)

**Hotfix of v0.5.2.** Fixes a PySide6 selection-handle exception and replaces the crowded annotation controls with stacked Stroke/Fill swatches, a colour swap control, one Thickness control and a unified Opacity pop-up. Quick swatches target the clicked colour channel; double-click a colour chip or press + Colour for a custom colour. Right-click a chip to enable/disable stroke or fill where applicable.

Opacity is edited only in the Opacity pop-up; the system colour dialog no longer edits alpha. Edits to selected annotations remain undoable. Everything else in Yomu Note is deliberately left unchanged. **PySide6 GUI tests have not been executed in this build environment; please retain your working v0.5.1 as rollback.**

# Yomu Note v0.5.2 — Annotation Appearance & Highlight Tools (Source Candidate)

This candidate builds on the **v0.4.5d per-tab Undo and scroll hotfix**. It is a
complete cross-platform Python / PySide6 application source tree, **not** an
already compiled Windows executable. Keep your current installation and a
backup of your `.yominote` notebooks until you've tested this candidate.

## New in v0.5.2 — Annotation appearance only

- **Stroke and fill controls:** Independent RGB colours and 0–100% alpha, plus independent Stroke/Fill on/off switches. Opaque fills are supported. Every shape's line thickness can be edited afterwards in Select mode. The controls load the selected annotation's *actual* properties and revert to the tool's last-used defaults when you deselect.
- **Quick palette:** Ten compact swatches, up to three recent custom colours, a Stroke / Fill / Highlight target chooser, and a right-click "Apply to…" menu. The native custom colour dialog exposes alpha. The appearance panel can be collapsed.
- **Two page-highlighter modes:** The original rectangle and a new straight, flat-ended line highlighter under the highlight button. Both always Multiply against the page; neither has a separate outline. The line has editable thickness and Shift angle constraints. Both can be selected, moved, resized and erased.
- **Undo/Redo:** New shapes, highlights and completed appearance changes use the existing per-tab history. A single appearance change stores only the affected mark; live spinbox preview changes only an existing graphics item's pen/brush, not the PDF cache or history.
- **Compatibility:** Existing rectangular highlights, freehand marker strokes and old filled shapes retain their historical alpha if no new opacity is stored. Old rectangle highlights with no ID remain editable without deleting neighbouring highlights. Project manifest stays format v4.
- **Strict scope:** Only `vector_marks.py`, annotation validation in `project.py`, annotation canvas/toolbar/actions in `window.py`, and release/version/test files were changed. All notes editor behaviour, shortcuts, tab/page navigation/history and PDF rendering remain untouched.

**Testing:** The Python/QT-independent tests pass. PySide6 GUI tests are bundled but must be run on a Windows/macOS machine; the build environment cannot install PySide6. This is a source *candidate*, not a tested desktop release. Keep v0.5.1 available for rollback.

## Previously added in v0.5.1

- **Live pen preview:** Rebuilds the temporary path from the actual first mouse point; fixes the disappearing diagonal from the page's upper-left during drawing.
- **Marker:** New freehand highlighter tool with translucent **Multiply** blending. Existing older opaque Pen strokes and the original rectangular Multiply highlighter remain unchanged.
- **Shapes:** Line, Arrow, Rectangle and Ellipse are drawn as editable, page-relative vectors. Shift constrains lines/arrows to 45° or rectangles/ellipses to squares/circles. Alt/Option draws from centre. A **Fill shapes** checkbox adds a subtle translucent fill to rectangles/ellipses.
- **Resize:** In Select mode, click a saved pen stroke or shape to show handles; drag a corner to resize strokes, rectangles and ellipses, or an endpoint to adjust lines/arrows. Move and erase work for these marks too; each change is undoable/redoable in the current tab.
- **No other changes:** All non-annotation code, notebook/page/tab history, shortcuts, fonts, zoom and PDF preview remain based on v0.5.0. Older notes and annotations still load without migration.

## Previously added in Stage 3 / v0.5.0

- **Pen** draws editable, page-relative vector strokes in the centre PDF/blank-page
  canvas. They are stored as paths in notebook metadata, never painted into
  the PDF or the disposable JPEG cache. Change pen colour with its colour dot
  and thickness with the `pt` spinner.
- **Select** lets you click and drag an existing pen stroke to a new position.
  The entire path is constrained to the page bounds. **Eraser** removes one
  clicked stroke, not the underlying PDF. **Pan** returns to ordinary navigation.
- **Highlights** remain supported and are preserved when older notebooks load;
  use the original highlighter button. `Clear Marks` removes all annotation
  types on the active page (undoable).
- Each draw/move/erase is **one Undo/Redo action inside its own tab**. Actions
  retain compact stroke deltas rather than entire page mark lists.
- **Delete Tab** is tracked in separate notebook-level structural history.
  Ctrl/Cmd+Z and Edit → Undo can restore it **from any surviving tab**,
  without sharing normal text/page/annotation histories across tabs.
- **Between-page +** freezes the gap index when its popup opens, so both
  `Import File…` and `Add Blank Page` target the intended location.
- Existing rendering, font-size fixes, shortcut mappings, horizontal tab-strip
  navigation and memory-bounded PDF preview pipeline are otherwise retained.

**Earlier v0.5.1 scope:** That version originally included shape/resizable pen support. v0.5.2 additionally supports selecting and resizing rectangle highlights. Sticky notes, text boxes, annotation-to-notes linking and grouping are not included.

**Runtime status:** Python syntax and Qt-independent tests pass. The desktop interactions must still be checked in Windows because PySide6 is not installed in the build environment. Keep your working v0.5.0 version available for rollback.

## Build and test on Windows (PowerShell)

Open PowerShell inside the extracted source folder and run:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
uv pip install --python .venv\Scripts\python.exe pytest
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:QT_QPA_PLATFORM
.\.venv\Scripts\python.exe main.py
```

To build the Windows executable and an Inno Setup installer:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-windows.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-installer-windows.ps1
```

Inno Setup 6 or 7 is needed for the installer. The installer preserves Yomu
Note's existing Windows application ID so it upgrades the installed app.

## Windows smoke test checklist

1. Create a notebook with **three pages**, use the between-page + to add a
   blank page in the **middle** and verify its order; Undo and Redo it.
2. Draw several pen strokes on a blank page and an imported PDF. Select and
   move one, erase another, Undo and Redo both; change zoom / preview quality.
3. Save, close, reopen the notebook: strokes and existing highlights must
   retain exactly the same positions.
4. Make notes edits in two tabs, delete one tab, switch to another remaining
   tab and press Ctrl+Z: the deleted tab should reappear, complete with notes.
   Redo should delete it again. Undo/Redo of ordinary edits must remain per-tab.
5. Check the previous font resizing, tab scrolling and Ctrl+K page-linking
   behaviour remains unchanged.

**Testing limitation:** Pure-Python automated tests and source compilation
passed during packaging. PySide6 is unavailable in the authoring environment;
the Qt UI tests are included but could not run here. Test on your Windows system
before replacing your production installation.

---

# Yomu Note v0.4.5b — Regression Fixes (Source Candidate)

**Testing candidate:** Keep v0.4.5a and a backup of your `.yominote` files.
This is the **complete source tree** with Windows `.exe` and Inno Setup
installer build scripts; it is not a precompiled Windows binary.

## Fixes since v0.4.5a

1. **Tab + placement:** The Add Tab button follows the last real tab. Its
   widget is positioned over unused tab-row space, not by inflating the
   right corner. The corner is permanently 38×34 px and displays an alternate
   + only when the tab strip overflows. This also avoids hiding dragged tabs
   underneath an oversized transparent corner widget.
2. **Tab navigation:** Native Qt left/right overflow arrows and horizontal
   mouse wheel/trackpad strip scrolling are preserved.
3. **Tab creation performance:** Creating an ordinary tab adds just the new
   pane. No clearing/rebuilding every QTabWidget child; no whole-application
   stylesheet reapplication. Only the active and previous panes are visited
   for activation/preview cleanup. This removes an identified O(n) cascade
   repeated on every tab addition. It is **not proof of zero memory leaks**;
   more open tabs naturally require additional editor widgets and memory.
4. **Ctrl/Cmd+K restored:** Inserts an internal link to the selected page;
   Ctrl/Cmd+Alt/Option+K opens the external website-link dialog instead.
5. **Empty-paragraph font size:** Sets the paragraph separator font size plus
   an editable, recomputed **MinimumHeight** determined by font metrics, so
   the blank line grows and shrinks. Does NOT use FixedHeight, does not insert
   dummy characters, and wraps formatting in a native undoable edit block.

## Test commands (Windows PowerShell)

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
uv pip install --python .venv\Scripts\python.exe pytest
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:QT_QPA_PLATFORM
.\.venv\Scripts\python.exe main.py
```

**Build the Windows application and installer:**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-windows.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-installer-windows.ps1
```

The installer script requires Inno Setup 6 or 7 and uses the same AppId as
previous releases, so Windows treats it as an update. Keep all `dist\Yomu Note`
files together if running without an installer.

## Runtime verification still required

This Linux authoring environment cannot install or launch PySide6 from its
network-restricted package index. The included offscreen Qt regressions must
run on Windows, followed by a human visual check of tab dragging, scrolling,
font resizing and shared Undo/Redo. The source was syntax checked here.

---

# Yomu Note v0.4.5 — Unified History & Page Navigator Refinements 🌸

**Testing candidate: complete source code, not a signed executable.** Based on
v0.4.4c Editor Recovery. The `.yominote` file format and PDF cache behaviour
are unchanged. Keep your existing v0.4.4c installation and a copy of your
notebook while testing this candidate.

## What's new in v0.4.5

- **One chronological Undo/Redo:** Edit → Undo / Redo, Ctrl/Command+Z and
  Ctrl/Command+Shift+Z now coordinate native notes edits, PDF highlights,
  page insertion/import/removal/reordering, page and tab renames, tab creation,
  deletion and reordering. Edit menu labels describe the next action.
- **Bounds:** maximum **1,000** retained unified actions and **200 MiB**
  estimated custom history payload per open notebook. Native Qt text history
  remains independent internally and is *not* covered by the memory estimate;
  PDF bytes are not copied into the history. Undo is **session-only**.
- **Plus menus:** The navigator's + Add Page button and the hovering insertion
  + between pages offer **Import File…** and **Add Blank Page**. The latter
  inserts at the selected boundary; the main + menu inserts after the selected
  page or at the end when nothing is selected. Multiple PDF pages import as one
  undoable operation.
- **Compact sidebar grip:** The six-dot panel drag handle stays aligned to the
  top-left when the navigator shrinks into compact or mini modes.
- **Sticky font size:** Repeated font-size up/down on a text selection uses the
  real selected runs (not the formatting at the far end of the selection).
  Mixed point sizes change relatively, with one native undo step per click.
  No paragraph FixedHeight manipulation is introduced.
- **Preserved features:** Repair Notes Line Spacing, visual-only notes zoom,
  Crisp PDF preview setting, autosave, backups, notebook v5, and annotation data.

**Verification:** Python compilation and 75 automated tests passed in the
packaging environment. 11 tests that need PySide6 were skipped because
PySide6 was unavailable there. Run the included GUI tests on Windows/macOS
before trusting the update with your only copy of important notes.

## Installation from source

Extract this ZIP to its **own new folder**. Follow the platform's run script
(`run-windows.bat`, `run-mac.command`, or `run-linux.sh`) or install dependencies
in Python 3.12 with `pip install -r requirements.txt` then run `python main.py`.
Do not overwrite your existing v0.4.4c source directory.

## Previous v0.4.4 feature guide

# Yomu Note v0.4.4 — Stage 2: Project Notebooks & Recovery 🌸

**This is a test candidate, not a signed commercial release.** It includes
all v0.4.3 editing, Pomodoro, Montserrat, PDF/thumbnail and workspace features.
Source works on Windows 11, macOS and Linux with Python 3.12 + PySide6.

## Major change: one project file, many internal tabs

- A project/module is **one portable `.yominote` file** (SQLite-based), not a
  directory. It contains named internal tabs (classes, readings, essays, etc.).
  Each tab keeps independent PDF/image source files, pages, notes, highlights,
  scroll position, reading page and workspace panel layout.
- **＋** adds a project tab. **Double-click** or **right-click → Rename Tab** to
  rename it. Tabs reorder by dragging them along the bar.
- Hover a tab to reveal the **small red trash-bin** icon. Click to delete after
  a **Yes/No confirmation**; reverse accidental deletion using **Edit → Undo
  Tab Deletion** and **Redo Tab Deletion**. The last tab cannot be deleted.
  Tab deletion Undo/Redo is for the current app session, not after restarting.
- The selected tab is visually highlighted; old tab pins are no longer used.
- Drag selected page thumbnails **onto a different tab** to move them, or hold
  **Ctrl** (Windows/Linux) / **Option** (macOS) while dragging to copy. When the
  page navigator has focus, Ctrl/Command+C and Ctrl/Command+V can also copy
  selected pages between internal tabs. Source documents are copied once per
  group of pages from the same file; derived render caches are not copied.
- Only the active tab starts preview/thumbnail rendering. Inactive tabs clear
  their page pixmaps and thumbnail icon caches; your notes remain intact.
- Project switching is now **File → Open Project** or **Open Recent**, instead
  of keeping different modules as tabs in the same window.

## Saving, backups and recovering safely

- The existing autosave keeps its **2-second idle debounce / 20-second
  sustained-edit limit**, and never reloads QTextEdit or clears Undo history.
- Every **10 minutes**, Yomu checks for meaningful project changes and creates
  a timestamped recovery snapshot if the notebook has changed since the last
  backup. Backups include original imported documents, notes, page metadata
  and annotations, but **never include raster cache images**.
- Default backup location on Windows: **`%LOCALAPPDATA%\Yomu Note\Backups`**;
  this is the per-user *writable* application data area. We deliberately do
  **not** use `C:\Program Files\Common Files` because it requires administrator
  rights for normal writes. macOS defaults to
  `~/Library/Application Support/Yomu Note/Backups`.
- **Settings → Preferences → Project recovery** lets you change backup folder
  and maximum snapshot count (default **30**, range 1–100). To prevent giant
  stores, an additional **2 GiB per-project backup cap** also removes older
  snapshots, retaining at least the newest one.
- Use **File → Restore Backup As…** to select a snapshot and a **new project
  filename**. Restoring will REFUSE to overwrite a file that already exists,
  including the active project. Restored projects receive a separate identity
  so future backup rotations won't collide.
- **File → Save Copy As…** also creates an independent notebook file.

## Backwards compatibility (important)

- Old Yomu **v2/v3/v4 `.yominote` folders** remain readable via
  **File → Import Older Project Folder…**. Yomu creates a NEW v5 `.yominote`
  **file alongside** the original legacy folder, never overwriting/deleting it.
- An older folder remembered from a previous Yomu session may be copied to
  a new v5 file at startup. The original remains unchanged and usable by
  older app versions. Keep a backup before major upgrades.
- The new v5 container cannot be edited by v0.4.3 or earlier. To use a legacy
  version, retain your original v4 folder rather than downgrading the new file.
- Every tab still uses the proven, validated v4 page/annotation manifest
  internally, stored within the v5 container. Projects are not silently
  modified in place when migrating from the old directory format.

## Performance guarantees

- Original imported documents are incrementally committed into SQLite;
  autosave does **not** recompress all PDFs and pages into a ZIP each time.
- Individual files are read and written in **1 MiB chunks**, never loaded as
  a giant Python byte string. An open notebook extracts its source files into
  a temporary local working directory (disk space roughly comparable to the
  sources). The temporary workspace is not part of the portable file.
- Existing 12 MP PDF render safety cap, original thumbnail memory limit of
  20, adaptive 12 MiB / 3-file preview cache, responsive 8 MiB / 20-file thumb
  cache, and all lazy rendering/eviction policies remain unchanged.
- No preview caches or thumbnails enter the notebook container or backups.
- The *Crisp* text clarity setting is now the default **only if the user has
  not explicitly selected another clarity preference**.
- Splitter dragging anchors the visible caret/reading line in the notes editor,
  avoiding the unexpected scroll jump when panels are resized.

## Run or build

### Windows (PowerShell, opened in this extracted folder)

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.\.venv\Scripts\python.exe main.py
# Once tested:
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-windows.ps1
```

The portable built distribution will appear under `dist\Yomu Note\`.
The directory must stay intact with the `.exe` inside it.

### macOS

```bash
./run-mac.command
# Once tested:
./build-mac.command
```

The bundled `.app` appears in `dist/`. Unsigned apps may need a one-time
confirmation in macOS Privacy & Security.

### Testing

```bash
python -m pytest -q
```

**Testing limitation:** Python storage and rendering tests run in the Linux
builder. macOS/Windows Qt visual behaviour, drag/drop, tab hover buttons,
scroll anchoring, application packaging and real-file imports require a local
on-device test. Please try on a COPY of your main study project first.

## Previous-version development notes

See `CHANGELOG.md` and `DEVELOPER_GUIDE.md` for previous releases and design
constraints. Other basic features such as the Pomodoro, text formatting,
PDF-import utilities and focus effects remain available.


## v0.6.4 Safety Changes

See `RELEASE_064_SAFETY_AND_BEGINNER_COMMENTS.txt` for the complete change list.

Beginner programmers should start with `BEGINNERS_CODE_GUIDE.md`.


## v0.7.0a fixes

See `RELEASE_070A_NAVIGATOR_POLISH.txt` for import-placement, active-page
indicator and lazy Groups-view thumbnail changes.
