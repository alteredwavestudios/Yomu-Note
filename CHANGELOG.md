## v0.8.1b — Public-preview test and release hardening

- Fixed annotation identity tracking for Undo/Redo and autosave.
- Corrected ordered-list indentation across a blank paragraph.
- Isolated GUI tests from personal notebooks/settings and stabilised asynchronous preview assertions.
- Added timeout-protected test audit logs to GitHub Actions.
- Updated app and installer metadata to v0.8.1b; notebook storage schema is unchanged (v5).

## v0.8.1a — Pre-GitHub security, stability and beginner documentation

- No new functionality; user-confirmed v0.8.1 Tab Exchange behaviour retained.
- Validate untrusted SQLite metadata/BLOB sizes before large allocations or transfers; check full batch limits before starting a copy; verify export quick_check outcomes.
- Bound notebook extraction file count/total bytes; reject invalid timestamps; reduce Select All/None callback recursion.
- Use patched dependency minimums for PDFium, Pillow and PyInstaller (requires native cross-platform retesting).
- Central version, About, notebook save tags and installer updated to `0.8.1a`; storage schema remains v5.
- Extensive beginner-friendly in-source comments/docstrings, contributor code guide, focused GitHub README, security audit and precommit checklist.
- Eight added hostile-file / source-documentation regression tests. **430 tests passed, 48 GUI tests skipped, 3 subtests passed** in headless Python.

## v0.8.1 — Shareable Notebook Tabs

- Import any chosen tabs from an existing `.yomunote` notebook without replacing the current notebook; complete page sources, hierarchy, annotations, completion flags and rich-text notes preserved.
- Drop notebook files onto the tab bar, editor, navigator, preview or other main app surfaces to open the same selection review.
- Export one or several chosen tabs into a clean, independent `.yomunote` file; unselected/deleted data, old manifests and cache files excluded.
- Imported tabs get independent identities; duplicate titles are renamed. One notebook-level Undo/Redo entry for an entire imported batch.
- Qt-free, read-only and size-bounded streaming engine; staged validation, SQLite transactions, explicit failure/cancellation cleanup and privacy tests.
- Central app/installer version updated to 0.8.1; schema remains unchanged.

## v0.8.0a — Smart Import checkbox stability hotfix

- Prevents a potential native Qt crash when rapidly checking/unchecking chapters or subsections by never clearing a tree item inside its `itemChanged` callback.
- Keeps the selected and expanded chapter items intact while changing selection; updates mixed checkbox states with blocked recursive signals.
- Stops redundant PDF thumbnail rendering when only chapter inclusion changed.
- Makes inline chapter title edits safe inside their Qt callback; retains import Undo/Redo, page ranges and existing notebook formats.
- Updates app / About / saved app-version tag and Windows installer to `0.8.0a`.

## v0.8 — Selective Smart Import 3.0 (source candidate)

- Imported multi-page files now offer All pages (default), non-contiguous physical page ranges, and nested chapter/bookmark inclusion checkboxes. Chapter filtering is independent of whether chapter folders are created.
- A separate front-matter checkbox and clear INCLUDED/EXCLUDED preview status make the choices explicit. Range+chapter filters intersect, and duplicate/empty/out-of-bounds selections are rejected before commit.
- Selected page IDs and original source indices remain unchanged. Sparse chapter headings are remapped and empty groups pruned; `[chapter]` labels are resolved before filtering so omitted chapters do not renumber remaining ones.
- One-step undoable commit is preserved, with stage cleanup after cancellation and excluded-asset cleanup after successful commit. Unselected pages are never added to the notebook.
- Version advanced to `0.8` in About, Qt application metadata, save-file `app_version` and installer. Notebook schema v5 and project schema v4 unchanged.
- Added pure-Python selection tests and native-Qt-optional GUI tests. See `RELEASE_080_SMART_IMPORT_3.md` and `TEST_WINDOWS_MAC_V080.md`.

## v0.7.6.a — Version label and notebook metadata hotfix

- The About popup and Qt application version now read the shared `yomunote.__version__` value rather than showing an old hard-coded release number.
- Every `.yomunote` notebook save records `app_version: "0.7.6.a"` in the SQLite `meta`/`manifest` JSON. Each separately saved tab `project.json` likewise records the release that wrote it.
- Older saves without this optional field still open, and receive the new label when saved; the **notebook schema stays v5** and the **project schema stays v4**.
- Updated the Windows Inno Setup installer display version and output filename. Its four-integer Windows resource version remains `0.7.6.1`.
- No OCR, autosave, annotations, note content, or Undo/Redo behaviour was changed.

## v0.7.6a — Integrated Offline OCR (source candidate)

- Packaged Windows and macOS applications now prefer a private Tesseract
  executable and explicit `eng.traineddata` (optional `osd.traineddata`).
  Recognition remains entirely local: no OCR download or separate install
  happens on the end-user computer.
- Build scripts stage native OCR from a trusted build-machine installation;
  PyInstaller includes Windows DLLs / macOS dependent dylibs as binaries.
  The standalone-app check verifies English language discovery and actual
  recognition of a test image before a release can be packaged.
- macOS verification also rejects dynamically linked Homebrew Cellar/opt
  paths remaining in the app bundle. Native dependencies and licence notices
  still require a platform release review and an actual clean-machine test.
- Correct the Windows-specific OCR installation instructions that appeared
  on Mac. Source runs may still use an independently installed Tesseract.
- No notebook format changes, no OCR image-processing changes, no changes to
  v0.7.6 autosave, Undo, import, rendering, or resource ownership.
- The source ZIP does not ship Windows/macOS executables: build on each target
  OS and distribute the resulting installer/app, not the source ZIP, to users.

## v0.7.6 — Controlled Notebook Retirement & One-Minute Autosave (stability candidate)

