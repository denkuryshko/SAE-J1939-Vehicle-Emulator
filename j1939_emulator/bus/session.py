"""Bus session: START / STOP / RESET, cyclic PGN TX, J1939 claim/VIN/DM1, live stats."""

from __future__ import annotations

import heapq
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import can
from j1939 import ControllerApplication, ElectronicControlUnit, Name

# can-j1939 job-thread cleanup typos CoUnitialize on Windows; map to real API.
try:
    import pythoncom as _pythoncom

    if not hasattr(_pythoncom, "CoUnitialize"):
        _pythoncom.CoUnitialize = getattr(
            _pythoncom, "CoUninitialize", lambda: None
        )
except Exception:
    pass

from j1939_emulator.bus.detect import DetectedChannel, EmulationMode
from j1939_emulator.diagnostics import (
    DM1_CYCLE_MS,
    DM1_PDU_FORMAT,
    DM1_PDU_SPECIFIC,
    DM1_PRIORITY,
    DiagnosticState,
    encode_dm1,
)
from j1939_emulator.ecu_identity import (
    PGN_VI,
    VI_PDU_FORMAT,
    VI_PDU_SPECIFIC,
    VI_PRIORITY,
    EcuIdentity,
)
from j1939_emulator.meters_store import save_meters
from j1939_emulator.pgn import (
    CAN_ID_CCVS,
    CAN_ID_EEC1,
    CAN_ID_HOURS,
    CAN_ID_VD,
    SignalState,
    encode_ccvs,
    encode_eec1,
    encode_hours,
    encode_vd,
)

_BITS_PER_FRAME = 142
_METER_TICK_S = 0.2
_METER_SAVE_S = 10.0

_GLOBAL_ADDRESS = 0xFF
# Acknowledgement PGN 59392 (0xE800)
_ACK_PDU_FORMAT = 0xE8
_ACK_PRIORITY = 6
_ACK_CONTROL_NACK = 0x01
PGN_DM1 = 65226

# PGN → (priority, encoder) answered on Request (PGN 59904).
_REQUESTABLE: dict[int, tuple[int, Callable[[SignalState], bytes]]] = {
    61444: (3, encode_eec1),
    65265: (6, encode_ccvs),
    65248: (6, encode_vd),
    65253: (6, encode_hours),
}
_USB_SETTLE_S = 0.50
_JOIN_TIMEOUT_S = 3.0


def _set_windows_timer_resolution(enable: bool) -> None:
    """Request 1 ms timer resolution on Windows for tighter cyclic TX."""
    try:
        import ctypes

        if enable:
            ctypes.windll.winmm.timeBeginPeriod(1)
        else:
            ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        pass


def _force_release_bus(bus: can.BusABC | None) -> None:
    """Ensure USB backends fully release the device handle.

    The candleLight python-can backend resets channels in ``shutdown()`` but
    does not call ``CandleDevice.close()``, so the next open fails with
    ``Cannot open device`` until the process exits.
    """
    if bus is None:
        return
    try:
        bus.shutdown()
    except Exception:
        pass
    device = getattr(bus, "_device", None)
    if device is None:
        return
    try:
        if hasattr(device, "is_open") and not device.is_open:
            return
    except Exception:
        pass
    try:
        device.close()
    except Exception:
        pass


class BusHealth(str, Enum):
    OK = "OK"
    NO_ACK = "NO_ACK"  # nobody acknowledges our frames (wiring, termination, listen-only peers)
    TX_FAILING = "TX_FAILING"  # the adapter refuses / times out sends
    BUS_ERRORS = "BUS_ERRORS"  # other error frames (bit/stuff/form errors, error-passive …)


@dataclass
class SessionStats:
    running: bool = False
    uptime_s: float = 0.0
    tx_count: int = 0
    load_pct: float = 0.0
    bitrate: int = 500_000
    mode: EmulationMode = EmulationMode.VIRTUAL
    channel_label: str = ""
    sa: int = 0x00
    active_dtcs: int = 0
    address_claimed: bool = False
    bus_health: BusHealth = BusHealth.OK
    peers: int = 0


@dataclass(order=True)
class _HeapItem:
    next_t: float
    seq: int
    entry_id: int = field(compare=False)


@dataclass
class _SchedEntry:
    entry_id: int
    arb_id: int
    period_fn: Callable[[], float]
    data_fn: Callable[[], bytes]
    period_s: float = 0.02
    last_t: float = 0.0
    next_t: float = 0.0


