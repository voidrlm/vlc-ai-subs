@echo off
REM vlc-ai-subs - setup & install (Windows)
REM
REM Usage:
REM   setup.bat              Full setup
REM   setup.bat --install    Only install VLC extension
REM
REM NOTE: this file must stay pure ASCII with CRLF line endings. cmd.exe parses
REM batch files by byte offset, so UTF-8 characters or LF-only endings corrupt
REM its parsing and produce errors like '"ayedexpansion" is not recognized'.

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%venv"
set "SRC=%SCRIPT_DIR%aisubs.lua"

REM --- Install-only mode --------------------------------------

if "%~1"=="--install" goto :install_vlc

REM --- Full setup ---------------------------------------------

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

for /f "tokens=*" %%i in ('!PYTHON! --version 2^>^&1') do echo   Found %%i

REM 2. Create virtual environment
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo   Creating virtual environment...
    !PYTHON! -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo   Failed to create venv. Make sure Python 3.8+ is installed.
        exit /b 1
    )
    echo   Virtual environment created.
) else (
    echo   Virtual environment already exists.
)

REM 2b. Make sure the venv actually has a working pip. A previously aborted
REM     "pip install --upgrade pip" can leave Scripts\pip.exe behind while the
REM     pip package itself is gone, so test the module rather than the file.
"%VENV_DIR%\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo   Repairing pip in the virtual environment...
    "%VENV_DIR%\Scripts\python.exe" -m ensurepip --default-pip
    if errorlevel 1 (
        echo   Could not restore pip in the venv. Delete the venv folder and re-run.
        exit /b 1
    )
)

REM 3. Install faster-whisper
echo   Installing faster-whisper (this may take a few minutes)...
REM  Upgrade pip via "python -m pip", never via pip.exe: on Windows the running
REM  pip.exe is locked and cannot replace itself, which leaves pip destroyed.
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo   Failed to upgrade pip.
    exit /b 1
)
"%VENV_DIR%\Scripts\python.exe" -m pip install faster-whisper
if errorlevel 1 (
    echo   Failed to install faster-whisper.
    exit /b 1
)
"%VENV_DIR%\Scripts\python.exe" -c "from faster_whisper import WhisperModel; print('  faster-whisper installed!')"
if errorlevel 1 (
    echo   faster-whisper was installed but cannot be imported.
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
if not exist "%VLC_DIR%" mkdir "%VLC_DIR%" 2>nul
copy /y "%SRC%" "%VLC_DIR%\aisubs.lua" >nul 2>&1
if not errorlevel 1 (
    echo   Installed to %VLC_DIR%
    set "INSTALLED=1"
)

REM VLC Program Files (requires admin for system-wide).
REM Paths are referenced with !delayed! expansion, never %immediate%: the x86
REM path contains "(x86)" and its closing paren would otherwise terminate the
REM surrounding if-block while cmd parses it - even when the block never runs.
set "VLC_SYS=C:\Program Files\VideoLAN\VLC\lua\extensions"
if exist "C:\Program Files\VideoLAN\VLC" (
    if not exist "!VLC_SYS!" mkdir "!VLC_SYS!" 2>nul
    copy /y "%SRC%" "!VLC_SYS!\aisubs.lua" >nul 2>&1
    if not errorlevel 1 (
        echo   Installed to !VLC_SYS!
        set "INSTALLED=1"
    ) else (
        echo   Note: Run as Administrator to also install to Program Files.
    )
)

REM VLC Program Files x86
set "VLC_SYS86=C:\Program Files (x86)\VideoLAN\VLC\lua\extensions"
if exist "C:\Program Files (x86)\VideoLAN\VLC" (
    if not exist "!VLC_SYS86!" mkdir "!VLC_SYS86!" 2>nul
    copy /y "%SRC%" "!VLC_SYS86!\aisubs.lua" >nul 2>&1
    if not errorlevel 1 (
        echo   Installed to !VLC_SYS86!
        set "INSTALLED=1"
    )
)

if "!INSTALLED!"=="0" (
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
