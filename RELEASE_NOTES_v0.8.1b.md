# Yomu Note v0.8.1b 🌸 — First public preview

## What changed since v0.8.1a

- Stability fixes for annotation IDs/Undo and nested ordered-list indentation.
- Reliable, isolated GUI regression tests and timeout-protected build diagnostics.
- Notebook file format remains version 5; no migration is intended.


Welcome to an offline-first study notebook! Organise PDFs, annotate pages, write rich-text notes, tick off reading tasks and **share complete weeks of study material** as portable `.yomunote` tabs.

## Highlights

- **Tab Exchange:** Export selected tabs into a shareable notebook or import chosen tabs from another `.yomunote` file. Incoming tabs are independent copies; the whole import batch is one Undo/Redo step.
- **Smart Import 3.0:** Choose document page ranges and bookmark chapters before importing.
- **Organised reading:** Nested groups, thumbnails, editable page names, reading checklists and progress percentages.
- **Offline OCR:** Select scanned text, recognise locally and review before copying.
- **Study notes:** Rich-text notes, multiple notes pages per tab, annotations and Pomodoro focus tools.
- **Stability/security pass:** More defensive handling of imported notebooks and improved beginner-oriented code comments.

## Downloads

| Platform | Release asset |
| --- | --- |
| Windows x64 | `YomuNote_Setup_v0.8.1b.exe` |
| macOS Apple Silicon | `YomuNote-0.8.1b-macOS-arm64-unsigned.dmg` |
| macOS Intel | `YomuNote-0.8.1b-macOS-x86_64-unsigned.dmg` |
| Linux | [Run or build from GitHub source](docs/INSTALL.md) (no AppImage) |

**The three native installers only appear when the Windows/macOS builds succeed and the maintainer publishes the draft.** Linux installs from source. These preview builds are not signed/notarised and have not been universally verified on clean end-user machines. Use them with caution. See the [install guide](docs/INSTALL.md).

## For students and lecturers

Prepare a tab containing this week's reading material, notes and annotations. Choose **File → Export Selected Tabs as Notebook…** and share the resulting file. Recipients can import that tab into their own semester notebook, without replacing or modifying their existing tabs.

Only share documents you are allowed to redistribute. Your written notes and annotations are part of the exported tab.

## Compatibility and privacy

The saved notebook format remains version **5**. Yomu Note records the app version separately on save. Keep backups of coursework while testing any preview release. No account is required for the standard offline workflows. Some Office and EPUB conversions require external tools and are not fully self-contained.

This is **not v1.0**. See [SECURITY_AUDIT_081A.md](SECURITY_AUDIT_081A.md) and [PRE_GITHUB_CHECKLIST.md](PRE_GITHUB_CHECKLIST.md) for outstanding work.
