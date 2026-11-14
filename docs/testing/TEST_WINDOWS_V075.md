# Windows acceptance checks — v0.7.5 stability candidate

**Before testing:** back up a working `.yomunote` file; install/run this build from a separate location; keep the v0.7.4 source and setup available for rollback.

1. Open a copy of a v0.7.4 `.yomunote` notebook. Switch every tab; check chapter names, read flags, annotations and all notes pages.
2. Edit richly formatted notes with tables and links in two different notes pages. Save/close/reopen. Undo and Redo in each page before closing; verify contents and formatting survive.
3. Import a bookmarked PDF using Smart Import and a nested destination. Cancel one import, complete another. Confirm only the approved pages/groups remain.
4. Try deleting/restoring a tab and a notes page, then verify Undo restores both their contents and editing history. Do not stress-test with the only copy of notes.
5. Test thumbnail and full-page preview updates while resizing the navigator, including crisp mode and dark/light themes.
6. Use the menu command for a **clean notebook share copy**. Confirm it opens and retains current notes/pages. If the source was migrated from an old project, verify the clean file no longer embeds internal v2/v3 backup manifests. The original and separate recovery backups should remain intact.
7. Open/close 10–20 large **different** notebooks while monitoring Task Manager memory and the Windows temporary directory (`%TEMP%`, folders beginning `yomu-notebook-`). **Known R01 issue:** growth may persist until exiting the application; record peak and post-close values. Avoid leaving many multi-gigabyte source projects open in one session.
8. Test an automatic backup when the notebook is large; note any visible freezes. **Known R02 issue:** backup I/O is still synchronous.
9. Keep Yomu Note open for a substantial normal session (e.g., a few hours), using OCR, import, multiple notes pages, and Pomodoro. Watch memory and verify save/reopen. Log any warnings or crashes.
10. Run `python -m pytest -q` using the Windows virtual environment if desired. Qt GUI tests skipped in the source audit should run in an environment with PySide6 installed.

Failure report: Windows version, memory before/after, file size, exact actions, traceback, and whether the source notebook remains readable. Never send private notebook content unless necessary and intentionally redacted.
