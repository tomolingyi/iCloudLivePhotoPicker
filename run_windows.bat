@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

echo [iCloud Live Photo Picker] Checking shared Python environment...

set "PYEXE="
py -3.13 -c "import sys" >nul 2>nul && set "PYEXE=py -3.13"
if not defined PYEXE py -3.12 -c "import sys" >nul 2>nul && set "PYEXE=py -3.12"
if not defined PYEXE py -3.11 -c "import sys" >nul 2>nul && set "PYEXE=py -3.11"
if not defined PYEXE python -c "import sys" >nul 2>nul && set "PYEXE=python"

if not defined PYEXE (
    echo.
    echo Python 3.10-3.13 was not found.
    echo Please install Python from python.org and enable "Add Python to PATH".
    pause
    exit /b 1
)

for /f "delims=" %%V in ('%PYEXE% -c "import sys; print(sys.version_info.major*100+sys.version_info.minor)"') do set "PYVER=%%V"
if not defined PYVER goto :error

if defined LOCALAPPDATA (
    set "ENV_ROOT=%LOCALAPPDATA%\iCloudLivePhotoPicker"
) else (
    set "ENV_ROOT=%TEMP%\iCloudLivePhotoPicker"
)
set "VENV=%ENV_ROOT%\venv-py%PYVER%"
set "VPY=%VENV%\Scripts\python.exe"
set "STAMP=%VENV%\requirements.installed.txt"

if not exist "%ENV_ROOT%" mkdir "%ENV_ROOT%" || goto :error
if not exist "%VPY%" (
    echo Creating the shared environment once at:
    echo %VENV%
    %PYEXE% -m venv "%VENV%" || goto :error
    goto :install
)

if not exist "%STAMP%" goto :install
fc /b "requirements.txt" "%STAMP%" >nul 2>nul || goto :install
"%VPY%" -c "from icloud_live_picker.ui.qt_bootstrap import prepare_qt_runtime; prepare_qt_runtime(); import PyQt6, icloudpd, imageio_ffmpeg; from PIL import Image" >nul 2>nul || goto :install

echo Reusing shared environment. No installation is needed.
goto :launch

:install
echo Installing or updating dependencies...
"%VPY%" -m pip install --upgrade "pip>=25.1" || goto :error
"%VPY%" -m pip install -r requirements.txt || goto :error
copy /y "requirements.txt" "%STAMP%" >nul || goto :error

:launch
echo.
echo Starting iCloud Live Photo Picker...
"%VPY%" -m icloud_live_picker
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo Program exited with code %RC%.
    pause
)
exit /b %RC%

:error
echo.
echo Environment preparation failed. Please keep this window open and send the error text for diagnosis.
pause
exit /b 1
