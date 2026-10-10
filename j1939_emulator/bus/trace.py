"""Decoded J1939 trace of everything the ECU exchanges except its own cyclic broadcasts.

Meant for bench debugging of an ELD: which requests it sends and to which address,
which transport frames it answers with (CTS, EOMA, Abort), what the emulator sent back
and when, and send / bus errors. One file per START, kept in the app state directory.

Every frame (cyclic broadcasts included) also goes into small in-memory rings of raw
entries for the GUI Traffic Monitor; the rings never reach the file. Cyclic broadcasts
have a ring of their own, so a 20 ms EEC1 cannot push an ELD request out of view.
"""

from __future__ import annotations

import heapq
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import can

from j1939_emulator.meters_store import state_file
from j1939_emulator.pgn import KM_PER_MI

TRACE_DIR_NAME = "traces"
_KEEP_FILES = 20
_MAX_FILE_BYTES = 50 * 1024 * 1024
_RECENT_LINES = 500
_ERROR_SUMMARY_S = 1.0
TRAFFIC_ROWS = 1000  # raw frames kept in memory for the Traffic Monitor, per ring

_PGN_NAMES = {
    59904: "Request",
    59392: "ACK",
    60928: "Address Claimed",
    60416: "TP.CM",
    60160: "TP.DT",
    65260: "VI (VIN)",
    65226: "DM1",
    61444: "EEC1",
    65265: "CCVS",
    65248: "VD",
    65217: "HRVD",
    65253: "HOURS",
}
_ACK_CONTROL = {0: "ACK", 1: "NACK", 2: "Access Denied", 3: "Cannot Respond"}
_ABORT_REASONS = {
    1: "already in a session",
    2: "resources needed elsewhere",
    3: "timeout",
    4: "CTS while sending",
    5: "max retransmit reached",
    6: "unexpected data transfer",
    7: "bad sequence number",
    8: "duplicate sequence number",
    9: "message too large",
}


def trace_dir() -> Path:
    return state_file().parent / TRACE_DIR_NAME


def pgn_label(pgn: int) -> str:
    name = _PGN_NAMES.get(pgn)
    return f"{pgn} ({name})" if name else str(pgn)


def pgn_name(pgn: int) -> str:
    """Short name of a known PGN ("EEC1", "Request" …), or "" when unknown."""
    return _PGN_NAMES.get(pgn, "")


def split_id(arb_id: int) -> tuple[int, int, int, int]:
    """(priority, pgn, source address, destination address) of a 29-bit J1939 CAN ID."""
    priority = (arb_id >> 26) & 0x7
    dp = (arb_id >> 24) & 0x3
    pf = (arb_id >> 16) & 0xFF
    ps = (arb_id >> 8) & 0xFF
    sa = arb_id & 0xFF
    if pf < 240:  # PDU1: PS is the destination
        return priority, (dp << 16) | (pf << 8), sa, ps
    return priority, (dp << 16) | (pf << 8) | ps, sa, 0xFF


def _pgn_at(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 3], "little")


def describe(arb_id: int, data: bytes) -> str:
    """Human-readable meaning of one J1939 frame (transport frames, requests, claims, ACK)."""
    _prio, pgn, sa, da = split_id(arb_id)
    if pgn == 59904 and len(data) >= 3:
        return f"Request for PGN {pgn_label(_pgn_at(data, 0))}"
    if pgn == 60928 and len(data) == 8:
        name = int.from_bytes(data, "little")
        what = "Cannot Claim Address" if sa == 0xFE else "Address Claimed"
        return f"{what}, NAME 0x{name:016X}"
    if pgn == 59392 and len(data) == 8:
        control = _ACK_CONTROL.get(data[0], f"control {data[0]}")
        return f"{control} for PGN {pgn_label(_pgn_at(data, 5))}, to 0x{data[4]:02X}"
    if pgn == 60416 and len(data) == 8:
        ctrl = data[0]
        target = pgn_label(_pgn_at(data, 5))
        size = int.from_bytes(data[1:3], "little")
        if ctrl == 0x20:
            return f"TP.CM BAM: {size} bytes in {data[3]} packets, PGN {target}"
        if ctrl == 0x10:
            return f"TP.CM RTS: {size} bytes in {data[3]} packets (max {data[4]}/CTS), PGN {target}"
        if ctrl == 0x11:
            return f"TP.CM CTS: send {data[1]} packets from #{data[2]}, PGN {target}"
        if ctrl == 0x13:
            return f"TP.CM EOMA: {size} bytes / {data[3]} packets received, PGN {target}"
        if ctrl == 0xFF:
            reason = _ABORT_REASONS.get(data[1], "reason unknown")
            return f"TP.CM Abort ({data[1]}: {reason}), PGN {target}"
        return f"TP.CM control 0x{ctrl:02X}, PGN {target}"
    if pgn == 60160 and data:
        return f"TP.DT packet #{data[0]}"
    return f"PGN {pgn_label(pgn)}"


