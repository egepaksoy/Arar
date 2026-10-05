@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "ARAR_LAUNCH_PYTHON="
set "ARAR_LAUNCH_FLAG="
if defined ARAR_PYTHON (
    call :try_python "%ARAR_PYTHON%"
    if defined ARAR_LAUNCH_PYTHON goto run
    echo ARAR_PYTHON uyumlu degil. Tkinter iceren CPython 3.12.x gerekli.
    goto failed
)
call :try_python "%~dp0.venv\Scripts\python.exe"
if defined ARAR_LAUNCH_PYTHON goto run
call :try_python "py" "-3.12"
if defined ARAR_LAUNCH_PYTHON goto run
call :try_python "python"
if defined ARAR_LAUNCH_PYTHON goto run
call :try_python "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if defined ARAR_LAUNCH_PYTHON goto run
echo Tkinter iceren CPython 3.12.x bulunamadi. README_OFFLINE.md dosyasini okuyun.
goto failed

:try_python
"%~1" %~2 -c "import sys, tkinter; sys.exit(0 if sys.implementation.name == 'cpython' and sys.version_info[:2] == (3,12) else 1)" >nul 2>nul
if errorlevel 1 exit /b 1
set "ARAR_LAUNCH_PYTHON=%~1"
set "ARAR_LAUNCH_FLAG=%~2"
exit /b 0

:run
"%ARAR_LAUNCH_PYTHON%" %ARAR_LAUNCH_FLAG% -X utf8 -B "%~dp0prepare_local_libs.py" --launch %*
set "ARAR_LAUNCH_EXIT=%errorlevel%"
if "%ARAR_LAUNCH_EXIT%"=="0" exit /b 0
echo Baslatma tamamlanamadi. Yukaridaki hata bilgisini kontrol edin.
if not defined ARAR_NO_PAUSE pause
exit /b %ARAR_LAUNCH_EXIT%

:failed
if not defined ARAR_NO_PAUSE pause
exit /b 1
