@echo off
REM ============================================================
REM build_windows.bat
REM
REM Builds the Forensic AI Agent as a standalone Windows folder.
REM Run this on a Windows machine with Python + PyInstaller installed.
REM
REM Requirements:
REM   pip install pyinstaller pyside6
REM ============================================================

setlocal enabledelayedexpansion

echo [*] Forensic AI Agent — Windows Build Script
echo.

REM ── Check Python ────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python not found. Install Python 3.11+ and add it to PATH.
    pause & exit /b 1
)

REM ── Check PyInstaller ────────────────────────────────────────
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [*] Installing PyInstaller...
    pip install pyinstaller
)

REM ── Check PySide6 ────────────────────────────────────────────
python -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing PySide6...
    pip install pyside6
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

REM ── Verify output ────────────────────────────────────────────
if not exist "dist\ForensicAIAgent\ForensicAIAgent.exe" (
    echo [!] Build succeeded but .exe not found — check spec file.
    pause & exit /b 1
)

echo.
echo [+] Build complete!
echo     Output: dist\ForensicAIAgent\
echo.
echo [*] To distribute: zip the entire dist\ForensicAIAgent\ folder.
echo     Users run ForensicAIAgent.exe — Ollama setup wizard runs on first launch.
echo.
pause