- Changed ProjectPane autosave from the old **2-second idle / 20-second maximum**
  dual-timer strategy to **one dirty-only 60-second single-shot timer**.
  The timer starts on the first edit and is not reset by continuous typing.
  Successful saves disarm it. A failed autosave preserves the dirty flag and
  retries after one minute. Manual Save, tab switches, closing, and separate
  ten-minute recovery backups retain their existing semantics.
- Added a deferred Qt notebook-retirement queue for entire notebooks being
  closed or replaced. It waits for the old panes' queued worker completions,
  then schedules Qt widget deletion, then removes the obsolete extracted
  source workspace on a later GUI loop pass. Temporary-directory locks on
  Windows are retried, not forcibly deleted.
- Existing per-notebook Undo/Redo of deleted tabs is deliberately preserved;
  deleted/parked panes are only reclaimed when the *whole* notebook closes.
  They are not prematurely deleted while the notebook is open.
- Explicitly clear the last-active pane reference on Close and persist any
  still-dirty visible panes before retiring the notebook. No notebook schema,
  rendering, editor, import, OCR, or theme changes.
- Added Qt-independent worker-lifecycle tests, optional native PySide6 tests,
  a platform acceptance checklist and an audit of remaining limits. Windows
  and macOS native GUI verification is required before promoting to stable.

## v0.7.4 — Notes Pages, Navigator Stability & Extension Correction (source candidate)

- The original single rich-text notes document per tab migrates losslessly into
  **Notes 1**, preserving HTML, fonts, tables, hyperlinks, in-document page
  links, paragraph formatting, margins and scroll position. Each tab can now
  add, rename, cycle and remove independent notes pages (up to 128).
- One existing NotesEditor swaps persistent native QTextDocuments: no HTML
  flattening when switching, and each document retains Qt text Undo history.
  Add/rename/remove actions are recorded on the established per-tab Undo stack.
- All per-note metadata is stored in each existing tab's v4 manifest within
  the existing v5 SQLite notebook, without changing the container format.
  The first note page is also mirrored to the legacy `notes_html` fields.
- Prevent apparent missing group/page names caused by stale compact density
  after activating a hidden tab. Group labels always originate from saved
  page/group metadata before thumbnail loading. At rail/mini widths, page rows
  use visible text fallbacks until an icon is ready; text and cached image
  eviction remain independent.
- Give group-tree rows more breathing room and slightly smaller fonts; measure
  progress counter text with font metrics so counts and percentages cannot
  overlap the animated progress bar.
- Move tab hover-close buttons farther from the right edge; rename the
  Thumbnails view to **Individual**; add **Remove this page…** to the group
  navigator's page context menu (with confirmation and a reversible action).
- New SQLite notebooks/backups/exports use `.yomunote`. Opening an older
  `.yominote` notebook creates a collision-safe `.yomunote` copy without
  altering or deleting the old file. Old files remain openable. The Windows
  installer version strings are aligned to v0.7.4 (AppId unchanged).
- Added pure-Python note-page/legacy-file regressions and optional Qt tests;
  all non-GUI tests pass. Native Windows/macOS Qt UI behaviour remains to be
  verified, especially note-page switching, rich-text Undo, and skinny rails.

## v0.7.3a — Smart Import Initial Collapse & Real Chapter Label Tokens (source hotfix)

- Added **Collapse all newly imported groups and subgroups** to Smart Import options, **on by default**. It affects only newly created folders, not previously existing groups or reading state. The preference is saved across imports, and the group state persists in the notebook. Unchecking starts the new groups expanded instead.
- The structure review's outline now begins collapsed, with an **Expand all chapters in review** toggle. Editing, previewing, and approving pages remain unchanged.
- Custom page label patterns now recognise **[chapter]** as well as **{chapter}** (and matching bracket variants for other approved tokens). These resolve to the 1-based ordinal of the *final reviewed top-level heading* for each source file; nested sections do not increment the chapter counter. Before the first heading and when no headings exist, chapter number is 1. This is not inferred from digits in heading titles.
- Post-review relabelling occurs only for custom patterns containing the chapter token, preserving existing page-numbering rules and the special continuous page counter for combined-source imports. Chapter numbering restarts per source file.
- Added model, real-PDF save/reload, and optional Qt regression tests. No notebook schema changes or unrelated subsystem changes.
- Native PySide6 GUI checks remain necessary on Windows/macOS before promoting this candidate to stable.

## v0.7.3 — Smart Import 2.0, Structure Review & Safe Destinations (source candidate)

- Consolidated redundant import group checkbox + mode dropdown into one clear arrangement selection. The destination dropdown has an explicit root and named hierarchy paths.
- A selected navigator group, not the displayed preview page, determines the proposed destination; a deleted group raises an error rather than silently reverting to root.
- Read actual PDF bookmark titles, physical destination pages and nesting via the existing globally locked PDFium API; optionally use converted-PDF bookmarks for Office/EPUB, without guessing page alignment.
- Review before committing: edit and preview per-file chapter hierarchy and ranges, add/remove and indent/outdent chapters, reset detection and Undo/Redo provisional changes. Fixed N-page groups and no-outline manual fallback are available.
- Keep the page list, group tree and Undo history untouched until approval; remove staged source files on cancellation. Page-group validation preserves every stable page ID exactly once.
- Added pure-Python tests, a real-PDF end-to-end save/reload test, optional native Qt review tests, a Windows acceptance checklist and a release note with explicit detection limitations.
- No notebook format changes or modifications to notes, OCR, rendering, reading rewards, Pomodoro, themes or unrelated UI.
- Native Windows/macOS PySide6 GUI validation is still required before calling the release stable.

## v0.7.2b — Compact Navigator, Bigger Checkbox Targets & Kawaii Themes (source candidate)

- Increased reading checkbox hit targets while retaining their 16px painted
  appearance, stored check states, group/subgroup behaviour and Undo/Redo.
- Responsive Groups navigation uses Wide/Normal/Compact/Rail/Mini densities:
  small centred thumbnails and progress strips replace clipped text at narrow
  widths. Full titles remain in tooltips and model; no horizontal scrollbar.
