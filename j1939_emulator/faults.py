"""Fault injection for ELD testing: what the ECU does wrong on purpose.

SPN overrides, broadcast on/off and frozen meters live on SignalState (the encoders and the
meter thread read them); this module holds the session-level faults (silent ECU, request
handling) and lists everything that is currently not normal.
"""

from __future__ import annotations

from dataclasses import dataclass

from j1939_emulator.pgn import (
    OVERRIDABLE_SPNS,
    SPN_ERROR,
    SPN_NOT_AVAILABLE,
    SignalState,
)

# How the ECU handles Requests (PGN 59904) for the targeted PGNs.
REQ_NORMAL = "normal"
REQ_IGNORE = "ignore"  # no reply at all: the requester has to time out
REQ_NACK = "nack"  # NACK even for supported PGNs
REQ_DELAY = "delay"  # reply after request_delay_ms
REQUEST_MODES = (REQ_NORMAL, REQ_IGNORE, REQ_NACK, REQ_DELAY)
REQUEST_TARGET_ALL = 0  # every PGN instead of one
MAX_REQUEST_DELAY_MS = 10_000

# PGN key -> (acronym, PGN); the cyclic broadcasts that can be switched off.
BROADCAST_PGNS = {
    "eec1": ("EEC1", 61444),
    "ccvs": ("CCVS", 65265),
    "vd": ("VD", 65248),
    "hrvd": ("HRVD", 65217),
    "hours": ("HOURS", 65253),
}
_SPN_TEXT = {SPN_NOT_AVAILABLE: "not available (0xFF…)", SPN_ERROR: "error (0xFE…)"}
_REQ_TEXT = {REQ_IGNORE: "ignored", REQ_NACK: "NACKed"}


@dataclass
class FaultState:
    """Session-level faults; runtime only, kept across STOP / START, never saved."""

    silent: bool = False  # the ECU sends nothing at all, but stays connected
    request_mode: str = REQ_NORMAL
    request_target: int = REQUEST_TARGET_ALL  # PGN, or REQUEST_TARGET_ALL
    request_delay_ms: int = 500

    def request_fault_for(self, pgn: int) -> str:
        """The request mode that applies to a request for this PGN."""
        if self.request_target in (REQUEST_TARGET_ALL, pgn):
            return self.request_mode
        return REQ_NORMAL


def pgn_enabled(signals: SignalState, key: str) -> bool:
    return bool(getattr(signals, f"{key}_enabled"))


def active_faults(signals: SignalState, faults: FaultState) -> list[str]:
    """One short line per fault that is on, for the GUI badge and the trace."""
    out: list[str] = []
    if faults.silent:
        out.append("ECU silent: sends nothing")
    for key, (acronym, pgn) in BROADCAST_PGNS.items():
        if not pgn_enabled(signals, key):
            out.append(f"{acronym} (PGN {pgn}) broadcast off")
    for key, (spn, _pgn_key) in OVERRIDABLE_SPNS.items():
        mode = signals.spn_override.get(key)
        if mode in _SPN_TEXT:
            out.append(f"SPN {spn} sends {_SPN_TEXT[mode]}")
    if faults.request_mode != REQ_NORMAL:
        target = (
            "all PGNs" if faults.request_target == REQUEST_TARGET_ALL
            else f"PGN {faults.request_target}"
        )
        what = (
            f"delayed {faults.request_delay_ms} ms" if faults.request_mode == REQ_DELAY
            else _REQ_TEXT[faults.request_mode]
        )
        out.append(f"Requests for {target} {what}")
    if signals.freeze_odometer:
        out.append("Odometer frozen")
    if signals.freeze_hours:
        out.append("Engine hours frozen")
    return out
