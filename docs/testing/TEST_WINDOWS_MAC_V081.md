# v0.8.1 — Windows / macOS Tab Exchange Acceptance Tests

Run these using the **compiled app**, first on COPIES of existing `.yomunote` notebooks. No extra Tesseract installation should be required for the bundled OCR release.

1. **Import through File menu.** Open destination A; File → Import Tabs from Notebook…; select source B containing at least three different tabs. Tick only tabs 1 and 3. Confirm only those two appear in A, in source order; B is unchanged.
2. **Content integrity.** In the imported tabs, verify PDF pages, nested chapter groups, completed-page indicators, notes page names, rich HTML, highlights and drawings. Save and reopen A. Verify content persists.
3. **One-step Undo/Redo.** Import two tabs; type in an imported notes page; Undo the text edit first, then Undo the import once. Both tabs disappear together. Redo the import once; both tabs reappear. Test a second import and repeated undo/redo cycles.
4. **Duplicate names and identities.** Import the same Week 2 share twice. Existing Week 2 stays untouched; new tabs have independent names/contents and no cross-editing.
5. **Drag from Explorer/Finder.** Drop a `.yomunote` onto (a) tab strip, (b) page navigator, (c) PDF preview, (d) notes editor and (e) empty main header. Every case must open the same selection dialog; never open/replace the project or create a document page from the notebook.
6. **Ordinary drag regression.** Drag a PDF or image into the page navigator and a page onto another tab. Both pre-existing workflows still work. Dropping a `.yomunote` must not turn into a note hyperlink.
7. **Export selected tabs.** File → Export Selected Tabs as Notebook…; tick 1 of 3, save with a NEW filename. Open resulting file; it should contain only that tab and its documents/notes. Repeat with two tabs using the tab-bar right-click action.
8. **Privacy check.** Export a tab from a notebook with deleted pages and prior edits. Scan recipient notebook: unselected tabs, old project.v2/v3 backups, cached previews and deleted original files must be absent. Be mindful that LIVE notes/annotations are shared in full.
9. **Cancellation/failure.** Start a large import, then Cancel; neither the original nor destination should be changed. Repeat export cancellation. Try a broken/corrupted notebook and an export destination that already exists; verify friendly errors and no overwrite.
10. **Large files.** Import/export 500 MB of referenced PDFs and check RAM stays bounded. Note that the final synchronous SQLite commit may briefly freeze the app: report duration and any 'not responding' message. Check disk-space failure on a copy if safe to do so.
11. **Lifetime and save stability.** Close/reopen recipient notebook, change tabs repeatedly, use rich-text Undo, edit annotations and allow the one-minute autosave. Verify no native Qt crashes and that notebook version tags are 0.8.1 in About and saved metadata.
12. **Cross-platform.** Export on Windows, import on Apple Silicon Mac and, if available, Linux; then export from Mac and import on Windows. Confirm source page indices and fonts/formatting stay correct.

**Known limitations:** No live cloud sync, no cross-computer Undo history, no automatic PDF copyright/licence validation. Native platform tests cannot be performed in a Linux-only test environment without PySide6 or packaged Windows/macOS binaries.
