# Yomu Note — checklist before the first GitHub commit

## 1. Test the candidate on copies of real notebooks

- [ ] Back up the current working v0.8.1 build and personal `.yomunote` files elsewhere.
- [ ] On Windows, build v0.8.1b with PowerShell from the source folder. Check the About window says **v0.8.1b**.
- [ ] Open an older `.yomunote`, create/edit a notes page, save, close/reopen, verify no lost text/annotations.
- [ ] Import two shared tabs, Undo, Redo, save/reopen, export one tab and import the resulting notebook into a *different* notebook.
- [ ] Drag an exported notebook onto the preview, notes editor and navigator; it must offer tab selection rather than overwrite/open unexpectedly.
- [ ] In Smart Import, rapidly select/deselect chapters, Select All/None, and preview different pages; no crashes.
- [ ] Check 60-second dirty-only autosave and manual Save on a copy, including a longer continuous editing period.
- [ ] Try OCR from the **packaged app** on a clean computer without separately installed Tesseract.
- [ ] macOS: repeat the critical import/Undo and OCR checks if distributing Mac builds; verify signing/notarisation separately.
- [ ] Review any app or OS crash logs and compare CPU/RAM when opening several large PDFs.

## 2. Confirm what you're putting on GitHub

- [x] **Select GPL-3.0-or-later for the original source code**, with full text in `LICENSE`; review `THIRD_PARTY_NOTICES.md`. Confirm that all original-code rights holders approve before publishing.
- [ ] Confirm permission for app icon, chiptune audio, fonts, sample data and any artwork. Keep third-party licence notices.
- [ ] Never commit personal course documents, notebook SQLite files, backups, login credentials, `.env` files, private keys or unrelated local source folders.
- [ ] Run `git status --short` and `git diff --cached --stat` before your commit. Check that only the intended source, tests, build scripts and documentation are staged.
- [ ] Make sure no packaged binary, virtual environment, PyInstaller output, source ZIP or temporary OCR executable is staged.
- [ ] State in the repository description that this is a **pre-1.0 project**, and distinguish source code from signed installers.

## 3. Run automated checks

```bash
python -m compileall -q main.py yomunote ocr_packaging tests
python -m pytest -q
```

Run Python **from the project folder**. For Windows users, the Python executable is typically `.venv\Scripts\python.exe`; for macOS/Linux, `.venv/bin/python`.

## 4. Git commands (first local commit)

Run in the intended source folder, **only after reviewing .gitignore and the staged files**:

```bash
git init
git add .
git status --short
git diff --cached --stat
git commit -m "Yomu Note v0.8.1b: pre-GitHub security and documentation hardening"
```

If you've already initialised a repository, skip `git init`. Publishing/pushing to GitHub is a separate step requiring your account and the intended repository destination. Nothing in this source ZIP auto-publishes notebooks or code.

## 5. Known release gates

The 48 skipped Qt-dependent tests are **not** equivalent to GUI coverage. The source audit also identifies synchronous heavyweight saving, untrusted native PDF parsing, and separately tested dependency upgrades as v1.0 work. See `SECURITY_AUDIT_081A.md`.