# --- SPN decoding (J1939-71), read back from the bytes on the wire ---

_KM_PER_MI = KM_PER_MI
_PROTOCOL_PGNS = {59904, 59392, 60928, 60416, 60160}
_LAMP_SHIFTS = (("MIL", 6), ("RSL", 4), ("AWL", 2), ("PL", 0))


def _num(value: float, decimals: int) -> str:
    text = f"{value:.{decimals}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _scaled(data: bytes, offset: int, size: int, scale: float) -> float | str:
    """SPN value at data[offset:offset+size] (little endian) times scale, or why it has none.

    J1939-71 ranges: above 0xFA… is reserved, 0xFE… is an error indicator, 0xFF… not available.
    """
    if len(data) < offset + size:
        return "missing"
    raw = int.from_bytes(data[offset:offset + size], "little")
    top = raw >> (8 * (size - 1))
    if top == 0xFF:
        return "not available"
    if top == 0xFE:
        return "error"
    if top > 0xFA:
        return f"reserved 0x{raw:0{size * 2}X}"
    return raw * scale


def decode_dm1(payload: bytes) -> str:
    """DM1 (PGN 65226): active DTCs (SPN / FMI / occurrence count) and lamps that are on."""
    if len(payload) < 6:
        return ""
    lamps = [name for name, shift in _LAMP_SHIFTS if (payload[0] >> shift) & 0x3 == 1]
    dtcs = []
    for i in range(2, len(payload) - 3, 4):
        chunk = payload[i:i + 4]
        if chunk in (b"\x00\x00\x00\x00", b"\xff\xff\xff\xff"):
            continue
        spn = chunk[0] | (chunk[1] << 8) | ((chunk[2] >> 5) << 16)
        dtcs.append(f"SPN {spn} / FMI {chunk[2] & 0x1F} (OC {chunk[3] & 0x7F})")
    faults = ", ".join(dtcs) if dtcs else "no active DTCs"
    return f"DM1: {faults}; lamps {'+'.join(lamps) if lamps else 'off'}"


def decode_payload(pgn: int, data: bytes) -> str:
    """Engineering values of the SPNs this emulator knows in one PGN's payload; "" if unknown."""
    if pgn == 61444:
        rpm = _scaled(data, 3, 2, 0.125)
        value = f"{_num(rpm, 3)} rpm" if isinstance(rpm, float) else rpm
        return f"SPN 190 Engine Speed: {value}"
    if pgn == 65265:
        kmh = _scaled(data, 1, 2, 1 / 256)
        if isinstance(kmh, float):
            value = f"{_num(kmh / _KM_PER_MI, 1)} mph ({_num(kmh, 2)} km/h)"
        else:
            value = kmh
        return f"SPN 84 Wheel-Based Speed: {value}"
    if pgn == 65248:
        km = _scaled(data, 4, 4, 0.125)
        if isinstance(km, float):
            value = f"{_num(km / _KM_PER_MI, 1)} mi ({_num(km, 3)} km)"
        else:
            value = km
        return f"SPN 245 Total Distance: {value}"
    if pgn == 65217:
        km = _scaled(data, 0, 4, 0.005)
        if isinstance(km, float):
            value = f"{_num(km / _KM_PER_MI, 2)} mi ({_num(km, 3)} km)"
        else:
            value = km
        return f"SPN 917 HR Total Distance: {value}"
    if pgn == 65253:
        hours = _scaled(data, 0, 4, 0.05)
        value = f"{_num(hours, 2)} h" if isinstance(hours, float) else hours
        return f"SPN 247 Engine Hours: {value}"
    if pgn == 65226:
        return decode_dm1(data)
    if pgn == 65260:
        vin = data.decode("ascii", errors="replace").split("*")[0]
        return f"VIN {vin} ({len(vin)} chars)"
    return ""


def decode(arb_id: int, data: bytes) -> str:
    """What one frame means: protocol frames via describe(), known data PGNs as SPN values."""
    _prio, pgn, _sa, _da = split_id(arb_id)
    if pgn in _PROTOCOL_PGNS:
        return describe(arb_id, data)
    return decode_payload(pgn, data)


_TP_CM_TYPES = {0x10: "RTS", 0x11: "CTS", 0x13: "EOMA", 0x20: "BAM", 0xFF: "ABORT"}


