"""Fault injection: encoders, scheduler gating, silent ECU and request faults on a virtual bus."""

import itertools
import time

import can
import pytest

from j1939_emulator.bus.detect import DetectedChannel, EmulationMode
from j1939_emulator.bus.session import EmulatorSession
from j1939_emulator.bus.trace import decode
from j1939_emulator.faults import FaultState, active_faults
from j1939_emulator.pgn import (
    CAN_ID_CCVS,
    CAN_ID_EEC1,
    CAN_ID_HOURS,
    CAN_ID_VD,
    SPN_ERROR,
    SPN_NOT_AVAILABLE,
    SignalState,
    encode_ccvs,
    encode_eec1,
    encode_hours,
    encode_vd,
)

ELD_SA = 0xF9
_ids = itertools.count()


@pytest.fixture
def bench():
    name = f"faults{next(_ids)}"
    ch = DetectedChannel(
        uid=f"virtual:{name}", label=name, interface="virtual",
        bus_kwargs={"interface": "virtual", "channel": name}, kind=EmulationMode.VIRTUAL,
    )
    eld = can.Bus(interface="virtual", channel=name)
    session = EmulatorSession(mode=EmulationMode.VIRTUAL)
    session.start(ch)
    time.sleep(0.2)
    yield session, eld
    session.stop()
    eld.shutdown()


def _frames(bus, seconds):
    """CAN IDs (and data) the ELD sees during `seconds`, after dropping what was queued."""
    while bus.recv(0):
        pass
    out, end = [], time.time() + seconds
    while time.time() < end:
        m = bus.recv(0.02)
        if m is not None:
            out.append((m.arbitration_id, bytes(m.data), time.time()))
    return out


def _request(bus, pgn):
    bus.send(can.Message(arbitration_id=0x18EA00F9, is_extended_id=True,
                         data=pgn.to_bytes(3, "little")))
    return time.time()


def _last_result(session):
    return session.recent_requests()[-1].result


# --- encoders and meters ---


def test_spn_overrides_reach_the_wire():
    s = SignalState(spn190_rpm=800, spn84_speed_mph=35)
    s.spn_override = {"spn190": SPN_NOT_AVAILABLE, "spn84": SPN_ERROR,
                      "spn245": SPN_ERROR, "spn247": SPN_NOT_AVAILABLE}
    assert encode_eec1(s)[3:5] == b"\xff\xff"
    assert encode_ccvs(s)[1:3] == b"\x00\xfe"
    assert encode_vd(s)[4:8] == b"\x00\x00\x00\xfe"
    assert encode_hours(s)[0:4] == b"\xff\xff\xff\xff"
    assert decode(CAN_ID_EEC1, encode_eec1(s)).endswith("not available")
    assert decode(CAN_ID_CCVS, encode_ccvs(s)).endswith("error")
    assert decode(CAN_ID_VD, encode_vd(s)).endswith("error")
    assert decode(CAN_ID_HOURS, encode_hours(s)).endswith("not available")


def test_freeze_meters():
    s = SignalState(spn190_rpm=800, spn84_speed_mph=60)
    s.freeze_odometer = True
    odo, hours = s.spn245_total_mi, s.spn247_engine_hours
    s.advance_meters(3600)
    assert s.spn245_total_mi == odo
    assert s.spn247_engine_hours == hours + 1
    s.freeze_hours = True
    s.advance_meters(3600)
    assert s.spn247_engine_hours == hours + 1


def test_active_faults_lists_what_is_not_normal():
    s, f = SignalState(), FaultState()
    assert active_faults(s, f) == []
    s.ccvs_enabled = False
    s.spn_override["spn190"] = SPN_ERROR
    s.freeze_hours = True
    f.silent = True
    f.request_mode, f.request_target, f.request_delay_ms = "delay", 65260, 700
    assert active_faults(s, f) == [
        "ECU silent: sends nothing",
        "CCVS (PGN 65265) broadcast off",
        "SPN 190 sends error (0xFE…)",
        "Requests for PGN 65260 delayed 700 ms",
        "Engine hours frozen",
    ]


