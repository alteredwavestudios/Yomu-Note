"""Fail a release build unless packaged OCR runs with its own English data.

This deliberately strips developer-library environment variables in the
subprocess: successful OCR on the build computer must not rely on Homebrew or
another system Tesseract installation at runtime.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def verify_bundle(distribution: Path, target: str) -> Path:
    distribution = distribution.absolute()
    if target == 'windows':
        roots = (distribution / '_internal' / 'ocr', distribution / 'ocr')
        binary_name = 'tesseract.exe'
    elif target == 'linux':
        roots = (distribution / '_internal' / 'ocr', distribution / 'ocr')
        binary_name = 'tesseract'
    elif target == 'macos':
        contents = distribution / 'Contents' if distribution.suffix == '.app' else distribution
        roots = (contents / 'Frameworks' / 'ocr',
                 contents / 'Resources' / 'ocr',
                 contents / 'MacOS' / 'ocr')
        binary_name = 'tesseract'
    else:
        raise ValueError('target must be windows, macos or linux')
    binaries = [folder / binary_name for folder in roots if (folder / binary_name).is_file()]
    models = [folder / 'tessdata' for folder in roots if (folder / 'tessdata' / 'eng.traineddata').is_file()]
    if not binaries or not models:
        raise RuntimeError('Missing bundled Tesseract executable or eng.traineddata in the application')
    binary, data = binaries[0], models[0]
    if target in ('macos', 'linux') and not os.access(binary, os.X_OK):
        raise RuntimeError(f'Tesseract is not executable: {binary}')
    environment = os.environ.copy()
    environment.pop('TESSDATA_PREFIX', None)
    for variable in ('DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH', 'DYLD_INSERT_LIBRARIES', 'LD_LIBRARY_PATH', 'LD_PRELOAD'):
        environment.pop(variable, None)
    if target == 'macos':
        environment['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
    elif target == 'linux':
        # Tools such as ldd need /usr/bin; a Windows SystemRoot PATH hides them.
        environment['PATH'] = '/usr/bin:/bin'
        # Simulate PyInstaller's private library lookup, never the developer's
        # LD_LIBRARY_PATH. ldd below must still show that libtesseract and
        # liblept resolve INSIDE the distributable, or the build fails closed.
        private_dirs = (distribution / '_internal', binary.parent)
        environment['LD_LIBRARY_PATH'] = os.pathsep.join(
            str(folder) for folder in private_dirs if folder.is_dir())
    else:
        system = os.environ.get('SystemRoot', r'C:\Windows')
        environment['PATH'] = str(Path(system) / 'System32') + os.pathsep + system
    completed = subprocess.run(
        [str(binary), '--list-langs', '--tessdata-dir', str(data)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        stdin=subprocess.DEVNULL, env=environment, timeout=30,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    if completed.returncode != 0:
        raise RuntimeError(f'Bundled Tesseract failed to start independently: '
                           f'{(completed.stderr or completed.stdout).strip()}')
    if not re.search(r'^eng\s*$', completed.stdout + '\n' + completed.stderr, re.MULTILINE):
        raise RuntimeError('Bundled OCR could not load its English language model')
    # A language-listing check alone does not prove that image decoder DLLs
    # or Leptonica's dynamic libraries can actually process a PNG.
    # Exercise the same command-line OCR path the application will invoke.
    from PIL import Image, ImageDraw, ImageFont
    with tempfile.TemporaryDirectory(prefix='yomu-ocr-selftest-') as tmp:
        sample = Path(tmp) / 'test.png'
        picture = Image.new('RGB', (1200, 240), 'white')
        draw = ImageDraw.Draw(picture)
        try:
            font = ImageFont.load_default(size=52)
        except TypeError:  # For old local Pillow versions
            font = ImageFont.load_default()
        draw.text((55, 85), 'YOMU NOTE OCR', fill='black', font=font)
        picture.save(sample)
        recognised = subprocess.run(
            [str(binary), str(sample), 'stdout', '-l', 'eng',
             '--psm', '6', '--tessdata-dir', str(data)],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            stdin=subprocess.DEVNULL, env=environment, timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if recognised.returncode != 0 or 'YOMU' not in recognised.stdout.upper():
            raise RuntimeError('Bundled OCR executable cannot recognise a test PNG: '
                               + (recognised.stderr or recognised.stdout).strip()[:500])
    if target == 'macos':
        # All dynamically linked Homebrew libraries must be collected and
        # relinked by PyInstaller. A laptop with no Homebrew cannot resolve
        # /opt/homebrew/Cellar/... references left in the final .app.
        files_to_inspect = [binary]
        framework = (distribution / 'Contents' / 'Frameworks')
        if framework.is_dir():
            files_to_inspect.extend(p for p in framework.rglob('*.dylib') if p.is_file())
        for candidate in files_to_inspect:
            inspected = subprocess.run(['otool', '-L', str(candidate)],
                                       capture_output=True, text=True, timeout=15)
            if inspected.returncode != 0:
                raise RuntimeError(f'Cannot inspect dynamic dependencies of {candidate}')
            for line in inspected.stdout.splitlines()[1:]:
                library = line.strip().split(' (', 1)[0]
                if library.startswith(('/opt/homebrew/', '/usr/local/Cellar/', '/usr/local/opt/')):
                    raise RuntimeError(f'Unsafe build-machine library link in {candidate}: {library}')
    if target == 'linux':
        # A healthy build on a developer's machine can still accidentally use
        # the host's libtesseract or liblept. Require these OCR-specific shared
        # libraries to resolve from INSIDE the packaged application's tree.
        linked = subprocess.run(['ldd', str(binary)], capture_output=True,
                                text=True, timeout=15, env=environment)
        if linked.returncode != 0:
            raise RuntimeError('Cannot check Linux Tesseract shared libraries')
        for line in linked.stdout.splitlines():
            lower = line.lower()
            if 'not found' in lower:
                raise RuntimeError('Missing bundled Linux OCR dependency: ' + line.strip())
            if any(marker in lower for marker in ('libtesseract.so', 'liblept.so')):
                if '=>' not in line:
                    raise RuntimeError('Unresolved Linux OCR dependency: ' + line.strip())
                library = line.split('=>', 1)[1].strip().split(' (', 1)[0]
                try:
                    Path(library).resolve().relative_to(distribution.resolve())
                except (OSError, ValueError):
                    raise RuntimeError('Linux OCR relies on a library outside the app: ' + library)
    return binary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, choices=('windows', 'macos', 'linux'))
    parser.add_argument('--dist', required=True, type=Path)
    args = parser.parse_args()
    try:
        binary = verify_bundle(args.dist, args.target)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f'OCR BUNDLE VERIFICATION FAILED: {exc}', file=sys.stderr)
        return 1
    print(f'OCR bundle verified: {binary} (English, independent native runtime)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
