# Yomu Note v0.7.5 — Architecture, memory, privacy, and data-integrity audit

**Baseline:** verified v0.7.4 source (213 files). **Scope:** stability/security-only release; no change to notebook schema, notes rendering, reading rewards, import UI, or Undo semantics. All findings below are from source inspection unless explicitly described as a tested outcome. **No claim of native GUI validation**: PySide6 is unavailable in the audit environment.

## Executive summary

Yomu Note is substantially safer than a typical early Python/Qt desktop prototype: source assets are kept local, large notebook BLOBs are streamed, SQL changes occur in transactions, generated PDF images have memory/disk limits, all PDFium calls share one global lock, document paths receive validation, diagnostics rotate locally, Smart Import stages then validates, and project metadata retains stable page IDs.

**However, it is not yet accurate to call the whole application memory-leak-free, privacy-proof, or corruption-proof.** Native Qt lifetime and multi-hour stress tests remain essential. High-priority risks are long-lived old notebook workspaces/Qt objects and synchronous notebook saves/backups. Those require more intrusive changes and are deliberately *not* silently rewritten in this release.

## Findings addressed in this candidate

| ID | Severity | Evidence | What changed / how verified |
|---|---|---|---|
| S01 | Medium — Windows compatibility/security | `notebook._safe_file_segment` and `project.validate_relpath` checked drive/ADS, traversal and device names, but not `< > " | ? *` | Reject all these forbidden characters *on every OS*, before extracting untrusted notebook file entries. Positive and negative path tests. |
| S02 | Medium — save integrity | `Notebook.save()` streams SQLite BLOB writes, then checks mtime and size; a short or unexpectedly growing read should always abort the transaction with a clear error | Explicit byte count, immediate EOF failure, extra trailing-byte check. Regression test artificially returns a truncated asset stream and verifies previous SQLite contents survive unchanged. |
| S03 | Low — unbounded Python bookkeeping | `importers._CACHE_WRITES` retained a counter for each new cache directory encountered, including old notebooks | Limit to 512 folder counters; lock updates across worker threads. Clearing counters only causes an additional safe cache-trim pass, not deletion of original materials. |
| S04 | Medium — privacy of clean exports | `Notebook.create_clean_share_copy()` ran `VACUUM INTO` but preserved internal `project.v2/v3.backup.json` records, which can contain old deleted text | Strip *only internal migration-backup JSON* from the new clean share copy and VACUUM it again. Original and separately stored recovery backups remain intact. Test verifies private historical text does not appear in clean output bytes. |

## Major unresolved risks, ranked

### R01 — High: retained notebooks and discarded Qt panels can consume disk/RAM over time

`window.MainWindow.show_notebook()` and `close_current()` append old `Notebook` instances to `_retired_notebooks` without a corresponding steady-state cleanup. Each instance owns a `TemporaryDirectory` containing decompressed imported PDFs; simply opening a long series of different notebooks can keep workspaces alive for the remainder of the session. Tab deletion uses `_parked_panes` to preserve native `QTextDocument` Undo state, and removed notes-page documents stay in `_note_documents`. While some retention is intentional, it is not strictly linked to an Undo-history retirement event. This is the clearest potential long-session disk/RAM growth risk.

**Future fix:** add a lifecycle manager tracking per-notebook workers, per-page document history ownership, and retired undo references; reclaim resources only when no task or history entry can use them. Add native GUI tests for deleting/restoring tabs and note pages, switching notebooks 50+ times, and watching resident memory and temp-directory footprint plateau. Avoid a naive `close()` on switch: background renders may still be using those paths.

### R02 — High: synchronous persistence on the UI thread

`ProjectPane.save()` writes JSON and directly invokes `Notebook.save()`. `MainWindow._periodic_backup()` can also copy a large notebook via SQLite backup on the GUI thread. The save debounce is sensible, and files are streamed in 1 MiB chunks, but a 500 MB–1 GB imported source, a slow drive, several active tabs, or a large backup can still cause an unresponsive UI. Streaming reduces RAM consumption; it does **not** make disk I/O non-blocking.

**Future fix:** snapshot immutable per-tab manifests on the GUI thread, serialize writes through one save worker per notebook with coalescing and generation/version tokens, make close wait for the final successful commit, and add crash-injection tests. Do not simply call current `Notebook.save()` from concurrent workers while `Project` models mutate.

### R03 — High: transfer/import multi-step failure atomicity

`Notebook.transfer_pages()` writes copied assets to the target workspace, saves the target, then edits/saves the source on moves. A failure between these operations can leave workspace state partially applied, although notebook persistence uses SQL transactions for each individual save. Cross-tab moves were already documented as not fully Undoable. Smart Import has good staging cleanup but further failure-injection tests are warranted for cancellation near commit, duplicate sources, and device-full errors.

**Future fix:** use a validated transfer plan, stage all destination assets first, modify both model snapshots only after all source reads succeed, and commit one notebook-level transaction with rollback/recovery of in-memory state. Test interrupted moves at every phase.

### R04 — Medium: no persistent per-asset cryptographic integrity hash

Notebook file entries store size and timestamp but no checksum. SQLite handles transaction integrity and detects many corruptions, but a same-length mutation of a BLOB is not individually detected by file-length verification alone. Current save-time hashing covers small JSON manifests, not all large originals.

