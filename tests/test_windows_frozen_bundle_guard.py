"""Regression guard for Windows packaged-app startup (not merely source tests)."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_selftest_executes_before_gui_imports():
    source = (ROOT / 'main.py').read_text(encoding='utf-8')
    # The EXE must be able to run a silent SQLite + module import smoke test
    # without creating a MainWindow or touching an existing notebook.
    assert '--yomu-bundle-smoke' in source
    assert "sqlite3.connect(':memory:')" in source
    assert source.index("if __name__ == '__main__' and '--yomu-bundle-smoke'") < source.index('from PySide6.QtGui')
    ast.parse(source)


def test_build_restores_interpreter_sqlite_before_packaging_and_tests_exe():
    build = (ROOT / 'build-windows.ps1').read_text(encoding='utf-8')
    install = (ROOT / 'build-installer-windows.ps1').read_text(encoding='utf-8')
    helper = (ROOT / 'scripts' / 'verify_windows_frozen.py').read_text(encoding='utf-8')
    assert 'verify_windows_frozen.py' in build and '--fix-sqlite' in build
    assert build.index('verify_windows_frozen.py') < build.index('verify_ocr_bundle.py')
    assert 'verify_windows_frozen.py' in install
    assert 'restore_matching_python_sqlite' in helper
    assert "'_sqlite3.pyd'" in helper
    assert "'sqlite3.dll'" in helper
    assert 'subprocess.run(args' in helper
    assert 'timeout=40' in helper
    ast.parse(helper)


def test_repair_chooses_matching_cpython_dll_not_ocr_dll(tmp_path):
    from scripts.verify_windows_frozen import restore_matching_python_sqlite
    runtime = tmp_path / 'python' / 'DLLs'
    runtime.mkdir(parents=True)
    (runtime / '_sqlite3.pyd').write_bytes(b'cpython sqlite extension')
    (runtime / 'sqlite3.dll').write_bytes(b'known good CPython SQLite')
    frozen = tmp_path / 'dist' / '_internal'
    frozen.mkdir(parents=True)
    (frozen / '_sqlite3.pyd').write_bytes(b'cpython sqlite extension')
    (frozen / 'sqlite3.dll').write_bytes(b'older conflicting OCR SQLite')
    (frozen / 'ocr').mkdir()
    (frozen / 'ocr' / 'sqlite3.dll').write_bytes(b'OCR DLL must be preserved')

    restore_matching_python_sqlite(tmp_path / 'dist', tmp_path / 'python')
    assert (frozen / 'sqlite3.dll').read_bytes() == b'known good CPython SQLite'
    assert (frozen / 'ocr' / 'sqlite3.dll').read_bytes() == b'OCR DLL must be preserved'
    # Repeating the operation must be harmless.
    restore_matching_python_sqlite(tmp_path / 'dist', tmp_path / 'python')


def test_repair_rejects_mismatched_sqlite_extension(tmp_path):
    import pytest
    from scripts.verify_windows_frozen import restore_matching_python_sqlite
    runtime = tmp_path / 'python' / 'DLLs'
    runtime.mkdir(parents=True)
    (runtime / '_sqlite3.pyd').write_bytes(b'expected extension')
    (runtime / 'sqlite3.dll').write_bytes(b'expected dll')
    frozen = tmp_path / 'dist' / '_internal'
    frozen.mkdir(parents=True)
    (frozen / '_sqlite3.pyd').write_bytes(b'wrong extension')
    (frozen / 'sqlite3.dll').write_bytes(b'old dll')
    with pytest.raises(RuntimeError, match='does not match'):
        restore_matching_python_sqlite(tmp_path / 'dist', tmp_path / 'python')
    assert (frozen / 'sqlite3.dll').read_bytes() == b'old dll'
