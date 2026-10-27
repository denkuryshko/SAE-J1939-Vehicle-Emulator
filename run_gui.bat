@echo off
setlocal
rem SAE J1939 Vehicle Emulator - GUI launcher.
rem First run creates .venv and installs dependencies; later runs start the GUI directly.
cd /d "%~dp0"

set "CONFIG=my_ecu.toml"
set "VENV_PY=.venv\Scripts\python.exe"
rem Written only after a successful install, so an interrupted first run is retried.
set "MARKER=.venv\.installed"

if not exist "%CONFIG%" (
    echo [error] Config "%CONFIG%" not found next to run_gui.bat.
    goto :fail
)

if exist "%MARKER%" goto :run

echo === First run: setting up Python environment ===
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [error] Python 3.11+ not found. Install it from https://www.python.org/downloads/
    echo         and tick "Add python.exe to PATH".
    goto :fail
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo [error] Python 3.11 or newer is required:
    %PY% --version
    goto :fail
)
%PY% -m venv .venv || goto :fail
"%VENV_PY%" -m pip install --upgrade pip || goto :fail
rem candle = candleLight / CANable driver; base install already covers gs_usb and serial adapters.
"%VENV_PY%" -m pip install -e . "python-can[candle]" || goto :fail
type nul > "%MARKER%"
echo.

:run
echo Starting GUI with %CONFIG% ... (close other CAN tools such as Cangaroo before START)
echo Use QUIT in the GUI to stop; this window closes afterwards.
"%VENV_PY%" -m j1939_emulator --gui --config "%CONFIG%"
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo Launcher stopped because of the error above.
pause
exit /b 1
