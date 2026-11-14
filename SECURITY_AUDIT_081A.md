# Yomu Note v0.8.1a — Pre-GitHub security & stability audit

**Historical note:** This audit predates the GPL-3.0-or-later licensing draft. Its note about a missing source licence describes the earlier state. See `LICENSE` and `THIRD_PARTY_NOTICES.md` for the current draft.

**Audit scope:** Source files from the user-confirmed working v0.8.1 Tab Exchange release, storage, file import, Qt worker boundaries, packaging scripts, `.gitignore`, documentation and automated tests. Date: 11 November 2026. **This is a targeted source audit, not a penetration test or a guarantee of safety.**

## Results and implemented safeguards

| Category | Change | Why |
| --- | --- | --- |
| Shared notebook manifests | Read SQLite `length(value)` and enforce size limit BEFORE fetching manifest content into Python | Prevent maliciously oversized metadata from causing avoidable RAM spikes |
| Shared tab project metadata | Compare actual SQLite `length(data)` to declared size before deserialising JSON | The `size` column is untrusted input |
| Tab Exchange batch | Inventory *all selected* referenced files and their real BLOB sizes BEFORE any asset copy | Avoid partial multi-GB copies and enforce the 4 GiB / 100,000 file transfer limits early |
| Tab Exchange export | Actually read and validate `PRAGMA quick_check` result | Executing PRAGMA without fetching its result was not an integrity check |
| Notebook opening | Preflight total asset count, declared/actual size and total temporary extraction budget | Protect against hostile notebooks with millions of entries or unexpectedly huge extraction |
| Notebook opening | Validate file timestamps before `os.utime` | Avoid malformed timestamps crashing extraction partway through |
| Tab selection dialog | Block recursive item-change notifications during Select All/None | Avoid unnecessary callbacks with large notebook tab lists |
| Version | Central version, About, saved notebook/project metadata, Windows installer | All report 0.8.1a (notebook schema stays v5) |
| Contributor docs | In-code docstrings, source map, modernised README, precommit checklist | Explain ownership, working directory, Ctrl/Undo, Qt signal/thread safety and data boundaries |
| Dependency floors | Raise Pillow/pypdfium2 minimums and PyInstaller minimum | Address recent upstream parser and bootloader fixes; **platform retest needed** |

## Checks actually performed in this environment

- Original v0.8.1 baseline: **422 passed, 48 skipped**, plus 3 passed subtests.
- v0.8.1a suite: **430 passed, 48 skipped**, plus 3 passed subtests.
- Source syntax: `compileall` and AST parse succeeded.
- New tests validate malicious declared asset sizes, oversized metadata, negative timestamps, safe export failure, preflight order and key beginner comments.
- GitHub source/archives inspected for accidentally included user notebooks and generated caches.
- Changes-only patch and resulting source ZIP will be validated before delivery.

**Not tested here:** native PySide6 GUI (Qt not installed in the test environment), Windows Inno Setup installer, macOS application signing/notarisation, Linux standalone packaging, clean-PC OCR, and the recently patched pypdfium2 5.15.2 runtime. Our test environment used pypdfium2 5.8.0 and Pillow 12.3.0; the new dependency floor needs separate platform tests.

## Remaining risks / non-blocking for a source commit, but important for releases

1. **Native PDF and image parsers are not sandboxed.** A malicious PDF could exploit PDFium; validate source/size and use current builds, but do not treat third-party documents as fully safe. The pypdfium2 maintainers explicitly caution against unsandboxed untrusted files. The 5.15.2 release (9 Nov 2026) includes native lifecycle fixes. See <https://pypdfium2-team.github.io/pypdfium2/changelog.html>.
2. **Large notebook saves and some commits can briefly block the GUI thread.** A future background-save architecture with immutable snapshots and recovery is still needed before v1.0.
3. **Cross-tab page *moves* are not yet fully transactional** (separate from the new complete-tab exchange, which has staged rollback). Do not describe cross-tab page moves as atomic.
4. **Worker/UI lifecycle needs native stress testing.** Qt is not installed here; repeat chapter toggles, tab imports and undos on the user's Windows/Mac builds, with repeated opening and closing.
5. **Build scripts install dependencies from package indexes and collect system Tesseract**, so release security also depends on verifying dependency provenance, versions and licence notices. Native hashes/attestations and reproducible builds remain release work.
6. **External Office/EPUB converters** are optional subprocesses invoked for user-selected files. They have their own security patching and crash risks; Yomu Note does not sandbox them.
7. **The app's source-code licence is NOT selected.** Publishing source does not grant others permission to modify/redistribute. Choose a licence before marketing the GitHub repository as open source. Check rights to bundled assets and third-party licences.
8. **macOS signing/notarisation** and proper macOS microphone permissions (future dictation feature) are not covered by this candidate.
9. **Voice recognition, sticky notes, photo annotations and flattened PDF export** are future milestones, not included in this stability patch.

## Security-focused dependency notes (as of 11 Nov 2026)

- Pillow **12.3.0** addressed several parser advisories, including CVE-2026-59203; see <https://pillow.readthedocs.io/en/stable/releasenotes/12.3.0.html>.
- pypdfium2 **5.15.2** was published 9 November and fixed resource lifecycle bugs after its preceding release; see <https://pypdfium2-team.github.io/pypdfium2/changelog.html>.
- PyInstaller **6.22.1** addressed GHSA-9fxf-4qw3-ghmr; this build now asks for **6.22.3 or newer** within major version 6. See <https://github.com/pyinstaller/pyinstaller/security/advisories/GHSA-9fxf-4qw3-ghmr>.
- Updated security floors do not prove compatibility on every operating system. Run both native release tests *before distributing builds*.

## Scope discipline

No public API, notebook schema, user-visible import behavior, annotation formats, rich-text engine, reading progress or autosave cadence were intentionally changed. The targeted hardening guards only malformed/untrusted inputs and trims recursive checkbox notifications. Keep the confirmed working v0.8.1 baseline alongside this candidate until you finish native acceptance tests.
