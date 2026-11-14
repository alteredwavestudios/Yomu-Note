# Yomu Note v0.8.1b - Windows standalone bundle with PRIVATE offline OCR.
# Tesseract must be installed on this BUILD computer only, NOT on user PCs.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Run run-windows.bat first to create .venv.'
}
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    & uv pip install --python $python 'pyinstaller>=6.22.3,<7'
} else {
    & $python -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Could not bootstrap pip' }
    & $python -m pip install 'pyinstaller>=6.22.3,<7'
}
if ($LASTEXITCODE -ne 0) { throw 'Could not install PyInstaller' }
try {
    & $python fetch_fonts.py
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Optional font download unavailable; using system fallbacks' }
} catch { Write-Warning "Font setup skipped: $_" }

# Staging is under .build so the source ZIP contains no platform-specific
# binaries. The released app/installer MUST contain these runtime files.
$stage = Join-Path $PSScriptRoot '.build\ocr'
& $python ocr_packaging\prepare_ocr.py --target windows --output $stage
if ($LASTEXITCODE -ne 0) {
    throw 'OCR preparation failed. On the build computer only: winget install UB-Mannheim.TesseractOCR'
}
$exe = Join-Path $stage 'tesseract.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'Staging did not produce tesseract.exe' }
$pyiArgs = @('--noconfirm', '--clean', '--windowed', '--onedir',
    '--name', 'Yomu Note', '--icon', 'assets/icon.ico',
    '--add-data', 'assets;assets',
    '--add-data', 'LICENSE;.',
    '--add-data', 'THIRD_PARTY_NOTICES.md;.',
    '--add-binary', "$exe;ocr", 
    '--add-data', "$(Join-Path $stage 'tessdata');ocr/tessdata")
foreach ($dll in Get-ChildItem -LiteralPath $stage -File -Filter '*.dll') {
    $pyiArgs += @('--add-binary', "$($dll.FullName);ocr")
}
foreach ($file in Get-ChildItem -LiteralPath $stage -File | Where-Object { $_.Extension -in @('.txt', '.json', '.license', '.licence') }) {
    $pyiArgs += @('--add-data', "$($file.FullName);ocr")
}
$pyiArgs += 'main.py'
& $python -m PyInstaller @pyiArgs
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
# Restore CPython's SQLite DLL if OCR's copy was chosen, then launch
# the frozen EXE itself before making an installer.
& $python scripts\verify_windows_frozen.py --dist (Join-Path $PSScriptRoot 'dist\Yomu Note') --fix-sqlite
if ($LASTEXITCODE -ne 0) { throw 'Frozen app startup check failed; refuse to package' }
& $python ocr_packaging\verify_ocr_bundle.py --target windows --dist (Join-Path $PSScriptRoot 'dist\Yomu Note')
if ($LASTEXITCODE -ne 0) { throw 'OCR verification failed. Do not distribute this build.' }
Write-Host 'Finished! Offline OCR is bundled in dist\Yomu Note\Yomu Note.exe'
