"""End-to-end on python-can's virtual bus: the emulator plus a fake ELD node."""

import itertools
import threading
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


def _wait_bam_start(bus, pgn, seconds=1.5):
    end = time.time() + seconds
    while time.time() < end:
        m = bus.recv(0.05)
        pf = (m.arbitration_id >> 16) & 0xFF if m else None
        if pf == 0xEC and m.data[0] == 0x20 and int.from_bytes(m.data[5:8], "little") == pgn:
            return
    raise AssertionError(f"no BAM for PGN {pgn}")


@pytest.mark.parametrize("dest", [0x00, 0xFF])
def test_vin_answered_on_request(bench, dest):
    _session, eld = bench
    _drain(eld)
    _request(eld, 65260, dest)
    assert _read_bam(eld, 65260) == b"1HTMMAAL5GH123456*"


def test_engine_hours_answered_on_request(bench):
    _session, eld = bench
    _drain(eld)
    _request(eld, 65253)
    assert _collect(eld, 0.5, 0xFEE5)


def test_hrvd_broadcast_and_answered_on_request(bench):
    _session, eld = bench
    _drain(eld)
    assert _collect(eld, 1.2, 0xFEC1)  # cyclic, 1 s
    _drain(eld)
    _request(eld, 65217)
    assert _collect(eld, 0.3, 0xFEC1)


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
    session.set_dtc("spn110_fmi3", True)
    assert _collect(eld, 0.3, 0xFECA)[0][:6] == bytes([0x04, 0xFF, 0x6E, 0x00, 0x03, 0x01])
    session.set_dtc("spn110_fmi3", False)
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


def test_vin_request_during_dm1_bam_is_answered(bench):
    # Two DTCs make DM1 a 10-byte BAM; can-j1939 sends one BAM at a time, so the VIN reply must wait, not drop.
    session, eld = bench
    session.inject_all_dtcs()
    for _ in range(3):
        _drain(eld)
        _wait_bam_start(eld, 65226)  # DM1 BAM now holds the transport slot
        _request(eld, 65260)
        assert _read_bam(eld, 65260) == b"1HTMMAAL5GH123456*"


def test_request_log_records_answers(bench):
    session, eld = bench
    session.clear_requests()
    _request(eld, 65260)
    _request(eld, 60928, dest=0xFF)  # address claim, answered inside can-j1939
    _request(eld, 65260, dest=0x17)  # for another node
    _request(eld, 65024)  # unsupported, addressed to us
    time.sleep(0.6)
    log = [(ev.src, ev.dest, ev.pgn, ev.result) for ev in session.recent_requests()]
    assert log == [
        (ELD_SA, 0x00, 65260, "answered"),
        (ELD_SA, 0xFF, 60928, "answered (address claim)"),
        (ELD_SA, 0x17, 65260, "not for this ECU (to 0x17)"),
        (ELD_SA, 0x00, 65024, "NACK (not supported)"),
    ]


def test_send_failures_do_not_stop_the_ecu(bench):
    # A real adapter raises on send when nobody ACKs; that used to kill can-j1939's job thread.
    session, eld = bench
    raw_bus = session._bus

    def failing_send(msg, timeout=None):
        raise can.CanOperationError("Send timeout")

    raw_bus.send = failing_send
    time.sleep(1.2)  # DM1 tick fails at least once
    del raw_bus.send
    assert session.stats().bus_health is BusHealth.TX_FAILING
    _drain(eld)
    _request(eld, 65260)
    assert _read_bam(eld, 65260) == b"1HTMMAAL5GH123456*"


def test_adapter_echo_does_not_cause_claim_flood(bench):
    # candleLight echoes every sent frame back over USB (is_rx=False) a moment later.
    session, eld = bench
    ecu_bus, notifier = session._ecu._bus, session._ecu._notifier
    plain_send = ecu_bus.send

    def send_with_echo(msg, timeout=None):
        plain_send(msg, timeout)
        echo = can.Message(arbitration_id=msg.arbitration_id, data=bytes(msg.data), is_rx=False)
        threading.Timer(0.002, lambda: [l.on_message_received(echo) for l in list(notifier.listeners)]).start()

    ecu_bus.send = send_with_echo
    _drain(eld)
    _request(eld, 60928, dest=0xFF)  # ELD asks every node to announce itself
    claims = _collect(eld, 1.0, 0xEEFF)
    del ecu_bus.send
    assert len(claims) == 1


def test_key_on_engine_off_still_answers_vin(bench):
    session, eld = bench
    session.signals.spn190_rpm = 650
    session.signals.set_spn("engine_running", False)
    _drain(eld)
    rpm_frames = _collect(eld, 0.3, 0xF004)
    assert rpm_frames and all(f[3:5] == b"\x00\x00" for f in rpm_frames)
    _request(eld, 65260)
    assert _read_bam(eld, 65260) == b"1HTMMAAL5GH123456*"


def test_dm11_to_this_ecu_clears_dtcs_and_acks(bench):
    session, eld = bench
    session.inject_all_dtcs()
    _drain(eld)
    _request(eld, 65235, dest=0x00)
    assert _collect(eld, 0.4, 0xE8FF) == [bytes([0x00, 0xFF, 0xFF, 0xFF, ELD_SA, 0xD3, 0xFE, 0x00])]
    assert session.diagnostics.active_count == 0
    assert session.recent_requests()[-1].result == "cleared 2 active DTCs (DM11), ACK"


def test_global_dm11_clears_without_ack(bench):
    session, eld = bench
    session.set_dtc("spn190_fmi0", True)
    _drain(eld)
    _request(eld, 65235, dest=0xFF)
    assert _collect(eld, 0.4, 0xE8FF) == []
    assert session.diagnostics.active_count == 0
    assert _collect(eld, 1.2, 0xFECA)[-1][2:6] == bytes(4)  # DM1: no DTC


def test_dm11_refused_by_request_fault(bench):
    session, eld = bench
    session.set_dtc("spn110_fmi3", True)
    session.set_request_fault("nack", target=65235)
    _drain(eld)
    _request(eld, 65235)
    assert _collect(eld, 0.4, 0xE8FF)[0][0] == 0x01  # NACK
    assert session.diagnostics.active_count == 1
