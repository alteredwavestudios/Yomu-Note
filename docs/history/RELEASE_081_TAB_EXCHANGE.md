# Yomu Note v0.8.1 — Shareable Notebook Tabs (source candidate)

**Built from v0.8.0a Smart Import chapter-selection stability hotfix.**

## New workflow

### Import another notebook's tabs into the notebook you already have open

- **File → Import Tabs from Notebook…** selects a `.yomunote` file.
- Review the source tab list: individual titles, page and notes-page counts, and estimated live asset size.
- Select one, several or all. Confirm to copy them **as new tabs** in the current project.
- Or drop a single `.yomunote` notebook file from Finder/File Explorer/a Linux file manager onto the main app, including the navigator, preview, tab strip or notes editor.
- Tab names that already exist are made independent, e.g. `Week 3 (Imported)`.
- **Undo once** to remove the whole incoming batch; **Redo once** to restore it, including edits made before Undo. After closing/reopening the notebook, normal session Undo is not persisted.
- The source notebook is never modified. The destination is never replaced by drag-and-drop.

### Export selected tabs into a standalone notebook

- **File → Export Selected Tabs as Notebook…** or right-click a tab → **Export This Tab…**.
- Tick any combination of tabs in the selection window.
- Choose a NEW `.yomunote` filename. An existing file is *not* overwritten.
- Share the resulting notebook as a file. Its original readings, page order, groups, reading progress, vector marks and rich-text notes are included.
- Unselected tabs, recovery backups, deleted/unused asset records and render caches are excluded from exports.

## Implementation and important safeguards

- `tab_exchange.py` is Qt-free; source SQLite connections use read-only mode and a consistent read transaction.
- Only *referenced* source files are transferred. BLOB data is streamed in 1 MiB chunks, not accumulated in memory. Each file is capped at the existing 1 GiB notebook limit, transfers at 4 GiB, and files at 100,000.
- Imports are staged into a temporary workspace directory, validated with the existing `Project.load()` rules, given fresh internal tab/project IDs and only then committed. New tab names cannot replace existing tabs.
- The SQLite save includes the entire imported batch within one transaction; on save failure the tab manifest is restored. No history action is recorded for failed preparations.
- Imported tab sources remain in the temporary working workspace for in-session Redo, while undone tabs are removed from saved notebook content.
- The background worker handles large source asset extraction/export, while Qt widgets and import history updates occur on the GUI thread.
- **Limitation:** The final `Notebook.save()` at import commit remains synchronous and may briefly pause the interface for very large PDFs. Moving all saves to a dedicated serialized worker belongs to a later stability release; do not promise a fully nonblocking v0.8.1 import.
- The `.yomunote` schema remains **v5** and the standalone tab project schema remains **v4**; all newly saved/exported manifests tag application version **0.8.1**.

## Testing and platform status

Backend and static regressions are automated; this environment does not have PySide6, Windows or macOS, so native Qt acceptance tests require a compiled build on those platforms. See `TEST_WINDOWS_MAC_V081.md`.

Keep your v0.8.0a source and a backup of your important notebooks until you have tested on Windows and Mac. Do not distribute unverified binaries as a stable release.

## Preparing a public repository

A `.gitignore` is included to avoid committing local personal notebooks, virtual environments, release installers and Python caches. Before a public GitHub release, choose and add a project source-code licence yourself, audit embedded third-party font/icon/OCR notices, and ensure no real students' notebooks are accidentally tracked (including Git history).
