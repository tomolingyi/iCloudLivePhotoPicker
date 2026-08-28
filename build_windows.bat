@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_windows.ps1"
if errorlevel 1 (
    echo.
    echo Build failed. Keep this window open and review the error above.
    pause
    exit /b 1
)
echo.
echo The Windows package is ready in the dist folder.
pause
