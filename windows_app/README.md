# V2 Scanner — Portable Windows App

Standalone Windows app that tests V2Ray/Xray proxy configs and lists working ones.

## Quick Start (pre-built)

1. Download `V2Scanner.exe`
2. Double-click to run
3. Paste configs or load a `.txt` file
4. Click **START TEST**
5. Copy or export working configs

## Build from Source

### Requirements

- Windows 10/11
- Python 3.9+
- xray-core Windows binary

### Steps

```powershell
# 1. Install dependencies
pip install requests pyinstaller

# 2. Download xray-core for Windows
# From: https://github.com/XTLS/Xray-core/releases
# Extract xray.exe into this directory

# 3. Build
pyinstaller build.spec

# 4. Output
# → dist/V2Scanner.exe (single portable file, ~25MB)
```

### Optional: Add icon

Place an `icon.ico` file in this directory before building.

## How It Works

1. Parses each config URI (vmess, vless, trojan, shadowsocks)
2. Generates an xray JSON config for each
3. Starts xray as a local proxy
4. Tests connectivity through the proxy to YouTube/Google
5. Reports working configs with latency

## Supported Protocols

- VMESS
- VLESS (including REALITY)
- Trojan
- Shadowsocks

## Settings

- **Workers**: Number of parallel test threads (1-12, default 6)
- **Test timeout**: 10 seconds per config
- **Test URLs**: youtube.com/generate_204, google.com/generate_204