- Enlarged wide Groups thumbnails using existing cached images; optional
  navigator maximum width is 540px. Thumbnail count and rendering limits stay.
- Removed an extra literal `}` in KawaiiNotice's stylesheet to stop Qt parse
  warnings. Notification behaviour and Pomodoro text are unchanged.
- Playful is the default for previously unset celebration animation settings;
  the existing Crisp preview default is retained. Never override preferences
  that users explicitly saved.
- Added six more saturated but readable Kawaii themes with WCAG-tested
  foreground/surface contrast; kept all existing theme IDs and labels.
- Added targeted source tests and optional Windows/macOS GUI acceptance tests.
  No unrelated storage, import, notes, rendering or annotation changes.
- GUI tests require Windows/macOS PySide6 and remain unverified here.

## v0.7.2a — Reading Rewards, Kaomoji & Animation Corrections (source candidate)

- Corrected GROUP checkbox overlay geometry: it now uses the exact shortened
  Qt title rectangle, rather than the full row whose bottom 13 px are reserved
  for group reading-progress bars. Explicit high-contrast ticks/dashes for each theme.
- Improved per-tab and notebook HP-style bars: cubic eased increase/decrease,
  up-only glint, 0.01-percentage-point visual resolution, theme-accent fill.
  A single shared animation drives grouped/nested group progress bars too.
  Reduced motion disables all reading progress animations and flashes.
- Added a non-modal, theme-aware, plain-text Kawaii notification card with a
  soft pop-in. It shows Pomodoro reminders, completions, and milestones without
  blocking editing or reading. Preserve existing sound/stop schedules.
- Twenty kaomoji-friendly Pomodoro messages, exactly ten per kind of session;
  preserve the requested last focus message verbatim and ten-minute limit.
- Reading celebrations are one per deliberate checkbox action, in priority
  order: whole notebook > tab > group/subgroup > 25/50/75% milestone.
  A group/subgroup has 12 confetti particles, tab 24, notebook 36 with hearts.
  The messages use real titles, are varied, and do not modify saved reading data.
- Preferences: completion messages, confetti, milestone messages, and
  Gentle/Playful/None motion. The original Reduce animations setting takes
  precedence; no automatic celebrations on Undo/Redo or project load.
- Updated stale v0.7.1a Qt tests for notebook progress in the header; added
  new pure-Python and optional GUI regression checks.
- Scope held to reading-progress views/feedback and Pomodoro presentation.
  No changes to imports, OCR, notes, storage, annotations, renderers or caches.
- GUI testing on Windows/macOS is still required before describing as stable.

## v0.7.2 — Reading Rewards (source candidate)

- Added animated, interruptible reading-progress transitions and a brief
  increase-only glint, retaining the existing per-page reading state model.
- Moved the notebook-wide progress summary from the status bar into the header.
- Corrected checkbox mark normalisation and contrast in themed group navigation.
- Added non-blocking kawaii completion messages and reused existing confetti.
- Added ten progressively playful Pomodoro reminders per timer mode, retaining
  the original reminder schedule, sounds and ten-minute cut-off.
- No changes to import, page storage, OCR, editor, annotations or preview caching.

# v0.7.1a — Reading Progress / Theme Checkbox Hotfix (9 November 2026)

- Fixed repeated ``libshiboken: QLabel already deleted`` (and potentially the
  progress bar) when checking pages or adding tabs. ``MainWindow`` now creates
  its QStatusBar once, before adding the notebook progress label and bar;
  it no longer replaces that bar during startup.
- In the Groups navigator only, overlay native checkbox indicators with
  theme-coloured unread, read and partially-read states. Existing Qt click
  regions, selection, model check states and per-tab Undo/Redo remain intact.
- Added focused static and optional live-Qt GUI regression tests; see
  ``RELEASE_071A_READING_PROGRESS_HOTFIX.txt`` for verification boundaries.
- No modifications to document persistence, import/planning, grouping,
  note editing, PDF/image rendering, caches, tab Undo or existing themes.

# v0.7.1 — Reading Progress, Smart Import & Group Dragging

- Per-page saved completion states; recursive group checkboxes and progress.
- One Undo step for group-wide read status and whole-folder dragging.
- Combined progress across internal notebook tabs in the status bar.
- Optional per-file or combined Smart Import groups and configurable labels.
- Original filename stored as metadata; generated short internal file paths.
- +Add navigation button; import menus and themed options dialog.
- New Qt regression tests and a Windows acceptance test guide.
- No automatic PDF chapter outline parsing yet (scheduled separately).

# v0.7.0a — Navigator highlighting, imports and thumbnails

- Active-page accent stripe follows keyboard navigation without clearing
  groups/pages selected for organisation. Collapsed containing groups show a dot.
- Button imports now choose an explicit destination: root unless exactly one
  group is selected in Groups view. File drops onto a group keep working.
- Groups view includes Montserrat bold folder titles and lazy thumbnail rows.
- Thumbnail decoding is limited to visible pages, with offscreen icons evicted.
- No changes to PDF source files, annotations, tables or notes HTML.

# v0.7.0 — Page Groups & Nested Navigation (source test candidate)

- Collapsible, nested groups built from stable page-ID references.
- Groups/Thumbnails switch, tree selection and drag/drop.
- Create, rename, ungroup, delete-with-pages and group selected pages.
- Save/reopen group hierarchy; preserve flat page order on old notebooks.
- Per-tab Undo/Redo snapshots preserve both hierarchy and page ordering.
- Safe recovery from malformed group metadata into a copied notebook.
- New desktop and headless regression tests.

# v0.6.7c — Whole-table indent and deletion controls

- Indent/outdent the complete table 18 px per step via Edit Table.
- Delete a corner-selected whole table with Delete or Backspace.
- Add focused shortcuts for deleting one current row or column.
- Label the table's context submenu **Edit Table**.
- Correct Qt selectedTableCells tuple order for selection/merge.
- Retain the working v0.6.7b mouse-release and resize lifecycle.

# v0.6.7b — Fix unhandled table mouse release, freeze, deletion

