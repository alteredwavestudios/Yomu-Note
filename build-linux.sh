#!/usr/bin/env bash
# Build an offline-OCR-enabled Linux application directory.
# Run on the intended Linux architecture. GitHub release automation builds
# the AppImage from this directory; PyInstaller output alone is not an AppImage.
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Create .venv and install requirements first (see docs/BUILD_RELEASES.md).' >&2
  exit 1
fi
.venv/bin/python -m pip install 'pyinstaller>=6.22.3,<7'
if ! .venv/bin/python fetch_fonts.py; then
  echo 'Optional font download unavailable; system fallbacks will be used.' >&2
fi
# Linux requires Tesseract on the BUILD HOST, not on the end-user machine.
stage="$PWD/.build/ocr"
.venv/bin/python ocr_packaging/prepare_ocr.py --target linux --output "$stage"
.venv/bin/python -m PyInstaller --noconfirm --clean --windowed --onedir \
  --name 'Yomu Note' --add-data 'assets:assets' \
  --add-data 'LICENSE:.' --add-data 'THIRD_PARTY_NOTICES.md:.' \
  --add-binary "$stage/tesseract:ocr" \
  --add-data "$stage/tessdata:ocr/tessdata" \
  --add-data "$stage/THIRD_PARTY_OCR_NOTICES.txt:ocr" \
  --add-data "$stage/TESSERACT_APACHE_2.0.txt:ocr" \
  main.py
.venv/bin/python ocr_packaging/verify_ocr_bundle.py \
  --target linux --dist "$PWD/dist/Yomu Note"
printf 'Built dist/Yomu Note/Yomu Note with local English OCR\n'
