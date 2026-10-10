from pathlib import Path

import pytest

from j1939_emulator.bus.detect import DetectedChannel, EmulationMode, match_channel
from j1939_emulator.config import load_config
from j1939_emulator.meters_store import restore_meters, save_meters, state_file
from j1939_emulator.pgn import SignalState

ROOT = Path(__file__).resolve().parent.parent
BUS = '[bus]\nmode = "virtual"\nchannel = "vcan0"\nbitrate = 250000\n'


def _write(tmp_path, text):
    p = tmp_path / "ecu.toml"
    p.write_text(text, encoding="utf-8")
    return p


@pytest.mark.parametrize("name", ["examples/ecu.toml", "my_ecu.toml"])
def test_shipped_configs_load(name):
    cfg = load_config(ROOT / name)
    assert cfg.identity.name == 0x1000000000000000


def test_legacy_keys_still_accepted(tmp_path):
    cfg = load_config(_write(tmp_path, BUS + "[ecu]\nname = 0x0020000000000000\n"
                             "[pgn.vd]\nspn917_total_mi = 42\n"))
    assert cfg.identity.vehicle_system == 16
    assert cfg.signals.spn245_total_mi == 42


def test_name_fields_override_full_name(tmp_path):
    cfg = load_config(_write(tmp_path, BUS + "[ecu]\nname = 0x0020000000000000\nindustry_group = 1\n"))
    assert cfg.identity.industry_group == 1
    assert cfg.identity.vehicle_system == 16


def test_bad_bitrate_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, BUS.replace("250000", "300000")))


def test_persist_meters_flag(tmp_path):
    assert load_config(_write(tmp_path, BUS)).persist_meters is True
    off = load_config(_write(tmp_path, BUS + "[vehicle]\npersist_meters = false\n"))
    assert off.persist_meters is False


def test_meters_saved_per_vin(isolated_state_dir):
    save_meters(SignalState(spn245_total_mi=111, spn247_engine_hours=11), "VINA")
    save_meters(SignalState(spn245_total_mi=222, spn247_engine_hours=22), "VINB")
    assert state_file().parent == isolated_state_dir

    restored = SignalState()
    assert restore_meters(restored, "VINA")
    assert (restored.spn245_total_mi, restored.spn247_engine_hours) == (111, 11)
    assert not restore_meters(SignalState(), "UNKNOWN")


def test_corrupt_state_file_is_ignored():
    state_file().parent.mkdir(parents=True)
    state_file().write_text("{not json", encoding="utf-8")
    assert not restore_meters(SignalState(), "VINA")
    save_meters(SignalState(spn245_total_mi=5), "VINA")  # overwrites cleanly
    assert restore_meters(SignalState(), "VINA")


def test_match_channel_by_number_and_name():
    chans = [
        DetectedChannel(
            uid=f"virtual:vcan{i}",
            label=f"Virtual CAN  (vcan{i})",
            interface="virtual",
            bus_kwargs={"interface": "virtual", "channel": f"vcan{i}"},
            kind=EmulationMode.VIRTUAL,
        )
        for i in range(3)
    ]
    assert match_channel(chans, "2") is chans[1]
    assert match_channel(chans, "vcan2") is chans[2]
    assert match_channel(chans, "4") is None
    assert match_channel(chans, "nope") is None


def test_ignition_from_config(tmp_path):
    assert load_config(_write(tmp_path, BUS)).signals.engine_running
    cfg = load_config(_write(tmp_path, BUS + '[vehicle]\nignition = "on"\n'))
    assert not cfg.signals.engine_running
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, BUS + '[vehicle]\nignition = "off"\n'))


def test_hrvd_section_switches_and_times_the_broadcast(tmp_path):
    assert load_config(_write(tmp_path, BUS)).signals.hrvd_enabled
    cfg = load_config(_write(tmp_path, BUS + "[pgn.hrvd]\nenabled = false\ncycle_ms = 500\n"))
    assert not cfg.signals.hrvd_enabled
    assert cfg.signals.cycle_hrvd_ms == 500
