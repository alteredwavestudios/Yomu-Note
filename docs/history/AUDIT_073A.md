# v0.7.3a targeted source audit

## Scope
- Smart Import custom page label token grammar and post-review chapter numbers
- Smart Import's NEW group expansion state and review outline convenience
- Option persistence, pure grouping plan and regression tests

## Safety invariants
- Only newly constructed group nodes use the collapse flag; existing page-group nodes are deep-copied and their saved expansion state is untouched.
- All pages still have unique stable IDs and remain in one flat page order (`flatten()` / `validate()` regression tested).
- Page labels change staged page metadata only, after the user approves the final chapter structure and BEFORE its single Undoable commit. No page removal, file conversion, or storage change.
- Old curly-brace tokens are supported; square brackets map to the identical whitelist, not Python `str.format` or arbitrary expression evaluation.
- Unstructured documents use chapter 1; top-level headings increment it, nested headings do not. User-edited boundaries override originally detected PDF TOC.
- The notebook's existing collapsed boolean format is retained; reload retains both titles and collapsed groups.

## Automated checks
- `python -m compileall -q yomunote`
- `python -m pytest -q --disable-warnings --maxfail=1` — 348 passed, 43 skipped, 3 subtests passed.
- Real PDF bookmark -> edit proposed boundary -> labels -> collapsed plan -> save/reload test passed.
- Optional Qt tests added for checkbox default, disabled case, and review expansion switch; they are skipped here because PySide6 is not installed.

## Known validation gap
Native Windows/macOS Qt widget rendering and actual checkbox/toggle interaction were not run here. Confirm using `TEST_WINDOWS_V073A.md`.

## Unchanged code
No changes to rendering, thumbnail cache, OCR, editor, annotation canvas, storage schema, PDFium lock, fonts, themes, Pomodoro, reading-reward logic or build scripts.
