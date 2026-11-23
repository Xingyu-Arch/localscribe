@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo   localscribe setup
echo ==========================================
echo.

set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto nopython

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment .venv ...
    %PY% -m venv .venv
    if errorlevel 1 goto fail
) else (
    echo [1/3] Virtual environment already exists, skipping.
)
set "VPY=.venv\Scripts\python.exe"

echo [2/3] Installing dependencies (Tsinghua mirror, about 50-100 MB) ...
"%VPY%" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
"%VPY%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto fail

set "HASGPU="
where nvidia-smi >nul 2>nul
if not errorlevel 1 set "HASGPU=1"
if not defined HASGPU goto nogpu

echo.
echo [3/3] NVIDIA GPU detected. GPU libraries are about 700 MB and make transcription much faster.
set "GPUANS="
set /p GPUANS=Install GPU libraries now? [y/N]:
if /i not "%GPUANS%"=="y" goto nogpu
"%VPY%" -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 echo [WARN] GPU library install failed. The tool will fall back to CPU.
goto done

:nogpu
echo [3/3] Using CPU mode. It still works, just slower.
goto done

:nopython
echo [ERROR] Python not found.
echo Install Python 3.9 or newer from https://www.python.org/downloads/
echo IMPORTANT: check "Add python.exe to PATH" during installation.
echo Then run setup.bat again.
echo.
pause
exit /b 1

:fail
echo.
echo [ERROR] Setup failed. Please screenshot the messages above.
echo.
pause
exit /b 1

:done
echo.
echo Setup complete.
echo Usage: drag a video/audio file onto run.bat, or run:
echo   .venv\Scripts\python localscribe.py video.mp4
echo.
pause
exit /b 0