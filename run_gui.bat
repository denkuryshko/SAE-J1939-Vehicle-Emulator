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
rem candle-api (python-can[candle]) ships prebuilt Windows wheels only for 3.11-3.14;
rem on other versions pip tries to compile it and fails without a C++ toolchain.
set "VERCHECK=import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 14) else 1)"
rem Reuse an existing .venv on a supported Python: re-running venv with another Python
rem would upgrade it in place and break already-installed compiled packages.
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "%VERCHECK%" && goto :install
)
set "PY="
for %%V in (3.14 3.13 3.12 3.11) do (
    if not defined PY (
        py -%%V -c "" >nul 2>nul && set "PY=py -%%V"
    )
)
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [error] Python 3.11-3.14 not found. Install it from https://www.python.org/downloads/
    echo         and tick "Add python.exe to PATH".
    goto :fail
)
%PY% -c "%VERCHECK%"
if errorlevel 1 (
    echo [error] Python 3.11-3.14 is required, found:
    %PY% --version
    goto :fail
)
rem --clear replaces a .venv left on an unsupported Python.
%PY% -m venv --clear .venv || goto :fail

:install
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
