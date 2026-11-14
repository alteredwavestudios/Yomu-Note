# Contributing to Yomu Note 🌸

Thanks for helping make offline study tools more useful and accessible!

Yomu Note is written in **Python and PySide6 (Qt)**. If you're new to Python, start with [BEGINNERS_ARCHITECTURE_GUIDE.md](BEGINNERS_ARCHITECTURE_GUIDE.md). Comments explain the most important data, UI and worker boundaries.

## Reporting bugs

Use the GitHub issue template. Mention the Yomu Note version, operating system, expected behaviour, actual behaviour and exact steps to reproduce. Screenshots help, but **remove personal notes, student information and private readings before posting them publicly**.

## Working locally

1. Create a clean Python virtual environment: `python -m venv .venv`.
2. Activate it and install `python -m pip install -r requirements.txt pytest`.
3. Run `python -m compileall -q main.py yomunote ocr_packaging tests`.
4. Run `python -m pytest -q`.
5. Launch `python main.py` with Qt and test your change in a copy of a notebook.

## Pull request guidelines

Keep each change focused. Add a regression test for bugs and describe any file-format, Undo/Redo, page-selection or migration effects. Never perform heavy file operations in the Qt GUI thread; keep GUI objects on their owning thread. Avoid deleting tab workspaces when Undo or background workers might still need them. Keep source and notebook format versions separate.

Don't upload proprietary PDFs, coursework, personal notebooks, third-party font binaries or secrets in a PR. See [SECURITY.md](SECURITY.md) for security issues. Original Yomu Note code is licensed `GPL-3.0-or-later`. By contributing code, you must have the right to submit it under these terms. Do not copy incompatible third-party code into pull requests.
