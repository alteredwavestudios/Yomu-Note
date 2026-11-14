#!/usr/bin/env python3
"""Run every Yomu Note test module in a separate, time-limited Python process.

Why this exists:
* One invisible Qt dialog can hang ordinary pytest for hours.
* MainWindow's Windows QSettings normally reads your registry/recent notebooks.
* Independent processes let us finish the audit and retain every failure.

Use from the extracted Yomu-Note repository root:
    python YomuNote-Full-Test-Audit.py

The script only creates temporary test state and a ZIP of test logs.
It does not edit application code, existing notebooks, or Git metadata.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import zipfile


def worker(test_file: str, settings_root: str) -> int:
    """Set up isolated user preferences before importing ANY test module."""
    import pytest
    import pathlib

    home = Path(settings_root) / 'home'
    home.mkdir(parents=True, exist_ok=True)
    # Be explicit even on Windows where the registry ignores HOME/XDG paths.
    pathlib.Path.home = classmethod(lambda cls: home)

    test_source = Path(test_file).read_text(encoding='utf-8')
    uses_qt = ('PySide6' in test_source or 'MainWindow' in test_source
               or 'yomunote.window' in test_source)
    if uses_qt:
        try:
            from PySide6.QtCore import QSettings
        except ImportError:
            pass  # pytest.importorskip in the module will report the skip.
        else:
            cfg = Path(settings_root) / 'qt-settings'
            cfg.mkdir(parents=True, exist_ok=True)
            QSettings.setDefaultFormat(QSettings.Format.IniFormat)
            QSettings.setPath(QSettings.Format.IniFormat,
                              QSettings.Scope.UserScope, str(cfg))
            # Explicitly redirect the two-argument constructors in MainWindow.
            # Otherwise Windows may use registry-backed settings even when
            # HOME/XDG_CONFIG_HOME are set to a temporary location.
            from yomunote import window as window_module
            original_settings = QSettings

            def safe_settings(*args, **kwargs):
                if (len(args) == 2 and not kwargs
                        and all(isinstance(a, str) for a in args)):
                    filename = '--'.join(re.sub(r'[^A-Za-z0-9_-]', '_', a)
                                         for a in args) + '.ini'
                    return original_settings(str(cfg / filename),
                                             original_settings.Format.IniFormat)
                return original_settings(*args, **kwargs)

            window_module.QSettings = safe_settings

    diagnostics_after = os.environ.get('YOMU_TEST_FAULTHANDLER_SECONDS', '60')
    return int(pytest.main(['-q', '--tb=short', '-ra',
                            '-o', f'faulthandler_timeout={diagnostics_after}',
                            test_file]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--per-file-timeout', type=int, default=90,
                        help='Seconds before killing one hung test file (default 90).')
    parser.add_argument('--match', default='', help='Only filenames containing this string.')
    parser.add_argument('--max-files', type=int, default=0,
                        help='Limit number of files (for a quick smoke test).')
    parser.add_argument('--worker', nargs=2, metavar=('TEST_FILE', 'CONFIG_DIR'),
                        help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(*args.worker)

    root = Path.cwd()
    if not (root / 'tests').is_dir() or not (root / 'yomunote').is_dir():
        print('ERROR: Open PowerShell inside the Yomu-Note source folder first.')
        return 2
    if args.per_file_timeout < 10:
        print('ERROR: Use a timeout of at least 10 seconds.')
        return 2
    tests = sorted((root / 'tests').glob('test_*.py'))
    if args.match:
        tests = [p for p in tests if args.match.lower() in p.name.lower()]
    if args.max_files:
        tests = tests[:args.max_files]
    if not tests:
        print('No matching test files.')
        return 2

    startstamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    output = root / f'YomuNote-Test-Audit-{startstamp}.zip'
    summary = []
    results = []
    failures = 0
    print(f'Yomu Note test audit | {len(tests)} test files | {args.per_file_timeout}s cap per file', flush=True)
    print('All tests run with disposable HOME/USERPROFILE and isolated Qt preferences.', flush=True)
    print('A HANG in one file will not prevent other files being tested.\n', flush=True)
    started = time.monotonic()
    interrupted = False
    with tempfile.TemporaryDirectory(prefix='yomu-test-audit-') as scratch:
        scratch = Path(scratch)
        log_dir = scratch / 'logs'
        log_dir.mkdir()
        for i, test_path in enumerate(tests, start=1):
            label = str(test_path.relative_to(root)).replace('\\', '/')
            cfg = scratch / 'state' / test_path.stem
            cfg.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env.update({'HOME': str(cfg / 'home'),
                        'USERPROFILE': str(cfg / 'home'),
                        'XDG_CONFIG_HOME': str(cfg / 'config'),
                        'XDG_DATA_HOME': str(cfg / 'data'),
                        'APPDATA': str(cfg / 'appdata'),
                        'LOCALAPPDATA': str(cfg / 'localappdata'),
                        'QT_QPA_PLATFORM': 'offscreen',
                        'PYTHONUTF8': '1',
                        'PYTHONIOENCODING': 'utf-8',
                        'YOMU_TEST_FAULTHANDLER_SECONDS': str(
                            min(60, max(10, args.per_file_timeout - 15)))})
            for key in ('home', 'config', 'data', 'appdata', 'localappdata'):
                (cfg / key).mkdir(parents=True, exist_ok=True)
            logfile = log_dir / f'{test_path.stem}.txt'
            cmd = [sys.executable, str(Path(__file__).resolve()),
                   '--worker', label, str(cfg)]
            t0 = time.monotonic()
            try:
                with logfile.open('w', encoding='utf-8', errors='replace') as stream:
                    proc = subprocess.run(cmd, cwd=str(root), env=env,
                                          stdin=subprocess.DEVNULL,
                                          stdout=stream, stderr=subprocess.STDOUT,
                                          timeout=args.per_file_timeout, check=False)
                exit_code = proc.returncode
                if exit_code == 0:
                    status = 'PASS'
                elif exit_code == 5 and 'skipped' in logfile.read_text(
                        encoding='utf-8', errors='replace').lower():
                    status = 'SKIP'
                else:
                    status = 'FAIL'
            except subprocess.TimeoutExpired:
                exit_code = 124
                status = 'HANG'
                with logfile.open('a', encoding='utf-8') as stream:
                    stream.write(f'\nAUDIT WATCHDOG: test module exceeded {args.per_file_timeout} seconds.\n')
            except KeyboardInterrupt:
                interrupted = True
                print('\nInterrupted; packaging all results collected so far.', flush=True)
                break
            elapsed = time.monotonic() - t0
            if status in ('FAIL', 'HANG'):
                failures += 1
            results.append((label, status, elapsed, exit_code, logfile))
            print(f'[{i:3d}/{len(tests)}] {status:4s} {elapsed:6.1f}s  {label}', flush=True)

        total = time.monotonic() - started
        summary.extend([
            'YOMU NOTE FULL TEST AUDIT',
            f'Timestamp: {startstamp}',
            f'Python: {sys.version}',
            f'Test modules scheduled: {len(tests)}',
            f'Test modules completed: {len(results)}',
            f'FAIL/HANG modules: {failures}',
            f'Total runtime: {total:.1f} seconds',
            f'Interrupted: {interrupted}',
            '', 'MODULE RESULTS',
        ])
        for label, status, elapsed, rc, _ in results:
            summary.append(f'{status:4s}  {elapsed:7.1f}s  exit={rc:4d}  {label}')
        summary.append('')
        summary.append('Note: each module runs in a separate Python process. '
                       'This isolates Qt state and identifies hangs, but does NOT '
                       'replace a final integrated suite run or interactive app testing.')
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('SUMMARY.txt', '\n'.join(summary) + '\n')
            for _, _, _, _, log in results:
                z.write(log, f'logs/{log.name}')
    print(f'\nAudit complete: {len(results)} modules, {failures} failing/hung modules, {total:.0f}s.', flush=True)
    print(f'UPLOAD THIS ZIP: {output}', flush=True)
    return 1 if failures or interrupted else 0


if __name__ == '__main__':
    raise SystemExit(main())
