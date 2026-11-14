# Windows & Mac acceptance checklist — Yomu Note v0.8

Run on **copies** of your notebooks. Prefer testing in a fresh app configuration with one or two sample PDFs containing nested bookmarks.

## Import behaviour

- [ ] Build launches; **Help → About** shows `v0.8`.
- [ ] Import an ordinary 20-page PDF: review opens with **All page numbers** checked; import all 20.
- [ ] Import the same PDF using `2-7, 12, 18-20` and verify **10** pages, in correct original source order, with no duplicates.
- [ ] Try malformed `1,`, `5-3`, `0`, a number beyond the end and a blank custom range. Confirm no pages enter the notebook and the dialog stays open.
- [ ] Import a bookmarked textbook: choose one chapter, then choose multiple nonadjacent chapters. Verify page counts and original PDF page indices.
- [ ] Deselect a subsection but leave its parent and siblings checked. Confirm only the subsection's pages disappear.
- [ ] Choose a **custom range plus chapter checkboxes**. Confirm only their intersection is imported.
- [ ] Import a PDF with front matter before Chapter 1. Uncheck **Include pages before the first chapter** and verify those pages are omitted.
- [ ] Select **Do not create chapter subgroups** while leaving chapter selection enabled. Confirm no new chapter folders appear.
- [ ] Choose a **group destination explicitly**; confirm the result is inserted there. The currently visible preview page must not silently control the destination.
- [ ] Import multiple source files with different ranges; switch between sources during review and confirm each remembers its own choices.
- [ ] Try an unbookmarked multipage PDF: range selection works and the absence of chapters is clear.
- [ ] Try a 1-page image: no unnecessary page selection dialog should appear.
- [ ] Use a custom `[chapter]` page title, import only Chapter 3 and check that labels still say Chapter 3, not Chapter 1.

## Safety and performance

- [ ] Cancel in review and confirm **no notebook changes** and no orphaned source originals remain.
- [ ] Undo one selective import; verify the existing notebook/group tree returns exactly. Redo; verify all selected pages return in the same order.
- [ ] Reopen a saved notebook; ensure the filtered pages, groups, labels and document links still work.
- [ ] Make a small edit after importing, wait one minute and reopen: confirm autosave retained it. Manual Save, closing and switching tabs must still work.
- [ ] Test a large PDF with many bookmarks (including invalid/duplicate/absent entries), and inspect UI responsiveness and memory growth.
- [ ] With a deliberately interrupted/failed import, verify the existing notebook remains untouched and a clear error appears.
- [ ] OCR on the compiled Windows and Mac app works offline, with no system Tesseract dependency on the end-user test machine.
- [ ] Version inside a **newly saved notebook**'s manifest is `app_version: "0.8"` while notebook format stays `5`.

**Release status:** Unit and source-level regression tests are not replacements for native Qt GUI testing. Do not distribute this candidate as final v1.0 before Windows/macOS acceptance.
