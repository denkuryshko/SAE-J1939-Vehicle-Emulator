import pytest

from j1939_emulator.meters_store import STATE_DIR_ENV


@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path, monkeypatch):
    """Never touch the real meters.json of the person running the tests."""
    monkeypatch.setenv(STATE_DIR_ENV, str(tmp_path / "state"))
    return tmp_path / "state"
