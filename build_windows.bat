@echo off
REM ============================================================
REM build_windows.bat — Windows build + installer pipeline.
REM
REM Produces:
REM   dist\AIRforensics\                  portable folder
REM   dist\AIRforensics_Setup-Full.exe    offline installer (~2.4 GB)
REM   dist\AIRforensics_Setup-Lite.exe    small installer (~500 MB)
REM
REM Requirements:
REM   Python 3.11+, pip install -r requirements.txt
REM   Inno Setup 6           https://jrsoftware.org/isinfo.php
REM   Ollama on this machine https://ollama.com  (Full variant only)
REM ============================================================

setlocal enabledelayedexpansion
echo [*] AIRforensics -- Windows Build Pipeline
echo.

REM -- Python + deps -------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python not found. Install Python 3.11+ and add it to PATH.
    pause & exit /b 1
)
python -m pip install -q -r requirements.txt

REM -- Clean + PyInstaller -------------------------------------
echo [*] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo [*] Running PyInstaller...
python -m PyInstaller forensic_agent.spec
if errorlevel 1 (
    echo [!] PyInstaller failed. Check errors above.
    pause & exit /b 1
)
if not exist "dist\AIRforensics\AIRforensics.exe" (
    echo [!] Build succeeded but .exe not found -- check the spec file.
    pause & exit /b 1
)
echo [+] Portable build complete: dist\AIRforensics\
echo.

REM -- Installer payloads --------------------------------------
if not exist redist mkdir redist

if not exist "redist\OllamaSetup.exe" (
    echo [*] Downloading OllamaSetup.exe...
    curl -L -o "redist\OllamaSetup.exe" "https://ollama.com/download/OllamaSetup.exe"
    if errorlevel 1 (
        echo [!] Ollama download failed -- installers will be skipped.
        pause & exit /b 1
    )
)

if not exist "redist\ollama-models\manifests" (
    echo [*] Staging model payload for the Full installer...
    python tools\prepare_model_payload.py
    if errorlevel 1 (
        echo [~] Model payload unavailable -- Full installer will be skipped.
        echo     Run `ollama pull llama3.2:3b` on this machine, then rebuild.
        set SKIP_FULL=1
    )
)

REM -- Inno Setup ----------------------------------------------
set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
)

if not defined ISCC (
    echo [~] Inno Setup not found -- skipping installers.
    echo     Download from https://jrsoftware.org/isinfo.php
    echo     The portable folder at dist\AIRforensics\ still works.
    goto done
)

REM Parentheses in echo text inside if-blocks break cmd's parser, so the
REM installer builds use plain goto flow instead of blocks.
echo [*] Building LITE installer - model downloads on first launch...
%ISCC% /Q /DLITE AIRforensics_Setup.iss
if errorlevel 1 echo [!] Lite installer failed.

if defined SKIP_FULL goto done
echo [*] Building FULL installer - fully offline, large...
%ISCC% /Q AIRforensics_Setup.iss
if errorlevel 1 echo [!] Full installer failed.

:done
echo.
echo [+] Build pipeline finished.
echo     Portable : dist\AIRforensics\
echo     Lite     : dist\AIRforensics_Setup-Lite.exe  (GitHub Releases)
echo     Full     : dist\AIRforensics_Setup-Full.exe  (website download)
echo.
pause
