import pytest

from j1939_emulator.pgn import (
    SignalState,
    encode_ccvs,
    encode_eec1,
    encode_hours,
    encode_vd,
)


def test_defaults_engine_off_and_standing():
    s = SignalState()
    assert s.spn190_rpm == 0
    assert s.spn84_speed_mph == 0


def test_eec1_engine_speed_bytes_4_5_and_rest_not_available():
    s = SignalState(spn190_rpm=800)  # 800 / 0.125 = 6400 = 0x1900
    assert encode_eec1(s) == bytes([0xFF, 0xFF, 0xFF, 0x00, 0x19, 0xFF, 0xFF, 0xFF])


def test_ccvs_speed_is_km_per_h_times_256():
    data = encode_ccvs(SignalState(spn84_speed_mph=60))
    assert int.from_bytes(data[1:3], "little") == round(60 * 1.60934 * 256)
    assert data[0] == 0xFF and data[3:] == b"\xff" * 5


def test_vd_total_distance_in_bytes_5_8_trip_not_available():
    data = encode_vd(SignalState(spn245_total_mi=1000))
    assert data[:4] == b"\xff" * 4
    assert int.from_bytes(data[4:], "little") == round(1000 * 1.60934 / 0.125)


def test_hours_spn247_0_05_h_per_bit():
    s = SignalState(spn247_engine_hours=10000.15)
    assert encode_hours(s) == bytes([0x43, 0x0D, 0x03, 0x00, 0xFF, 0xFF, 0xFF, 0xFF])


def test_meters_only_advance_with_rpm_and_speed():
    s = SignalState(spn247_engine_hours=10, spn245_total_mi=100)
    s.advance_meters(3600)
    assert (s.spn247_engine_hours, s.spn245_total_mi) == (10, 100)

    s.spn190_rpm, s.spn84_speed_mph = 650, 60
    s.advance_meters(60)
    assert s.spn247_engine_hours == pytest.approx(10 + 1 / 60)
    assert s.spn245_total_mi == pytest.approx(101)


def test_set_spn_accepts_pre_2_0_odometer_key():
    s = SignalState()
    s.set_spn("vd.spn917_total_mi", "1234.5")
    assert s.spn245_total_mi == 1234.5
    assert s.get_spn("vd.spn245_total_mi") == 1234.5


def test_set_spn_rejects_unknown_key_and_bad_cycle():
    s = SignalState()
    with pytest.raises(KeyError):
        s.set_spn("eec1.spn513_torque_pct", 10)
    with pytest.raises(ValueError):
        s.set_spn("hours.cycle_ms", 0)


def test_ignition_switch_sets_idle_or_zero_rpm():
    s = SignalState(spn190_rpm=1250, engine_running=False)
    s.set_ignition(True)
    assert (s.engine_running, s.spn190_rpm) == (True, 650)
    s.set_ignition(False)
    assert (s.engine_running, s.spn190_rpm) == (False, 0)


def test_engine_speed_flips_ignition():
    s = SignalState(spn190_rpm=800, engine_running=True)
    s.set_engine_speed(0)
    assert not s.engine_running
    s.set_engine_speed(300)  # below 600 rpm: switch stays where it is
    assert not s.engine_running
    s.set_engine_speed(600)
    assert s.engine_running
    s.set_engine_speed(300)
    assert s.engine_running
    s.set_spn("eec1.spn190_rpm", "0")
    assert not s.engine_running


def test_key_on_engine_off_sends_zero_and_keeps_settings():
    s = SignalState(spn190_rpm=650, spn84_speed_mph=60, spn247_engine_hours=10, spn245_total_mi=100)
    s.set_spn("engine_running", "false")
    assert encode_eec1(s) == encode_eec1(SignalState())
    assert encode_ccvs(s) == encode_ccvs(SignalState())
    s.advance_meters(3600)
    assert (s.spn247_engine_hours, s.spn245_total_mi) == (10, 100)

    s.set_spn("engine_running", True)
    assert encode_eec1(s) == encode_eec1(SignalState(spn190_rpm=650))
