"""Prevent a silent mismatch between v0.8.2 binaries and their release metadata."""
from pathlib import Path

from yomunote import __version__

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_version_and_windows_upgrade_id():
    assert __version__ == '0.8.2'
    iss = read('YomuNote_v050_Installer.iss')
    assert '#define MyAppVersion "0.8.2"' in iss
    assert 'VersionInfoVersion=0.8.2.0' in iss
    assert 'OutputBaseFilename=YomuNote_Setup_v0.8.2' in iss
    # Preserve the stable Inno Setup AppId so upgrades use the same installation.
    assert 'AppId={{974AD665-3F47-4CC5-9AAE-0A5F43565469}' in iss
    assert 'YomuNote_Setup_v0.8.2.exe' in read('build-installer-windows.ps1')


def test_release_asset_names_agree_with_builders():
    workflow = read('.github/workflows/release.yml')
    for name in (
        'YomuNote_Setup_v0.8.2.exe',
        'YomuNote-0.8.2-macOS-arm64-unsigned.dmg',
        'YomuNote-0.8.2-macOS-x86_64-unsigned.dmg',
    ):
        assert name in workflow
    assert '--draft --prerelease' in workflow
    assert '--notes-file RELEASE_NOTES_v0.8.2.md' in workflow
    assert 'needs: [windows, macos]' in workflow
    assert 'version="0.8.2"' in read('scripts/package-macos-dmg.sh')
    assert 'YomuNote_Setup_v0.8.2.exe' in read('RELEASE_NOTES_v0.8.2.md')


def test_readme_keeps_existing_published_installer_live_until_new_one_is_published():
    readme = read('README.md')
    assert 'v0.8.1b-rc4' in readme
    assert 'v0.8.2' in readme
    assert 'Reading View Memory' in readme
    assert 'docs/screenshots/01-interface.png' in readme
    assert 'docs/screenshots/02-ocr.png' in readme
    assert 'docs/screenshots/03-reading-progress.png' in readme
