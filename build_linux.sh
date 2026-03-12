#!/usr/bin/env bash
# ==============================================================
# build_linux.sh
#
# Builds the Forensic AI Agent for Linux.
# Produces:  dist/ForensicAIAgent/   (portable folder)
#            dist/ForensicAIAgent.AppImage  (single-file AppImage)
#
# Run on: Ubuntu 22.04+ or any glibc 2.35+ distro.
# Requirements: python3, pip, fuse (for AppImage)
#
# Usage:
#   chmod +x build_linux.sh
#   ./build_linux.sh
# ==============================================================

set -e

echo "[*] Forensic AI Agent — Linux Build Script"
echo

# ── Check Python ──────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[!] python3 not found. Install Python 3.11+."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[+] Python $PYTHON_VERSION found."

# ── Install build deps ────────────────────────────────────────
echo "[*] Installing/upgrading build dependencies..."
pip3 install --quiet --upgrade pyinstaller pyside6

# ── Clean ─────────────────────────────────────────────────────
echo "[*] Cleaning previous build..."
rm -rf build dist

# ── PyInstaller ───────────────────────────────────────────────
echo "[*] Running PyInstaller..."
pyinstaller forensic_agent.spec

if [ ! -f "dist/ForensicAIAgent/ForensicAIAgent" ]; then
    echo "[!] Build failed — binary not found. Check spec output above."
    exit 1
fi

echo "[+] PyInstaller build complete: dist/ForensicAIAgent/"

# ── AppImage (optional but recommended for distribution) ──────
echo
echo "[*] Building AppImage..."

# Download appimagetool if not present
APPIMAGETOOL="./appimagetool-x86_64.AppImage"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "[*] Downloading appimagetool..."
    curl -L -o "$APPIMAGETOOL" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

# Build the AppDir structure
APPDIR="dist/ForensicAIAgent.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy the PyInstaller output into AppDir
cp -r dist/ForensicAIAgent/* "$APPDIR/usr/bin/"

# AppRun entrypoint
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export LD_LIBRARY_PATH="$HERE/usr/bin:$LD_LIBRARY_PATH"
exec "$HERE/usr/bin/ForensicAIAgent" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Desktop file
cat > "$APPDIR/usr/share/applications/forensicaiagent.desktop" << EOF
[Desktop Entry]
Name=Forensic AI Agent
Exec=ForensicAIAgent
Icon=forensicaiagent
Type=Application
Categories=Security;
EOF

# Copy icon (fall back to placeholder if missing)
if [ -f "assets/icon.png" ]; then
    cp "assets/icon.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/forensicaiagent.png"
    cp "assets/icon.png" "$APPDIR/forensicaiagent.png"
else
    echo "[~] assets/icon.png not found — AppImage will have no icon."
    touch "$APPDIR/forensicaiagent.png"
fi

# Also copy the .desktop to AppDir root (required by appimagetool)
cp "$APPDIR/usr/share/applications/forensicaiagent.desktop" "$APPDIR/"

# Build the AppImage
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "dist/ForensicAIAgent.AppImage"

echo
echo "[+] Build complete!"
echo "    Portable folder : dist/ForensicAIAgent/"
echo "    AppImage        : dist/ForensicAIAgent.AppImage"
echo
echo "[*] To distribute: share the .AppImage file."
echo "    Users run it directly — Ollama setup wizard runs on first launch."