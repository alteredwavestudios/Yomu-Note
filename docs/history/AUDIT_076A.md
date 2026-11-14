# Yomu Note v0.7.6a — Integrated Offline OCR architecture audit

## Scope of change

Runtime Tesseract discovery (`ocr_runtime.py`), explicit language-model paths
(`ocr_engine.py`), platform-neutral missing-engine messaging, native build
staging (`ocr_packaging/`), PyInstaller Windows/macOS scripts, installer
verification and redistribution notes. Notebook schema, autosave, Undo/Redo,
PDFium rendering, cancellation and OCR-region limits are unchanged.

## What is verified here

- Source compiles; regression suite: **385 passed, 46 GUI-related skips**,
  3 pytest subtests passed.
- Simulated PyInstaller roots prefer app-owned engines and handle macOS
  Frameworks/Resources separation of executable and model files.
- Staging tests cover Windows DLL copying, English/orientation data,
  missing-model failure, and SHA-256 inventories.
- A **real local Tesseract executable copied to an isolated directory** with
  its own `eng.traineddata` recognised `YOMU NOTE BUNDLED OCR` from a generated
  PNG when the Python interpreter was simulated as frozen. This is a Linux
  runtime integration test, **not** verification of a Windows or Mac binary.
- The post-build verifier checks both `--list-langs` and actual generated PNG
  OCR using a restricted environment. On Mac it additionally inspects dylib
  links for build-machine Homebrew references. Windows installer builds are
  rejected if standalone OCR verification fails.
- Archive integrity checked. Existing source files are preserved; no original
  project files or user data are deleted/converted.

## What remains to verify before distributing

- A **real Windows x64 build** and Inno Setup installer running on a clean
  Windows computer without separately installed Tesseract or development DLLs.
- An **Apple Silicon .app** launched from Finder on a Mac with no Homebrew
  Tesseract runtime available. Verify image and PDF OCR after relaunch.
- User-visible OCR selector/review, cancellation, and tab switching in native
  Qt GUI. Qt tests were skipped in this source environment.
- macOS Developer ID signing/notarisation and the licensing notices for every
  DLL/dylib supplied by the selected native Tesseract distribution.

## Privacy and supply chain

OCR remains entirely local. No downloads happen at runtime and no network
service receives image crops or recognised text. Subprocess command arguments
are passed as lists (no shell), models are pinned using `--tessdata-dir`, and
OCR temp files use an automatically cleaned directory. The build computer is
responsible for supplying **trusted** native Tesseract binaries and maintaining
security updates. Hash inventories aid auditing but do not authenticate a
third-party release by themselves.

## Source ZIP versus user installer

This ZIP contains source code and build scripts, not Windows/macOS OCR
executables. Run the revised build script **on each target OS**. The resulting
Windows installer or Mac app must contain the native engine and `eng.traineddata`;
the end user then needs no separate OCR installation. See `OCR_BUILD_GUIDE.md`.
