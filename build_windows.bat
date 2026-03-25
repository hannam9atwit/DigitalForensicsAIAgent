@echo off
REM ============================================================
REM build_windows.bat
REM
REM Builds the Forensic AI Agent for Windows and optionally
REM packages it into a single installer .exe via Inno Setup.
REM
REM Requirements:
REM   pip install pyinstaller pyside6 reportlab
REM   Inno Setup 6 (optional, for installer):
REM     https://jrsoftware.org/isinfo.php
REM ============================================================

setlocal enabledelayedexpansion

echo [*] Forensic AI Agent -- Windows Build Script
echo.

REM ── Check Python ─────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python not found. Install Python 3.11+ and add it to PATH.
    pause & exit /b 1
)

REM ── Check / install dependencies ─────────────────────────────
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [*] Installing PyInstaller...
    pip install pyinstaller
)

python -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing PySide6...
    pip install pyside6
)

python -c "import reportlab" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing reportlab...
    pip install reportlab
)

REM ── Clean previous build ─────────────────────────────────────
echo [*] Cleaning previous build...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist

REM ── Run PyInstaller ──────────────────────────────────────────
echo [*] Running PyInstaller...
pyinstaller forensic_agent.spec

if errorlevel 1 (
    echo [!] PyInstaller failed. Check errors above.
    pause & exit /b 1
)

if not exist "dist\ForensicAIAgent\ForensicAIAgent.exe" (
    echo [!] Build succeeded but .exe not found -- check spec file.
    pause & exit /b 1
)

echo [+] PyInstaller build complete: dist\ForensicAIAgent\

REM ── Inno Setup (optional) ────────────────────────────────────
echo.
echo [*] Checking for Inno Setup...

set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
)

if defined ISCC (
    echo [*] Inno Setup found -- building installer...
    %ISCC% ForensicAIAgent_Setup.iss
    if errorlevel 1 (
        echo [!] Inno Setup failed. Portable folder is still available in dist\ForensicAIAgent\
    ) else (
        echo [+] Installer created: dist\ForensicAIAgent_Setup.exe
    )
) else (
    echo [~] Inno Setup not found -- skipping installer creation.
    echo     Download from https://jrsoftware.org/isinfo.php to build a single-file installer.
    echo     The portable folder at dist\ForensicAIAgent\ still works -- zip it to distribute.
)

echo.
echo [+] Build complete!
echo     Portable folder : dist\ForensicAIAgent\
if defined ISCC echo     Installer       : dist\ForensicAIAgent_Setup.exe
echo.
pause
