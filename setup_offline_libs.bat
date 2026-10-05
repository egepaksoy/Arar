@echo off
setlocal
chcp 65001 >nul
rem ARAR_PYTHON can select the compatible preparation interpreter.
if defined ARAR_PYTHON (
    "%ARAR_PYTHON%" "%~dp0prepare_local_libs.py" %*
) else (
    python "%~dp0prepare_local_libs.py" %*
)
exit /b %errorlevel%