def frame_type(direction: str, arb_id: int, data: bytes) -> str:
    """Short message type for the Traffic Monitor, from the same fields describe() uses."""
    if direction == "TX!":
        return "ERROR"
    _prio, pgn, _sa, da = split_id(arb_id)
    if pgn == 59904:
        return "REQUEST"
    if pgn == 59392 and data:
        return _ACK_CONTROL.get(data[0], "ACK").upper()
    if pgn == 60928:
        return "ADDRESS CLAIM"
    if pgn == 60416 and data:
        return f"TP.CM {_TP_CM_TYPES[data[0]]}" if data[0] in _TP_CM_TYPES else "TP.CM"
    if pgn == 60160:
        return "TP.DT"
    return "BROADCAST" if da == 0xFF else "DATA"


@dataclass(frozen=True)
class TrafficEntry:
    """One frame (or bus-error summary, arb_id None) as the Traffic Monitor shows it."""

    seq: int
    at: float  # wall clock, time.time()
    direction: str  # TX, RX, TX! (send failed) or ERR (bus error frames)
    arb_id: int | None
    data: bytes
    kind: str
    text: str = ""  # error summary, or the reassembled message on a transfer's last TP.DT
    cyclic: bool = False  # one of this ECU's cyclic broadcasts (EEC1, CCVS, VD, HRVD, HOURS)


def _payload_text(pgn: int, payload: bytes) -> str:
    if pgn == 65260:
        return repr(payload.decode("ascii", errors="replace"))
    return payload.hex(" ").upper()


