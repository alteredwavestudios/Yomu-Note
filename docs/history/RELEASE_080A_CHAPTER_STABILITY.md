# Yomu Note v0.8.0a — Smart Import chapter checkbox stability

**Focused hotfix to v0.8. No changes to notebook file format or page filtering rules.**

## Cause and fix

Qt emits `QTreeWidget.itemChanged` synchronously while the user interacts with a checkbox. In v0.8 the handler called `_rebuild()`, which called `tree.clear()`. This destroyed the native checkbox item *before Qt had finished processing the click*, risking a hard application crash. Rebuilding also reset expanded chapters and the current tree item, and restarted the PDF preview even though the page number had not changed.

- Checkbox changes now update existing tree items in place with `tree.blockSignals()` to prevent nested callbacks.
- Parent `PartiallyChecked` indicators and child checkbox propagation are preserved.
- The bulk Select All / Select None controls use the same safe in-place update.
- Editing a chapter title from the tree no longer rebuilds inside `itemChanged` either.
- Checkbox toggles refresh INCLUDE/EXCLUDE text without restarting PDF thumbnail loading.
- Structural actions such as add/remove/reindent, Undo/Redo and Reset continue to rebuild their tree **outside** item-change callbacks.
- v0.8.0a app version is reflected in About, save metadata and Windows installer; notebook format remains v5, project format remains v4.

## How to test on Windows or Mac

1. Back up any important `.yomunote` notebooks. Build the source into the native app (existing Windows/Mac build instructions still apply).
2. Start Smart Import on a PDF containing nested bookmarks; expand its chapter tree.
3. Toggle a parent chapter on/off 30+ times, then toggle various subsections. Confirm no crash and correct mixed-parent checkbox state.
4. Use Select All / Select None repeatedly, then Undo/Redo. Confirm the imported page count updates and the selected chapter stays visible.
5. Try a custom page range combined with chapter filtering and confirm the import contains only selected pages.
6. Edit a chapter title by double-clicking it. Verify it survives import and can be undone.
7. Cancel an import; verify the existing notebook is unchanged. Reopen a notebook to verify persistence.

## Test limitation

Pure-Python tests exercise import selection and the static item-lifetime guard, but the GUI tests require PySide6 and native runtime testing. A Windows/macOS user should confirm the crash no longer reproduces before treating this as fully verified.
