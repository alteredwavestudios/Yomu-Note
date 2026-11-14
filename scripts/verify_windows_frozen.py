#!/usr/bin/env python3
"""Repair DLL selection after PyInstaller and smoke-test the *frozen* EXE.

Why: Tesseract also distributes sqlite3.dll. PyInstaller may collect that
older copy into _internal next to Python's _sqlite3.pyd, producing the Windows
error "The specified procedure could not be found" at startup.

We restore the DLL distributed with the actual Python interpreter that built
_sqlite3.pyd. OCR's own DLLs remain isolated in _internal/ocr. Then we run the
EXE itself, with a disposable in-memory SQLite DB and no user notebook.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restore_matching_python_sqlite(distribution: Path, interpreter_root: Path) -> str:
    frozen = distribution / '_internal'
    extension = frozen / '_sqlite3.pyd'
    destination = frozen / 'sqlite3.dll'
    python_extension = interpreter_root / 'DLLs' / '_sqlite3.pyd'
    candidates = (interpreter_root / 'DLLs' / 'sqlite3.dll',
                  interpreter_root / 'sqlite3.dll')
    matching = next((p for p in candidates if p.is_file()), None)
    if not extension.is_file():
        raise RuntimeError(f'Frozen _sqlite3.pyd missing: {extension}')
    if not python_extension.is_file():
        raise RuntimeError(f'Cannot verify build interpreter extension: {python_extension}')
    if digest(extension) != digest(python_extension):
        raise RuntimeError('Frozen _sqlite3.pyd does not match the build interpreter')
    if matching is None:
        raise RuntimeError('Build Python sqlite3.dll not found; refusing unverified DLL')
    # The source is CPython's DLL, never the Tesseract OCR copy.
    if not destination.is_file() or digest(destination) != digest(matching):
        shutil.copy2(matching, destination)
        print(f'Restored CPython sqlite3.dll from {matching}', flush=True)
    if digest(destination) != digest(matching):
        raise RuntimeError('Copied sqlite3.dll hash does not match build Python')
    return digest(destination)


def smoke_test(distribution: Path) -> dict:
    executable = distribution / 'Yomu Note.exe'
    if not executable.is_file():
        raise RuntimeError(f'No frozen Yomu Note executable: {executable}')
    # Do not borrow the builder's Python modules or Tesseract installations.
    environment = os.environ.copy()
    for var in ('PYTHONPATH', 'PYTHONHOME', 'TESSDATA_PREFIX',
                'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
        environment.pop(var, None)
    windir = Path(os.environ.get('SystemRoot', r'C:\Windows'))
    environment['PATH'] = str(windir / 'System32') + os.pathsep + str(windir)
    with tempfile.TemporaryDirectory(prefix='yomu-installed-smoke-') as folder:
        marker = Path(folder) / 'result.json'
        args = [str(executable), '--yomu-bundle-smoke', str(marker)]
        try:
            result = subprocess.run(args, cwd=distribution, env=environment,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=40, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('Frozen EXE did not exit within 40 seconds; check for a startup error dialog') from exc
        if result.returncode != 0 or not marker.is_file():
            failure = marker.with_name(marker.name + '.error.txt')
            traceback_text = failure.read_text(encoding='utf-8', errors='replace') if failure.is_file() else ''
            raise RuntimeError(f'Frozen EXE startup check failed with exit code {result.returncode}:\n{traceback_text}')
        payload = json.loads(marker.read_text(encoding='utf-8'))
        if payload.get('status') != 'ok' or not payload.get('sqlite_version'):
            raise RuntimeError(f'Frozen EXE returned invalid probe status: {payload}')
        return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, required=True, help='PyInstaller directory OR installed app directory')
    parser.add_argument('--fix-sqlite', action='store_true', help='Only when building: restore Python interpreter sqlite3.dll')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Windows-specific DLL verification must run on Windows')
    distribution = args.dist.resolve()
    try:
        if args.fix_sqlite:
            restore_matching_python_sqlite(distribution, Path(sys.base_prefix))
        else:
            if not (distribution / '_internal' / 'sqlite3.dll').is_file():
                raise RuntimeError('Packaged sqlite3.dll is missing')
        result = smoke_test(distribution)
    except (OSError, ValueError, RuntimeError) as error:
        print(f'WINDOWS FROZEN RUNTIME CHECK FAILED: {error}', file=sys.stderr)
        return 1
    print(f"FROZEN EXE OK: SQLite {result['sqlite_version']}; MainWindow imported", flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