class J1939Trace(can.Listener):
    """Writes decoded frames to a log file and keeps the last lines in memory for the UI."""

    def __init__(self, own_sa: int, header: list[str], directory: Path | None = None) -> None:
        self._own_sa = own_sa & 0xFF
        self._lock = threading.Lock()
        self._recent: deque[str] = deque(maxlen=_RECENT_LINES)
        self._count = 0
        self._traffic: deque[TrafficEntry] = deque(maxlen=TRAFFIC_ROWS)
        self._cyclic: deque[TrafficEntry] = deque(maxlen=TRAFFIC_ROWS)
        self._traffic_seq = 0
        self._last_t: float | None = None
        self._transfers: dict[tuple[int, int], dict] = {}
        self._errors = 0
        self._ack_errors = 0
        self._error_since = 0.0
        self._bytes = 0
        self._full = False
        self._closed = False
        self.path: Path | None = None
        self._file = None
        directory = directory or trace_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self.path = directory / time.strftime("trace-%Y%m%d-%H%M%S.log")
            self._file = open(self.path, "a", encoding="utf-8", buffering=1)
            _prune(directory)
        except OSError:
            self.path = None
            self._file = None
        for line in header:
            self._write(f"# {line}")
        self._write("# time          delta     dir  CAN ID    prio  PGN   SA->DA  data                     meaning")

    # --- can.Listener: frames from other nodes and bus errors ---

    def on_message_received(self, msg: can.Message) -> None:
        if msg.is_error_frame:
            self._error_frame(msg)
            return
        if not msg.is_rx or not msg.is_extended_id:
            return  # our own echo / not J1939
        self.frame("RX", msg.arbitration_id, bytes(msg.data))

    # --- called by the session ---

    def frame(self, direction: str, arb_id: int, data: bytes, note: str = "") -> None:
        self._flush_errors()
        prio, pgn, sa, da = split_id(arb_id)
        done = self._reassemble(pgn, sa, da, data)
        complete = ""
        if done:
            decoded = decode_payload(*done) or _payload_text(*done)
            complete = f"complete PGN {pgn_label(done[0])}: {decoded}"
        self._record(direction, arb_id, data, frame_type(direction, arb_id, data), complete)
        meaning = describe(arb_id, data)
        if done:
            meaning += f" -> complete PGN {pgn_label(done[0])}: {_payload_text(*done)}"
        if note:
            meaning += f"  [{note}]"
        self._line(
            f"{direction:<4} {arb_id:08X}  P{prio}  {pgn:>5}  {sa:02X}->{da:02X}  "
            f"{data.hex(' ').upper():<23}  {meaning}"
        )

    def broadcast(self, arb_id: int, data: bytes, ok: bool) -> None:
        """A cyclic broadcast (EEC1, CCVS …): Traffic Monitor only, never written to the file."""
        direction = "TX" if ok else "TX!"
        self._record(direction, arb_id, data, frame_type(direction, arb_id, data), cyclic=True)

    def note(self, text: str) -> None:
        self._line(f"---  {text}")

    def recent(self) -> tuple[int, list[str]]:
        """(total lines written so far, last lines); the total lets a viewer fetch only new ones."""
        with self._lock:
            return self._count, list(self._recent)

    def traffic_since(self, seq: int) -> tuple[int, list[TrafficEntry]]:
        """(newest seq, entries after seq still in the rings, oldest first); seq 0 returns all."""
        with self._lock:
            last = self._traffic_seq
            if seq >= last:
                return last, []
            events = _newer(self._traffic, seq)
            cyclic = _newer(self._cyclic, seq)
        return last, list(heapq.merge(events, cyclic, key=lambda e: e.seq))

    def export_candump(self, path: Path, channel: str = "can0") -> int:
        """Write the frames still in memory as a candump -l log (canplayer, SavvyCAN, Wireshark).

        Frames that failed to send and bus-error summaries are left out. Returns frames written.
        """
        _last, entries = self.traffic_since(0)
        lines = [
            f"({e.at:.6f}) {channel} {e.arb_id:08X}#{e.data.hex().upper()}"
            for e in entries
            if e.arb_id is not None and e.direction in ("TX", "RX")
        ]
        path.write_text("".join(line + "\n" for line in lines), encoding="ascii")
        return len(lines)

    def traffic_seq(self) -> int:
        with self._lock:
            return self._traffic_seq

    def close(self, text: str = "") -> None:
        """Write a closing note and close the file; later calls do nothing."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._flush_errors(force=True)
        if text:
            self.note(text)
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None

    # --- internals ---

    def _reassemble(self, pgn: int, sa: int, da: int, data: bytes) -> tuple[int, bytes] | None:
        key = (sa, da)
        if pgn == 60416 and len(data) == 8 and data[0] in (0x10, 0x20):
            with self._lock:
                self._transfers[key] = {
                    "pgn": _pgn_at(data, 5),
                    "size": int.from_bytes(data[1:3], "little"),
                    "buf": bytearray(),
                }
            return None
        if pgn != 60160 or not data:
            return None
        with self._lock:
            t = self._transfers.get(key)
            if t is None:
                return None
            t["buf"] += data[1:]
            if len(t["buf"]) < t["size"]:
                return None
            del self._transfers[key]
            return t["pgn"], bytes(t["buf"][: t["size"]])

    def _error_frame(self, msg: can.Message) -> None:
        with self._lock:
            if self._errors == 0:
                self._error_since = time.time()
            self._errors += 1
            if msg.arbitration_id & 0x20:  # SocketCAN CAN_ERR_ACK
                self._ack_errors += 1
        self._flush_errors()

    def _flush_errors(self, force: bool = False) -> None:
        with self._lock:
            if not self._errors or (not force and time.time() - self._error_since < _ERROR_SUMMARY_S):
                return
            errors, acks = self._errors, self._ack_errors
            self._errors = self._ack_errors = 0
        ack = f", {acks} of them ACK errors (nobody acknowledges our frames)" if acks else ""
        self.note(f"bus error frames: {errors}{ack}")
        self._record("ERR", None, b"", "ERROR", f"bus error frames: {errors}{ack}")

    def _record(
        self,
        direction: str,
        arb_id: int | None,
        data: bytes,
        kind: str,
        text: str = "",
        cyclic: bool = False,
    ) -> None:
        with self._lock:
            self._traffic_seq += 1
            ring = self._cyclic if cyclic else self._traffic
            ring.append(
                TrafficEntry(
                    self._traffic_seq, time.time(), direction, arb_id, data, kind, text, cyclic
                )
            )

    def _line(self, body: str) -> None:
        now = time.time()
        with self._lock:
            delta = 0.0 if self._last_t is None else (now - self._last_t) * 1000
            self._last_t = now
        stamp = time.strftime("%H:%M:%S", time.localtime(now)) + f".{int(now * 1000) % 1000:03d}"
        self._write(f"{stamp}  {f'+{delta:.1f}ms':>9}  {body}")

    def _write(self, line: str) -> None:
        with self._lock:
            self._count += 1
            self._recent.append(line)
            if self._file is None or self._full:
                return
            self._bytes += len(line) + 1
            if self._bytes > _MAX_FILE_BYTES:
                self._full = True
                line = "# trace file size limit reached; further lines are only shown in the app"
            try:
                self._file.write(line + "\n")
            except OSError:
                self._file = None


def _newer(ring: deque[TrafficEntry], seq: int) -> list[TrafficEntry]:
    """Entries of a ring with seq above the given one; walks back only over the new ones."""
    out: list[TrafficEntry] = []
    for entry in reversed(ring):
        if entry.seq <= seq:
            break
        out.append(entry)
    out.reverse()
    return out


def _prune(directory: Path) -> None:
    files = sorted(directory.glob("trace-*.log"))
    for old in files[:-_KEEP_FILES]:
        try:
            old.unlink()
        except OSError:
            pass
