# Windows acceptance checklist — v0.7.3a

Use a BACKUP copy of an existing `.yominote` notebook.

1. In **Smart Import** with a bookmarked PDF, check the new **Collapse all newly imported groups and subgroups** box is ticked by default (on an install without an older preference). Import and confirm that the new file group and nested chapters are collapsed. Existing folders must keep their previous expansion state.
2. Repeat with that checkbox unticked. Only the newly created groups should start expanded. Confirm that the preference remains as you left it the next time the import dialog opens.
3. In the **structure review**, confirm that chapter branches start collapsed; toggle **Expand all chapters in review**, then toggle it back. Verify renaming, page-number edits and Undo/Redo still work.
4. Choose **Page labels → Custom pattern** and enter `Chapter [chapter] — Page [page]`. Preview should show `Chapter 1 — Page 2`. Import a PDF with at least two top-level chapter headings; pages under the second chapter should display `Chapter 2` while page numbers keep increasing.
5. Repeat with `Chapter {chapter} — Page {n}`, and adjust one chapter boundary in the review. The final page labels must follow the ADJUSTED boundary, not the original PDF bookmarks.
6. Check files with no bookmarks: `[chapter]` resolves to `1` for all pages, not literal `[chapter]`. Check a multi-file import: chapter numbering restarts for each file, while **one combined group** retains continuous `[page]` numbering.
7. Save, close, reopen. Verify every collapsed/expanded group and generated title survives. Verify Undo/Redo of the import and page counts are unchanged.
8. Import into an existing expanded group. The destination group must remain expanded; the newly created children should follow the checkbox. Try a cancelled import to ensure nothing is added.
9. Spot-check light/dark themes, checkbox hit targets, progress bars, PDF previews, and chapter reading rewards. Nothing in those systems was modified.

**Native GUI testing was not possible in the build environment.** Report a screenshot/traceback if a dialog or restored group behaves differently on Windows.
