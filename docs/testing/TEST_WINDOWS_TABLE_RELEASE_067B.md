# v0.6.7b — Windows table input tests

Use a COPY of a notebook. Close the old running app completely
before starting the rebuilt version.

## Automated Qt tests

From the source directory with PySide6 and pytest installed:

```powershell
python -m pytest -q tests/test_v067b_table_mouse_release_gui.py
```

The actual widget test sends a left-button press and release,
which previous source-only tests missed.

## Manual checks

1. Insert a new 3 x 2 table.
2. Drag the inner vertical boundary, then release.
   The blue resize preview MUST disappear.
   The adjacent columns should have different widths.
3. Press Ctrl+Z then Ctrl+Shift+Z. Widths should undo/redo.
4. Drag a horizontal divider down and release.
   It adds space below the text in that row; text can still grow.
5. Start dragging, press Escape. Resize must cancel.
6. Start dragging, change notebook tabs. No tab-switch freeze.
7. Test with left, centre and right text alignment.
8. Right-click in a disposable table > Delete entire table.
   Ctrl+Z must restore all cell text, Ctrl+Shift+Z deletes again.
9. Save and reopen after deletion. Deleted cell text must be absent.
10. Try on an OLD table. If it has no percentage widths,
    choose "Make old table columns resizable (equal widths)"
    before dragging. This is Undoable.
11. Empty every cell, click the first cell and press Backspace.
    The empty table should disappear.
12. Click hyperlinks and use tab navigation to verify no regression.

If the old build is already frozen, use Windows Task Manager
to end that old process before opening the new one.

This build does not promise forensic erasure of previous backups
or SQLite pages. Use Export Clean Notebook for Sharing.
