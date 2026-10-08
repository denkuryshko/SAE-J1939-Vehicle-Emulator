import time

import can

from j1939_emulator.bus.detect import DetectedChannel, EmulationMode
from j1939_emulator.bus.session import EmulatorSession
from j1939_emulator.bus.trace import J1939Trace, describe, split_id


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
