# v0.7.6a — packaged OCR acceptance checklist

**Run on both Windows and macOS with the built application.**

- [ ] Build script reports *OCR bundle verified* before printing success.
- [ ] Inspect bundle: Tesseract executable, `eng.traineddata`, native libraries,
      Apache licence and third-party notice are present.
- [ ] On a clean Windows installation with **no Tesseract installed**,
      install Yomu Note and recognise English text in a scanned PDF.
- [ ] On a clean Mac with **no Homebrew Tesseract installed**, launch the `.app`
      from Finder (not Terminal), select OCR and recognise a PDF text region.
- [ ] Repeat with imported PNG/JPG and multiple OCR rectangles.
- [ ] Uncheck, cancel, switch tabs during OCR. No stale callbacks or lost notes.
- [ ] OCR error if bundle deliberately missing has no Windows paths on Mac.
- [ ] OCR stops at existing per-region timeout; temp selections are deleted.
- [ ] Close/reopen notebook: notes/formatting, reading states, imports,
      annotations, and 60-second dirty-only autosave are unchanged.
- [ ] Windows installer contains all `_internal/ocr` files after installation;
      upgrading an existing installation retains the established AppId.
- [ ] Confirm the macOS app has no unresolved `/opt/homebrew/Cellar/` or
      `/usr/local/opt/` binary references (the build verifier checks this).
- [ ] Review actual native dependency licences before public release.

Qt and native OS GUI testing **cannot be completed in the source-test container**.
A green source suite and post-build verifier are necessary but not sufficient.
