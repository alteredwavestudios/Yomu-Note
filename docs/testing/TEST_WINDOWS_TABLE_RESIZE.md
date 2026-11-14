# Windows check — Table Resize Hotfix (v0.6.7a)

Use a **copy** of a notebook to test.

## 1. Alignment and guides

1. Create a borderless 3 × 2 table.
2. Type some words in the first two cells.
3. Click inside the first cell.
4. Switch alignment Left → Centre → Right → Left.
5. Check that the table's dashed outer and inner lines stay put.
6. Repeat in a visible-border table.

**Expected:** No drift, duplicate lines, repeated Python errors
or disappearance of the table.

## 2. Drag a column divider

1. Click inside a 3 × 2 table so the guide is visible.
2. Hover over the centre divider until the horizontal resize icon
   appears; hold left mouse and drag right about 30 pixels.
3. Release the button. The preview line must disappear.
4. Column 1 should grow and column 2 shrink, retaining the same
   total table width.
5. Ctrl+Z should restore the previous widths, then Ctrl+Y redo.
6. Save and reopen; the resized proportions should remain.

If grabbing the divider is difficult, use Table →
Table size and spacing… to enter a numeric width; report
whether that changes the table independently of dragging.

## 3. Row spacing

1. Hover the bottom edge of a row, drag down and release.
2. Extra space should appear below the cell text.
3. Undo and redo; no unrelated cell text should change.

Row height is still content-driven. Drags add bottom padding.

## 4. Remove and undo a table

1. Use a disposable table with several rows and columns.
2. Edit or remove some cells, then Undo/Redo.
3. Scroll away and back, change tabs, or replace the test text.
4. No repeated `QTextTable already deleted` error should appear.

Please report whether a resize fails **while the mouse cursor icon
changes**, or whether the pointer never recognises a divider. Those
are different failure points.
