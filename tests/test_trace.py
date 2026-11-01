import time

import can

from j1939_emulator.bus import trace as trace_mod

from j1939_emulator.bus.detect import DetectedChannel, EmulationMode
from j1939_emulator.bus.session import EmulatorSession
from j1939_emulator.bus.trace import (
    TRAFFIC_ROWS,
    J1939Trace,
    decode,
    decode_payload,
    describe,
    frame_type,
    split_id,
)
from j1939_emulator.diagnostics import DiagnosticState, encode_dm1
from j1939_emulator.pgn import (
    CAN_ID_CCVS,
    CAN_ID_EEC1,
    CAN_ID_HOURS,
    CAN_ID_HRVD,
    CAN_ID_TCO1,
    CAN_ID_VD,
    SignalState,
    encode_ccvs,
    encode_eec1,
    encode_hours,
    encode_hrvd,
    encode_tco1,
    encode_vd,
)


def test_split_id_pdu1_and_pdu2():
    assert split_id(0x18EA00F9) == (6, 59904, 0xF9, 0x00)
    assert split_id(0x18FEEC00) == (6, 65260, 0x00, 0xFF)


def test_describe_transport_and_requests():
    assert describe(0x18EA00F9, bytes([0xEC, 0xFE, 0x00])) == "Request for PGN 65260 (VI (VIN))"
    assert describe(0x1CEC00F9, bytes([0x10, 18, 0, 3, 0xFF, 0xEC, 0xFE, 0])) == (
        "TP.CM RTS: 18 bytes in 3 packets (max 255/CTS), PGN 65260 (VI (VIN))"
    )
    assert describe(0x1CECF900, bytes([0x11, 3, 1, 0xFF, 0xFF, 0xEC, 0xFE, 0])) == (
        "TP.CM CTS: send 3 packets from #1, PGN 65260 (VI (VIN))"
    )
    assert describe(0x1CEC00F9, bytes([0x13, 18, 0, 3, 0xFF, 0xEC, 0xFE, 0])) == (
        "TP.CM EOMA: 18 bytes / 3 packets received, PGN 65260 (VI (VIN))"
    )
    assert describe(0x1CEC00F9, bytes([0xFF, 3, 0xFF, 0xFF, 0xFF, 0xEC, 0xFE, 0])) == (
        "TP.CM Abort (3: timeout), PGN 65260 (VI (VIN))"
    )
    assert describe(0x18E8FF00, bytes([1, 0xFF, 0xFF, 0xFF, 0xF9, 0, 0xFE, 0])) == (
        "NACK for PGN 65024, to 0xF9"
    )
    assert describe(0x18EEFFFE, bytes(8)) == "Cannot Claim Address, NAME 0x0000000000000000"


def test_trace_reassembles_bam_and_writes_file(tmp_path):
    trace = J1939Trace(0x00, ["header"], directory=tmp_path)
    trace.frame("TX", 0x18ECFF00, bytes([0x20, 18, 0, 3, 0xFF, 0xEC, 0xFE, 0]))
    for seq, chunk in enumerate((b"1HTMMAA", b"L5GH123", b"456*\xff\xff\xff"), start=1):
        trace.frame("TX", 0x1CEBFF00, bytes([seq]) + chunk)
    trace.close("STOP")
    text = trace.path.read_text(encoding="utf-8")
    assert "complete PGN 65260 (VI (VIN)): '1HTMMAAL5GH123456*'" in text
    assert text.rstrip().endswith("STOP")


def test_session_trace_shows_request_and_reply():
    ch = DetectedChannel(
        uid="virtual:trace", label="trace", interface="virtual",
        bus_kwargs={"interface": "virtual", "channel": "trace"}, kind=EmulationMode.VIRTUAL,
    )
    eld = can.Bus(interface="virtual", channel="trace")
    session = EmulatorSession(mode=EmulationMode.VIRTUAL)
    session.start(ch)
    try:
        time.sleep(0.4)
        eld.send(can.Message(arbitration_id=0x18EA00F9, is_extended_id=True, data=[0xEC, 0xFE, 0x00]))
        time.sleep(0.5)
    finally:
        session.stop()
        eld.shutdown()
    _count, lines = session.trace.recent()
    request = next(i for i, l in enumerate(lines) if "RX   18EA00F9" in l)
    after = "\n".join(lines[request:])
    assert "TP.CM BAM: 18 bytes in 3 packets, PGN 65260" in after
    assert "request from 0xF9 to 0x00 for PGN 65260 (VI (VIN)): answered" in after
    assert "'1HTMMAAL5GH123456*'" in after
    assert session.trace.path.read_text(encoding="utf-8").count("\n") >= len(lines)


