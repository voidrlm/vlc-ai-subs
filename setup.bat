@echo off
REM vlc-ai-subs — setup & install (Windows)
REM
REM Usage:
REM   setup.bat              Full setup
REM   setup.bat --install    Only install VLC extension

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%venv"
set "SRC=%SCRIPT_DIR%aisubs.lua"

REM ── Install-only mode ──────────────────────────────────────

if "%~1"=="--install" goto :install_only

REM ── Full setup ─────────────────────────────────────────────

echo.
echo   vlc-ai-subs setup
echo   -----------------
echo.

REM 1. Check Python
echo   Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    python3 --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo   Python 3 is not installed.
        echo   Download it from https://www.python.org/downloads/
        echo   Make sure to check "Add Python to PATH" during install.
        exit /b 1
    )
    set "PYTHON=python3"
) else (
    set "PYTHON=python"
)

for /f "tokens=*" %%i in ('%PYTHON% --version 2^>^&1') do echo   Found %%i

REM 2. Create virtual environment
if not exist "%VENV_DIR%\Scripts\pip.exe" (
    echo   Creating virtual environment...
    %PYTHON% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo   Failed to create venv. Make sure Python 3.8+ is installed.
        exit /b 1
    )
    echo   Virtual environment created.
) else (
    echo   Virtual environment already exists.
)

REM 3. Install faster-whisper
echo   Installing faster-whisper (this may take a few minutes)...
"%VENV_DIR%\Scripts\pip.exe" install --quiet --upgrade pip
"%VENV_DIR%\Scripts\pip.exe" install --quiet faster-whisper
"%VENV_DIR%\Scripts\python.exe" -c "from faster_whisper import WhisperModel; print('  faster-whisper installed!')"
if errorlevel 1 (
    echo   Failed to install faster-whisper.
    exit /b 1
)

REM 4. Install VLC extension
:install_vlc
echo.
echo   Installing VLC extension...
echo.

set "INSTALLED=0"

REM Standard VLC install
set "VLC_DIR=%APPDATA%\vlc\lua\extensions"
if not exist "%VLC_DIR%" mkdir "%VLC_DIR%"
copy /y "%SRC%" "%VLC_DIR%\aisubs.lua" >nul 2>&1
if not errorlevel 1 (
    echo   Installed to %VLC_DIR%
    set "INSTALLED=1"
)

REM VLC Program Files (requires admin for system-wide)
set "VLC_SYS=C:\Program Files\VideoLAN\VLC\lua\extensions"
if exist "C:\Program Files\VideoLAN\VLC" (
    if not exist "%VLC_SYS%" mkdir "%VLC_SYS%" 2>nul
    copy /y "%SRC%" "%VLC_SYS%\aisubs.lua" >nul 2>&1
    if not errorlevel 1 (
        echo   Installed to %VLC_SYS%
        set "INSTALLED=1"
    ) else (
        echo   Note: Run as Administrator to install to Program Files.
    )
)

REM VLC Program Files (x86)
set "VLC_SYS86=C:\Program Files (x86)\VideoLAN\VLC\lua\extensions"
if exist "C:\Program Files (x86)\VideoLAN\VLC" (
    if not exist "%VLC_SYS86%" mkdir "%VLC_SYS86%" 2>nul
    copy /y "%SRC%" "%VLC_SYS86%\aisubs.lua" >nul 2>&1
    if not errorlevel 1 (
        echo   Installed to %VLC_SYS86%
        set "INSTALLED=1"
    )
)

if "%INSTALLED%"=="0" (
    echo   WARNING: No VLC directory found.
    echo   Copy aisubs.lua manually to your VLC lua\extensions folder.
)

echo.
echo   Setup complete!
echo.
echo   1. Restart VLC
echo   2. Go to View ^> AI Subs Generator
echo   3. Play a video and click Generate
echo.
pause
exit /b 0

:install_only
goto :install_vlc
