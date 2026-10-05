"""End-to-end on python-can's virtual bus: the emulator plus a fake ELD node."""

import itertools
import time

import can
import pytest

from j1939_emulator.bus.detect import DetectedChannel, EmulationMode
from j1939_emulator.bus.session import BusHealth, EmulatorSession

ELD_SA = 0xF9
_channel_ids = itertools.count()


@pytest.fixture
def bench():
    """Running emulator on a private virtual channel + the ELD side of that bus."""
    name = f"pytest{next(_channel_ids)}"
    ch = DetectedChannel(
        uid=f"virtual:{name}",
        label=name,
        interface="virtual",
        bus_kwargs={"interface": "virtual", "channel": name},
        kind=EmulationMode.VIRTUAL,
    )
    eld = can.Bus(interface="virtual", channel=name)
    session = EmulatorSession(mode=EmulationMode.VIRTUAL)
    session.start(ch)
    time.sleep(0.2)
    yield session, eld
    session.stop()
    eld.shutdown()


def _drain(bus):
    while bus.recv(0):
        pass


def _collect(bus, seconds, pf_ps):
    out, end = [], time.time() + seconds
    while time.time() < end:
        m = bus.recv(0.05)
        if m and (m.arbitration_id >> 8) & 0xFFFF == pf_ps:
            out.append(bytes(m.data))
    return out


def _request(bus, pgn, dest=0x00):
    bus.send(
        can.Message(
            arbitration_id=0x18EA0000 | (dest << 8) | ELD_SA,
            is_extended_id=True,
            data=pgn.to_bytes(3, "little"),
        )
    )


def _read_bam(bus, pgn, seconds=1.5):
    total, buf, end = None, bytearray(), time.time() + seconds
    while time.time() < end:
        m = bus.recv(0.05)
        if not m:
            continue
        pf = (m.arbitration_id >> 16) & 0xFF
        if pf == 0xEC and m.data[0] == 0x20 and int.from_bytes(m.data[5:8], "little") == pgn:
            total, buf = int.from_bytes(m.data[1:3], "little"), bytearray()
        elif pf == 0xEB and total is not None:
            buf += m.data[1:]
            if len(buf) >= total:
                return bytes(buf[:total])
    return None


@pytest.mark.parametrize("dest", [0x00, 0xFF])
def test_vin_answered_on_request(bench, dest):
    _session, eld = bench
    _drain(eld)
    _request(eld, 65260, dest)
    assert _read_bam(eld, 65260) == b"1HTMMAAL7GH123456*"


def test_engine_hours_answered_on_request(bench):
    _session, eld = bench
    _drain(eld)
    _request(eld, 65253)
    assert _collect(eld, 0.5, 0xFEE5)


def test_unsupported_pgn_nacked_only_when_addressed(bench):
    _session, eld = bench
    _drain(eld)
    _request(eld, 65024, dest=0xFF)
    assert _collect(eld, 0.4, 0xE8FF) == []
    _request(eld, 65024, dest=0x00)
    assert _collect(eld, 0.4, 0xE8FF) == [bytes([0x01, 0xFF, 0xFF, 0xFF, ELD_SA, 0x00, 0xFE, 0x00])]


def test_dm1_always_broadcast_and_clears(bench):
    session, eld = bench
    _drain(eld)
    assert _collect(eld, 1.3, 0xFECA)[-1] == bytes([0x00, 0xFF, 0, 0, 0, 0, 0xFF, 0xFF])
    session.set_dtc1(True)
    assert _collect(eld, 0.3, 0xFECA)[0][:6] == bytes([0x04, 0xFF, 0x6E, 0x00, 0x03, 0x01])
    session.set_dtc1(False)
    assert _collect(eld, 0.3, 0xFECA)[0] == bytes([0x00, 0xFF, 0, 0, 0, 0, 0xFF, 0xFF])


def test_health_counts_peers_and_flags_ack_errors(bench):
    session, eld = bench
    assert session.stats().bus_health is BusHealth.OK
    eld.send(can.Message(arbitration_id=0x18FEF100 | ELD_SA, is_extended_id=True, data=bytes(8)))
    time.sleep(0.2)
    assert session.stats().peers == 1
    # A SocketCAN-style ACK error frame, as candle / gs_usb adapters report it.
    session._health.on_message_received(
        can.Message(is_error_frame=True, arbitration_id=0x24, data=bytes(8))
    )
    assert session.stats().bus_health is BusHealth.NO_ACK


def test_meters_count_while_running(bench):
    session, _eld = bench
    s = session.signals
    start_mi, start_h = s.spn245_total_mi, s.spn247_engine_hours
    s.spn190_rpm, s.spn84_speed_mph = 1200, 60
    time.sleep(1.2)
    assert s.spn245_total_mi - start_mi == pytest.approx(1.2 * 60 / 3600, rel=0.3)
    assert s.spn247_engine_hours - start_h == pytest.approx(1.2 / 3600, rel=0.3)


def test_stop_saves_meters_when_persisting(bench):
    from j1939_emulator.meters_store import restore_meters
    from j1939_emulator.pgn import SignalState

    session, _eld = bench
    session.persist_meters = True
    session.signals.spn245_total_mi = 4321.0
    session.stop()
    restored = SignalState()
    assert restore_meters(restored, session.identity.vin)
    assert restored.spn245_total_mi == 4321.0