def test_frame_type_from_existing_fields():
    assert frame_type("RX", 0x18EA00F9, bytes([0xEC, 0xFE, 0x00])) == "REQUEST"
    assert frame_type("TX", 0x18E8FF00, bytes([1, 0xFF, 0xFF, 0xFF, 0xF9, 0, 0xFE, 0])) == "NACK"
    assert frame_type("TX", 0x18EEFF00, bytes(8)) == "ADDRESS CLAIM"
    assert frame_type("TX", 0x18ECFF00, bytes([0x20, 18, 0, 3, 0xFF, 0xEC, 0xFE, 0])) == "TP.CM BAM"
    assert frame_type("TX", 0x1CEBFF00, bytes([1]) + bytes(7)) == "TP.DT"
    assert frame_type("TX", 0x0CF00400, bytes(8)) == "BROADCAST"
    assert frame_type("TX!", 0x0CF00400, bytes(8)) == "ERROR"


def test_traffic_ring_keeps_cyclic_out_of_the_file(tmp_path):
    trace = J1939Trace(0x00, ["header"], directory=tmp_path)
    trace.broadcast(0x0CF00400, bytes(8), ok=True)
    trace.frame("RX", 0x18EA00F9, bytes([0xEC, 0xFE, 0x00]))
    last, entries = trace.traffic_since(0)
    assert last == 2 and [e.kind for e in entries] == ["BROADCAST", "REQUEST"]
    assert trace.traffic_since(last) == (2, [])
    for _ in range(TRAFFIC_ROWS + 5):
        trace.broadcast(0x0CF00400, bytes(8), ok=True)
    _last, entries = trace.traffic_since(0)
    # Cyclic frames are capped on their own (oldest dropped first); the request stays.
    assert len(entries) == TRAFFIC_ROWS + 1
    assert sum(e.cyclic for e in entries) == TRAFFIC_ROWS
    assert [e.kind for e in entries if not e.cyclic] == ["REQUEST"]
    assert [e.seq for e in entries] == sorted(e.seq for e in entries)
    trace.close("STOP")
    assert "0CF00400" not in trace.path.read_text(encoding="utf-8")


def test_session_traffic_includes_cyclic_and_requests():
    ch = DetectedChannel(
        uid="virtual:traffic", label="traffic", interface="virtual",
        bus_kwargs={"interface": "virtual", "channel": "traffic"}, kind=EmulationMode.VIRTUAL,
    )
    eld = can.Bus(interface="virtual", channel="traffic")
    session = EmulatorSession(mode=EmulationMode.VIRTUAL)
    session.start(ch)
    try:
        time.sleep(0.4)
        eld.send(can.Message(arbitration_id=0x18EA00F9, is_extended_id=True, data=[0xEC, 0xFE, 0x00]))
        time.sleep(0.5)
    finally:
        session.stop()
        eld.shutdown()
    _last, entries = session.trace.traffic_since(0)
    kinds = {(e.direction, e.arb_id, e.kind) for e in entries}
    assert ("TX", 0x0CF00400, "BROADCAST") in kinds  # EEC1, cyclic
    assert ("RX", 0x18EA00F9, "REQUEST") in kinds
    assert ("TX", 0x18ECFF00, "TP.CM BAM") in kinds  # the VIN reply


def test_decode_reads_back_the_encoders():
    s = SignalState(spn190_rpm=800, spn84_speed_mph=35, spn245_total_mi=248912.4,
                    spn247_engine_hours=10000.05)
    assert decode(CAN_ID_EEC1, encode_eec1(s)) == "SPN 190 Engine Speed: 800 rpm"
    assert decode(CAN_ID_CCVS, encode_ccvs(s)) == "SPN 84 Wheel-Based Speed: 35 mph (56.33 km/h)"
    assert decode(CAN_ID_VD, encode_vd(s)).startswith("SPN 245 Total Distance: 248912.4 mi")
    assert decode(CAN_ID_HOURS, encode_hours(s)) == "SPN 247 Engine Hours: 10000.05 h"
    assert decode(CAN_ID_HRVD, encode_hrvd(s)).startswith("SPN 917 HR Total Distance: 248912.4")