- Table hover and dragging store document positions, not QTextTable
  objects that may have been destroyed by Qt.
- Drop stale resize previews on document edits, Undo, focus loss,
  Escape and mouse release.
- Grab and release the mouse during divider drags.
- Transform table geometry from document to viewport using the
  scrollbar offsets, not the caret X that changes with alignment.
- Add live-Qt regression tests for centring, table replacement,
  drag cancellation and release.
- Retain all v0.6.7 features and project format.

# v0.6.7 — Table Resizing, Selection & Shortcuts

- Added proportional column divider dragging with single-step Undo.
- Added drag-to-adjust extra row height using native cell padding.
- Added a table-corner select-all handle and size dialog.
- Added row/column insertion before and after the active cell.
- Displayed editor and page navigation shortcuts on hover.
- Added default 4 pt cell padding to new borderless tables.
- Preserved existing notebooks, PDF/OCR and annotation functionality.
- Expanded the beginner-facing documentation and tests.

See `RELEASE_067_RESIZABLE_TABLES.txt`.

---

# v0.6.6a — Table Integrity & Rendering (source test candidate)

Table guide geometry no longer takes internal column positions from
the text caret, which moves when you change paragraph alignment.
Safe row/column deletion and custom-width preservation added.
See RELEASE_066A_TABLE_INTEGRITY.txt.

---

# v0.6.6 — Native rich-text tables and ten themes

- Added a native `QTextTable` toolbar menu, defaulting to 3×2.
- Tables default to borderless, zero cell padding and spacing.
- Faint editing guides are painted only while editing a borderless table.
- Added optional permanent borders and 0/3/6 px cell padding.
- Tab and Shift+Tab navigate table cells; the final Tab adds a new row.
- Added rows/columns, deletion, merge/split, header and equal widths.
- Default paragraph spacing no longer introduces gaps in table cells.
- Added ten light/dark palettes with text contrast checks.
- Improved malformed manifest error messages and restored last-edit state.
- Added source tests and Windows/macOS PySide6 GUI tests for tables.

# v0.6.5a — List, headings, themed dialog controls

- All Page Setup numeric fields now use the active theme palette,
  including QDoubleSpinBox in light Windows themes.
- Centralised application-wide widget palette for future dialogs.
- Native bullet markers now reflect depth: solid, hollow, square.
- Indentation can be repeated for a first item in a nested list,
  as long as a real preceding list item exists.
- New list items created with Return have their marker block style
  normalised and keep the correct scroll/caret location.
- Heading dropdown follows cursor and selection; mixed selections
  display a read-only “Mixed” state.
- List conversion clears leftover horizontal paragraph offsets.
- Added static and GUI regression checks; the GUI checks must run
  with PySide6 on Windows/macOS before calling this stable.

---

# v0.6.5 — Editor reliability, portable spacing and history

- Headings style all explicitly selected paragraphs in one Undo action.
- Clear Formatting removes hard-coded foreground and highlight colours,
  allowing the selected light/dark theme to supply the default ink.
- Explicit paragraph gaps, including 0 pt, remain separate from defaults.
  They are stored as typographic points in an optional HTML comment.
- Paragraph spacing reset now removes overrides, instead of writing
  new values that are merely equal to the current document defaults.
- Page Setup changes coordinate Qt's native block-format Undo step
  with the corresponding saved notebook settings.
- Right-click Undo/Redo uses the notebook history, and Ctrl+Y works
  as an alternative Redo shortcut on Windows/Linux.
- Fixed a missing plus-key glyph in macOS notes zoom shortcut labels.
- Added File → Quit and expanded beginner-friendly code comments.

**Pending desktop verification:** Qt GUI tests are included but cannot
run in the headless build environment without PySide6. Keep v0.6.4
available as your rollback.

---

# v0.6.4 — Safety, recovery and beginner code comments

- Shared PDFium lock across previews, imports and OCR.
- Reference-safe notebook packaging and clean copy export.
- Opt-in recovery copy for damaged cosmetic metadata.
- Safer paths, SQL, startup errors and OCR result retention.
- Detailed, narrow-width code comments and a beginner guide.

# v0.6.3 — Page setup, paragraph/list spacing and notes resize anchoring

- Per-project page setup and four document margins; existing notebooks retain their legacy margins unless opted in.
- Native Qt line-height and paragraph before/after controls, plus list spacing and 0.25-inch nesting grid.
- Optional Jump to Edit Position toolbar button and fixed scrollbar delta formula during reflows.
- Regression tests for persisted document defaults and selected-block UI scope.

