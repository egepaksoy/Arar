@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "main.py"
    exit /b
)
set "ARAR_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%ARAR_PYTHON%" (
    start "" "%ARAR_PYTHON%" "main.py"
    exit /b
)
where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "main.py"
    exit /b
)
echo Python ve yerel kutuphaneler bulunamadi. KULLANIM.md dosyasini okuyun.
pause
