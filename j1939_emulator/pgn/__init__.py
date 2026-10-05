"""PGN / SPN state and encoders matching standalone_v1.0.html."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class SignalState:
    """Runtime SPN values for the broadcast PGNs (EEC1, CCVS, VD, HOURS)."""

    # EEC1
    spn190_rpm: float = 0.0
    eec1_enabled: bool = True

    # CCVS
    spn84_speed_mph: float = 0.0
    ccvs_enabled: bool = True

    # VD
    spn917_total_mi: float = 248912.4
    vd_enabled: bool = True

    # HOURS
    spn247_engine_hours: float = 10000.0
    hours_enabled: bool = True

    # Cycle times (ms) — configurable per PGN
    cycle_eec1_ms: int = 20
    cycle_ccvs_ms: int = 100
    cycle_vd_ms: int = 1000
    cycle_hours_ms: int = 1000

    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def clear_listeners(self) -> None:
        self._listeners.clear()

    def notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    def advance_meters(self, dt_s: float) -> None:
        """Advance engine hours (while rpm > 0) and odometer (by vehicle speed) over dt_s seconds."""
        if dt_s <= 0:
            return
        if self.spn190_rpm > 0:
            self.spn247_engine_hours += dt_s / 3600.0
        if self.spn84_speed_mph > 0:
            self.spn917_total_mi += self.spn84_speed_mph * dt_s / 3600.0

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
            "eec1.spn190_rpm": "spn190_rpm",
            "spn190_rpm": "spn190_rpm",
            "ccvs.spn84_speed_mph": "spn84_speed_mph",
            "spn84_speed_mph": "spn84_speed_mph",
            "vd.spn917_total_mi": "spn917_total_mi",
            "spn917_total_mi": "spn917_total_mi",
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


# CAN IDs (priority + PGN + SA 0x00) matching HTML mock
CAN_ID_EEC1 = 0x0CF00400
CAN_ID_CCVS = 0x18FEF100
CAN_ID_VD = 0x18FEE000
CAN_ID_HOURS = 0x18FEE500

PERIOD_EEC1_S = 0.020
PERIOD_CCVS_S = 0.100
PERIOD_VD_S = 1.000
PERIOD_HOURS_S = 1.000


def encode_eec1(state: SignalState) -> bytes:
    """EEC1 PGN 61444 — SPN 190 engine speed; other SPNs not available."""
    raw_rpm = min(65535, max(0, round(state.spn190_rpm / 0.125)))
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
    kmh = state.spn84_speed_mph * 1.60934
    raw_speed = min(65535, max(0, round(kmh * 256)))
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
    dist_km = state.spn917_total_mi * 1.60934
    raw_dist = round(dist_km / 0.125)
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