# SocketCAN-style error class bits in an error frame's arbitration_id (candle / gs_usb, socketcan …)
_CAN_ERR_ACK = 0x20
_HEALTH_WINDOW_S = 3.0


class _BusHealthMonitor(can.Listener):
    """Watches error frames, send failures and other nodes' traffic on the bus."""

    def __init__(self, own_sa: int) -> None:
        self._own_sa = own_sa & 0xFF
        self._lock = threading.Lock()
        self._last_ack_error = -1e9
        self._last_error = -1e9
        self._last_tx_fail = -1e9
        self._peers: dict[int, float] = {}

    def on_message_received(self, msg: can.Message) -> None:
        now = time.monotonic()
        with self._lock:
            if msg.is_error_frame:
                self._last_error = now
                if msg.arbitration_id & _CAN_ERR_ACK:
                    self._last_ack_error = now
                return
            if not msg.is_rx or not msg.is_extended_id:
                return  # our own TX echo, or not J1939
            sa = msg.arbitration_id & 0xFF
            if sa != self._own_sa:
                self._peers[sa] = now

    def tx_failed(self) -> None:
        with self._lock:
            self._last_tx_fail = time.monotonic()

    def snapshot(self) -> tuple[BusHealth, int]:
        """(health, number of other nodes heard in the last few seconds)."""
        now = time.monotonic()
        cutoff = now - _HEALTH_WINDOW_S
        with self._lock:
            peers = sum(1 for t in self._peers.values() if t >= cutoff)
            if self._last_ack_error >= cutoff:
                return BusHealth.NO_ACK, peers
            if self._last_tx_fail >= cutoff:
                return BusHealth.TX_FAILING, peers
            if self._last_error >= cutoff:
                return BusHealth.BUS_ERRORS, peers
            return BusHealth.OK, peers


class _PgnScheduler(threading.Thread):
    """Single worker: heap of next-fire times (scales beyond a few PGNs)."""

    def __init__(
        self,
        bus: can.BusABC,
        entries: list[tuple[int, Callable[[], float], Callable[[], bytes]]],
        on_tx: Callable[[], None],
        on_tx_fail: Callable[[], None],
    ) -> None:
        super().__init__(daemon=True, name="pgn-scheduler")
        self._bus = bus
        self._on_tx = on_tx
        self._on_tx_fail = on_tx_fail
        self._stop_event = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._seq = 0
        self._entries: dict[int, _SchedEntry] = {}
        self._heap: list[_HeapItem] = []
        now = time.monotonic()
        for i, (arb_id, period_fn, data_fn) in enumerate(entries):
            period = max(0.001, float(period_fn()))
            entry = _SchedEntry(
                entry_id=i,
                arb_id=arb_id,
                period_fn=period_fn,
                data_fn=data_fn,
                period_s=period,
                last_t=now,
                next_t=now,  # fire immediately on start (matches prior behaviour)
            )
            self._entries[i] = entry
            self._push(entry)

    def _push(self, entry: _SchedEntry) -> None:
        self._seq += 1
        heapq.heappush(
            self._heap, _HeapItem(entry.next_t, self._seq, entry.entry_id)
        )

    def stop(self) -> None:
        self._stop_event.set()
        self._wake.set()

    def notify_periods_changed(self) -> None:
        """Recompute next fire from last_t + new period; wake the waiter."""
        now = time.monotonic()
        with self._lock:
            changed = False
            for entry in self._entries.values():
                new_p = max(0.001, float(entry.period_fn()))
                if abs(new_p - entry.period_s) < 1e-9:
                    continue
                entry.period_s = new_p
                nxt = entry.last_t + new_p
                if nxt < now:
                    nxt = now
                entry.next_t = nxt
                changed = True
            if changed:
                self._heap.clear()
                for entry in self._entries.values():
                    self._push(entry)
                self._wake.set()

    def _precise_wait(self, deadline: float) -> None:
        """Wait until deadline or wake/stop; spin the last ~1 ms for accuracy."""
        while not self._stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            if self._wake.is_set():
                return
            if remaining > 0.002:
                self._wake.wait(remaining - 0.001)
            else:
                while (
                    not self._stop_event.is_set()
                    and not self._wake.is_set()
                    and time.monotonic() < deadline
                ):
                    pass
                return

    def run(self) -> None:
        _set_windows_timer_resolution(True)
        try:
            while not self._stop_event.is_set():
                with self._lock:
                    if not self._heap:
                        wait_s = 0.05
                        deadline = None
                    else:
                        item = self._heap[0]
                        entry = self._entries.get(item.entry_id)
                        if entry is None or item.next_t != entry.next_t:
                            heapq.heappop(self._heap)
                            continue
                        deadline = entry.next_t
                        wait_s = deadline - time.monotonic()

                if deadline is None or wait_s > 0:
                    self._wake.clear()
                    if deadline is None:
                        self._wake.wait(wait_s)
                    else:
                        self._precise_wait(deadline)
                    if self._stop_event.is_set():
                        break
                    if self._wake.is_set():
                        self._wake.clear()
                        continue

                due: list[_SchedEntry] = []
                now = time.monotonic()
                with self._lock:
                    while self._heap and self._heap[0].next_t <= now + 1e-6:
                        item = heapq.heappop(self._heap)
                        entry = self._entries.get(item.entry_id)
                        if entry is None or item.next_t != entry.next_t:
                            continue
                        due.append(entry)

                for entry in due:
                    if self._stop_event.is_set():
                        break
                    data = entry.data_fn()
                    msg = can.Message(
                        arbitration_id=entry.arb_id,
                        data=data,
                        is_extended_id=True,
                        dlc=min(8, len(data)),
                    )
                    try:
                        self._bus.send(msg, timeout=0.2)
                        self._on_tx()
                    except Exception:
                        if self._stop_event.is_set():
                            break
                        self._on_tx_fail()
                    now = time.monotonic()
                    with self._lock:
                        entry.last_t = now
                        entry.period_s = max(0.001, float(entry.period_fn()))
                        entry.next_t = now + entry.period_s
                        self._push(entry)
        finally:
            _set_windows_timer_resolution(False)


