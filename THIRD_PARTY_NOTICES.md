# Third-party software and font notices

Yomu Note's **original application source code** is distributed under
**GNU GPL version 3 or (at your option) any later version** (`GPL-3.0-or-later`).
See [`LICENSE`](LICENSE). The copyrights and licence terms of **third-party**
components remain with their authors and are **not** changed by this file.

This file is an attribution/inventory starting point for the **source** release.
It is not a complete list of native dependencies in any particular frozen
Windows/macOS/Linux binary. A maintainer **must** inventory each platform's
actual executable/DLL/dylib/.so dependencies and provide their complete required
licences/notices and source/compliance information before distributing installers.

## Direct dependencies identified in `requirements.txt`

| Component | Upstream licence | Use in Yomu Note | Upstream information |
| --- | --- | --- | --- |
| PySide6 / Shiboken6 and Qt | Dual-licensed; LGPL-3.0/GPL-3.0 and other applicable terms by module | GUI and multimedia | https://doc.qt.io/qtforpython-6/ and https://www.qt.io/development/open-source-lgpl-obligations |
| pypdfium2 | Apache-2.0 / BSD-3-Clause | PDF renderer | https://pypi.org/project/pypdfium2/ |
| PDFium and bundled libraries | BSD-style and additional dependency licences | Native PDF rendering via pypdfium2 | https://pypdfium2-team.github.io/pypdfium2/readme.html |
| Pillow | MIT-CMU | Image processing | https://github.com/python-pillow/Pillow/blob/main/LICENSE |

**PySide6/Qt**: For the compiled application, identify every Qt module and
its licence and satisfy the elected GPLv3 or LGPLv3 distribution path.
If distributing LGPL libraries, comply with notices, corresponding source,
replacement/relinking and installation-information requirements as applicable.
Qt Multimedia may also include codecs / FFmpeg components with independent
licences: check the actual platform build.

**pypdfium2/PDFium**: Do not stop at pypdfium2's own licence. Its published
binary wheels include further PDFium dependency licence texts, described in
upstream's `BUILD_LICENSES/` material. Include those exact notices with each
binary release; this list cannot determine which libraries any future wheel
contains.

## OCR (included in standalone installers)

| Component | Upstream licence | Upstream information |
| --- | --- | --- |
| Tesseract OCR | Apache-2.0 | https://github.com/tesseract-ocr/tesseract |
| Tesseract English trained data (`tessdata`) | Apache-2.0 | https://github.com/tesseract-ocr/tessdata |
| Leptonica | BSD-style (check specific build) | https://github.com/DanBloomberg/leptonica |

The source repository already contains `ocr_packaging/licenses/TESSERACT_APACHE_2.0.txt`
and `ocr_packaging/THIRD_PARTY_OCR_NOTICES.txt`.
Native bundles may also contain libjpeg, libpng, zlib, libtiff, libwebp,
ICU, and other platform-specific libraries. Their exact notices must be
collected from the actual build used. This list is illustrative, not exhaustive.

## Bundled fonts (downloaded during building, not in the source ZIP)

| Family | Licence | Source directory |
| --- | --- | --- |
| Montserrat | SIL Open Font License 1.1 | https://github.com/google/fonts/tree/main/ofl/montserrat |
| Mochiy Pop One | SIL Open Font License 1.1 | https://github.com/google/fonts/tree/main/ofl/mochiypopone |
| Nunito | SIL Open Font License 1.1 | https://github.com/google/fonts/tree/main/ofl/nunito |

`fetch_fonts.py` downloads each family alongside its own `OFL.txt` notice.
Keep those original notices with bundled font binaries; do not relicense
font files as GPL. The licensing of original documents made with these fonts
is not changed by embedding the fonts.

## Build tools (typically **not** redistributed as libraries)

- **PyInstaller**: uses GPL-2.0 plus an exception covering redistribution of
  applications built with it. This does not change Yomu Note's GPL licence or
  waive any dependency obligations. https://pyinstaller.org/en/stable/license.html
- **Inno Setup, AppImage tooling**: building an installer does not automatically
  grant permission to redistribute their libraries/components. Check exactly
  what goes into each final installer and the applicable notices.

## Optional user-installed converters

Yomu Note may invoke **LibreOffice** (`soffice`) for Office formats or
**Calibre** (`ebook-convert`) for EPUB. These tools are not currently included
inside the source ZIP; when users install them separately, they remain subject
to their own licences. If a future installer bundles them, perform a separate
licensing review before publishing.

## Artwork, audio, screenshots and imported documents

- `assets/icon.*`: verify the icon's authorship and licence/permission before
  declaring that it is covered by Yomu Note's original-code GPL.
- `assets/audio/*.wav`: `make_jingles.py` documents that these are locally
  generated original tunes; verify authorship/rights if they were supplied by
  outside contributors.
- `docs/screenshots/*.png`: screenshots include examples of third-party
  academic material, potentially copyrighted. Permission for those embedded
  excerpts is **not established** by licensing Yomu Note itself. Review and
  replace/redact as appropriate before making the repository public.
- `.yomunote` projects and user-created coursework are not automatically
  GPL-licensed because they were made with the app.

## Maintainer binary-release checklist

1. Lock and record exact direct/transitive dependencies **per operating system**.
2. Generate a software bill of materials (SBOM) or full asset/library inventory
   from the actual frozen installer and identify licence terms for each entry.
3. Collect and retain actual licence texts, copyright attributions and `NOTICE`
   files for Qt, Pillow, PDFium dependencies, Tesseract, fonts, and native libraries.
4. Elect and document which Qt licensing route is used in each build; satisfy
   GPL/LGPL source, notices, user rights and relinking requirements as applicable.
5. Supply the corresponding source for the distributed Yomu Note binaries,
   including build scripts, and the required third-party source/access information.
6. Ensure each installer includes `LICENSE` and this file, and ships all
   additional third-party notices the particular build requires.
7. Verify Mac/Windows/Linux installers individually before publishing.
8. Verify ownership/permissions for project artwork, jingles and screenshots.

This is a practical engineering checklist, not a legal opinion or certification.
