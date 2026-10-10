"""TOML configuration for bus + PGN + ECU/VIN + diagnostics defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

from j1939_emulator.bus.detect import EmulationMode
from j1939_emulator.diagnostics import DiagnosticState
from j1939_emulator.ecu_identity import (
    DEFAULT_SOURCE_ADDRESS,
    NAME_FIELDS,
    DEFAULT_VIN,
    EcuIdentity,
    validate_vin,
)
from j1939_emulator.pgn import SignalState


@dataclass
class BusConfig:
    mode: EmulationMode = EmulationMode.VIRTUAL
    channel: str = "vcan0"
    bitrate: int = 500_000


@dataclass
class AppConfig:
    bus: BusConfig
    signals: SignalState
    identity: EcuIdentity
    diagnostics: DiagnosticState
    vin: str = DEFAULT_VIN  # alias of identity.vin for back-compat
    start_on_launch: bool = True
    persist_meters: bool = True


_REQUIRED_SECTIONS = ("bus",)


def load_config(path: str | Path) -> AppConfig:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Config not found: {p}")
    with p.open("rb") as f:
        raw = tomllib.load(f)

    missing = [s for s in _REQUIRED_SECTIONS if s not in raw]
    if missing:
        raise ValueError(f"Missing required TOML section(s): {', '.join(missing)}")

    bus_raw = raw["bus"]
    for key in ("mode", "channel", "bitrate"):
        if key not in bus_raw:
            raise ValueError(f"Missing required [bus] key: {key}")

    mode_s = str(bus_raw["mode"]).strip().lower()
    if mode_s not in ("real", "virtual"):
        raise ValueError(f"Invalid bus.mode {mode_s!r}; expected 'real' or 'virtual'")
    bitrate = int(bus_raw["bitrate"])
    if bitrate not in (125_000, 250_000, 500_000, 1_000_000):
        raise ValueError(
            f"Invalid bitrate {bitrate}; expected 125000, 250000, 500000, or 1000000"
        )

    bus = BusConfig(
        mode=EmulationMode(mode_s),
        channel=str(bus_raw["channel"]),
        bitrate=bitrate,
    )

    signals = SignalState()
    _apply_pgn(signals, raw.get("pgn", {}).get("eec1"), "eec1")
    _apply_pgn(signals, raw.get("pgn", {}).get("ccvs"), "ccvs")
    _apply_pgn(signals, raw.get("pgn", {}).get("vd"), "vd")
    _apply_pgn(signals, raw.get("pgn", {}).get("hrvd"), "hrvd")
    _apply_pgn(signals, raw.get("pgn", {}).get("hours"), "hours")
    signals.engine_running = _engine_running(raw.get("vehicle", {}) or {})

    identity = _load_identity(raw)
    diagnostics = _load_diagnostics(raw)

    start_on_launch = bool(raw.get("bus", {}).get("start_on_launch", True))
    if "start_on_launch" in raw.get("run", {}):
        start_on_launch = bool(raw["run"]["start_on_launch"])

    return AppConfig(
        bus=bus,
        signals=signals,
        identity=identity,
        diagnostics=diagnostics,
        vin=identity.vin,
        start_on_launch=start_on_launch,
        persist_meters=bool((raw.get("vehicle", {}) or {}).get("persist_meters", True)),
    )


IGNITION_VALUES = {"run": True, "on": False}


def _engine_running(vehicle: dict) -> bool:
    """[vehicle] ignition: "run" (engine running, default) or "on" (key ON, engine off)."""
    ignition = str(vehicle.get("ignition", "run")).strip().lower()
    if ignition not in IGNITION_VALUES:
        raise ValueError(f"Invalid vehicle.ignition {ignition!r}; expected 'run' or 'on'")
    return IGNITION_VALUES[ignition]


def _load_identity(raw: dict) -> EcuIdentity:
    ecu = raw.get("ecu", {}) or {}
    vehicle = raw.get("vehicle", {}) or {}

    vin_raw = vehicle.get("vin", ecu.get("vin", DEFAULT_VIN))
    vin = validate_vin(str(vin_raw))

    sa = ecu.get("source_address", DEFAULT_SOURCE_ADDRESS)
    if isinstance(sa, str):
        sa = int(sa, 0)
    else:
        sa = int(sa)

    # NAME: either a full 64-bit `name`, or individual J1939-81 fields (which win if both given).
    fields: dict[str, int] = {}
    if "name" in ecu:
        fields.update(EcuIdentity.name_fields(_int(ecu["name"])))
    for key in NAME_FIELDS:
        if key in ecu:
            fields[key] = _int(ecu[key])
    if "vehicle_system" not in ecu and "vehicle_system" in vehicle:
        fields["vehicle_system"] = _int(vehicle["vehicle_system"])

    return EcuIdentity(vin=vin, source_address=sa & 0xFF, **fields)


def _int(value: object) -> int:
    """TOML ints, or strings like "0x20" / "32"."""
    return int(value, 0) if isinstance(value, str) else int(value)


def _load_diagnostics(raw: dict) -> DiagnosticState:
    diag = raw.get("diagnostics", {}) or {}
    return DiagnosticState(
        dtc_spn110_fmi3=bool(
            diag.get(
                "dtc_spn110_fmi3",
                diag.get("inject_coolant_voltage_high", False),
            )
        ),
        dtc_spn190_fmi0=bool(
            diag.get(
                "dtc_spn190_fmi0",
                diag.get("inject_crankshaft_overspeed", False),
            )
        ),
    )


def _apply_pgn(signals: SignalState, section: dict | None, name: str) -> None:
    if not section:
        return
    enabled = bool(section.get("enabled", True))
    if name == "eec1":
        signals.eec1_enabled = enabled
        if "spn190_rpm" in section:
            signals.spn190_rpm = float(section["spn190_rpm"])
        if "cycle_ms" in section:
            signals.cycle_eec1_ms = int(section["cycle_ms"])
    elif name == "ccvs":
        signals.ccvs_enabled = enabled
        if "spn84_speed_mph" in section:
            signals.spn84_speed_mph = float(section["spn84_speed_mph"])
        if "cycle_ms" in section:
            signals.cycle_ccvs_ms = int(section["cycle_ms"])
    elif name == "vd":
        signals.vd_enabled = enabled
        # spn917_total_mi: pre-2.0 key name, still accepted
        for key in ("spn917_total_mi", "spn245_total_mi"):
            if key in section:
                signals.spn245_total_mi = float(section[key])
        if "cycle_ms" in section:
            signals.cycle_vd_ms = int(section["cycle_ms"])
    elif name == "hrvd":
        # No value of its own: HRVD sends the [pgn.vd] odometer.
        signals.hrvd_enabled = enabled
        if "cycle_ms" in section:
            signals.cycle_hrvd_ms = int(section["cycle_ms"])
    elif name == "hours":
        signals.hours_enabled = enabled
        if "spn247_engine_hours" in section:
            signals.spn247_engine_hours = float(section["spn247_engine_hours"])
        if "cycle_ms" in section:
            signals.cycle_hours_ms = int(section["cycle_ms"])
