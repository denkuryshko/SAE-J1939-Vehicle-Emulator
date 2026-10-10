"""Diagnostics: a configurable list of injectable DTCs, DM1 (PGN 65226) encoding, DM11 clear."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Callable

from j1939.diagnostic_messages import DTC, DtcLamp

# PGN 65226 DM1 — CAN ID 0x18FECA00 (Prio 6, SA 0x00)
DM1_PDU_FORMAT = 0xFE
DM1_PDU_SPECIFIC = 0xCA
DM1_PRIORITY = 6
DM1_CYCLE_MS = 1000
PGN_DM1 = 65226
# PGN 65235 DM11: on Request, clear all active DTCs (J1939-73)
PGN_DM11 = 65235

# Lamp name (config / GUI) -> can-j1939 lamp key
LAMPS = {"amber": "awl", "red": "rsl", "mil": "mil", "protect": "pl"}
LAMP_LABELS = {
    "amber": "Amber Warning",
    "red": "Red Stop Lamp",
    "mil": "Malfunction Indicator (MIL)",
    "protect": "Protect Lamp",
}
MAX_SPN = (1 << 19) - 1
MAX_FMI = 31
MAX_OC = 126  # 127 = not available
MAX_DTCS = 50
_KEY_RE = re.compile(r"spn(\d+)_fmi(\d+)$")


def dtc_key(spn: int, fmi: int) -> str:
    """Stable name of a DTC in configs and scenarios, e.g. "spn110_fmi3"."""
    return f"spn{spn}_fmi{fmi}"


def parse_dtc_key(key: str) -> tuple[int, int]:
    """(spn, fmi) from "spn110_fmi3"; ValueError if the key has another shape."""
    m = _KEY_RE.match(str(key).strip().lower())
    if m is None:
        raise ValueError(f"DTC key {key!r} must look like spn110_fmi3")
    return int(m.group(1)), int(m.group(2))


@dataclass
class Dtc:
    """One injectable fault: SPN / FMI, the lamp it lights, and how often it occurred."""

    spn: int
    fmi: int
    lamp: str = "amber"
    name: str = ""
    description: str = ""
    oc: int = 1  # occurrence count sent while active; +1 each time it becomes active again
    active: bool = False
    # Set once it has been active, so becoming active again counts as a new occurrence.
    was_active: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not 0 <= self.spn <= MAX_SPN:
            raise ValueError(f"DTC SPN {self.spn} out of range 0..{MAX_SPN}")
        if not 0 <= self.fmi <= MAX_FMI:
            raise ValueError(f"DTC FMI {self.fmi} out of range 0..{MAX_FMI}")
        if self.lamp not in LAMPS:
            raise ValueError(f"DTC lamp {self.lamp!r}; expected one of {', '.join(LAMPS)}")
        if not 0 <= self.oc <= MAX_OC:
            raise ValueError(f"DTC occurrence count {self.oc} out of range 0..{MAX_OC}")

    @property
    def key(self) -> str:
        return dtc_key(self.spn, self.fmi)

    @property
    def label(self) -> str:
        return f"SPN {self.spn} / FMI {self.fmi}"


DEFAULT_DTCS = (
    Dtc(
        110, 3, "amber", "Engine Coolant Temp Voltage High",
        "Voltage Above Normal, Or Shorted To High Source.",
    ),
    Dtc(
        190, 0, "red", "Engine Crankshaft Overspeed",
        "Data Valid But Above Normal Operational Range - Most Severe Level.",
    ),
)


def default_dtcs() -> list[Dtc]:
    return [replace(d) for d in DEFAULT_DTCS]


@dataclass
class DiagnosticState:
    """The DTCs this ECU can report; the active ones go out on DM1."""

    dtcs: list[Dtc] = field(default_factory=default_dtcs)
    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if len(self.dtcs) > MAX_DTCS:
            raise ValueError(f"At most {MAX_DTCS} DTCs")
        keys = [d.key for d in self.dtcs]
        dup = {k for k in keys if keys.count(k) > 1}
        if dup:
            raise ValueError(f"Duplicate DTC: {', '.join(sorted(dup))}")

    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def clear_listeners(self) -> None:
        self._listeners.clear()

    def notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    @property
    def active(self) -> list[Dtc]:
        return [d for d in self.dtcs if d.active]

    @property
    def active_count(self) -> int:
        return len(self.active)

    def get(self, key: str) -> Dtc:
        for d in self.dtcs:
            if d.key == key:
                return d
        raise KeyError(f"No DTC {key} in the config")

    def _set(self, dtc: Dtc, active: bool) -> None:
        active = bool(active)
        if active and not dtc.active and dtc.was_active:
            dtc.oc = min(MAX_OC, dtc.oc + 1)  # occurred again
        if active:
            dtc.was_active = True
        dtc.active = active

    def set_active(self, key: str, active: bool) -> None:
        self._set(self.get(key), active)
        self.notify()

    def set_many(self, states: dict[str, bool]) -> None:
        """Several DTCs at once (scenario steps); KeyError before any change if one is unknown."""
        targets = [(self.get(k), v) for k, v in states.items()]
        for dtc, active in targets:
            self._set(dtc, active)
        self.notify()

    def set_all(self, active: bool) -> None:
        for d in self.dtcs:
            self._set(d, active)
        self.notify()

    def clear_all(self) -> None:
        self.set_all(False)

    def inject_all(self) -> None:
        self.set_all(True)

    def lamp_status(self) -> dict[str, int]:
        """Lamp dict for can-j1939 DtcLamp.get_data: a lamp is on if any active DTC lights it."""
        lit = {LAMPS[d.lamp] for d in self.active}
        return {k: DtcLamp.ON if k in lit else DtcLamp.OFF for k in ("pl", "awl", "rsl", "mil")}


def encode_dm1(state: DiagnosticState) -> bytes:
    """DM1 payload: 2 lamp bytes + 4 bytes per active DTC, at least 8 bytes (J1939-73).

    No active faults → SPN/FMI/OC all zero ("no DTC"). One fault → padded with 0xFF
    to a single 8-byte frame. Two or more → 6 + 4 per extra DTC bytes, sent via BAM.
    """
    data = bytearray(DtcLamp().get_data(state.lamp_status()))
    active = state.active
    for d in active:
        data += DTC(spn=d.spn, fmi=d.fmi, oc=d.oc).dtc.to_bytes(4, "little")
    if not active:
        data += bytes(4)
    data.extend([0xFF] * (8 - len(data)))
    return bytes(data)
