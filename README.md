# V2 Scanner

Portable proxy config tester for **Windows** and **macOS**. Tests V2Ray/Xray configs in bulk and shows which ones work.

Dark-themed GUI — no installation needed. Just download and run.

---

## Download

| Platform | Download |
|----------|----------|
| **Windows** (x64) | [V2Scanner.exe](https://github.com/0x2JZ/v2scanner/releases/latest/download/V2Scanner-Windows.zip) |
| **macOS** Intel | [V2Scanner-macOS-Intel](https://github.com/0x2JZ/v2scanner/releases/latest/download/V2Scanner-macOS-Intel.zip) |
| **macOS** Apple Silicon (M1/M2/M3/M4) | [V2Scanner-macOS-AppleSilicon](https://github.com/0x2JZ/v2scanner/releases/latest/download/V2Scanner-macOS-AppleSilicon.zip) |

> **No Python or other dependencies required.** Everything is bundled into a single portable file.

---

## Usage

1. Download the file for your platform
2. Run it (on macOS: right-click > Open the first time)
3. Paste proxy configs or load a `.txt` file
4. Click **START TEST**
5. Copy or export working configs

## Supported Protocols

- **VMESS** — Base64 JSON format
- **VLESS** — Including REALITY
- **Trojan** — With TLS/gRPC support
- **Shadowsocks** — All modern ciphers

## Features

- Dark-themed GUI
- Up to 32 parallel workers
- Real-time progress with latency display
- Copy results to clipboard or export to file
- Protocol detection and labeling
- Automatic xray process management

## Settings

| Setting | Default | Range |
|---------|---------|-------|
| Workers | 6 | 1–32 |
| Timeout | 10s | per config |
| Test URL | youtube.com/generate_204 | — |

---

## Build from Source

### Windows

```powershell
cd windows_app
.\build.bat
# Output: dist\V2Scanner.exe
```

### macOS

```bash
cd mac_app
chmod +x build_mac.sh
./build_mac.sh
# Output: dist/V2Scanner
```

### Requirements (build only)

- Python 3.9+
- pip packages: `requests`, `pyinstaller`, `pysocks`
- xray-core binary (auto-downloaded by build scripts)

---

## CI/CD

Builds are automated via GitHub Actions. Every push to `main` builds all 3 targets (Windows, macOS Intel, macOS Apple Silicon).

## License

MIT
