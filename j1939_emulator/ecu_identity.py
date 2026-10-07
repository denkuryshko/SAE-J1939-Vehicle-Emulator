"""ECU identity: SA 0x00, J1939-81 NAME, VIN (PGN 65260)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from j1939 import Name

# Defaults
DEFAULT_VIN = "1HTMMAAL5GH123456"
DEFAULT_SOURCE_ADDRESS = 0x00
DEFAULT_INDUSTRY_GROUP = 1  # On-Highway Equipment
DEFAULT_VEHICLE_SYSTEM = 0  # Non-specific
DEFAULT_FUNCTION = 0  # Engine

# J1939-81 NAME fields with their bit widths, in the order j1939.Name takes them.
NAME_FIELDS = {
    "arbitrary_address_capable": 1,
    "industry_group": 3,
    "vehicle_system_instance": 4,
    "vehicle_system": 7,
    "function": 8,
    "function_instance": 5,
    "ecu_instance": 3,
    "manufacturer_code": 11,
    "identity_number": 21,
}

# PGN 65260 Vehicle Identification (VI) — PDU format/specific for send_pgn
PGN_VI = 65260  # 0xFEEC
VI_PDU_FORMAT = 0xFE
VI_PDU_SPECIFIC = 0xEC
VI_PRIORITY = 6

_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{1,17}$")


def validate_vin(vin: str, *, allow_empty: bool = False) -> str:
    """Normalize and validate VIN. Returns uppercase VIN."""
    if vin is None:
        raise ValueError("VIN is required")
    cleaned = str(vin).strip().upper()
    if not cleaned:
        if allow_empty:
            return ""
        raise ValueError("VIN cannot be empty")
    if len(cleaned) > 17:
        raise ValueError("VIN must be at most 17 characters")
    if not _VIN_RE.match(cleaned):
        raise ValueError(
            "VIN may only contain A–Z and 0–9 (excluding I, O, Q)"
        )
    return cleaned


_VIN_TRANSLIT = {
    **{str(d): d for d in range(10)},
    **dict(zip("ABCDEFGH", range(1, 9))),
    **dict(zip("JKLMNPR", (1, 2, 3, 4, 5, 7, 9))),
    **dict(zip("STUVWXYZ", range(2, 10))),
}
_VIN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)


def vin_check_digit_warning(vin: str) -> str | None:
    """Warn when a 17-char VIN fails the North American check digit (position 9).

    Not an error: test VINs and some non-NA VINs legitimately skip it, but ELDs
    and backends that validate VINs may reject them.
    """
    if len(vin) != 17:
        return None
    total = sum(_VIN_TRANSLIT[c] * w for c, w in zip(vin, _VIN_WEIGHTS))
    expected = "X" if total % 11 == 10 else str(total % 11)
    if vin[8] == expected:
        return None
    return f"VIN check digit (position 9) is {vin[8]!r}, expected {expected!r}"


@dataclass
class EcuIdentity:
    """Single ECU node identity. The 64-bit NAME is built from the J1939-81 fields."""

    vin: str = DEFAULT_VIN
    source_address: int = DEFAULT_SOURCE_ADDRESS
    arbitrary_address_capable: int = 0
    industry_group: int = DEFAULT_INDUSTRY_GROUP
    vehicle_system_instance: int = 0
    vehicle_system: int = DEFAULT_VEHICLE_SYSTEM
    function: int = DEFAULT_FUNCTION
    function_instance: int = 0
    ecu_instance: int = 0
    manufacturer_code: int = 0
    identity_number: int = 0
    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.vin = validate_vin(self.vin)
        for key, bits in NAME_FIELDS.items():
            value = int(getattr(self, key))
            if not 0 <= value < (1 << bits):
                raise ValueError(f"NAME field {key}={value} out of range 0..{(1 << bits) - 1}")
            setattr(self, key, value)

    @staticmethod
    def name_fields(name: int) -> dict[str, int]:
        """Split a 64-bit NAME into its J1939-81 fields."""
        decoded = Name(value=int(name))
        return {key: int(getattr(decoded, key)) for key in NAME_FIELDS}

    @property
    def name(self) -> int:
        return int(Name(**{key: getattr(self, key) for key in NAME_FIELDS}).value)

    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def clear_listeners(self) -> None:
        self._listeners.clear()

    def notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    def set_vin(self, vin: str) -> str:
        self.vin = validate_vin(vin)
        self.notify()
        return self.vin

    @property
    def name_hex(self) -> str:
        return f"0x{self.name:016X}"

    def vin_payload(self) -> list[int]:
        """PGN 65260 payload: ASCII VIN + '*' delimiter (SPN 237 is variable length; > 8 → BAM/TP)."""
        return list((self.vin + "*").encode("ascii"))
