"""Stage a builder's Tesseract installation for PyInstaller.

This is a BUILD-TIME helper; the distributed app never downloads OCR files.
Run only on the target OS/architecture. The Windows Tesseract installation
should be a trusted UB Mannheim build; on macOS use Homebrew's formula,
and on Linux use the distribution-packaged tesseract-ocr binary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NOTICE = ROOT / 'ocr_packaging' / 'THIRD_PARTY_OCR_NOTICES.txt'
LICENSE = ROOT / 'ocr_packaging' / 'licenses' / 'TESSERACT_APACHE_2.0.txt'


def find_source_binary(target: str, source: str | None = None) -> Path:
    name = 'tesseract.exe' if target == 'windows' else 'tesseract'
    if source:
        path = Path(source).expanduser()
        if path.is_dir():
            path = path / name
        if not path.is_file():
            raise FileNotFoundError(f'Cannot find {name} at {path}')
        return path.resolve()
    override = os.environ.get('YOMU_TESSERACT_SOURCE')
    if override:
        return find_source_binary(target, override)
    candidates: list[Path] = []
    on_path = shutil.which(name)
    if on_path:
        candidates.append(Path(on_path))
    if target == 'windows':
        for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            base = os.environ.get(variable)
            if base:
                for sub in ('Tesseract-OCR', 'Programs/Tesseract-OCR'):
                    candidates.append(Path(base) / sub / name)
    else:
        if shutil.which('brew'):
            result = subprocess.run(['brew', '--prefix', 'tesseract'],
                                    capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                candidates.append(Path(result.stdout.strip()) / 'bin' / name)
        candidates.extend((Path('/opt/homebrew/bin/tesseract'),
                           Path('/usr/local/bin/tesseract'),
                           Path('/usr/bin/tesseract')))
    for item in candidates:
        if item.is_file():
            return item.resolve()
    hint = ('winget install UB-Mannheim.TesseractOCR' if target == 'windows'
            else 'brew install tesseract' if target == 'macos'
            else 'sudo apt-get install tesseract-ocr tesseract-ocr-eng')
    raise FileNotFoundError(
        f'Tesseract is required on the BUILD COMPUTER only. Run: {hint}. '
        'Then rebuild; people installing Yomu Note will not need to install it.')


def find_language_directory(binary: Path, target: str, *,
                            allow_system_fallback: bool = True) -> Path:
    # An explicitly supplied OCR executable must use matching language data,
    # rather than silently borrowing Tesseract's model from the build host.
    candidates = [binary.parent / 'tessdata',
                  binary.parent.parent / 'share' / 'tessdata']
    if target == 'macos' and allow_system_fallback:
        candidates += [Path('/opt/homebrew/share/tessdata'),
                       Path('/usr/local/share/tessdata')]
        if shutil.which('brew'):
            result = subprocess.run(['brew', '--prefix', 'tesseract'],
                                    capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                candidates.append(Path(result.stdout.strip()) / 'share' / 'tessdata')
    if target == 'linux' and allow_system_fallback:
        # Debian/Ubuntu and other distributions place tessdata in different
        # versioned directories; search only the usual system data locations.
        candidates.extend((Path('/usr/share/tessdata'),
                           Path('/usr/share/tesseract-ocr/tessdata')))
        root = Path('/usr/share/tesseract-ocr')
        if root.is_dir():
            candidates.extend(root.glob('*/tessdata'))
    for folder in candidates:
        if (folder / 'eng.traineddata').is_file():
            return folder.resolve()
    raise FileNotFoundError(f'English OCR model eng.traineddata not found near {binary}. '
                            'Check the build computer Tesseract installation.')


def stage_ocr(target: str, destination: Path, source: str | None = None) -> dict:
    if target not in ('windows', 'macos', 'linux'):
        raise ValueError('Only Windows, macOS and Linux bundle creation is supported')
    binary = find_source_binary(target, source)
    # --source and YOMU_TESSERACT_SOURCE are explicit dependencies. Their
    # language data must accompany that executable; don't mask omissions with
    # another Tesseract installation's global data on the build machine.
    explicit_source = source is not None or bool(os.environ.get('YOMU_TESSERACT_SOURCE'))
    models = find_language_directory(binary, target,
                                     allow_system_fallback=not explicit_source)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    shutil.copy2(binary, destination / binary.name)
    if target == 'windows':
        # UB Mannheim's redistributable has native DLLs beside tesseract.exe.
        # PyInstaller receives them as BINARY, not DATA, so the loader can use
        # them; the post-build smoke test detects unresolved DLL dependencies.
        dlls = [p for p in binary.parent.iterdir() if p.is_file() and p.suffix.lower() == '.dll']
        if not dlls:
            raise FileNotFoundError('No Tesseract DLL dependencies found beside the Windows binary; '
                                    'this is not a supported redistributable installation.')
        for dll in dlls:
            shutil.copy2(dll, destination / dll.name)
    data = destination / 'tessdata'
    data.mkdir()
    shutil.copy2(models / 'eng.traineddata', data / 'eng.traineddata')
    if (models / 'osd.traineddata').is_file():
        shutil.copy2(models / 'osd.traineddata', data / 'osd.traineddata')
    for legal in (NOTICE, LICENSE):
        if not legal.is_file():
            raise FileNotFoundError(f'Missing required OCR notice: {legal}')
        shutil.copy2(legal, destination / legal.name)
    for legal in binary.parent.glob('*'):
        if legal.is_file() and legal.suffix.lower() in ('.license', '.licence'):
            shutil.copy2(legal, destination / legal.name)
    # Hashes assist the packager in documenting precisely what was shipped;
    # they're not a substitute for verifying the provenance of the binary.
    files = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in destination.rglob('*') if p.is_file()}
    report = {'target': target, 'host': platform.platform(),
              'engine_source': str(binary), 'traineddata_source': str(models),
              'files_sha256': files}
    (destination / 'BUILD_PROVENANCE.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, choices=('windows', 'macos', 'linux'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source', help='Tesseract executable or its folder on this build computer')
    args = parser.parse_args()
    host = 'windows' if sys.platform == 'win32' else 'macos' if sys.platform == 'darwin' else 'linux'
    if args.target != host and not args.source:
        parser.error('Run the OCR packager on the target platform (or provide --source for tests).')
    try:
        report = stage_ocr(args.target, args.output, args.source)
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    print(f'Bundled OCR staged for {args.target}: {len(report["files_sha256"])} files')
    print('All runtime OCR recognition remains local/offline.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