# v0.6.2 — Notes view anchoring + list marker rebuild (source test candidate)
- OCR review text editor explicitly uses the selected light/dark `paper` and `ink` palette; selection remains readable.
- Actual `QTextList` membership owns bullets/numbering. List creation uses positive first-level indent so markers remain positioned beside their text.
- Ctrl/Cmd + ] and Ctrl/Cmd + [ operate on exactly the caret block or selected Qt paragraphs, not visually wrapped lines or neighbouring list items. No Tab bindings.
- Indenting one item moves only that `QTextBlock` into an appropriate nested list; never reformats the original entire `QTextList`.
- A top-level list item outdented to zero becomes an ordinary paragraph. A first sibling cannot be nested without a prior sibling.
- Ordered lists can share native numbering across plain blank separators; bullet lists are split by them. Selected blank paragraphs are never converted or indented implicitly.
- Related operations use one Qt edit transaction for Undo, preserving saved rich text and the existing notebook format.
- Qt GUI regression tests are included but cannot be executed in the current environment without PySide6.

# v0.6.0 — Stage 4 local multi-region OCR & contextual Pen size (source candidate)

- Temporary multi-rectangle OCR selections on original PDF and image pages;
  white/light focus overlays, dimmed surrounding page, region resizing and
  repositioning, and scroll/edge-autoscroll during selection.
- DPI-independent 300 DPI PDF source crop rendering through existing PDFium,
  adaptive 14-MP region cap, optional 200/400/600 DPI, detected Tesseract
  languages and cancellable worker processing.
- Region-by-region top-to-bottom/left-to-right extraction, clipboard copy,
  editable text review and optional paragraph line joining.
- A contextual Pen thickness slider by the annotation toolbar, with saved
  per-app preference and no alteration to existing pen strokes.
- No change to the project schema, notes text editor, PDF preview cache,
  existing saved annotation properties or Undo/Redo architecture.
- Local source/tests verified; Windows GUI integration still needs testing.

# v0.5.2a — Selection/Colour UI Hotfix (source candidate)

- Fixed PySide6 `QRectF` error during annotation selection, move, release, and resizing. `mapRectToScene(QRectF)` already returns a rectangle and must not receive `.boundingRect()`.
- Simplified the annotation toolbar into stacked Stroke/Fill swatches, swap-colours button, one Thickness control and an Opacity pop-up with two sliders.
- Quick colours now apply to the selected colour channel; right-click palette colours to choose Stroke, Fill or Highlight explicitly. Single-click a colour chip to target that channel; double-click to open its custom colour picker. No unwanted alpha changes in native colour pickers.
- Right-click the colour chip for No Fill/No Stroke (where applicable); cannot inadvertently create an invisible outline-less, fill-less shape.
- Selected annotations show their own settings; changes remain undoable. Deselecting shows drawing defaults again.
- No modifications to rich text, shortcuts, tab history, page navigation, PDFs or cache pipelines.

# v0.5.2 — Annotation Appearance & Highlight Tools (source candidate)

- Independent stroke/fill RGB colours, opacity, and optional fill/stroke on vector annotations.
- Appearance toolbar updates when selecting a saved mark; changing defaults does not recolour existing marks.
- Post-creation stroke thickness for pen strokes and shapes, and thickness for flat-ended Multiply highlight lines.
- Page Highlight offers rectangle and straight-line modes; existing rectangle highlight metadata remains compatible.
- Quick colour palette with a target selector, right-click target choices, custom colour+alpha dialog, and up to three recent colours.
- Annotation appearance changes can be undone/redone in the existing per-tab history. New highlights use compact individual-object deltas.
- Historical pen/marker/filled-shape alpha preserved exactly when loading legacy files.
- No changes to the notes editor, shortcuts, tabs, page navigation, or PDF renderer.

# v0.5.1 Stage 3 shapes & resizable vectors (source candidate)

- Fix the *temporary* pen stroke preview connecting to the page origin; saved strokes remain unchanged.
- Add a separate freehand Marker tool with Multiply blending; preserve the original opaque Pen and rectangular highlighter.
- Add editable vector Line, Arrow, Rectangle and Ellipse tools, Shift/Alt modifiers and optional translucent fills.
- Allow Select handles to resize freehand vector strokes and shapes; resize, move, create and erase remain per-tab Undo/Redo operations.
- Allow shapes to be stored alongside older strokes and highlights without schema migration.
- No changes to unrelated editor, page/tab management, fonts, shortcuts, or performance logic.
- GUI behaviour requires a Windows runtime check; PySide6 unavailable for local GUI testing.

---

# v0.5.0 Stage 3 vector foundation (candidate)

- Persistent page-relative vector pen strokes, select/drag, eraser, colour and size.
- Compact reversible stroke deltas integrated with each tab’s local history.
- Notebook-level Undo/Redo of deleted tabs, reachable from any surviving tab.
- Between-page insertion popup captures its insertion boundary on opening.
- V4 project/legacy highlight compatibility preserved; Windows installer version
  updated without changing the app's registered AppId.
- GUI runtime verification required on Windows; see README.

---

## v0.4.5b — Regression fixes (candidate)

- Remove oversized top-right tab corner/spacer, position inline + using
  mapped tab geometry; reserve fixed 38 px corner and show overflow + there.
- Preserve native QTabBar arrow scrolling and normal drag handling.
- Add tabs incrementally, avoiding repeated entire tab/widget reconstruction
  and application-wide stylesheet resets. Limit tab switch work to two panes.
- Restore Ctrl/Command+K for internal selected-page linking; Ctrl/Command+
  Alt/Option+K is now website-link insertion.
- Use MinimumHeight (NOT FixedHeight) on empty paragraphs with calculated
  current font metrics, allowing visual line height to change up and down.
- Add non-GUI regression checks and Qt offscreen tests for reported issues.
- No notebook schema or annotation/zoom format change.

## v0.4.5a — tab strip scrolling and inline Add Tab (candidate)

- Move Add Tab + next to the last tab while the strip fits the window.
- Keep + visible at the right during overflow; retain Qt native scroll arrows.
- Scroll tabs with wheel / horizontal trackpad gestures without selecting them.
- Refresh button position on resize, tab rename, reordering and restoration.
- No project-format or unified-history changes. Stage 3 vector pen not included.

# v0.4.5 — Unified History & Editor Refinements (source candidate)

- Restore a cautious chronological undo coordinator on top of v0.4.4c's native
  QTextDocument undo stack, using Qt's `undoCommandAdded` signal. Avoid cloning
  HTML or recreating the editor on every edit.
- Route Ctrl/Command+Z, Ctrl/Command+Shift+Z, menu commands, notes editor,
  page navigator and annotations to the same notebook history controller.
- Add reversible page rename, blank insertion at any position, grouped imports,
  removal and drag/arrow reordering. Add reversible tab rename, creation,
  deletion and drag reordering. UI menu labels show the next operation.
- Add + dropdown options on the navigator toolbar and hovering insertion grip.
- Align panel drag handles to the top left in compact/mini navigator modes.
- Fix repeated selected-text font-size shortcuts by reading selected runs and
  adjusting them within one native QTextDocument edit block.
- Set shared history bounds to 1,000 actions / ~200 MiB custom retained data;
  native Qt text history memory is not part of that bound. Session-only.
- No notebook schema migration, fixed-height paragraph hack, PDF regeneration,
  or change to Crisp preferences or zoom anchoring.
- All Python-only checks pass; actual PySide6 GUI runtime and merged native
  text undo boundaries must be verified on the target machine.

## v0.4.4c — Critical PySide6 line-height TypeError correction

- Removed the crashing `setLineHeight` call from the normal font-size handler.
- Restored native Qt text undo/redo; experimental unified proxy disabled.
- Optional fixed-line-height repair now passes the required integer type and
  closes its edit group in a `finally` block.
- Further empty-line caret sizing is postponed, rather than risking notes.

# v0.4.4c — Emergency editor recovery

- Restore proven native QTextEdit Undo/Redo. The experimental unified
  text/annotation proxy from v0.4.4b is temporarily rolled back because it
  prevented reliable Undo/Redo in Windows testing. Per-tab editor instances
  retain their separate session-only histories; annotations/page deletion use
  the proven pre-v0.4.4b commands. No history is saved to disk.
- Remove the v0.4.4b FixedHeight paragraph hack that caused overlapping or
  clipped text during typing. Keep the conservative pre-v0.4.4b font handler
  instead until there is a verified, native-layout solution.
- Add Edit > Repair Notes Line Spacing... as an opt-in, single-Undo
  recovery for fixed-height paragraph formatting accidentally saved by v0.4.4b.
- Ensure new/restored tab panes inherit the current theme; keep draggable
  tab reordering, disabled-action contrast and existing recovery features.
- No cache, image, project-container, autosave or backup policy changes.

# v0.4.4a — Startup Hotfix (6 November 2026)

- Restore the `MainWindow.apply_theme()` method accidentally omitted during the v0.4.4 refactor. Without it the application raised `AttributeError` at startup on Windows and Mac.
- Add two Qt-independent static regression tests that check essential MainWindow methods and all internal `self` calls.
- Add an optional PySide6 offscreen GUI smoke test for first-launch and theme switching.
- **No changes** to the notebook v5 storage format, autosave/backup policy, PDF rendering, thumbnail quality, cache limits, or notes data.

> Static and non-GUI tests can run in this environment. Qt integration requires Windows, macOS, or a runner with PySide6 installed.

# v0.4.4 — Stage 2: Notebook Containers, Tabs & Recovery (test candidate)

- Replaced multiple open-project tabs with internal, renamable tabs inside a
  single v5 `.yominote` notebook container (incremental SQLite).
- Project tabs support reorder, highlighted active tab, hover-only red bin,
  confirmation and Undo/Redo for tab deletion. Removed pins.
- Per-tab notes, page assets, annotations, scroll, zoom/layout state and
  selected page. Inactive views deactivate their PDF rendering and pixmaps.
- Copy/move page thumbnails across tabs using drag/drop (Ctrl/Option to copy),
  or clipboard copy/paste from the page navigator. Notes copy/paste remains
  handled by the native text editor.
- Default quiet autosave unchanged: 2 seconds idle / 20 seconds sustained.
  New 10-minute rotating backup snapshots are configurable (folder/count,
  default 30), with safety 2 GiB per-project cap and zero render caches.
- File → Restore Backup As… always requires a NEW file name and never
  overwrites the active project. Save Copy As creates an independent identity.
- Safe copy migration from v2/v3/v4 folder projects to v5 single-file
  notebooks; originals are kept untouched.
- Notes editor follows its caret/visible line during workspace splitter drag.
- Crisp experimental sharpening is the new default for users without a
  previous clarity setting; the existing Off/Gentle/Crisp preference remains.
- Bounded 1 MiB asset streaming, incremental SQLite commits. All previous
  PDF raster/cache limits unchanged.

**Tests:** Storage, backup, rotation, migration, page-transfer and path
validation tests included. GUI checks must run on Windows/macOS with PySide6.

---

# Yomu Note v0.4.3 — Stage 2: Editing & Clarity (candidate)

- Windows/Linux Ctrl+Delete removes only the next word and Ctrl+Backspace the prior word, never the whole paragraph. Mac Option+Delete/Backspace removes words; Command+Delete/Backspace acts to the end/start of the line. Running OS sets behaviour automatically for source and packaged app.
- Google Docs-style Ctrl/Command+Shift+Z for Redo Notes and Ctrl/Command+K for a regular hyperlink. Yomu-specific internal-page linking moves to Ctrl/Command+Alt/Option+K, avoiding the Google Docs Ctrl+K conflict. Other formatting/navigation shortcuts retain platform-aware mappings.
- Restore saved rich-text vertical scroll when reopening a project; keep scroll through Alt+Tab/minimisation. Notes view zoom now anchors the active editing line at its previous vertical position (or preserves the visible reading line when the caret is offscreen), instead of jumping to another paragraph. Save reading position after scroll settles. Legacy v4 project files without the optional field still load.
- Empty paragraph font-size updates now set its minimum line height immediately, preserving Undo/Redo and without inserting invisible characters.
- Removed the lossless-compression diagnostic button. Internal test helper retained for regression comparisons only.
- Optional **Off / Gentle / Crisp** preview text-edge enhancement in Preferences. Sharpen brightness only using a contrast threshold, **after Lanczos**; applies to at most 1.5 MP of current below-100% preview pixels, in a worker, in RAM only. No sharpened disk caches, no thumbnail algorithm changes.
- Autosave remains 2-second idle / 20-second continuous editing, without resetting undo history.
- Existing low-memory rendering caps, lazy loading, PDF original assets, annotation coordinates and format v4 remain unchanged.

**Qt visual tests must be run on actual Windows/macOS machines.** Python-only tests do not prove the pixel appearance or caret geometry. This build does not implement the Stage 2 internal notebook tabs or zipped project containers.

# Yomu Note v0.4.2 — JPEG vs Lossless Comparison (6 November 2026)

**Focused diagnostic build based on v0.4.1.** This release is deliberately NOT
an edge-sharpening experiment and does not change default PDF rendering.

- Added a **Lossless test** toggle beside Fit in the page-preview toolbar.
  OFF shows the original disposable quality-87, 4:4:4 JPEG cache.
  ON re-renders the **same selected page** through the identical raster and
  Lanczos-3 pipeline, but hands the RGB result directly to Qt without JPEG.
- The lossless pixels are in RAM only, never saved to PNG or added to cache.
  Only one full-page QPixmap remains displayed at a time. The short-lived
  worker buffer is bounded by the existing 12-million-pixel render limit.
- Preserve the page's **existing zoom, scroll and highlight coordinates** when
  switching. A/B results are rejected if their pixel dimensions differ.
- An in-progress comparison is cancelled logically when the page or zoom
  changes. The A/B sample waits for the zoom-matched preview to settle.
- No change to navigator thumbnails, standard JPEG compression, cache budgets,
  autosave, notes or project format. The experiment is off by default.

**How to interpret:** If text looks indistinguishable with Lossless ON and OFF,
JPEG compression is probably not the dominant source of softness at that zoom;
the number of display pixels, downsampling and screen scaling are better next
investigations. Lossless cannot recreate text detail missing at ~13% Fit.

**Testing:** 51 non-GUI tests pass. 6 Qt GUI tests require PySide6/a graphical
target environment; Windows/macOS appearance is not yet verified.

---

# Yomu Note v0.4.1 — Aspect & Display Isolation Hotfix

- Display-only: navigator thumbnail images now retain **their own source aspect ratio**, independent of the fixed thumbnail card, and are centred horizontally and vertically in the space above the page-number footer. Landscape slides remain landscape. Portrait pages remain portrait.
- Qt still draws card backgrounds, selection and focus using its native style. Only the thumbnail placement is explicit. No new image caches or new PDF renders.
- At near-exact pixel-for-pixel display ratios, skip a redundant Qt smoothing pass on the *main page preview* after its existing Lanczos-3 downsampling. At every other zoom ratio, keep smooth Qt display scaling.
- Keep zoom interaction, animation, annotation and project format unchanged.
- Keep ALL existing PDF/thumbnail disk cache budgets, RAM limits, lazy loading, font and UI settings unchanged.
- GUI presentation requires target-platform verification. No claim that resampling produces more source detail than the PDFs contain.

---

## v0.4 — Scaling & Fit Hotfix (6 November 2026)

- Fit toolbar action is explicitly checkable, selected by default, visually
  outlined while enabled, and toggles off on a second click without changing
  zoom. Manual zoom and 100% clear the checked state; resize only fits when on.
- Navigator images are genuinely vertically centred via transparent padding
  inside the existing up-to-20 visible Qt icons. Retains native delegate paint.
- Responsive navigator PDF thumbs rendered up to 1.35x then downsampled using
  Pillow Lanczos-3 and saved JPEG 4:4:4 at quality 86 for improved clarity.
- Existing zoom-matched PDF previews already use Lanczos-3; existing bicubic
  magnification refinement remains bounded and unchanged.
- Removed redundant cross-panel redraws on notes scrolling; scroll-reactive
  notes backdrop now debounced. Native trackpad scrolling remains untouched.
- No changes to project format v4, cache caps, imported source files, other
  rendering resolution caps or autosave/Undo behaviour.

## v0.3.4e — Stage 1: editing reliability and display polish (6 November 2026)

- **Navigator thumbnails vertically centred** inside their allocated icon area; page numbers remain in their own footer. The proven Qt native icon painter is still used to avoid the old blank-thumbnail regression.
- **Autosave:** debounced for 2 seconds after the last editing action, but saves after a maximum of 20 seconds of continuous changes. No timer-driven writes while nothing changed; autosave serialises notes without replacing the QTextDocument, so its undo history remains available. Manual save/confetti behaviour is unchanged.
- **Annotation history:** a per-project bounded `QUndoStack` (75 commands), with undoable and redoable highlight creation and clearing. New annotation operations can use the same command pattern. Separate Edit menu actions are disabled automatically when no relevant history exists. Notes Undo/Redo and page-removal Undo actions also reflect availability.
- **Highlights:** the vector overlay now paints using `CompositionMode_Multiply`, giving stronger readability for text beneath the colour. Existing annotation JSON and coordinates are unchanged.
- **Rich-text editing:** Insert → Horizontal Line (also in the notes formatting overflow menu). Adjusting a font size refreshes the active insertion formatting, cursor and empty paragraph layout before typing.
- **Zoomed-out pages:** retains the existing original-PDF / modest supersampling / Lanczos downsampling path. No changes to original PDF rendering or its file budgets.
- **Zoomed-in pages:** after a zoom/pan gesture settles, a worker generates a bicubic-refined **visible crop of the existing page bitmap only**, with source 2.5 MP / output 2.25 MP limits. No higher-res PDF rendering, no new disk cache, no additional complete-page QPixmap; native Qt smoothing remains the immediate fallback and if caps are exceeded.
- **Refresh-rate-conscious animation:** preserves Qt's event-driven animations, redraws only on changes, and defers CPU-heavy bicubic work until interaction settles. No forced 120 Hz idle refresh loop or monitor-rate promises.
- **Compatibility:** project format remains v4; importers, project save/load code, all cache budgets, supplied build scripts, assets, fonts and original data are unchanged.
- **Test boundary:** Python unit tests and compilation pass in a non-Qt environment. GUI smoke tests are included for Windows/macOS but must be run with PySide6, and actual trackpad/refresh-rate feel must be checked on device.

## v0.3.4d — Flexible Workspace and smart on-demand preview (6 November 2026)

- Added six-dot drag grips to all three existing panel headings; drag/drop before or after another heading to reorder. Live panels are moved within the same QSplitter (no duplicated editor, preview or cache).
- Saved `panel_order` as an additive optional property in the **unchanged v4** project JSON. `splitter_sizes` continues storing widths in legacy Pages/Preview/Notes order for backward compatibility. View → Workspace Layout and Reset to Classic added.
- Removed Hi-res button and View-menu action. Above 100% zoom uses Qt's existing smooth interpolation. Below 100%, custom renders from the original PDF adapt to the settled zoom (5% output buckets), with small capped supersampling and JPEG 4:4:4 compression.
- Added `cache/previews-adaptive`: hard 12 MiB disk budget and max 3 files, cleaned at every new render; only selected page. Automatically remove old `previews-hi` and `previews-small` derived JPEGs upon project activation.
- Added width-matched visible-only thumb variants: hard 8 MiB disk budget and max 20 files at widths up to 420 pixels. Small original 110×144 thumbnails remain and virtualised icons stay at 20 maximum.
- Navigator maximum width follows its bottom action row with a 465 px ceiling; it still adapts to Mini/Compact/Normal at any column position.
- Respect minimise state for newly scheduled thumbnail work; no change to Pomodoro timer scheduling or saved notes.
- Added non-GUI regression tests for new caches and all six saved arrangements, plus optional GUI smoke tests for target machines.
- Existing normal-preview/thumbnail budgets, PDF 12 MP ceiling, default thumbnail cache, background worker limit, page-link handling, notes font settings and user originals remain intact.

## v0.3.4b — Modern Kawaii & Crisp UI

- Restored contrast and refined seven theme palettes without changing existing theme IDs.
- Themed Preferences inner scroll page, text inputs (including rename), checkboxes and focus borders.
- Navigator shows only native-rendered thumbnails and dynamic numbers; full titles on hover.
- Improved HiDPI SVG toolbar icon rasterisation (tiny fixed-size assets only).
- Ensured the thumbnail delegate opts into smooth pixmap compositing.
- Paused decorative animations when minimised; Pomodoro sound timing remains active.
- Kept all page/PDF rendering and all cache policies exactly unchanged from v0.3.4a Montserrat.

## v0.3.4a · Montserrat UI-font update

- The app's default UI family is now **Montserrat** when available; it falls back to Nunito or the system default.
- `fetch_fonts.py` also retrieves official Montserrat normal/italic variable TTFs and its SIL OFL licence. Existing Mac, Windows and Linux build scripts automatically include them, fully offline at runtime.
- Brand wordmark remains Mochiy Pop One. Rich-text notes and their defaults are unchanged.
- Font-only update: **no** changes to PDFs, previews, caches, memory limits, page navigators or existing project files.

# Yomu Note v0.3.4a — Thumbnail navigator hotfix 🌸

- Restores the native Qt thumbnail/icon painter from v0.3.3 to address missing page preview images in the v0.3.4 navigator.
- Keeps automatically updating page numbers, hover glow, theme styling, and the normal/compact/mini sidebar modes.
- Makes no changes to the project file format, PDF renderer, page cache, or storage.
- This change is source-verified and syntax-checked; macOS GUI testing remains necessary.

# Yomu Note v0.3.4 — Kawaii garden update 🌸

- New colourful cat-and-notebook app icon with `.png`, `.ico` and `.icns` assets.
- Page numbers under thumbnails, dynamically reflecting order and responsive widths.
- Click-to-rename current page title with Return/Escape.
- Extra tab-close padding; brighter complementary theme accents.
- Animated, scroll-responsive gradient panels with reduced-motion support.
- Refined macOS native pinch gesture handling and pointer-anchored continuous zoom.
- Native touchpad momentum preserved; traditional mouse-wheel easing for notes and page navigator.
- Original offline E-flat-major 3-second break and study WAV jingles.
- Optional once-a-minute overdue reminders (up to, but not beyond, ten minutes).
- Miniature focus flower, sound/volume/reminder preferences.
- Short save confetti effect only after meaningful edits, including those already autosaved.
- Integrated v0.3.3 independent text-view zoom and correctly themed notes Find field hotfix.
- Retains project format v4 and lazy PDF rendering with 20 thumbnail memory ceiling.

## Testing boundaries

Pure Python tests, resource verification, Python compilation and archive integrity are checked. This environment cannot run the Qt UI on a real Mac or Windows machine, so physical trackpad/sound/gui interaction is unverified.

## v0.3.4c — adaptive preview prototype (6 November 2026)
- The document preview now reports its live zoom, including Fit, zoom buttons,
  mouse/trackpad wheel and native macOS pinch. The notes toolbar separately
  reports notes zoom without changing saved HTML or fonts.
- Tiny 10% and 25% PDF raster tiers are generated from the original page on
  demand, with bounded supersampling and Lanczos anti-aliasing. They share a
  separate, disposable **8 MiB** disk cache. Only the selected page is eligible;
  its neighbours continue to use the existing normal prefetch policy.
- At higher zoom the existing normal preview and existing capped Hi-res path
  are reused. The 200% level is a *quality preference*, not a promise of a
  2x full-page bitmap: the previous 18-million-pixel safety limit still holds.
- The displayed bitmap is exchanged without altering the zoom transform,
  scroll position, page coordinates or highlight annotations. No extra large
  QPixmaps are retained in memory.
- Thumbnail *display rectangles* grow in Normal mode as the navigator widens,
  with margins for the page number. Only up to 20 visible icons are scaled in
  memory using Qt smooth interpolation, so enlarged thumbnails use a few more
  transient pixels but **no new source PDFs, thumbnail files, or disk cache**.
  The original 110×144 thumbnail JPEGs and lazy eviction rules are unchanged.
- Adjusted tab close-button inset for cleaner spacing.
- This is a **test candidate**. CI/unit tests validate PDF raster limits and
  old storage paths; GUI placement, Windows HiDPI appearance, pinch behaviour
  and graphics-scene annotations require real-device testing.


## v0.7.5 — Stability hardening candidate
- Reject Windows-illegal asset path characters consistently.
- Guard against truncated or growing source files during streamed SQLite saves.
- Bound/thread-synchronize preview-cache bookkeeping.
- Remove embedded old project-manifest backups from clean share exports and compact the output, without touching recovery backups.
- Deep architectural audit and Windows acceptance tests (`AUDIT_075.md`, `TEST_WINDOWS_V075.md`).
