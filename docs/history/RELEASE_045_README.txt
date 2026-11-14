Yomu Note v0.4.5 — Unified History & Page Navigator candidate
Based on: Yomu_Note_v0.4.4c_EditorRecovery_Fixed

CHANGES
- Shared chronological Undo/Redo for text, PDF annotations, page and tab operations.
- Page add dropdown (Import File / Add Blank Page) both in toolbar and at the page boundaries.
- Compact and mini navigator handle pinned to top-left.
- Font-size changes on selected text use the run's actual point size.
- Max 1,000 unified actions and ~200 MiB estimated custom command payload per notebook.

INSTALL / TEST
1. BACK UP your .yominote files first.
2. Extract this ZIP into a new folder; do not overwrite v0.4.4c.
3. Run run-windows.bat, run-mac.command, or run-linux.sh with the dependencies installed.
4. Verify ordinary typing and Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z first.
5. Edit text -> highlight a PDF -> rename a page -> undo 3x -> redo 3x.
6. Select a word in the middle of a line and decrease its font size repeatedly.
7. Insert a blank page using the + menu between two existing pages, then undo/redo.
8. Resize the navigator to Mini; grip should remain in the top-left.
9. Verify autosave and reopen, and Edit > Repair Notes Line Spacing.

TEST STATUS
75 automated tests passed; 11 GUI/PySide6 tests skipped in this build environment
(no PySide6 available and package installer lacks network access). Python
compilation succeeded. Do not mistake this for a fully GUI-tested binary.

KNOWN LIMITATIONS
- Native QTextDocument undo internals are still responsible for merging typing.
  In particular, test rapidly switching between typing and PDF highlights.
- Undo history is not persisted on application restart.
- Native Qt text undo memory is separate from the 200 MiB custom history budget.
- Move/copy pages BETWEEN tabs uses the existing transfer implementation;
  this cross-tab transfer operation is not yet a unified undo step.
