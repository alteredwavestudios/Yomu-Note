# Yomu Note v0.7.6a — Integrated offline OCR build guide

## The difference between BUILD computers and USERS

The **source ZIP** contains Python changes and build tooling, but **does not
contain native Windows or macOS OCR executables**. They cannot be compiled and
verified for those operating systems in the Linux source-test environment.

The developer building a Windows installer or macOS app needs a trusted native
Tesseract install **on the build machine**. The revised scripts automatically
copy the engine, English language model, and required native files into the
finished app. The people installing the finished app **do not** need to install
Tesseract, Homebrew, Python, or language data separately.

## Windows 11 build (x64)

1. Install Tesseract on the **build machine only**, if not already installed:
   `winget install UB-Mannheim.TesseractOCR`. Verify `tesseract --version`, or
   check `C:\Program Files\Tesseract-OCR\tesseract.exe`.
2. Extract this source ZIP. Run `run-windows.bat` once to create `.venv`.
3. In PowerShell from the source root:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\build-windows.ps1
   ```

4. This stages OCR under `.build\ocr`, bundles `tesseract.exe`, adjacent
   DLLs and `eng.traineddata`, and runs `verify_ocr_bundle.py`. The build **fails**
   if the bundled copy cannot start or read its own English language model.
5. Check `dist\Yomu Note\_internal\ocr\tesseract.exe` and
   `...\tessdata\eng.traineddata` are present. Keep the whole `dist\Yomu Note`
   folder together; do not copy just the EXE.
6. Optionally create the installable package:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\build-installer-windows.ps1
   ```

   The installer recursively includes `_internal\ocr` and reruns the OCR
   verifier before packing.

## Apple Silicon Mac build

1. Install Tesseract **on the Mac doing the build only**: `brew install tesseract`.
   Check `tesseract --version`. You do **not** need `tesseract-lang` to bundle
   English; Tesseract's formula provides `eng.traineddata`.
2. Run `run-mac.command` once, then `build-mac.command` (or `zsh build-mac.command`).
3. The build stages Tesseract plus `eng.traineddata`, passes the executable to
   PyInstaller as a **binary**, and has PyInstaller collect/relink its dylib
   dependencies into the `.app` bundle. The post-build check fails on missing
   English data, unusable OCR, or remaining absolute Homebrew library paths.
4. Output is `dist/Yomu Note.app`. This build is for the architecture of the
   Mac performing the build; make a separate native build for Intel Macs.
5. Developer ID signing/notarisation is a separate distribution task. A
   working locally built `.app` is not proof of notarisation or universal
   architecture support.

## QA before public release

Test each finished package on a CLEAN machine/VM **without a system Tesseract**.
On macOS, launch the app from Finder with Homebrew absent from PATH. On Windows,
test the real Inno Setup-installed app, not just the PyInstaller folder. Verify
OCR on both a scanned PDF and an imported image, and repeat after relaunch.

The build verifier uses a local generated PNG and no network. That verifies the
normal recognition process, but it cannot prove that every Windows CRT/DLL or
macOS image codec is available on a different computer. A clean-machine smoke
test remains mandatory.

## Language policy, licensing, security

English is bundled by default; `osd` is included only if already present in
this build's Tesseract installation. Other language data can be added in a
future version, with appropriate controls. Do not ship every language file.

`ocr_packaging/THIRD_PARTY_OCR_NOTICES.txt` and the Apache-2.0 text are
bundled. Review all third-party DLL/dylib dependency licences and notices for
your selected Tesseract distribution before distributing publicly. The build
writes a SHA-256 inventory of the staged files to `BUILD_PROVENANCE.json`,
which documents *what* was bundled but is not independent provenance proof.

OCR never sends document data or recognized text to an external service. The
existing 40-region limit, pixel cap, two-minute per-region timeout,
cancellation and temporary-image cleanup are unchanged.

Sources: https://tesseract-ocr.github.io/tessdoc/Installation.html and
https://pyinstaller.org/en/stable/usage.html
