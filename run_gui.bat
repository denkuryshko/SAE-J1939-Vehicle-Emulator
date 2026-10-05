@echo off
cd /d "%~dp0"
echo === CAN adapters ===
.venv\Scripts\python.exe -m j1939_emulator --list-channels --mode real
echo.
echo Check that [bus] channel in my_ecu.toml matches the candleLight number above.
echo Close Cangaroo before START.
echo.
.venv\Scripts\python.exe -m j1939_emulator --gui --config my_ecu.toml
pause
