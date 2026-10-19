from playlist_sorter.analysis import camelot


def test_known_keys():
    assert camelot.to_camelot(0, 1) == "8B"    # C major
    assert camelot.to_camelot(9, 0) == "8A"    # A minor (relative of C major)
    assert camelot.to_camelot(7, 1) == "9B"    # G major
    assert camelot.to_camelot(11, 1) == "1B"   # B major
    assert camelot.to_camelot(8, 0) == "1A"    # G#/Ab minor
    assert camelot.to_camelot(1, 0) == "12A"   # C#/Db minor


def test_unknown_key():
    assert camelot.to_camelot(-1, 1) is None
    assert camelot.to_camelot(None, None) is None


def test_tables_match_circle_of_fifths_formula():
    for pitch in range(12):
        major = (7 * pitch + 8) % 12 or 12
        minor = (7 * pitch + 5) % 12 or 12
        assert camelot.MAJOR_TO_CAMELOT[pitch] == major
        assert camelot.MINOR_TO_CAMELOT[pitch] == minor


def test_relative_keys_share_a_number():
    # Every major key's relative minor is 3 semitones below it.
    for pitch in range(12):
        relative_minor = (pitch - 3) % 12
        assert camelot.to_camelot(pitch, 1)[:-1] == camelot.to_camelot(relative_minor, 0)[:-1]


def test_transition_costs():
    assert camelot.transition_cost("8A", "8A") == 0
    assert camelot.transition_cost("8A", "9A") == 1
    assert camelot.transition_cost("12A", "1A") == 1   # wraps around the clock
    assert camelot.transition_cost("8A", "8B") == 1
    assert camelot.transition_cost("8A", "10A") == 2
    assert camelot.transition_cost("8A", "2A") == 6    # opposite side of the wheel


def test_describe_transition():
    assert camelot.describe_transition("8A", "8B") == "relative maj/min"
    assert camelot.describe_transition("8A", "7A") == "±1 step"
    assert camelot.describe_transition("8A", "3B") == "key clash"


def test_from_camelot_is_inverse_of_to_camelot():
    for pitch in range(12):
        for mode in (0, 1):
            assert camelot.from_camelot(camelot.to_camelot(pitch, mode)) == (pitch, mode)
    assert camelot.from_camelot("8a") == (9, 0)
    for bad in ("", "13A", "0B", "8C", "A8", "xx"):
        assert camelot.from_camelot(bad) is None
