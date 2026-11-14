#!/bin/zsh
# Yomu Note v0.8.1b - macOS .app with private, local Tesseract OCR.
# Homebrew is a BUILD-COMPUTER dependency, not an end-user dependency.
set -e
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Run run-mac.command first to create .venv.'
  if [[ -t 0 && -z "${CI:-}" ]]; then read '?Press Return to close...'; fi
  exit 1
fi
if command -v uv >/dev/null 2>&1; then
  uv pip install --python .venv/bin/python 'pyinstaller>=6.22.3,<7'
else
  .venv/bin/python -m pip install 'pyinstaller>=6.22.3,<7'
fi
if ! .venv/bin/python fetch_fonts.py; then
  echo 'Optional font download unavailable; system fallbacks will be used.'
fi

# Avoid accidentally shipping a .app that still depends on Homebrew on the
# *end user's* Mac: PyInstaller collects and relinks Tesseract's dylibs.
if ! .venv/bin/python ocr_packaging/prepare_ocr.py --target macos --output .build/ocr; then
  echo 'OCR build dependency missing. On this build Mac only, run: brew install tesseract'
  if [[ -t 0 && -z "${CI:-}" ]]; then read '?Press Return to close...'; fi
  exit 1
fi
args=(--noconfirm --clean --windowed --onedir --name 'Yomu Note'
  --icon 'assets/icon.icns' --add-data 'assets:assets'
  --add-data 'LICENSE:.' --add-data 'THIRD_PARTY_NOTICES.md:.'
  --add-binary "$PWD/.build/ocr/tesseract:ocr"
  --add-data "$PWD/.build/ocr/tessdata:ocr/tessdata")
for file in .build/ocr/*.txt .build/ocr/*.json; do
  [[ -f "$file" ]] && args+=(--add-data "$PWD/$file:ocr")
done
.venv/bin/python -m PyInstaller "${args[@]}" main.py
.venv/bin/python ocr_packaging/verify_ocr_bundle.py --target macos --dist "$PWD/dist/Yomu Note.app"

# A separately signed/notarized release requires the developer's Apple ID
# signing identity and notarization credentials. Do not claim notarization.
printf '\nDone. Offline OCR is bundled: %s/dist/Yomu Note.app\n' "$PWD"
if [[ -t 0 && -z "${CI:-}" ]]; then read '?Press Return to close...'; fi
