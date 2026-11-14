# v0.7.6 Windows & macOS stability acceptance checklist

Before testing, **back up your .yomunote project**, and keep your known-good
v0.7.5 source or app. Test a copied notebook in a separate directory.

1. Open a large notebook, write continuously for 30 seconds, and check that
   autosave has NOT yet happened. Continue past 60 seconds: it should save
   even if you never paused typing. Verify file timestamp/Save status and
   reopen the notebook to confirm the recent text exists.
2. After that save, leave the notebook untouched for 2–3 minutes. No new
   autosave disk writes should occur because the tab is no longer dirty.
3. Make an edit and immediately press Ctrl+S/Cmd+S. Save should succeed now,
   the waiting auto timer should stop, and subsequent Undo should still undo
   text and formatting inside the current notes page.
4. Change notes pages and tabs repeatedly with tables, links, annotations and
   reading checkmarks. Each page should retain its native Undo/Redo behaviour.
5. Change an unsaved note, then close the notebook within a minute. Reopen
   and confirm the edit was saved. Try the same while quitting the app.
6. Load another notebook while thumbnails are rendering in the first one.
   Confirm the new notebook stays usable, and there is no 'QObject already
   deleted' traceback or missing original source file error.
7. Open and close 10–20 DIFFERENT notebooks (some with PDFs) in one process.
   Watch memory and the temp folder (`%TEMP%` on Windows; `/tmp`/`$TMPDIR` on
   macOS). After a few seconds, retired `yomu-notebook-` workspaces should
   disappear once their workers finish. Do not mistake the ACTIVE workspace
   for a leak. Note memory high-water marks; OS allocators may retain pages.
8. Delete a tab, Undo its deletion, and confirm all notes pages, formatting,
   page groups and Undo/Redo work. The deleted tab's workspace should only be
   reclaimed when its enclosing notebook closes.
9. Test switching notebooks while OCR or a lengthy preview is running. The
   app must not crash or prematurely delete a source file. Switch back and
   verify any completed OCR text in the current notebook remains available.
10. Observe the existing ten-minute recovery backups. Confirm backups still
    occur on changes; this release intentionally does NOT change their cadence.
11. Run `python -m pytest -q` in the app's Python environment. Qt tests will
    be skipped on machines without PySide6.

If a test fails, record the action, original/copy filename, platform, app
memory before/after, terminal traceback, and whether reopening the original
notebook works. Do not share private notebook data unless redacted.
