@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 (echo Install Python from python.org first. & pause & exit /b 1)
)
.venv\Scripts\python.exe -c "import PySide6, pypdfium2, PIL" 2>nul
if errorlevel 1 (
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 (pause & exit /b 1)
)
.venv\Scripts\python.exe main.py
