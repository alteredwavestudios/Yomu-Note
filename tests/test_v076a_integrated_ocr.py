"""Integrated OCR packaging tests; no native Qt, Windows, or Mac needed."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest import mock

from yomunote import ocr_engine, ocr_runtime
from ocr_packaging.prepare_ocr import stage_ocr, find_source_binary
from ocr_packaging.verify_ocr_bundle import verify_bundle


def test_frozen_app_prefers_own_ocr_and_own_language_data():
    with TemporaryDirectory() as temp:
        base = Path(temp)
        ocr = base / 'ocr'
        (ocr / 'tessdata').mkdir(parents=True)
        exe = ocr / 'tesseract'
        exe.write_text('fake-native-exe')
        (ocr / 'tessdata' / 'eng.traineddata').write_bytes(b'fake-lang-data')
        with mock.patch.object(sys, 'frozen', True, create=True), \
             mock.patch.object(sys, '_MEIPASS', str(base), create=True), \
             mock.patch.object(ocr_runtime, '_engine_filename', return_value='tesseract'), \
             mock.patch.object(ocr_runtime.shutil, 'which', return_value='/usr/bin/tesseract'):
            found = ocr_runtime.find_tesseract()
            assert found == str(exe)
            assert ocr_runtime.tesseract_data_args(found) == ['--tessdata-dir', str(ocr / 'tessdata')]


def test_mac_framework_binary_and_resource_data_are_compatible():
    with TemporaryDirectory() as temp:
        contents = Path(temp) / 'Yomu Note.app' / 'Contents'
        binary_dir = contents / 'Frameworks' / 'ocr'
        data_dir = contents / 'Resources' / 'ocr' / 'tessdata'
        binary_dir.mkdir(parents=True)
        data_dir.mkdir(parents=True)
        (binary_dir / 'tesseract').write_bytes(b'executable')
        (data_dir / 'eng.traineddata').write_bytes(b'language')
        with mock.patch.object(sys, 'frozen', True, create=True), \
             mock.patch.object(sys, 'platform', 'darwin'), \
             mock.patch.object(ocr_runtime, '_engine_filename', return_value='tesseract'), \
             mock.patch.object(sys, 'executable', str(contents / 'MacOS' / 'Yomu Note')), \
             mock.patch.object(sys, '_MEIPASS', str(contents / 'Frameworks'), create=True):
            assert ocr_runtime.find_tesseract() == str(binary_dir / 'tesseract')
            assert ocr_runtime.tesseract_data_args(str(binary_dir / 'tesseract')) == [
                '--tessdata-dir', str(data_dir)]


def test_language_listing_pins_bundled_data_without_global_env_change():
    with mock.patch.object(ocr_engine, 'tesseract_data_args', return_value=['--tessdata-dir', '/app/ocr/tessdata']), \
         mock.patch.object(ocr_engine.subprocess, 'run') as runner:
        runner.return_value.returncode = 0
        runner.return_value.stdout = 'List of available languages (2):\neng\nosd\n'
        runner.return_value.stderr = ''
        assert ocr_engine.installed_languages('/app/ocr/tesseract') == ['eng', 'osd']
        assert runner.call_args.args[0] == [
            '/app/ocr/tesseract', '--list-langs', '--tessdata-dir', '/app/ocr/tessdata']


def test_packager_stages_english_without_all_other_language_models():
    with TemporaryDirectory() as temp:
        base = Path(temp)
        home = base / 'opt'
        bin_dir = home / 'bin'
        data = home / 'share' / 'tessdata'
        bin_dir.mkdir(parents=True)
        data.mkdir(parents=True)
        (bin_dir / 'tesseract').write_bytes(b'fake-binary')
        (data / 'eng.traineddata').write_bytes(b'eng')
        (data / 'osd.traineddata').write_bytes(b'osd')
        (data / 'fra.traineddata').write_bytes(b'fr')
        output = base / 'stage' / 'ocr'
        result = stage_ocr('macos', output, str(bin_dir / 'tesseract'))
        assert (output / 'tesseract').read_bytes() == b'fake-binary'
        assert (output / 'tessdata' / 'eng.traineddata').read_bytes() == b'eng'
        assert (output / 'tessdata' / 'osd.traineddata').read_bytes() == b'osd'
        assert not (output / 'tessdata' / 'fra.traineddata').exists()
        assert 'tesseract' in result['files_sha256']
        assert (output / 'TESSERACT_APACHE_2.0.txt').is_file()
        assert (output / 'THIRD_PARTY_OCR_NOTICES.txt').is_file()


def test_windows_builder_copies_dependent_dlls_and_language_data():
    with TemporaryDirectory() as temp:
        base = Path(temp)
        binary_dir = base / 'installed'
        (binary_dir / 'tessdata').mkdir(parents=True)
        (binary_dir / 'tesseract.exe').write_bytes(b'exe')
        (binary_dir / 'liblept-5.dll').write_bytes(b'dll')
        (binary_dir / 'tessdata' / 'eng.traineddata').write_bytes(b'eng')
        output = base / 'stage' / 'ocr'
        stage_ocr('windows', output, str(binary_dir))
        assert (output / 'tesseract.exe').is_file()
        assert (output / 'liblept-5.dll').is_file()
        assert (output / 'tessdata' / 'eng.traineddata').is_file()


def test_missing_english_is_a_build_failure():
    with TemporaryDirectory() as temp:
        binary = Path(temp) / 'tesseract'
        binary.write_bytes(b'exe')
        try:
            stage_ocr('macos', Path(temp) / 'out', str(binary))
        except FileNotFoundError as error:
            assert 'eng.traineddata' in str(error)
        else:
            raise AssertionError('Must fail closed when English language data is missing')


def test_postbuild_verifier_checks_independent_ocr_runtime():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        bundle = root / 'Yomu Note'
        binary = bundle / '_internal' / 'ocr' / 'tesseract.exe'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b'exe')
        model = binary.parent / 'tessdata' / 'eng.traineddata'
        model.parent.mkdir()
        model.write_bytes(b'eng')
        with mock.patch('ocr_packaging.verify_ocr_bundle.subprocess.run') as run:
            run.return_value.returncode = 0
            run.side_effect = [
                subprocess.CompletedProcess([], 0, 'List of available languages:\neng\n', ''),
                subprocess.CompletedProcess([], 0, 'YOMU NOTE OCR\n', '')]

            assert verify_bundle(bundle, 'windows') == binary
            argv = run.call_args_list[0].args[0]
            assert argv[:2] == [str(binary), '--list-langs']
            assert '--tessdata-dir' in argv
            assert '/tesseract-ocr' not in run.call_args.kwargs['env']['PATH'].lower()


def test_explicit_mac_source_cannot_borrow_homebrew_language_data():
    # On GitHub macOS runners Homebrew has an unrelated real English model.
    # Explicit source fixtures must not acquire that model accidentally.
    with TemporaryDirectory() as temp:
        base = Path(temp)
        binary = base / 'custom' / 'bin' / 'tesseract'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b'fake-exe')
        with mock.patch('ocr_packaging.prepare_ocr.shutil.which', return_value='/opt/homebrew/bin/brew'), \
             mock.patch('ocr_packaging.prepare_ocr.subprocess.run',
                        return_value=subprocess.CompletedProcess([], 0, '/opt/homebrew/opt/tesseract\n', '')):
            try:
                stage_ocr('macos', base / 'out', str(binary))
            except FileNotFoundError as error:
                assert 'eng.traineddata' in str(error)
            else:
                raise AssertionError('Explicit Tesseract source must not borrow system language models')


def test_linux_ocr_verifier_uses_private_libraries_and_system_ldd():
    import os
    with TemporaryDirectory() as temp:
        bundle = Path(temp) / 'Yomu Note'
        ocr = bundle / '_internal' / 'ocr'
        ocr.mkdir(parents=True)
        binary = ocr / 'tesseract'
        binary.write_bytes(b'exe')
        binary.chmod(0o755)
        data = ocr / 'tessdata'
        data.mkdir()
        (data / 'eng.traineddata').write_bytes(b'eng')
        lib = bundle / '_internal' / 'libtesseract.so.5'
        lept = bundle / '_internal' / 'liblept.so.5'
        lib.write_bytes(b'fake')
        lept.write_bytes(b'fake')
        calls = []

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            if argv[0] == 'ldd':
                return subprocess.CompletedProcess(argv, 0,
                    f'libtesseract.so.5 => {lib} (0x123)\n'
                    f'liblept.so.5 => {lept} (0x456)\n', '')
            if '--list-langs' in argv:
                return subprocess.CompletedProcess(argv, 0, 'List of languages:\neng\n', '')
            return subprocess.CompletedProcess(argv, 0, 'YOMU NOTE OCR\n', '')

        with mock.patch('ocr_packaging.verify_ocr_bundle.subprocess.run', side_effect=fake_run):
            assert verify_bundle(bundle, 'linux') == binary
        environment = calls[0][1]['env']
        assert environment['PATH'] == '/usr/bin:/bin'
        assert environment['LD_LIBRARY_PATH'].split(os.pathsep) == [str(bundle / '_internal'), str(ocr)]
        assert calls[2][0] == ['ldd', str(binary)]

        # A host-side Tesseract library must still invalidate the package.
        def host_link(argv, **kwargs):
            if argv[0] == 'ldd':
                return subprocess.CompletedProcess(argv, 0,
                    'libtesseract.so.5 => /usr/lib/libtesseract.so.5 (0x123)\n', '')
            if '--list-langs' in argv:
                return subprocess.CompletedProcess(argv, 0, 'eng\n', '')
            return subprocess.CompletedProcess(argv, 0, 'YOMU NOTE OCR\n', '')
        with mock.patch('ocr_packaging.verify_ocr_bundle.subprocess.run', side_effect=host_link):
            try:
                verify_bundle(bundle, 'linux')
            except RuntimeError as error:
                assert 'outside the app' in str(error)
            else:
                raise AssertionError('Verifier must reject a host-side libtesseract')


def test_existing_ocr_core_processing_and_cancellation_unchanged():
    source = Path(ocr_engine.__file__).read_text(encoding='utf-8')
    assert 'process.communicate(timeout=.15)' in source
    assert 'process.kill()' in source
    assert 'MAX_REGION_PIXELS' in source
    assert "*tesseract_data_args(executable)" in source


def test_native_scripts_fail_closed_and_installer_includes_everything():
    root = Path(__file__).resolve().parents[1]
    win = (root / 'build-windows.ps1').read_text()
    mac = (root / 'build-mac.command').read_text()
    iss = (root / 'YomuNote_v050_Installer.iss').read_text()
    assert 'prepare_ocr.py' in win and 'verify_ocr_bundle.py' in win
    assert 'prepare_ocr.py' in mac and 'verify_ocr_bundle.py' in mac
    assert '--add-binary' in win and '--add-binary' in mac
    assert 'recursesubdirs' in iss
    assert 'Program Files\\Tesseract-OCR' not in (root / 'yomunote/window.py').read_text()
