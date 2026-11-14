"""Low-cost tests for the public-preview release's packaging contract.

These tests don't build native applications; the separate platform jobs must
still build and smoke-test their artifacts on real Windows/macOS/Linux hosts.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_readme_screenshots_are_present():
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    for number, name in enumerate(('interface', 'ocr', 'reading-progress', 'tab-exchange'), start=1):
        path = ROOT / f'docs/screenshots/{number:02}-{name}.png'
        assert path.is_file() and path.stat().st_size > 2000
        assert path.relative_to(ROOT).as_posix() in readme


def test_release_process_is_draft_only():
    workflow = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
    assert '--draft --prerelease' in workflow
    assert 'needs: [windows, macos]' in workflow
    assert 'actions/upload-artifact@v4' in workflow
    assert 'YomuNote_Setup_v0.8.1b.exe' in workflow
    assert 'YomuNote-0.8.1b-macOS-arm64-unsigned.dmg' in workflow
    assert 'YomuNote-0.8.1b-macOS-x86_64-unsigned.dmg' in workflow
    assert '\n  linux:\n' not in workflow
    # Linux remains source-only, with its regression suite in CI.
    ci = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
    assert 'ubuntu-22.04' in ci
    assert 'YomuNote-Full-Test-Audit.py' in ci
    assert 'macos-15-intel' in workflow


def test_all_release_builds_stage_local_ocr():
    for filename, target in (
        ('build-windows.ps1', 'windows'),
        ('build-mac.command', 'macos'),
        ('build-linux.sh', 'linux'),
    ):
        script = (ROOT / filename).read_text(encoding='utf-8')
        assert f'--target {target}' in script
        assert 'prepare_ocr.py' in script
        assert 'verify_ocr_bundle.py' in script


def test_linux_staging_uses_existing_local_tesseract(tmp_path):
    if not sys.platform.startswith('linux'):
        return
    from ocr_packaging.prepare_ocr import stage_ocr
    from shutil import which
    if not which('tesseract'):
        return  # source tests on machines without Tesseract are valid
    target = tmp_path / 'ocr'
    report = stage_ocr('linux', target)
    assert report['target'] == 'linux'
    assert (target / 'tesseract').is_file()
    assert (target / 'tessdata' / 'eng.traineddata').is_file()
