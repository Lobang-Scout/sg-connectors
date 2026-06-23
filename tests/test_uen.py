"""UEN format validation tests."""

from uen import validate_uen


def test_business_format_a():
    c = validate_uen("53123456A")
    assert c.valid and c.format == "A"


def test_local_company_format_b():
    c = validate_uen("201912345K")
    assert c.valid and c.format == "B"
    assert "2019" in c.description


def test_other_entity_format_c():
    c = validate_uen("T10LL0001B")
    assert c.valid and c.format == "C"
    assert "LL" in c.description


def test_lowercase_is_normalised():
    c = validate_uen("t10ll0001b")
    assert c.valid and c.format == "C"
    assert c.uen == "T10LL0001B"


def test_whitespace_is_trimmed():
    assert validate_uen("  53123456A  ").uen == "53123456A"


def test_invalid_prefix_for_format_c():
    # Only T / S / R are valid prefixes.
    assert not validate_uen("X10LL0001B").valid


def test_too_short_is_invalid():
    assert not validate_uen("12345A").valid


def test_empty_is_invalid():
    c = validate_uen("")
    assert not c.valid and c.format is None
