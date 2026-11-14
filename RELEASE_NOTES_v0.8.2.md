# Yomu Note 0.8.2 🌸 — Reading View Memory (release candidate 1)

Yomu Note is an offline-first desktop notebook for academic readings, PDF
annotations, rich-text notes, reading checklists and shareable `.yomunote` tabs.
This **pre-release** adds a much more continuous reading experience.

## What's new

- **Remember reading positions per page.** Return to the scroll position you
  left, including the bottom of a long page.
- **Shared zoom across a root group.** Change zoom once and its pages and nested
  chapters inherit that zoom. Previously unvisited pages start at the top.
- **Independent page zoom.** Opt pages out of the group zoom, or disable shared
  zoom for a group.
- **Reading-view context menus.** Reset page or group zoom, clear remembered
  positions, or reset all reading-view settings.
- **Saved reading continuity.** Zoom and scroll memory can be restored when you
  reopen a `.yomunote` notebook, with preferences controlling the behaviour.
- **No extra page-image caching.** View state is compact notebook metadata;
  original PDFs, annotations and preview cache limits are unchanged.

The rest of the v0.8.1b features remain: offline OCR, Smart Import, nested page
organization, Tab Exchange, rich-text notes, annotations and Pomodoro tools.

## Downloads (after the draft is manually published)

| Platform | Release asset |
| --- | --- |
| Windows 10/11 (x64) | `YomuNote_Setup_v0.8.2.exe` |
| macOS Apple Silicon (arm64) | `YomuNote-0.8.2-macOS-arm64-unsigned.dmg` |
| macOS Intel (x86_64) | `YomuNote-0.8.2-macOS-x86_64-unsigned.dmg` |
| Linux | [Run or build from source](https://github.com/alteredwavestudios/Yomu-Note/blob/main/docs/INSTALL.md); no AppImage |

**The workflow creates an unpublished draft, not an automatic public release.**
Installers are unsigned, and the macOS DMGs are not notarised. Please test the
actual installed Windows application, and where possible the Mac DMGs on clean
Macs, before manually publishing this candidate.

## Compatibility and safety

- Notebook SQLite container format remains **5**; the legacy project manifest
  format remains **4**. The app version advances to **0.8.2** separately.
- Existing notes, original pages, annotations and tab IDs are preserved.
- View metadata is cosmetic and is validated when a notebook is reopened.
- Back up important `.yomunote` notebooks before testing a preview build.
- Some Office/EPUB conversions still need external programs. Normal reading,
  annotations and OCR are offline. Linux source OCR requires system Tesseract.

See the [installation guide](https://github.com/alteredwavestudios/Yomu-Note/blob/main/docs/INSTALL.md) and
[prior v0.8.1b notes](https://github.com/alteredwavestudios/Yomu-Note/blob/main/RELEASE_NOTES_v0.8.1b.md).
