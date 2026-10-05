"""Persist odometer and engine hours between runs, one record per VIN."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from j1939_emulator.pgn import SignalState

APP_DIR_NAME = "j1939-emulator"
STATE_FILE_NAME = "meters.json"
# Overrides the state directory (tests, portable installs).
STATE_DIR_ENV = "J1939_EMULATOR_STATE_DIR"


def state_file() -> Path:
    override = os.environ.get(STATE_DIR_ENV)
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_DIR_NAME
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / APP_DIR_NAME
    return base / STATE_FILE_NAME


def _read_all(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def restore_meters(signals: SignalState, vin: str) -> bool:
    """Load the saved odometer / engine hours for this VIN into signals. True if a record existed."""
    record = _read_all(state_file()).get(vin)
    if not isinstance(record, dict):
        return False
    try:
        odometer = float(record["odometer_mi"])
        hours = float(record["engine_hours"])
    except (KeyError, TypeError, ValueError):
        return False
    signals.spn245_total_mi = odometer
    signals.spn247_engine_hours = hours
    return True


def save_meters(signals: SignalState, vin: str) -> None:
    """Write the current odometer / engine hours for this VIN (atomic replace)."""
    path = state_file()
    data = _read_all(path)
    data[vin] = {
        "odometer_mi": round(signals.spn245_total_mi, 4),
        "engine_hours": round(signals.spn247_engine_hours, 5),
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        # Persistence is best effort; never break emulation over it.
        pass
