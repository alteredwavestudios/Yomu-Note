# Yomu Note v0.8 — Selective Smart Import 3.0

**Source candidate.** Builds for Windows and macOS still require native compilation and hands-on verification. **Keep a backup of the v0.7.6.a working app and important `.yomunote` files.**

## What changed

1. For any imported multi-page source, *including ordinary Import*, the existing review now offers **All page numbers (default)** or a custom list of physical source pages such as `2-10, 15, 22-30`.
2. When a PDF / converted PDF has reliable embedded bookmarks, each chapter and subsection receives a checkbox. **All chapters are included by default.** Checking a parent checks its subsections; unchecking a parent excludes them. An independently selected child chapter can be included without its parent's other pages.
3. Front matter before the first chapter has its own checkbox. This prevents a chapter-only import silently bringing a book's unnumbered cover and contents pages along.
4. When both page ranges and chapters are selected, Yomu Note imports the **intersection**. Repeated/overlapping ranges do not create duplicate pages. Malformed, empty and out-of-bounds ranges produce a helpful error and do not commit.
5. The review shows the *original* PDF page number plus an INCLUDED/EXCLUDED status. Original `page_index` metadata is preserved; sparse chapter structures are remapped into valid new group boundaries and empty chapter folders are pruned.
6. Chapter filtering is available even if **Do not create chapter subgroups** is selected. Whether a page is included is independent of whether the imported pages are put into new folders.
7. The full import remains one Undoable action; cancellation leaves the notebook untouched and cleans staged assets. Excluded pages' assets are cleaned **after** successfully committing included pages, because PDF pages often reference the same original file.
8. The About window, Qt version, save manifest `app_version`, and Windows installer label are **v0.8**. Saved notebook format remains v5 and per-tab project format v4.

## A couple of deliberate limits

- Source documents are still **indexed into temporary staging first** so we can inspect their page counts and embedded bookmarks. A future performance improvement could skip copying excluded source pages earlier for selected formats; this release does not change the importer architecture.
- The page preview can still browse **all physical source pages**, including excluded ones, because seeing chapter boundary context is useful. Each page is clearly labelled INCLUDED or EXCLUDED. Only selected pages enter the notebook.
- A converted Word, EPUB or other file can have selectable chapters only if the converter retained PDF bookmark information. There is no OCR-based guessed chapter detection in v0.8.
- Chapter checkboxes and source-page selection are a **temporary review state**. They are not permanently attached to a source PDF or to any existing notebook file.

## What's not in this build

Sticky notes, photograph annotations, clipboard image pasting and JPEG compression, and microphone dictation remain queued for v0.8.1–v0.9. The existing one-minute autosave, integrated OCR packaging, original navigator selection rules, notes pages, annotation tools and document schema are not intentionally changed.

## Installation / builds

**Windows:** Open PowerShell in the extracted source folder and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build-windows.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build-installer-windows.ps1
```

The installer will be `installer\YomuNote_Setup_v0.8.exe`. The build computer needs a trusted Tesseract installation so the *compiled installer* can contain its own OCR engine. End users should not need a separate OCR install.

**Mac:** Run `build-mac.command` from the extracted source folder after the usual environment setup. Builds need a trusted Tesseract build and may need macOS permission adjustments. The resulting app needs a native OCR test and (for public distribution) signing/notarisation review.

See `TEST_WINDOWS_MAC_V080.md` for the acceptance checklist, including Clean Windows/Mac verification and cancellation/Undo checks.
