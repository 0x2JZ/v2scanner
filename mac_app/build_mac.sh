#!/bin/bash
set -e

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║   V2 Scanner — macOS Build           ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 not found. Install via: brew install python3"
    exit 1
fi

PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[INFO] Python $PYVER found."

# Install dependencies
echo "[1/4] Installing dependencies..."
pip3 install requests pyinstaller pysocks --quiet
echo "       Done."

# Check for xray binary
if [ ! -f "$SCRIPT_DIR/xray" ]; then
    echo ""
    echo "[2/4] Downloading xray-core..."

    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        XRAY_URL="https://github.com/XTLS/Xray-core/releases/latest/download/Xray-macos-arm64-v8a.zip"
    else
        XRAY_URL="https://github.com/XTLS/Xray-core/releases/latest/download/Xray-macos-64.zip"
    fi

    echo "       Downloading for $ARCH..."
    curl -sL "$XRAY_URL" -o "$SCRIPT_DIR/xray.zip"

    if [ $? -ne 0 ]; then
        echo "[ERROR] Download failed. Please manually download from:"
        echo "        https://github.com/XTLS/Xray-core/releases"
        echo "        Extract 'xray' into this folder and run build_mac.sh again."
        exit 1
    fi

    echo "       Extracting..."
    unzip -o -q "$SCRIPT_DIR/xray.zip" xray -d "$SCRIPT_DIR/"
    chmod +x "$SCRIPT_DIR/xray"
    rm -f "$SCRIPT_DIR/xray.zip"
    echo "       Done."
else
    echo "[2/4] xray binary found."
fi

# Verify xray works
echo "[3/4] Verifying xray..."
if ! "$SCRIPT_DIR/xray" version &>/dev/null; then
    echo "[ERROR] xray failed to run. Make sure you have the correct macOS version."
    echo "        For Apple Silicon (M1/M2/M3): Xray-macos-arm64-v8a.zip"
    echo "        For Intel Macs: Xray-macos-64.zip"
    exit 1
fi
echo "       OK."

# Build
echo "[4/4] Building V2Scanner..."
pyinstaller build_mac.spec --noconfirm --clean 2>&1 | tail -3

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║           BUILD COMPLETE!            ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  Output: $SCRIPT_DIR/dist/V2Scanner"
echo ""

# Make executable
chmod +x "$SCRIPT_DIR/dist/V2Scanner" 2>/dev/null || true

# Open dist folder
open "$SCRIPT_DIR/dist" 2>/dev/null || true
