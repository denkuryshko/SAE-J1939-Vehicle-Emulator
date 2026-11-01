"""Scenarios: file format checks and playback on a virtual bus."""

import itertools
import time

import can
import pytest

from j1939_emulator.bus.detect import DetectedChannel, EmulationMode
from j1939_emulator.bus.session import EmulatorSession
from j1939_emulator.faults import active_faults
from j1939_emulator.pgn import CAN_ID_CCVS, SPN_NOT_AVAILABLE
from j1939_emulator.scenario import (
    RunState,
    ScenarioError,
    ScenarioRunner,
    _ease,
    format_time,
    list_scenarios,
    load_scenario,
    parse_duration,
    parse_scenario,
)

_ids = itertools.count()


@pytest.fixture
def bench():
    name = f"scen{next(_ids)}"
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


def _wait(runner, seconds=5.0):
    end = time.time() + seconds
    while runner.active and time.time() < end:
        time.sleep(0.02)


# --- format ---


def test_parse_duration_and_format_time():
    assert parse_duration("1m30s") == 90
    assert parse_duration("500ms") == 0.5
    assert parse_duration("2h") == 7200
    assert parse_duration(2.5) == 2.5
    for bad in ("5x", "", "m5", True, -1):
        with pytest.raises(ValueError):
            parse_duration(bad)
    assert format_time(90) == "1:30"
    assert format_time(0.5) == "0:00.5"
    assert format_time(3725) == "1:02:05"


def test_builtin_scenarios_load():
    names = {label for label, _p in list_scenarios() if label.startswith("Built-in")}
    assert {"Built-in: drive-and-stop", "Built-in: ecu-disconnect", "Built-in: sensor-failure",
            "Built-in: truck-change", "Built-in: slow-ecu"} <= names
    for label, path in list_scenarios():
        if label.startswith("Built-in"):
            s = load_scenario(path)
            assert s.steps and s.duration > 60


def test_steps_sorted_and_described():
    s = parse_scenario({"name": "x", "step": [
        {"at": "1m", "ramp": {"speed_mph": 35, "rpm": 1400, "over": "20s"}},
        {"at": "0s", "ignition": "run", "note": "go"},
        {"at": "2m", "fault": {"silent": True, "ccvs": False, "spn84": "na",
                               "requests": {"mode": "delay", "pgn": "vin", "delay": "3s"}}},
    ]})
    assert [st.at for st in s.steps] == [0, 60, 120]
    assert [st.index for st in s.steps] == [1, 2, 3]
    assert s.duration == 120
    assert s.steps[0].describe() == ["Ignition: engine running", "“go”"]
    assert s.steps[1].describe() == ["Speed → 35 mph, rpm → 1400 over 20 s"]
    assert s.steps[2].describe() == [
        "Fault: ECU silent ON", "Fault: CCVS broadcast OFF",
        "Fault: SPN 84 sends not available", "Requests for PGN 65260: delay 3 s",
    ]


@pytest.mark.parametrize("raw, message", [
    ({"step": []}, "no steps"),
    ({"stepz": [], "step": [{"at": 0, "note": "x"}]}, "unknown top-level key 'stepz'"),
    ({"step": [{"note": "x"}]}, "step 1: missing at"),
    ({"step": [{"at": "5q", "note": "x"}]}, "step 1: at: not a duration"),
    ({"step": [{"at": 0, "sped_mph": 5}]}, "step 1: unknown key 'sped_mph'"),
    ({"step": [{"at": 0, "speed_mph": 500}]}, "speed_mph = 500 is out of range"),
    ({"step": [{"at": 0, "ignition": "off"}]}, "ignition must be"),
    ({"step": [{"at": 0, "ramp": {"speed_mph": 5}}]}, "ramp needs over"),
    ({"step": [{"at": 0, "ramp": {"over": "5s"}}]}, "ramp needs speed_mph and / or rpm"),
    ({"step": [{"at": 0, "fault": {"spn84": "broken"}}]}, "fault.spn84 must be"),
    ({"step": [{"at": 0, "fault": {"requests": {"mode": "drop"}}}]}, "fault.requests.mode must be"),
    ({"step": [{"at": 0, "vin": "TOO-SHORT!!"}]}, "step 1: vin"),
    ({"step": [{"at": 0}]}, "the step does nothing"),
    ({"step": [{"at": 0, "dtc": {"spn110": True}}]}, "step 1: dtc: DTC key 'spn110'"),
])
def test_invalid_scenarios_say_where(raw, message):
    with pytest.raises(ScenarioError) as err:
        parse_scenario(raw)
    assert message in str(err.value)


def test_load_reports_file_name(tmp_path):
    p = tmp_path / "broken.toml"
    p.write_text('[[step]]\nat = "1s"\nrpm = "fast"\n', encoding="utf-8")
    with pytest.raises(ScenarioError, match=r"broken.toml: step 1: rpm must be a number"):
        load_scenario(p)


