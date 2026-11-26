@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Environment not found. Please run setup.bat first.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" localscribe.py --doctor
set "RC=%ERRORLEVEL%"
echo.
pause
exit /b %RC%