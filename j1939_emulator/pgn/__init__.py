"""PGN / SPN state and encoders for the broadcast PGNs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

IDLE_RPM = 650.0
# Exact (international mile); J1939 carries km and km/h, the GUI shows miles.
KM_PER_MI = 1.609344
# Engine Speed at or above this means the engine is running (follows the ignition switch).
RUNNING_RPM = 600.0

# Fault injection: what an SPN sends instead of its value (J1939-71 special ranges).
SPN_NORMAL = "normal"
SPN_NOT_AVAILABLE = "not_available"  # all bits 1 (0xFF…): sensor / parameter not available
SPN_ERROR = "error"  # 0xFE…: error indicator, the sensor is broken
SPN_OVERRIDE_MODES = (SPN_NORMAL, SPN_NOT_AVAILABLE, SPN_ERROR)
# Broadcast SPNs that can be overridden: key -> (SPN number, PGN key).
OVERRIDABLE_SPNS = {
    "spn190": (190, "eec1"),
    "spn84": (84, "ccvs"),
    "spn245": (245, "vd"),
    "spn247": (247, "hours"),
}


@dataclass
class SignalState:
    """Runtime SPN values for the broadcast PGNs (EEC1, CCVS, VD, HOURS)."""

    # Ignition: False = key ON, engine off. The ECU stays on the bus and answers requests, but
    # broadcasts 0 rpm / 0 mph and the meters stand still; the rpm / speed settings are kept for
    # when the engine is started again.
    engine_running: bool = True

    # EEC1
    spn190_rpm: float = 0.0
    eec1_enabled: bool = True

    # CCVS
    spn84_speed_mph: float = 0.0
    ccvs_enabled: bool = True

    # VD
    spn245_total_mi: float = 248912.4
    vd_enabled: bool = True

    # HOURS
    spn247_engine_hours: float = 10000.0
    hours_enabled: bool = True

    # Cycle times (ms) — configurable per PGN
    cycle_eec1_ms: int = 20
    cycle_ccvs_ms: int = 100
    cycle_vd_ms: int = 1000
    cycle_hours_ms: int = 1000

    # Fault injection (runtime only, never read from or saved to the config):
    # SPN key ("spn190" …) -> SPN_NOT_AVAILABLE / SPN_ERROR; missing means normal.
    spn_override: dict[str, str] = field(default_factory=dict)
    # Frozen meters stand still while the engine runs; values set by hand still apply.
    freeze_odometer: bool = False
    freeze_hours: bool = False

    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def clear_listeners(self) -> None:
        self._listeners.clear()

    def notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    def set_ignition(self, running: bool, notify: bool = True) -> None:
        """Ignition switch: engine running starts at idle, key ON / engine off drops to 0 rpm."""
        self.engine_running = running
        self.spn190_rpm = IDLE_RPM if running else 0.0
        if notify:
            self.notify()

    def set_engine_speed(self, rpm: float, notify: bool = True) -> None:
        """Set Engine Speed; 0 rpm turns the key to ON / engine off, >= 600 rpm to engine running.

        notify=False for many small steps from another thread (scenario ramps): the encoders
        read the value directly, and the GUI follows by polling.
        """
        self.spn190_rpm = float(rpm)
        if self.spn190_rpm <= 0:
            self.engine_running = False
        elif self.spn190_rpm >= RUNNING_RPM:
            self.engine_running = True
        if notify:
            self.notify()

    @property
    def broadcast_rpm(self) -> float:
        """Engine speed actually sent: 0 while the engine is off."""
        return self.spn190_rpm if self.engine_running else 0.0

    @property
    def broadcast_speed_mph(self) -> float:
        """Vehicle speed actually sent: 0 while the engine is off."""
        return self.spn84_speed_mph if self.engine_running else 0.0

    def advance_meters(self, dt_s: float) -> None:
        """Advance engine hours (while rpm > 0) and odometer (by vehicle speed) over dt_s seconds."""
        if dt_s <= 0:
            return
        if self.broadcast_rpm > 0 and not self.freeze_hours:
            self.spn247_engine_hours += dt_s / 3600.0
        if self.broadcast_speed_mph > 0 and not self.freeze_odometer:
            self.spn245_total_mi += self.broadcast_speed_mph * dt_s / 3600.0

    def set_spn(self, key: str, value: object) -> None:
        """Set a known SPN field by dotted or flat key and notify listeners."""
        attr = self._spn_attr(key)
        cur = getattr(self, attr)
        if isinstance(cur, bool):
            if isinstance(value, bool):
                setattr(self, attr, value)
            elif isinstance(value, str):
                setattr(self, attr, value.strip().lower() in ("1", "true", "yes", "on", "active"))
            else:
                setattr(self, attr, bool(int(value)))  # type: ignore[arg-type]
        elif attr == "spn190_rpm":
            self.set_engine_speed(float(value))  # type: ignore[arg-type]
            return
        elif attr.startswith("cycle_"):
            code = int(float(value))  # type: ignore[arg-type]
            if code < 1:
                raise ValueError("Cycle time must be >= 1 ms")
            setattr(self, attr, code)
        else:
            setattr(self, attr, float(value))  # type: ignore[arg-type]
        self.notify()

    def get_spn(self, key: str) -> object:
        """Read a known SPN field by dotted or flat key."""
        return getattr(self, self._spn_attr(key))

    @staticmethod
    def _spn_attr(key: str) -> str:
        mapping = {
            "engine_running": "engine_running",
            "engine.running": "engine_running",
            "eec1.spn190_rpm": "spn190_rpm",
            "spn190_rpm": "spn190_rpm",
            "ccvs.spn84_speed_mph": "spn84_speed_mph",
            "spn84_speed_mph": "spn84_speed_mph",
            "vd.spn245_total_mi": "spn245_total_mi",
            "spn245_total_mi": "spn245_total_mi",
            # pre-2.0 names (VD distance was mislabelled SPN 917)
            "vd.spn917_total_mi": "spn245_total_mi",
            "spn917_total_mi": "spn245_total_mi",
            "hours.spn247_engine_hours": "spn247_engine_hours",
            "spn247_engine_hours": "spn247_engine_hours",
            "eec1.cycle_ms": "cycle_eec1_ms",
            "cycle_eec1_ms": "cycle_eec1_ms",
            "ccvs.cycle_ms": "cycle_ccvs_ms",
            "cycle_ccvs_ms": "cycle_ccvs_ms",
            "vd.cycle_ms": "cycle_vd_ms",
            "cycle_vd_ms": "cycle_vd_ms",
            "hours.cycle_ms": "cycle_hours_ms",
            "cycle_hours_ms": "cycle_hours_ms",
        }
        attr = mapping.get(key)
        if attr is None:
            raise KeyError(f"Unknown SPN key: {key}")
        return attr


# CAN IDs (priority + PGN + SA 0x00)
CAN_ID_EEC1 = 0x0CF00400
CAN_ID_CCVS = 0x18FEF100
CAN_ID_VD = 0x18FEE000
CAN_ID_HOURS = 0x18FEE500


def _override(state: SignalState, key: str, raw: int, size: int) -> int:
    """The raw value to send for an SPN of `size` bytes, after fault injection."""
    mode = state.spn_override.get(key, SPN_NORMAL)
    if mode == SPN_NOT_AVAILABLE:
        return (1 << (8 * size)) - 1
    if mode == SPN_ERROR:
        return 0xFE << (8 * (size - 1))
    return raw


def encode_eec1(state: SignalState) -> bytes:
    """EEC1 PGN 61444 — SPN 190 engine speed; other SPNs not available."""
    raw_rpm = min(0xFAFF, max(0, round(state.broadcast_rpm / 0.125)))
    raw_rpm = _override(state, "spn190", raw_rpm, 2)
    return bytes(
        [
            0xFF,
            0xFF,
            0xFF,
            raw_rpm & 0xFF,
            (raw_rpm >> 8) & 0xFF,
            0xFF,
            0xFF,
            0xFF,
        ]
    )


def encode_ccvs(state: SignalState) -> bytes:
    """CCVS PGN 65265 — SPN 84 wheel-based speed; other SPNs not available."""
    kmh = state.broadcast_speed_mph * KM_PER_MI
    raw_speed = min(0xFAFF, max(0, round(kmh * 256)))
    raw_speed = _override(state, "spn84", raw_speed, 2)
    return bytes(
        [
            0xFF,
            raw_speed & 0xFF,
            (raw_speed >> 8) & 0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
        ]
    )


def encode_vd(state: SignalState) -> bytes:
    """VD PGN 65248 — bytes 1-4 trip (SPN 244, not available), bytes 5-8 total (SPN 245), 0.125 km/bit."""
    dist_km = state.spn245_total_mi * KM_PER_MI
    raw_dist = min(0xFAFFFFFF, max(0, round(dist_km / 0.125)))
    raw_dist = _override(state, "spn245", raw_dist, 4)
    return bytes(
        [
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            raw_dist & 0xFF,
            (raw_dist >> 8) & 0xFF,
            (raw_dist >> 16) & 0xFF,
            (raw_dist >> 24) & 0xFF,
        ]
    )


def encode_hours(state: SignalState) -> bytes:
    """HOURS PGN 65253 — bytes 1-4 SPN 247 engine hours (0.05 h/bit); SPN 249 revolutions not available."""
    raw_hours = min(0xFAFFFFFF, max(0, round(state.spn247_engine_hours / 0.05)))
    raw_hours = _override(state, "spn247", raw_hours, 4)
    return bytes(
        [
            raw_hours & 0xFF,
            (raw_hours >> 8) & 0xFF,
            (raw_hours >> 16) & 0xFF,
            (raw_hours >> 24) & 0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
        ]
    )


def payload_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def all_payloads(state: SignalState) -> dict[str, str]:
    return {
        "eec1": payload_hex(encode_eec1(state)),
        "ccvs": payload_hex(encode_ccvs(state)),
        "vd": payload_hex(encode_vd(state)),
        "hours": payload_hex(encode_hours(state)),
    }