def test_decode_special_values_and_protocol_frames():
    assert decode(CAN_ID_EEC1, bytes([0xFF] * 8)) == "SPN 190 Engine Speed: not available"
    assert decode(CAN_ID_EEC1, bytes([0xFF, 0xFF, 0xFF, 0x00, 0xFE, 0xFF, 0xFF, 0xFF])) == (
        "SPN 190 Engine Speed: error"
    )
    assert decode(0x18EA00F9, bytes([0xEC, 0xFE, 0x00])) == "Request for PGN 65260 (VI (VIN))"
    assert decode(0x18FF1200, bytes(8)) == ""  # unknown proprietary PGN


def test_decode_dm1():
    assert decode_payload(65226, encode_dm1(DiagnosticState())) == "DM1: no active DTCs; lamps off"
    state = DiagnosticState()
    state.set_active("spn110_fmi3", True)
    assert decode_payload(65226, encode_dm1(state)) == (
        "DM1: SPN 110 / FMI 3 (OC 1); lamps AWL"
    )
    state.set_active("spn190_fmi0", True)
    assert decode_payload(65226, encode_dm1(state)) == (
        "DM1: SPN 110 / FMI 3 (OC 1), SPN 190 / FMI 0 (OC 1); lamps RSL+AWL"
    )


def test_last_tp_dt_carries_the_decoded_message(tmp_path):
    trace = J1939Trace(0x00, ["header"], directory=tmp_path)
    trace.frame("TX", 0x18ECFF00, bytes([0x20, 18, 0, 3, 0xFF, 0xEC, 0xFE, 0]))
    for seq, chunk in enumerate((b"1HTMMAA", b"L5GH123", b"456*\xff\xff\xff"), start=1):
        trace.frame("TX", 0x1CEBFF00, bytes([seq]) + chunk)
    _last, entries = trace.traffic_since(0)
    assert [e.text for e in entries[:-1]] == ["", "", ""]
    assert entries[-1].text == "complete PGN 65260 (VI (VIN)): VIN 1HTMMAAL5GH123456 (17 chars)"
    trace.close("STOP")


def test_export_candump(tmp_path):
    trace = J1939Trace(0x00, ["header"], directory=tmp_path)
    trace.broadcast(0x0CF00400, bytes([0xFF, 0xFF, 0xFF, 0x00, 0x19, 0xFF, 0xFF, 0xFF]), ok=True)
    trace.broadcast(0x0CF00400, bytes(8), ok=False)  # failed send: not on the bus, left out
    trace.frame("RX", 0x18EA00F9, bytes([0xEC, 0xFE, 0x00]))
    out = tmp_path / "dump.log"
    assert trace.export_candump(out) == 2
    lines = out.read_text(encoding="ascii").splitlines()
    assert lines[0].endswith(" can0 0CF00400#FFFFFF0019FFFFFF")
    assert lines[1].endswith(" can0 18EA00F9#ECFE00")
    assert lines[0].startswith("(") and ") can0 " in lines[0]
    trace.close("STOP")


def test_decode_tco1():
    s = SignalState(spn84_speed_mph=60)
    assert decode(CAN_ID_TCO1, encode_tco1(s)) == (
        "SPN 1624 Tachograph Speed: 60 mph (96.56 km/h); SPN 1611 motion: yes"
    )


def test_speed_broadcasts_sampled_into_the_file(tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(trace_mod.time, "time", lambda: now[0])
    trace = J1939Trace(0x00, ["header"], directory=tmp_path)
    s = SignalState()

    def tick(dt):
        now[0] += dt
        trace.broadcast(CAN_ID_CCVS, encode_ccvs(s), ok=True)
        trace.broadcast(CAN_ID_EEC1, encode_eec1(s), ok=True)

    tick(0)  # first frame: written
    tick(0.1)  # same value, too soon
    s.spn84_speed_mph = 30
    tick(0.1)  # changed, but within 1 s of the last line: waits
    tick(1.0)  # changed vs. the last line written: written
    for _ in range(50):
        tick(0.1)  # unchanged for 5 s: nothing
    tick(5.0)  # 10 s heartbeat
    trace.close()
    lines = [ln for ln in trace.path.read_text(encoding="utf-8").splitlines() if "18FEF100" in ln]
    sent = [ln.split("Wheel-Based Speed: ")[1].split(" mph")[0] for ln in lines]
    assert sent == ["0", "30", "30"]
    assert all("[cyclic CCVS, sampled]" in ln for ln in lines)
    assert "0CF00400" not in trace.path.read_text(encoding="utf-8")
