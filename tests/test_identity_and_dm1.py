import pytest

from j1939_emulator.diagnostics import DiagnosticState, Dtc, encode_dm1
from j1939_emulator.ecu_identity import (
    EcuIdentity,
    generate_vin,
    validate_vin,
    vin_check_digit_warning,
)


def test_vin_payload_is_ascii_with_star_delimiter():
    ident = EcuIdentity(vin="1HTMMAAL5GH123456")
    assert bytes(ident.vin_payload()) == b"1HTMMAAL5GH123456*"


@pytest.mark.parametrize("bad", ["", "1HTMMAAL5GH1234567", "1HTMMAAL5GH12345O"])
def test_vin_validation(bad):
    with pytest.raises(ValueError):
        validate_vin(bad)


def test_vin_check_digit_warning():
    assert vin_check_digit_warning("1HTMMAAL5GH123456") is None
    assert "expected '5'" in vin_check_digit_warning("1HTMMAAL7GH123456")
    assert vin_check_digit_warning("ABC123") is None  # partial VINs are not checked


def test_generate_vin_is_valid_and_keeps_prefix():
    for _ in range(200):
        vin = generate_vin("1HTMMAAL5GH123456")
        assert validate_vin(vin) == vin and len(vin) == 17
        assert vin.startswith("1HTMMAAL")
        assert vin_check_digit_warning(vin) is None


def test_default_name_is_on_highway_engine():
    ident = EcuIdentity()
    assert ident.name == 0x1000000000000000
    fields = EcuIdentity.name_fields(ident.name)
    assert fields["industry_group"] == 1
    assert fields["function"] == 0


def test_name_round_trips_through_fields():
    legacy = 0x0020000000000000
    assert EcuIdentity(**EcuIdentity.name_fields(legacy)).name == legacy


def test_name_field_out_of_range():
    with pytest.raises(ValueError):
        EcuIdentity(industry_group=8)


def test_dm1_no_faults_is_a_full_8_byte_frame():
    assert encode_dm1(DiagnosticState()) == bytes([0x00, 0xFF, 0, 0, 0, 0, 0xFF, 0xFF])


def test_dm1_one_fault_padded_to_8_bytes():
    state = DiagnosticState()
    state.set_active("spn110_fmi3", True)
    data = encode_dm1(state)
    assert data == bytes([0x04, 0xFF, 0x6E, 0x00, 0x03, 0x01, 0xFF, 0xFF])


def test_dm1_two_faults_needs_multipacket():
    state = DiagnosticState()
    state.inject_all()
    data = encode_dm1(state)
    assert len(data) == 10
    assert data[0] == 0x14  # amber warning + red stop


def test_dtc_list_from_config_lights_its_lamps():
    state = DiagnosticState(dtcs=[Dtc(100, 1, "mil"), Dtc(3216, 2, "protect", oc=5)])
    state.inject_all()
    data = encode_dm1(state)
    assert len(data) == 10
    assert data[0] == 0x41  # MIL (bits 8-7) + protect (bits 2-1)
    assert data[5] & 0x7F == 1 and data[9] & 0x7F == 5  # occurrence counts


def test_occurrence_count_grows_when_a_dtc_comes_back():
    state = DiagnosticState()
    state.set_active("spn110_fmi3", True)
    state.set_active("spn110_fmi3", True)  # still active: same occurrence
    assert state.get("spn110_fmi3").oc == 1
    state.set_active("spn110_fmi3", False)
    state.set_active("spn110_fmi3", True)
    assert state.get("spn110_fmi3").oc == 2


@pytest.mark.parametrize("kwargs", [
    {"spn": 1 << 19, "fmi": 0}, {"spn": 1, "fmi": 32}, {"spn": 1, "fmi": 0, "lamp": "blue"},
    {"spn": 1, "fmi": 0, "oc": 127},
])
def test_dtc_out_of_range(kwargs):
    with pytest.raises(ValueError):
        Dtc(**kwargs)


def test_duplicate_and_unknown_dtcs():
    with pytest.raises(ValueError, match="Duplicate"):
        DiagnosticState(dtcs=[Dtc(110, 3), Dtc(110, 3, "red")])
    with pytest.raises(KeyError):
        DiagnosticState().set_active("spn1_fmi1", True)
