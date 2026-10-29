@echo off
rem SAE J1939 Vehicle Emulator - GUI launcher without a console window.
rem Output goes to %APPDATA%\j1939-emulator\gui.log; stop with QUIT in the GUI.
rem First run (no .venv yet) goes through run_gui.bat, which shows the setup in a console.
cd /d "%~dp0"

if not exist ".venv\.installed" (
    call run_gui.bat
    exit /b
)
start "" ".venv\Scripts\pythonw.exe" -m j1939_emulator --gui --config "my_ecu.toml"
