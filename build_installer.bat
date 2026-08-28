@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_installer.ps1"
if errorlevel 1 (
    echo.
    echo Installer build failed. Keep this window open and review the error above.
    pause
    exit /b 1
)
echo.
echo The Windows installer is ready in the dist folder.
pause