class _MeterThread(threading.Thread):
    """Advances engine hours and odometer in real time while the session runs."""

    def __init__(self, signals: SignalState, on_save: Callable[[], None] | None = None) -> None:
        super().__init__(name="j1939-meters", daemon=True)
        self._signals = signals
        self._on_save = on_save
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        last = time.monotonic()
        last_save = last
        while not self._stop_event.wait(_METER_TICK_S):
            now = time.monotonic()
            self._signals.advance_meters(now - last)
            last = now
            if self._on_save is not None and now - last_save >= _METER_SAVE_S:
                self._on_save()
                last_save = now
        self._signals.advance_meters(time.monotonic() - last)


@dataclass
class EmulatorSession:
    """Single-channel emulation session (one ECU node)."""

    signals: SignalState = field(default_factory=SignalState)
    identity: EcuIdentity = field(default_factory=EcuIdentity)
    diagnostics: DiagnosticState = field(default_factory=DiagnosticState)
    bitrate: int = 500_000
    mode: EmulationMode = EmulationMode.VIRTUAL
    # Save odometer / engine hours per VIN between runs (see meters_store).
    persist_meters: bool = False

    _bus: can.BusABC | None = field(default=None, init=False, repr=False)
    _ecu: ElectronicControlUnit | None = field(default=None, init=False, repr=False)
    _ca: ControllerApplication | None = field(default=None, init=False, repr=False)
    _scheduler: _PgnScheduler | None = field(default=None, init=False, repr=False)
    _channel: DetectedChannel | None = field(default=None, init=False, repr=False)
    _running: bool = field(default=False, init=False)
    _started_at: float | None = field(default=None, init=False)
    _tx_count: int = field(default=0, init=False)
    _frozen_uptime: float = field(default=0.0, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _stats_lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _tx_window_start: float = field(default=0.0, init=False)
    _tx_window_count: int = field(default=0, init=False)
    _load_pct: float = field(default=0.0, init=False)
    _period_listener: Callable[[], None] | None = field(
        default=None, init=False, repr=False
    )
    _meters: _MeterThread | None = field(default=None, init=False, repr=False)
    _health: _BusHealthMonitor | None = field(default=None, init=False, repr=False)

    @property
    def running(self) -> bool:
        return self._running

    @property
    def channel(self) -> DetectedChannel | None:
        return self._channel

    @property
    def address_claimed(self) -> bool:
        if self._ca is None:
            return False
        return self._ca.state == ControllerApplication.State.NORMAL

    def stats(self) -> SessionStats:
        with self._lock:
            with self._stats_lock:
                if self._running and self._started_at is not None:
                    uptime = time.monotonic() - self._started_at
                    self._update_load_locked()
                else:
                    uptime = self._frozen_uptime
                tx_count = self._tx_count
                load = 0.0 if not self._running else self._load_pct
            label = self._channel.label if self._channel else ""
            health, peers = (
                self._health.snapshot()
                if self._running and self._health is not None
                else (BusHealth.OK, 0)
            )
            return SessionStats(
                running=self._running,
                uptime_s=uptime,
                tx_count=tx_count,
                load_pct=load,
                bitrate=self.bitrate,
                mode=self.mode,
                channel_label=label,
                sa=self.identity.source_address & 0xFF,
                active_dtcs=self.diagnostics.active_count,
                address_claimed=self.address_claimed if self._running else False,
                bus_health=health,
                peers=peers,
            )

    def start(self, channel: DetectedChannel, bitrate: int | None = None) -> None:
        with self._lock:
            if self._running:
                self._stop_locked()
            if bitrate is not None:
                self.bitrate = int(bitrate)
            try:
                self._begin_locked(channel)
            except Exception:
                self._stop_locked()
                raise

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()
        # Also covers values set by hand while stopped (GUI QUIT / CLI quit call stop()).
        self.save_meters()

    def save_meters(self) -> None:
        if self.persist_meters:
            save_meters(self.signals, self.identity.vin)

    def reset(self, channel: DetectedChannel | None = None, bitrate: int | None = None) -> None:
        with self._lock:
            ch = channel or self._channel
            if ch is None:
                raise RuntimeError("No channel selected for RESET")
            if bitrate is not None:
                self.bitrate = int(bitrate)
            self._stop_locked()
            try:
                self._begin_locked(ch)
            except Exception:
                self._stop_locked()
                raise

    def set_vin(self, vin: str) -> str:
        """Update VIN; re-broadcast VI while running."""
        cleaned = self.identity.set_vin(vin)
        with self._lock:
            if self._running and self._ca is not None and self.address_claimed:
                self._broadcast_vin_locked()
        return cleaned

    def set_dtc1(self, active: bool) -> None:
        self.diagnostics.set_dtc1(active)
        with self._lock:
            self._sync_dm1_locked()

    def set_dtc2(self, active: bool) -> None:
        self.diagnostics.set_dtc2(active)
        with self._lock:
            self._sync_dm1_locked()

    def set_dtcs(self, dtc1: bool | None = None, dtc2: bool | None = None) -> None:
        if dtc1 is not None:
            self.diagnostics.dtc_spn110_fmi3 = bool(dtc1)
        if dtc2 is not None:
            self.diagnostics.dtc_spn190_fmi0 = bool(dtc2)
        self.diagnostics.notify()
        with self._lock:
            self._sync_dm1_locked()

    def clear_all_dtcs(self) -> None:
        self.diagnostics.clear_all()
        with self._lock:
            self._sync_dm1_locked()

    def inject_both_dtcs(self) -> None:
        self.diagnostics.inject_both()
        with self._lock:
            self._sync_dm1_locked()

    def _bus_kwargs(self, channel: DetectedChannel) -> dict[str, Any]:
        kwargs = dict(channel.bus_kwargs)
        if channel.interface != "virtual":
            kwargs.setdefault("bitrate", self.bitrate)
        if kwargs.get("interface") == "vector":
            kwargs.setdefault("app_name", "python-can")
        # Own claim frames need not echo; peer tests use a second Bus.
        kwargs.setdefault("receive_own_messages", False)
        return kwargs

    def _begin_locked(self, channel: DetectedChannel) -> None:
        self.mode = channel.kind
        self._channel = channel
        self._ecu = ElectronicControlUnit()
        try:
            self._bus = self._ecu.connect(**self._bus_kwargs(channel))
        except Exception:
            try:
                self._ecu.stop()
            except Exception:
                pass
            self._ecu = None
            self._bus = None
            raise
        self._health = _BusHealthMonitor(self.identity.source_address)
        # can-j1939 owns the bus Notifier; piggyback on it to see error frames and peer traffic.
        self._ecu._notifier.add_listener(self._health)

        name = Name(value=int(self.identity.name))
        self._ca = ControllerApplication(
            name, device_address_preferred=int(self.identity.source_address) & 0xFF
        )
        self._ecu.add_ca(controller_application=self._ca)
        self._ca.subscribe_request(self._on_request)
        self._ca.start()
        try:
            self._wait_claim_locked(timeout_s=1.5)
        except Exception:
            self._stop_locked()
            raise

        self._started_at = time.monotonic()
        with self._stats_lock:
            self._tx_count = 0
            self._tx_window_start = self._started_at
            self._tx_window_count = 0
            self._load_pct = 0.0
        self._frozen_uptime = 0.0
        self._running = True
        self._start_scheduler_locked()
        self._meters = _MeterThread(self.signals, self.save_meters if self.persist_meters else None)
        self._meters.start()
        self._broadcast_vin_locked()
        # DM1 goes out every second even with no faults (J1939-73), so an ELD sees faults clear.
        self._send_dm1()
        self._ca.add_timer(DM1_CYCLE_MS / 1000.0, self._dm1_tick)

    def _wait_claim_locked(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._ca is not None and self._ca.state == ControllerApplication.State.NORMAL:
                return
            # Release lock briefly so claim timer thread can progress cleanly
            self._lock.release()
            try:
                time.sleep(0.05)
            finally:
                self._lock.acquire()
        if self._ca is None or self._ca.state != ControllerApplication.State.NORMAL:
            raise RuntimeError(
                f"Address claim failed for SA 0x{self.identity.source_address:02X}"
            )

    def _broadcast_vin_locked(self) -> None:
        if self._ca is None:
            return
        payload = self.identity.vin_payload()
        self._ca.send_pgn(0, VI_PDU_FORMAT, VI_PDU_SPECIFIC, VI_PRIORITY, payload)
        # BAM uses multiple frames; count as one logical TX
        self._on_tx()

    def _on_request(self, src_address: int, dest_address: int, pgn: int) -> None:
        """Answer Request (PGN 59904) for VIN and the cyclic PGNs.

        Called from the can-j1939 receive thread; deliberately does not take
        the session lock so STOP (which holds it while joining) cannot deadlock.
        """
        ca = self._ca
        if not self._running or ca is None:
            return
        s = self.signals
        try:
            if pgn == PGN_VI:
                ca.send_pgn(0, VI_PDU_FORMAT, VI_PDU_SPECIFIC, VI_PRIORITY, self.identity.vin_payload())
            elif pgn in _REQUESTABLE:
                priority, encode = _REQUESTABLE[pgn]
                ca.send_pgn(0, (pgn >> 8) & 0xFF, pgn & 0xFF, priority, list(encode(s)))
            elif pgn == PGN_DM1:
                self._send_dm1()
                return
            elif dest_address != _GLOBAL_ADDRESS:
                # J1939-21: a destination-specific request for an unsupported PGN gets a NACK
                # (sent global, requester in byte 5) so the requester need not wait for a timeout.
                ca.send_pgn(
                    0, _ACK_PDU_FORMAT, _GLOBAL_ADDRESS, _ACK_PRIORITY,
                    [_ACK_CONTROL_NACK, 0xFF, 0xFF, 0xFF, src_address & 0xFF,
                     pgn & 0xFF, (pgn >> 8) & 0xFF, (pgn >> 16) & 0xFF],
                )
            else:
                return
        except RuntimeError:
            # Session stopping / claim lost between the check and the send.
            return
        self._on_tx()

    def _send_dm1(self) -> None:
        ca = self._ca
        if not self._running or ca is None:
            return
        try:
            ca.send_pgn(0, DM1_PDU_FORMAT, DM1_PDU_SPECIFIC, DM1_PRIORITY, list(encode_dm1(self.diagnostics)))
        except RuntimeError:
            return
        self._on_tx()

    def _dm1_tick(self, _cookie) -> bool:
        """can-j1939 timer callback; returning True keeps the 1 s DM1 cycle running."""
        if not self._running:
            return False
        self._send_dm1()
        return True

    def _sync_dm1_locked(self) -> None:
        # Push the new fault state immediately instead of waiting for the next 1 s tick.
        self._send_dm1()

    def _stop_locked(self) -> None:
        if self._started_at is not None and self._running:
            self._frozen_uptime = time.monotonic() - self._started_at

        meter = self._meters
        self._meters = None
        if meter is not None:
            meter.stop()
            meter.join(timeout=_JOIN_TIMEOUT_S)

        # 1) Stop cyclic TX first so nothing holds the bus during disconnect.
        self._detach_period_listener()
        sched = self._scheduler
        self._scheduler = None
        if sched is not None:
            sched.stop()
            # Join without holding session lock so TX/_on_tx cannot deadlock.
            self._lock.release()
            try:
                sched.join(timeout=_JOIN_TIMEOUT_S)
            finally:
                self._lock.acquire()

        # 2) Stop DM1 then CA (both use the bus / ECU job thread).
        if self._ca is not None:
            try:
                self._ca.remove_timer(self._dm1_tick)
            except Exception:
                pass

        if self._ca is not None:
            try:
                self._ca.stop()
            except Exception:
                pass
            self._ca = None

        # 3) Disconnect notifier + bus.shutdown via ECU; force USB handle release.
        bus = self._bus
        ecu = self._ecu
        iface = self._channel.interface if self._channel is not None else "virtual"
        self._bus = None
        self._ecu = None
        closed_real = False
        if ecu is not None:
            try:
                if bus is not None:
                    ecu.disconnect()
                    closed_real = iface != "virtual"
            except Exception:
                pass
            try:
                ecu.stop()
            except Exception:
                pass
        # Always force-release: candleLight otherwise keeps the USB handle open.
        if bus is not None:
            _force_release_bus(bus)
            closed_real = closed_real or (iface != "virtual")

        self._running = False
        with self._stats_lock:
            self._load_pct = 0.0
        self._started_at = None

        # USB / libusb needs a beat before the same candleLight can reopen.
        if closed_real:
            self._lock.release()
            try:
                time.sleep(_USB_SETTLE_S)
            finally:
                self._lock.acquire()

    def _ms(self, getter: Callable[[], int]) -> Callable[[], float]:
        return lambda: max(1, int(getter())) / 1000.0

    def _start_scheduler_locked(self) -> None:
        assert self._bus is not None
        s = self.signals
        specs = [
            (s.eec1_enabled, CAN_ID_EEC1, self._ms(lambda: s.cycle_eec1_ms), lambda: encode_eec1(s)),
            (s.ccvs_enabled, CAN_ID_CCVS, self._ms(lambda: s.cycle_ccvs_ms), lambda: encode_ccvs(s)),
            (s.vd_enabled, CAN_ID_VD, self._ms(lambda: s.cycle_vd_ms), lambda: encode_vd(s)),
            (s.hours_enabled, CAN_ID_HOURS, self._ms(lambda: s.cycle_hours_ms), lambda: encode_hours(s)),
        ]
        entries = [
            (arb_id, period_fn, data_fn)
            for enabled, arb_id, period_fn, data_fn in specs
            if enabled
        ]
        sched = _PgnScheduler(self._bus, entries, self._on_tx, self._health.tx_failed)
        self._scheduler = sched
        sched.start()

        def _on_sig_change() -> None:
            sch = self._scheduler
            if sch is not None:
                sch.notify_periods_changed()

        self._period_listener = _on_sig_change
        self.signals.on_change(_on_sig_change)

    def _detach_period_listener(self) -> None:
        listener = self._period_listener
        self._period_listener = None
        if listener is None:
            return
        try:
            self.signals._listeners.remove(listener)
        except ValueError:
            pass

    def _on_tx(self) -> None:
        # Separate from session RLock so stop/join cannot deadlock with TX.
        with self._stats_lock:
            self._tx_count += 1
            self._tx_window_count += 1
            self._update_load_locked()

    def _update_load_locked(self) -> None:
        now = time.monotonic()
        elapsed = now - self._tx_window_start
        if elapsed >= 0.5:
            bps = (self._tx_window_count * _BITS_PER_FRAME) / max(elapsed, 1e-6)
            self._load_pct = min(100.0, (bps / max(self.bitrate, 1)) * 100.0)
            self._tx_window_start = now
            self._tx_window_count = 0
        elif self._running and self._load_pct <= 0.0 and self._tx_count > 0:
            hz = 0.0
            s = self.signals
            if s.eec1_enabled:
                hz += 1000.0 / max(1, s.cycle_eec1_ms)
            if s.ccvs_enabled:
                hz += 1000.0 / max(1, s.cycle_ccvs_ms)
            if s.vd_enabled:
                hz += 1000.0 / max(1, s.cycle_vd_ms)
            if s.hours_enabled:
                hz += 1000.0 / max(1, s.cycle_hours_ms)
            hz += 1000.0 / DM1_CYCLE_MS
            self._load_pct = min(100.0, (hz * _BITS_PER_FRAME / max(self.bitrate, 1)) * 100.0)
