@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Run environment not found. Please double-click setup.bat first.
    echo.
    pause
    exit /b 1
)

set "QUIET="
set "ARGS="

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="/q" (
    set "QUIET=1"
) else (
    set "ARGS=%ARGS% "%~1""
)
shift
goto parse

:parsed
if not defined ARGS (
    if not defined QUIET (
        if exist "README-FIRST.txt" start "" "README-FIRST.txt"
    )
    echo Usage: drag one or more video/audio files onto run.bat.
    echo Or run: run.bat "video.mp4" "video2.mp3"
    echo Wildcards work too: run.bat "*.mp4"
    echo Add /q to skip the final pause.
    echo.
    if not defined QUIET pause
    exit /b 1
)

".venv\Scripts\python.exe" localscribe.py %ARGS%
set "RC=%ERRORLEVEL%"
echo.
if not defined QUIET pause
exit /b %RC%