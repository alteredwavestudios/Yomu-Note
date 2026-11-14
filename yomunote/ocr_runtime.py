"""Locate Yomu Note's *offline* Tesseract engine and its training data.

Keep OCR discovery separate from the Qt UI, source rendering and persistence.
PyInstaller's macOS bundle has different locations for executables and data;
search only app-owned locations before considering an existing system install.
No downloads or environment-wide changes happen while Yomu Note runs.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys


def _engine_filename() -> str:
    """Return the native executable name for the current operating system."""
    return 'tesseract.exe' if os.name == 'nt' else 'tesseract'


def _bundle_roots() -> tuple[Path, ...]:
    """Possible app-owned OCR directories (no arbitrary working-directory lookup)."""
    if getattr(sys, 'frozen', False):
        roots = []
        base = getattr(sys, '_MEIPASS', None)
        if base:
            base = Path(base)
            roots.extend((base / 'ocr', base / '_internal' / 'ocr'))
        executable = Path(sys.executable).absolute()
        roots.extend((executable.parent / 'ocr', executable.parent / '_internal' / 'ocr'))
        # Finder launches from Contents/MacOS; PyInstaller 6 commonly locates
        # collected binaries in Contents/Frameworks and data in Resources.
        if sys.platform == 'darwin':
            contents = executable.parent.parent
            if contents.name == 'Contents':
                roots.extend((contents / 'Frameworks' / 'ocr',
                              contents / 'Resources' / 'ocr',
                              contents / 'MacOS' / 'ocr'))
        return tuple(dict.fromkeys(roots))
    platform = 'windows' if os.name == 'nt' else 'macos' if sys.platform == 'darwin' else 'linux'
    return (Path(__file__).resolve().parents[1] / 'vendor' / 'ocr' / platform,)


def _valid_engine(root: Path) -> bool:
    """Require BOTH the Tesseract program and its local model directory.

    A bundle without ``eng.traineddata`` can launch but cannot recognise text;
    checking the pair catches that common packaging mistake early.
    """
    candidate = root / _engine_filename()
    return candidate.is_file() and any(
        (place / 'tessdata' / 'eng.traineddata').is_file()
        for place in _bundle_roots())


def _bundled_language_data(executable: str | os.PathLike[str]) -> Path | None:
    """Return data only for an executable from this application's OCR bundle.

    On macOS, PyInstaller may split binaries and data between Frameworks and
    Resources; the candidate roots refer to the same application bundle.
    """
    try:
        binary = Path(executable).resolve(strict=True)
    except (OSError, ValueError):
        return None
    roots = _bundle_roots()
    if not any((root / _engine_filename()).is_file() and
               (root / _engine_filename()).resolve() == binary for root in roots):
        return None
    for root in roots:
        data = root / 'tessdata'
        if (data / 'eng.traineddata').is_file():
            return data
    return None


def tesseract_data_args(executable: str | os.PathLike[str]) -> list[str]:
    """Pin language data to our private bundle without modifying global PATH."""
    directory = _bundled_language_data(executable)
    return ['--tessdata-dir', str(directory)] if directory else []


def find_tesseract() -> str | None:
    """Prefer a complete bundled OCR engine, then a pre-existing system one."""
    for root in _bundle_roots():
        if _valid_engine(root):
            return str(root / _engine_filename())
    installed = shutil.which('tesseract')
    if installed:
        return installed
    if os.name == 'nt':
        bases = (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'),
                 os.environ.get('LOCALAPPDATA'))
        for base in filter(None, bases):
            for sub in ('Tesseract-OCR/tesseract.exe', 'Programs/Tesseract-OCR/tesseract.exe'):
                path = Path(base) / sub
                if path.is_file():
                    return str(path)
    return None
