Yomu Note v0.4.4c - Emergency Editor Recovery (Windows/macOS/Linux)

WHY THIS HOTFIX EXISTS
- v0.4.4b introduced an unreliable proxy between QTextDocument undo and QUndoStack.
  Undo/Redo shortcuts could stop working. This reverts to native QTextEdit undo
  and preserves the older annotation and page-undo controls while a proper
  chronological unified history is redesigned and tested on Qt.
- v0.4.4b also used QTextBlockFormat.FixedHeight for blank lines. Once text was
  typed into those paragraphs, it could overlap or clip. This hotfix stops
  creating fixed-height lines and restores the v0.4.4a native layout.

IF YOU SAVED NOTES WHILE USING v0.4.4b
1. Make a backup copy of your project file first.
2. Open the copy in v0.4.4c.
3. Choose Edit > Repair Notes Line Spacing...
4. Confirm to reset only FixedHeight paragraph formats in the ACTIVE tab to
   natural line spacing; text is NOT removed. Repeat for other affected tabs.
5. The repair is one native undoable formatting operation.

NO CHANGES TO
- Notebook container format / backwards compatibility
- Quiet autosave and 10-minute backups
- PDF and thumbnail renderers, cache limits, Crisp sharpening
- Existing imported documents and annotations

This is a candidate build. Python-only checks are not a replacement for
running the Windows graphical editor. Use a copy of your study project.

IMPORTANT PYSide6 TYPEERROR FIX (06 NOVEMBER 2026)
- The old setLineHeight(height, LineHeightTypes.EnumValue) passes the wrong type
  for PySide6: it explicitly requires a plain int for the second argument.
- Normal font-size editing no longer calls setLineHeight at all, so a crash
  cannot leave an incomplete undo edit block or force unreadable fixed lines.
- The optional repair uses int(LineHeightTypes.SingleHeight.value) and always
  closes its undo edit block even if an error occurs.
- This deliberately does NOT claim the empty-line caret height is fixed;
  native text editing stability takes priority until that visual feature
  can be tested with PySide6 on Windows.
