# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for V2 Scanner portable Windows app.

Usage:
    pyinstaller build.spec

Prerequisites:
    1. Place xray.exe in this directory (download from github.com/XTLS/Xray-core/releases)
    2. pip install pyinstaller requests
"""

import os

block_cipher = None
spec_dir = os.path.dirname(os.path.abspath(SPEC))

# Xray binary to bundle
xray_binary = os.path.join(spec_dir, "xray.exe")
datas = []
if os.path.isfile(xray_binary):
    datas.append((xray_binary, "."))

# Optional icon
icon_file = os.path.join(spec_dir, "icon.ico")
icon = icon_file if os.path.isfile(icon_file) else None

a = Analysis(
    [os.path.join(spec_dir, "v2scanner.py")],
    pathex=[spec_dir],
    binaries=[],
    datas=datas,
    hiddenimports=["requests", "urllib3", "charset_normalizer", "certifi", "idna",
                    "socks", "sockshandler"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib", "numpy", "pandas", "scipy", "PIL", "cv2",
        "setuptools", "pkg_resources", "distutils",
        "unittest", "pydoc", "doctest", "xmlrpc", "lib2to3",
        "ensurepip", "venv", "tkinter.test", "test",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Strip unnecessary Tcl/Tk data (encodings, demos, tests, docs)
tcl_excludes = [
    'demos', 'tzdata', 'msgs', 'encoding', 'http-', 'tcltest',
    'clock.tcl', 'opt0.4', 'msgcat', 'tdbc', 'itcl', 'thread',
    'cookiejar', 'platform',
]
a.datas = [
    entry for entry in a.datas
    if not any(excl in entry[0] for excl in tcl_excludes)
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="V2Scanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
