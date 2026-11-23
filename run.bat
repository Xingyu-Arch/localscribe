@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Run environment not found. Please double-click setup.bat first.
    echo.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo Usage: drag one video/audio file onto run.bat.
    echo Or run: run.bat "video.mp4"
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" localscribe.py %*
echo.
pause