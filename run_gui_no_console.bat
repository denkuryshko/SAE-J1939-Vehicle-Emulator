@echo off
rem SAE J1939 Vehicle Emulator - GUI launcher without a console window.
rem Output goes to %APPDATA%\j1939-emulator\gui.log; stop with QUIT in the GUI.
rem First run (no .venv or no my_ecu.toml yet) goes through run_gui.bat, which shows the
rem setup in a console.
cd /d "%~dp0"

set "NEEDS_SETUP="
if not exist ".venv\.installed" set "NEEDS_SETUP=1"
if not exist "my_ecu.toml" set "NEEDS_SETUP=1"
if defined NEEDS_SETUP (
    call run_gui.bat
    exit /b
)
start "" ".venv\Scripts\pythonw.exe" -m j1939_emulator --gui --config "my_ecu.toml"
