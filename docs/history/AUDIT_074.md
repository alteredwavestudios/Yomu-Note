# v0.7.4 source audit — scope, tests and open risks

## Goals / edited areas
- `yomunote/project.py`: lossless old notes migration, bounded validated
  multiple note entries, legacy mirror, new file name.
- `yomunote/notebook.py`: backwards-compatible legacy filename opening and
  copied `.yomunote` migration (atomic replace, bounded memory, no overwrite),
  modern naming for save/backups/exports.
- `yomunote/window.py`: QTextDocument switching/navigation and Undo action
  routing; selected-note page setup/scroll/save; Group page right-click remove;
  navigator refresh, label/spacing improvements, open/save filters, tab padding.
- `yomunote/page_groups_ui.py`: text-first model rows, responsive labels,
  measured progress counter geometry, slightly softer row typography.
- `yomunote/__init__.py`, installer metadata and build-installer script:
  bump to v0.7.4 without altering installer AppId.
- `tests/test_v074_notes_and_extension.py`: old/new project model, notebook
  save/reload, file conversion checks.
- `tests/test_v074_gui_notes_navigator.py`: native Qt tests for page switching,
  removal and title retention (skipped when PySide6 unavailable).
- Older tests that expected `.yominote` as the only new-file suffix were
  updated to expect `.yomunote` without changing their underlying assertions.

## Integrity / compatibility decisions
- Never convert rich HTML to plain text. Existing `notes_html` is imported
  verbatim as Notes 1 and retained as a compatibility mirror.
- Keep every notes page as an individual QTextDocument while the tab is open;
  reparent old documents to the pane before QTextEdit.setDocument to prevent
  Qt deleting them and erasing their native Undo stacks. Do not reconstruct
  a document via setHtml on every page switch.
- Use the same v5 SQLite notebook and v4 per-tab manifest formats; optional
  metadata keys add notes pages without touching the underlying PDF page IDs.
- Legacy extension conversion uses a separate file; never mutate/delete the
  original `.yominote` source. Retain support for legacy folder projects too.
- Keep existing thumbnail cache size/caps and reading-progress data model.

## Tests / limitations
- `python -m compileall -q yomunote`
- `python -m pytest -q --disable-warnings`
- PySide6 absent in the source environment: Qt-dependent tests must be run on
  the user's Windows installation. Pure-Python tests cannot prove QWidget
  layout, native QTextDocument ownership, or Ctrl+Z interaction.
- Regression test status recorded below by the final build packager.
- Very narrow mini navigator widths cannot render whole titles; they retain
  the real model text and accessible tooltips instead of treating an unloaded
  thumbnail as an empty page.
- Keeping QTextDocuments alive until their owning notebook tab closes is a
  deliberate tradeoff to preserve session Undo for remove/restore actions.
- Notebooks stored in a read-only folder cannot be migrated in-place.

## Final automated audit
- Python compileall: passed.
- Pytest: **355 passed, 44 skipped, 3 subtests passed**.
- Skipped checks are principally Qt tests (PySide6 unavailable).
- Updated existing files: CHANGELOG.md, README.md, YomuNote_v050_Installer.iss, build-installer-windows.ps1, tests/test_notebook_v5.py, tests/test_v045_unified_history.py, tests/test_v064_data_safety.py, tests/test_v2_migration.py, yomunote/__init__.py, yomunote/notebook.py, yomunote/page_groups_ui.py, yomunote/project.py, yomunote/window.py.
- Newly added files: AUDIT_074.md, RELEASE_074_NOTES_PAGES_NAVIGATOR_POLISH.txt, TEST_WINDOWS_V074.md, tests/test_v074_gui_notes_navigator.py, tests/test_v074_notes_and_extension.py.
- Removed original files: none.
- No changes to original PDF assets, importers, annotation engine, preview
  rendering, OCR or Kawaii celebration logic.
