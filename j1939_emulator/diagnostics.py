"""Diagnostics: two injectable DTCs and DM1 (PGN 65226) encoding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from j1939.diagnostic_messages import DTC, DtcLamp

# PGN 65226 DM1 — CAN ID 0x18FECA00 (Prio 6, SA 0x00)
DM1_PDU_FORMAT = 0xFE
DM1_PDU_SPECIFIC = 0xCA
DM1_PRIORITY = 6
DM1_CYCLE_MS = 1000

# Fixed fault set
DTC1_SPN, DTC1_FMI = 110, 3  # Coolant temp voltage high → Amber Warning
DTC2_SPN, DTC2_FMI = 190, 0  # Crankshaft overspeed → Red Stop


@dataclass
class DiagnosticState:
    """Exactly two injectable DTCs."""

    dtc_spn110_fmi3: bool = False
    dtc_spn190_fmi0: bool = False
    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def clear_listeners(self) -> None:
        self._listeners.clear()

    def notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    @property
    def active_count(self) -> int:
        return int(self.dtc_spn110_fmi3) + int(self.dtc_spn190_fmi0)

    def set_dtc1(self, active: bool) -> None:
        self.dtc_spn110_fmi3 = bool(active)
        self.notify()

    def set_dtc2(self, active: bool) -> None:
        self.dtc_spn190_fmi0 = bool(active)
        self.notify()

    def set_both(self, active: bool) -> None:
        self.dtc_spn110_fmi3 = bool(active)
        self.dtc_spn190_fmi0 = bool(active)
        self.notify()

    def clear_all(self) -> None:
        self.set_both(False)

    def inject_both(self) -> None:
        self.set_both(True)

    def lamp_status(self) -> dict[str, int]:
        """Lamp dict for can-j1939 Dm1 / DtcLamp.get_data."""
        return {
            "pl": DtcLamp.OFF,
            "awl": DtcLamp.ON if self.dtc_spn110_fmi3 else DtcLamp.OFF,
            "rsl": DtcLamp.ON if self.dtc_spn190_fmi0 else DtcLamp.OFF,
            "mil": DtcLamp.OFF,
        }

    def dtc_list(self) -> list[dict[str, int]]:
        out: list[dict[str, int]] = []
        if self.dtc_spn110_fmi3:
            out.append({"spn": DTC1_SPN, "fmi": DTC1_FMI, "oc": 1})
        if self.dtc_spn190_fmi0:
            out.append({"spn": DTC2_SPN, "fmi": DTC2_FMI, "oc": 1})
        return out


def encode_dm1(state: DiagnosticState) -> bytes:
    """DM1 payload: 2 lamp bytes + 4 bytes per DTC, at least 8 bytes (J1939-73).

    No active faults → SPN/FMI/OC all zero ("no DTC"). One fault → padded with 0xFF
    to a single 8-byte frame. Two faults → 10 bytes, sent via BAM.
    """
    data = bytearray(DtcLamp().get_data(state.lamp_status()))
    dtcs = state.dtc_list()
    for dtc_dic in dtcs:
        word = DTC(spn=dtc_dic["spn"], fmi=dtc_dic["fmi"], oc=dtc_dic["oc"]).dtc
        data += word.to_bytes(4, "little")
    if not dtcs:
        data += bytes(4)
    data.extend([0xFF] * (8 - len(data)))
    return bytes(data)
