# Yomu Note v0.7.3 — Windows/macOS Smart Import acceptance checklist

**Use a COPY of a notebook first.** Source candidate, not GUI-verified here.

## Essentials

- [ ] Open existing v0.7.2b notebook, save, close, reopen; notes, annotations,
      read checkboxes, page order and tab progress stay unchanged
- [ ] Open **Smart Import** with nothing highlighted in Groups mode; destination
      visibly defaults to **Root of this tab**, regardless of middle PDF page
- [ ] Select a nested group deliberately, open Smart Import; its *name* appears
      in the destination dropdown; change it back to Root and verify root import
- [ ] Import two PDFs: choose one group per file. They appear as siblings, not
      accidentally nested under the last previewed group
- [ ] Choose one group for all and verify both source files' pages remain ordered
- [ ] Choose no new groups and verify pages are not wrapped in new file groups
- [ ] Import PDF with real bookmarks, including two levels; review displays
      exact headings and physical pages, not printed page numbers
- [ ] Rename chapter (double-click name), change start page with spinbox,
      view the associated page via slider / page-number control
- [ ] Use **Set start to preview page**, then Undo/Redo in review
- [ ] Add chapter, add nested subsection, indent/outdent, merge/remove;
      verify no page goes missing and page counts update
- [ ] Import a PDF without bookmarks; manual chapters and fixed N-page ranges
      work, and Automatic shows no invented headings
- [ ] On cancellation, notebook page count and group tree stay unchanged
- [ ] On confirmation, all pages arrive once in order and one Undo restores
      the previous project; Redo restores the complete imported tree
- [ ] Move a source page from one imported subgroup to another; read progress
      and original source image remain correct
- [ ] Open EPUB/DOCX/PPTX that converts successfully: if converted PDF has
      bookmarks, review them; otherwise manually create groups
- [ ] Deliberately pick an impossible fixed-range count (e.g. 1 page for
      thousands of pages): receive a sensible error, no partial import

## Visual and interaction checks

- [ ] Try light and dark themes; chapter preview, controls and warning labels
      remain readable without clipping or horizontal overflow
- [ ] Resize review window and switch across source files; no stale preview
      from a different source remains on screen
- [ ] Cancel while preview is still rendering; no crash or deleted-label error
- [ ] Import a large book; only the selected preview image is loaded on demand
- [ ] Existing Crisp preview, Playful celebrations, Pomodoro and checkboxes
      remain unchanged

## Command-line checks (run at source folder root)

```powershell
python -m pytest -q
python -m pytest tests/test_v073_smart_import_gui.py -q
python -m compileall -q yomunote
```

A test **skip** caused by a missing optional test dependency is not a GUI pass.
If any GUI test fails, keep the prior v0.7.2b copy and capture the traceback.
