@echo off
title V2 Scanner — Build
echo.
echo  ╔══════════════════════════════════════╗
echo  ║   V2 Scanner — Portable App Build    ║
echo  ╚══════════════════════════════════════╝
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.9+ from python.org
    echo         Make sure "Add to PATH" is checked during install.
    pause
    exit /b 1
)

:: Install dependencies
echo [1/4] Installing dependencies...
pip install requests pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
)
echo       Done.

:: Check for xray.exe
if not exist "%~dp0xray.exe" (
    echo.
    echo [2/4] Downloading xray-core for Windows...
    powershell -Command "& { $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/XTLS/Xray-core/releases/latest/download/Xray-windows-64.zip' -OutFile '%~dp0xray.zip' }"
    if errorlevel 1 (
        echo [ERROR] Download failed. Please manually download Xray-windows-64.zip from:
        echo         https://github.com/XTLS/Xray-core/releases
        echo         Extract xray.exe into this folder and run build.bat again.
        pause
        exit /b 1
    )
    echo       Extracting...
    powershell -Command "& { Expand-Archive -Path '%~dp0xray.zip' -DestinationPath '%~dp0xray_temp' -Force }"
    copy "%~dp0xray_temp\xray.exe" "%~dp0xray.exe" >nul
    rmdir /s /q "%~dp0xray_temp" >nul 2>&1
    del "%~dp0xray.zip" >nul 2>&1
    echo       Done.
) else (
    echo [2/4] xray.exe found.
)

:: Verify xray works
echo [3/4] Verifying xray...
"%~dp0xray.exe" version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] xray.exe failed to run. Make sure you have the Windows version.
    pause
    exit /b 1
)
echo       OK.

:: Build with PyInstaller
echo [4/4] Building V2Scanner.exe...
cd /d "%~dp0"
pyinstaller build.spec --noconfirm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Build failed. Running again with output:
    pyinstaller build.spec --noconfirm
    pause
    exit /b 1
)

echo.
echo  ╔══════════════════════════════════════╗
echo  ║           BUILD COMPLETE!            ║
echo  ╚══════════════════════════════════════╝
echo.
echo  Output: %~dp0dist\V2Scanner.exe
echo.

:: Open dist folder
explorer "%~dp0dist"
pause