# --- on the bus ---


def test_broadcast_switched_off_and_on_while_running(bench):
    session, eld = bench
    session.set_pgn_enabled("ccvs", False)
    ids = {f[0] for f in _frames(eld, 0.4)}
    assert CAN_ID_CCVS not in ids and CAN_ID_EEC1 in ids
    session.set_pgn_enabled("ccvs", True)
    ids = {f[0] for f in _frames(eld, 0.4)}
    assert CAN_ID_CCVS in ids


def test_silent_ecu_sends_nothing_and_ignores_requests(bench):
    session, eld = bench
    session.set_silent(True)
    time.sleep(0.05)
    _request(eld, 65260)
    assert [f for f in _frames(eld, 0.6) if f[0] & 0xFF == 0x00] == []
    assert _last_result(session) == "ignored: ECU silent (fault)"
    session.set_silent(False)
    assert CAN_ID_EEC1 in {f[0] for f in _frames(eld, 0.3)}


def test_request_fault_ignore_only_for_the_target_pgn(bench):
    session, eld = bench
    session.set_request_fault("ignore", target=65260)
    _request(eld, 65260)
    frames = _frames(eld, 0.5)
    assert not any(f[0] == 0x18ECFF00 for f in frames)  # no BAM for the VIN
    assert _last_result(session) == "ignored (fault: ignore requests)"
    _request(eld, 65248)  # another PGN: answered as usual
    time.sleep(0.2)
    assert _last_result(session) == "answered"


def test_request_fault_nack_for_a_supported_pgn(bench):
    session, eld = bench
    session.set_request_fault("nack", target=0)
    _request(eld, 65248)
    nacks = [f for f in _frames(eld, 0.4) if f[0] == 0x18E8FF00]
    assert nacks and nacks[0][1] == bytes([1, 0xFF, 0xFF, 0xFF, ELD_SA, 0xE0, 0xFE, 0x00])
    assert _last_result(session) == "NACK (fault: NACK requests)"


def test_request_fault_delay(bench):
    session, eld = bench
    session.set_request_fault("delay", target=65248, delay_ms=400)
    while eld.recv(0):
        pass
    sent = _request(eld, 65248)
    time.sleep(0.05)
    assert _last_result(session) == "waiting 400 ms (fault: delay replies)"
    replies, end = [], time.time() + 1.0
    while time.time() < end:  # the VD reply on request, not the 1 s broadcast
        m = eld.recv(0.01)
        if m is not None and m.arbitration_id == CAN_ID_VD:
            replies.append(time.time() - sent)
    assert any(0.35 <= t <= 0.6 for t in replies)
    assert _last_result(session) == "answered after 400 ms (fault delay)"


def test_stop_cancels_delayed_replies(bench):
    session, eld = bench
    session.set_request_fault("delay", target=0, delay_ms=2000)
    _request(eld, 65260)
    time.sleep(0.1)
    session.stop()
    assert _last_result(session) == "dropped: ECU stopped"


def test_faults_are_noted_in_the_trace_and_cleared(bench):
    session, _eld = bench
    session.set_pgn_enabled("vd", False)
    session.set_spn_override("spn84", SPN_NOT_AVAILABLE)
    session.set_freeze(odometer=True)
    assert len(active_faults(session.signals, session.faults)) == 3
    session.clear_faults()
    assert active_faults(session.signals, session.faults) == []
    _count, lines = session.trace.recent()
    text = "\n".join(lines)
    assert "FAULT VD (PGN 65248) broadcast OFF" in text
    assert "FAULT SPN 84 sends not available" in text
    assert "FAULT odometer frozen" in text
    assert "FAULT VD (PGN 65248) broadcast ON" in text
