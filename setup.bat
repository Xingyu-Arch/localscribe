@echo off
setlocal
cd /d "%~dp0"

set "AUTO="
set "WANTGPU="
set "DENYGPU="

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="/auto" set "AUTO=1"
if /i "%~1"=="/gpu" set "WANTGPU=1"
if /i "%~1"=="/cpu" set "DENYGPU=1"
if /i "%~1"=="/?" goto usage
shift
goto parse

:parsed
echo ==========================================
echo   localscribe setup
echo ==========================================
echo.
echo New here? Open README-FIRST.txt for step-by-step instructions.
echo.

set "PY="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY=py -3.12"
)
if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PY=py -3"
    )
)
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto nopython

%PY% -c "import sys" >nul 2>nul
if errorlevel 1 goto nopython
%PY% -c "import sys; sys.exit(0 if (3, 9) <= sys.version_info[:2] <= (3, 12) else 3)" >nul 2>nul
if errorlevel 3 goto newpython

echo [0/4] Checking VC++ runtime ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='C:\Windows\System32\msvcp140.dll'; if(Test-Path $p){$v=[version](Get-Item $p).VersionInfo.FileVersion; if($v -lt [version]'14.40'){exit 3}else{exit 0}}else{exit 4}" >nul 2>nul
if errorlevel 4 goto novc
if errorlevel 3 goto oldvc
goto vcok

:novc
echo [WARN] msvcp140.dll not found. If transcription crashes, install:
echo        https://aka.ms/vs/17/release/vc_redist.x64.exe
goto vcok

:oldvc
echo [WARN] Your VC++ runtime is older than 14.40.
echo        The pinned versions in this release still work.
echo        Newer ctranslate2/onnxruntime would crash. Recommended:
echo        https://aka.ms/vs/17/release/vc_redist.x64.exe
goto vcok

:vcok
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment .venv ...
    %PY% -m venv .venv
    if errorlevel 1 goto fail
) else (
    echo [1/4] Virtual environment already exists, skipping.
)
set "VPY=.venv\Scripts\python.exe"

"%VPY%" -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Existing .venv is broken or uses an unsupported Python.
    echo         Delete the .venv folder, then run setup.bat again.
    goto fail
)
"%VPY%" -c "import sys; sys.exit(0 if (3, 9) <= sys.version_info[:2] <= (3, 12) else 3)" >nul 2>nul
if errorlevel 3 (
    echo [ERROR] Existing .venv uses an unsupported Python version.
    echo         Delete the .venv folder, then run setup.bat again.
    goto fail
)

echo [2/4] Installing Python dependencies (Tsinghua mirror, about 50-100 MB) ...
"%VPY%" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto fail
"%VPY%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto fail

if defined DENYGPU goto nogpu
if defined WANTGPU goto wantgpu

set "HASGPU="
where nvidia-smi >nul 2>nul
if not errorlevel 1 set "HASGPU=1"
if not defined HASGPU goto nogpu
if defined AUTO goto nogpu

echo.
echo [3/4] NVIDIA GPU detected.
echo       GPU libraries are about 1.3 GB and make transcription much faster.
set "GPUANS="
set /p GPUANS=Install GPU libraries now? [y/N]:
if /i not "%GPUANS%"=="y" goto nogpu
goto installgpu

:wantgpu
set "HASGPU="
where nvidia-smi >nul 2>nul
if not errorlevel 1 set "HASGPU=1"
if not defined HASGPU echo [WARN] nvidia-smi not found, installing GPU libraries anyway.

:installgpu
echo [3/4] Installing GPU libraries (about 1.3 GB) ...
"%VPY%" -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 echo [WARN] GPU library install failed. The tool will fall back to CPU.
goto done

:nogpu
echo [3/4] Using CPU mode. It still works, just slower.
goto done

:nopython
echo [ERROR] Python not found.
echo Install Python 3.12 (64-bit) from https://www.python.org/downloads/
echo IMPORTANT: check "Add python.exe to PATH" during installation.
echo Then run setup.bat again.
echo.
if not defined AUTO pause
exit /b 1

:newpython
echo [ERROR] Unsupported Python version.
echo This version of localscribe pins ctranslate2 4.5.0, which has Windows
echo wheels only up to Python 3.12.
echo Please install Python 3.12 (64-bit): https://www.python.org/downloads/
echo Then delete the .venv folder (if any) and run setup.bat again.
echo.
if not defined AUTO pause
exit /b 1

:fail
echo.
echo [ERROR] Setup failed. Please screenshot the messages above.
echo.
if not defined AUTO pause
exit /b 1

:usage
echo Usage: setup.bat [ /auto ] [ /gpu ^| /cpu ]
echo.
echo   /auto   Run without prompts (no GPU question, no final pause)
echo   /gpu    Install GPU libraries without asking (about 1.3 GB)
echo   /cpu    Skip GPU libraries without asking
exit /b 0

:done
echo.
echo Setup complete.
echo Usage: drag one or more video/audio files onto run.bat, or run:
echo   .venv\Scripts\python localscribe.py video.mp4
echo Check environment:
echo   .venv\Scripts\python localscribe.py --doctor
echo.
if not defined AUTO pause
exit /b 0