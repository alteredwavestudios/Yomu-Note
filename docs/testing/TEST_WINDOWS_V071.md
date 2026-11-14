# Yomu Note v0.7.1 — Windows acceptance checklist

1. Back up your `.yominote` file. Keep v0.7.0a as your rollback.
2. Open a notebook containing multiple tabs and nested page groups.
3. Expand a group; tick a page. Confirm the group and current-tab counters
   update immediately. Ctrl+Z should undo; Ctrl+Y should redo.
4. Tick a parent group with a nested subgroup. All descendants should turn
   read in ONE Undo step. Unticking the group should clear them all.
5. Navigate with Ctrl+Alt+Up/Down and switch tabs repeatedly. Merely viewing
   a page should NEVER mark it read, and the navigator must not freeze.
6. Drag an entire folder above another folder; then into a different folder;
   then back to the root. Ensure all nested pages move, no duplicates are
   created, and Next/Previous Page follows the updated reading order.
7. Undo and Redo the folder move. Existing read states must stay intact.
8. Choose +Add -> Import and import WITHOUT a selected group. Pages should
   be separate at root; repeat with a selected group to import directly
   into it.
9. Choose +Add -> Smart Import; select multiple files. Check both one-group-per-file and combined-group modes. With a group
   selected, groups should become its subgroups.
10. Try labels: Page 1, Slide 1, Chapter 1, Page 001, Roman numerals,
    Filename + page and custom `{filename} — {n} of {total}`.
11. Import a PDF with a long academic title that failed in v0.7.0a. It
    should import without renaming; original filename remains visible as
    chosen by label formatting.
12. Save, close and reopen. Read marks, group order, titles and percentages
    must survive. No unrelated notebook data should be modified.
13. If something fails, capture the traceback and note whether you used the
    button, file drag/drop, group drag/drop or keyboard shortcut.

## Optional desktop regression tests

With PySide6 and pytest installed in the source environment:

```powershell
python -m pytest -q tests/test_v071_progress_gui.py
```

The pure-Python regression suite can be run with:

```powershell
python -m pytest -q
```
