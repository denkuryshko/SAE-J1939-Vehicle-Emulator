import pytest

from j1939_emulator.diagnostics import DiagnosticState, encode_dm1
from j1939_emulator.ecu_identity import EcuIdentity, validate_vin


def test_vin_payload_is_ascii_with_star_delimiter():
    ident = EcuIdentity(vin="1HTMMAAL7GH123456")
    assert bytes(ident.vin_payload()) == b"1HTMMAAL7GH123456*"


@pytest.mark.parametrize("bad", ["", "1HTMMAAL7GH1234567", "1HTMMAAL7GH12345O"])
def test_vin_validation(bad):
    with pytest.raises(ValueError):
        validate_vin(bad)


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
    data = encode_dm1(DiagnosticState(dtc_spn110_fmi3=True))
    assert data == bytes([0x04, 0xFF, 0x6E, 0x00, 0x03, 0x01, 0xFF, 0xFF])


def test_dm1_two_faults_needs_multipacket():
    data = encode_dm1(DiagnosticState(dtc_spn110_fmi3=True, dtc_spn190_fmi0=True))
    assert len(data) == 10
    assert data[0] == 0x14  # amber warning + red stop