def test_smooth_ramp_curve():
    assert _ease(0, "smooth") == 0 and _ease(1, "smooth") == 1 and _ease(0.5, "smooth") == 0.5
    assert _ease(0.1, "smooth") < 0.1  # gentle start
    assert _ease(0.9, "smooth") > 0.9  # gentle finish
    assert _ease(0.25, "linear") == 0.25


# --- playback ---


def test_runner_needs_a_running_ecu():
    runner = ScenarioRunner(EmulatorSession(mode=EmulationMode.VIRTUAL))
    with pytest.raises(RuntimeError, match="Press START"):
        runner.start(parse_scenario({"step": [{"at": 0, "note": "x"}]}))


def test_ramp_reaches_the_wire_smoothly(bench):
    session, eld = bench
    runner = ScenarioRunner(session)
    s = parse_scenario({"name": "ramp", "step": [
        {"at": 0, "ignition": "run"},
        {"at": "100ms", "ramp": {"speed_mph": 40, "rpm": 1500, "over": "1s"}},
    ]})
    while eld.recv(0):
        pass
    runner.start(s)
    speeds, end = [], time.time() + 1.6
    while time.time() < end:
        m = eld.recv(0.02)
        if m is not None and m.arbitration_id == CAN_ID_CCVS:
            speeds.append(int.from_bytes(m.data[1:3], "little") / 256 / 1.609344)
    _wait(runner)
    assert runner.state is RunState.FINISHED
    assert speeds == sorted(speeds)  # never goes back
    assert len({round(v) for v in speeds if 1 < v < 39}) >= 5  # many steps in between, no jump
    assert abs(speeds[-1] - 40) < 0.05
    assert session.signals.spn190_rpm == 1500 and session.signals.engine_running


def test_steps_apply_faults_and_clear_them_at_the_end(bench):
    session, _eld = bench
    runner = ScenarioRunner(session)
    s = parse_scenario({"step": [
        {"at": 0, "fault": {"ccvs": False, "spn84": "not_available", "freeze_odometer": True}},
        {"at": "300ms", "odometer_add_mi": 100, "dtc": {"spn110_fmi3": True}},
        {"at": "400ms", "note": "end"},
    ]})
    odo = session.signals.spn245_total_mi
    runner.start(s)
    time.sleep(0.15)
    assert session.signals.ccvs_enabled is False
    assert session.signals.spn_override["spn84"] == SPN_NOT_AVAILABLE
    _wait(runner)
    assert runner.state is RunState.FINISHED
    assert active_faults(session.signals, session.faults) == []  # clear_faults_on_end
    assert session.signals.spn245_total_mi == pytest.approx(odo + 100)
    assert session.diagnostics.get("spn110_fmi3").active
    text = "\n".join(session.trace.recent()[1])
    assert "SCENARIO 'Scenario' started: 3 steps" in text
    assert "SCENARIO step 2 @0:00.3: Odometer +100 mi; DTC SPN 110 / FMI 3 active" in text
    assert "SCENARIO 'Scenario' finished" in text


def test_pause_holds_the_clock_and_stop_ends(bench):
    session, _eld = bench
    runner = ScenarioRunner(session)
    runner.start(parse_scenario({"step": [
        {"at": 0, "fault": {"silent": True}},
        {"at": "600ms", "speed_mph": 20},
    ]}))
    time.sleep(0.2)
    runner.pause()
    held = runner.elapsed()
    time.sleep(0.6)
    assert runner.elapsed() == held and runner.state is RunState.PAUSED
    assert session.signals.spn84_speed_mph == 0  # step 2 has not run during the pause
    runner.resume()
    time.sleep(0.2)
    runner.stop()
    assert runner.state is RunState.STOPPED
    assert session.faults.silent is False  # cleared on stop too
    assert session.signals.spn84_speed_mph == 0


def test_ecu_stop_fails_the_scenario(bench):
    session, _eld = bench
    runner = ScenarioRunner(session)
    runner.start(parse_scenario({"step": [{"at": 0, "note": "a"}, {"at": "5s", "note": "b"}]}))
    time.sleep(0.1)
    session.stop()
    _wait(runner)
    assert runner.state is RunState.FAILED and runner.error == "the ECU was stopped"


def test_truck_change_restores_vin(bench):
    session, _eld = bench
    before = session.identity.vin
    runner = ScenarioRunner(session)
    runner.start(parse_scenario({"restore_vin_on_end": True, "step": [
        {"at": 0, "vin": "3AKJHHDR1LSLA4213"},
        {"at": "1s", "note": "end"},
    ]}))
    end = time.time() + 0.9  # wait for step 1, not a fixed time: CI runners can be slow
    while session.identity.vin != "3AKJHHDR1LSLA4213" and time.time() < end:
        time.sleep(0.02)
    assert session.identity.vin == "3AKJHHDR1LSLA4213"
    _wait(runner)
    assert session.identity.vin == before
