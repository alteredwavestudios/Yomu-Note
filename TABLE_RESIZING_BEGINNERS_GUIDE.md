# Yomu Note v0.6.7 — Table Resizing for Beginners

This guide assumes you have never programmed before.

The new features mainly live in two files:

- `yomunote/notes_tables.py`: commands and mouse actions.
- `yomunote/table_grid.py`: calculations for guide positions.

## What is a `class`?

A class groups related behaviour together.

For example, `TableTools` groups the operations that
can change a table. A `TableTools` object remembers
which notes editor it belongs to.

That matters because a notebook can have several tabs.
Changing a table in one tab must not affect another tab.

## What is a `QTextTable`?

It is Qt's native representation of a table.

Qt is the interface toolkit used by Yomu Note.
It already knows how to save table text, copy cells,
change formatting, and perform Undo.

We do **not** replace the entire notes document's HTML
when resizing or inserting a column. Doing so could
wipe out the user's Undo history and cursor position.

## What does "preview only" mean?

When you press the mouse on a column boundary, the
program remembers the starting widths.

As you move the mouse, we calculate the proposed widths.
These values are drawn over the editor as a coloured line.

Nothing is saved or modified yet.

When you release the mouse, Yomu Note applies the final
widths using `QTextTable.setFormat()`.

That change is grouped into **one native Undo step**.

Pressing Escape during a drag cancels the preview.

## Why are widths percentages?

Suppose a table has two columns, each 50% wide.

A drag might change them to 35% and 65%.

The whole table can still fit the notes column after
you resize the main application window.

Other columns aren't changed by that operation.

## Why can't row height be a fixed number?

Qt's rich-text table API supports column width rules,
but doesn't offer the same rule for one row's height.

Yomu Note uses the cell's *bottom padding* instead.

Padding means extra empty space around the cell's text.
That increases the row's visible height but doesn't
cut off words if you add more text later.

Zero extra padding returns the row to automatic sizing.

## What is an Undo transaction?

A transaction groups changes so the user can reverse them
with one Undo, even if several cells need updating.

`beginEditBlock()` starts the group.
`endEditBlock()` finishes it.

Table operations use the same native Undo history as text.
This avoids a separate history that could become out of sync.

## Why is the corner handle not part of the table?

The handle is a tiny square we draw on the screen.
Clicking it selects the native table cells.

It isn't part of the saved HTML document.
It won't appear in exports or a copied table.

## What is a regression test?

It's a small program that checks something still works.

For example, a width test checks that resizing columns
1 and 2 doesn't silently change column 3.

Tests catch problems before you discover them while
writing important study notes.

You can run them from the project folder with:

```powershell
python -m pytest -q
```

Some tests need PySide6 and a working desktop window.
Those tests must be run locally before treating a new
UI feature as completely verified.