**Future fix:** add optional SHA-256 to a backwards-compatible manifest or asset metadata schema, calculate it incrementally when importing/saving, and check during load or on-demand use; keep legacy notebooks openable. Confirm performance on huge PDFs.

### R05 — Medium: backups, private paths, and historical content

Automatic rotating backups can retain deleted source documents until their rotation window expires. Clean share copies now remove embedded migration backup JSON, but **do not** sanitize author metadata inside PDFs, external links in notes, or separately stored recovery backups. Logs are local and rotated but may include full filesystem paths and converter error messages. This is a privacy footnote rather than evidence of exfiltration. `open_external_url` permits only HTTP(S) schemes and is user-initiated.

**Recommendation:** add a future 'Privacy & Share' inspection dialog and an explicit separate-backup deletion option, never silently destroy recovery data. Make disclosures about what cleaned export does and does not sanitize.

### R06 — Medium: untrusted Office/PDF conversion boundary

LibreOffice, Calibre, Tesseract, and PDFium parse imported documents locally. Subprocess calls use argument arrays, no shell, and have timeouts, which is positive. However third-party parsers can have their own vulnerabilities, CPU/memory spikes, external-resource behaviour and patch cycles. `requirements.txt` specifies version ranges rather than hashes. The Python code cannot serve as a sandbox for those executables.

**Recommendation:** keep the bundled dependencies and local converters updated; avoid importing untrusted documents from unknown senders; consider an optional restricted converter process with separate temp directory, memory/time constraints and disabled remote resources where supported.

### R07 — Medium: global PDFium lock and cache throughput

The global `PDFIUM_LOCK` prevents unsafe parallel PDFium calls but serializes OCR, previews and PDF indexing. Large OCR operations can delay thumbnail and page rendering work. Bounded caches limit disk pressure, but there is no verified long-run RSS benchmark and disk-cache counters are only one part of memory use.

**Future fix:** instrument queue lengths, render durations, per-cache counts and memory at intervals in opt-in diagnostics. Move priority/cancellation decisions earlier; *do not* remove the PDFium lock without upstream thread-safety proof and native stress tests.

### R08 — Medium: native Qt lifetime and stale callbacks

Qt signals, animation timers, and worker receivers are complex; v0.7.1's deleted QLabel crash demonstrated the risk of accessing destroyed C++ objects. Current `TaskSignals` uses queued UI-thread delivery and `_closed` checks, but a real GUI stress suite should systematically test closing review dialogs while a preview is rendering, switching notes pages repeatedly, and deleting tabs while thumbnails are queued.

**Future fix:** add Qt object lifetime assertions (`shiboken6.isValid` where necessary), weak ownership for callbacks, explicit cancellation tokens and a fixed set of GUI stress tests.

### R09 — Low/medium: build-time font download supply chain

`fetch_fonts.py` downloads optional fonts from an official GitHub raw repository when invoked by the Windows build script. Downloads are HTTPS, size-limited and checked for an SFNT header, but are **not pinned to a cryptographic checksum or fixed commit**. Running the packaged app does not download fonts; the exposure is in building the application and distributing whatever was fetched.

**Future fix:** pin fonts to an audited repository revision and verify SHA-256 checksums of fonts and licences, or bundle verified assets in a controlled release process. A font header check alone does not ensure authenticity.

### R10 — Low/medium: format-specific rendering edge cases

The earlier project audit noted 16-bit TIFF clipping and first-frame-only behaviour for multi-frame images. These can affect user expectations or reading fidelity; no evidence here that they corrupt notebook metadata. Test 16-bit scans, animated/multi-page TIFF, malformed PDF outlines, and extremely large slide images before expanding format support.

## Things explicitly NOT changed

- No database, notebook or page-ID schema bump.
- No changes to OCR output, annotation tools, rich-text HTML, page-group hierarchy, Smart Import chapter structure, Kawaii animations, colours or UI layout.
- No automatic deletion of the user's separate recovery backups.
- No changes to Qt document ownership or Undo/Redo structures (needs native tests).
- No disabling of valid old `.yominote` notebooks.

## Audit methodology / limits

- Inspected notebook and project load/save/backup/extract paths, nested group and notes-page formats, source import/conversion, worker signalling, PDFium locking, thumbnail caches, OCR commands, local diagnostics, UI retirement, external URL routing, and packaging metadata.
- Python compile check + full existing pytest suite and new targeted tests.
- New regression tests include Windows-only forbidden path characters, successful valid paths, cache bookkeeping cap, partial asset read/transaction rollback, and historical-note removal from a clean share copy.
- **No native Windows/PySide6 tests, no malware fuzzing, no CVE audit of installed binaries, no memory profiling of a running Qt window, no power-failure hardware test.** A passing Python suite is not proof these risks are gone.

## Priority after this release

1. Run `TEST_WINDOWS_V075.md`, specifically save/reload, clean export, Undo/Redo and repeated notebook switching while watching memory/temp space.
2. Design/test proper retired-notebook and parked-Qt-widget reclamation (R01).
3. Move save/backup I/O to a serialized background persistence pipeline (R02), with crash and cancellation tests.
4. Make cross-tab asset transfers transactional (R03).
5. Add optional per-asset checksums and a clean-share privacy inspection workflow (R04–R05).

**Release posture:** v0.7.5 is a *limited safety-hardening candidate*, not a claim of full architectural completion or a security certification.
