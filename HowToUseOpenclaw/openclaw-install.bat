@echo off
chcp 65001 >nul 2>&1

echo ========================================
echo OpenClaw Windows Installer
echo ========================================
echo.

if not exist "%~dp0openclaw-install.ps1" (
    echo [ERROR] openclaw-install.ps1 not found
    pause
    exit /b 1
)

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [TIP] Run as Administrator for best experience
    echo.
)

cd /d "%~dp0"
echo [INFO] Starting installation...
echo ----------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0openclaw-install.ps1"
echo ----------------------------------------

echo.
if %errorlevel% equ 0 (
    echo [OK] Installation completed successfully
) else (
    echo [WARN] Script exited with code: %errorlevel%
)

echo.
pause