import pytest

from diamond360.d360_source import (
    FRAME_COUNT,
    KNOWN_SOURCES,
    PACK_COUNTS,
    PACK_START_SERIALS,
    canonical_progressive_positions,
    ordered_positions,
    parse_viewer,
    validate_scramble,
)


def test_parse_viewer_url_and_bare_id():
    url, item = parse_viewer("https://d360.tech/view.html?d=79-BB-5159600")
    assert item == "79-BB-5159600"
    assert url == "https://d360.tech/view.html?d=79-BB-5159600"

    url2, item2 = parse_viewer("79-BT-5165227")
    assert item2 == "79-BT-5165227"
    assert url2.endswith("?d=79-BT-5165227")


@pytest.mark.parametrize(
    "value",
    [
        "http://d360.tech/view.html?d=79-BB-5159600",
        "https://example.com/view.html?d=79-BB-5159600",
        "https://d360.tech/view.html",
        "https://d360.tech/view.html?d=../../etc/passwd",
    ],
)
def test_parse_viewer_rejects_untrusted_inputs(value):
    with pytest.raises(ValueError):
        parse_viewer(value)


def test_canonical_progressive_positions_are_complete():
    mapping = canonical_progressive_positions()
    assert len(mapping) == FRAME_COUNT
    assert set(mapping) == set(range(1, FRAME_COUNT + 1))
    assert set(mapping.values()) == set(range(1, FRAME_COUNT + 1))
    assert [mapping[i] for i in range(1, 9)] == [1, 65, 129, 193, 33, 97, 161, 225]


def test_pack_layout_covers_256_progressive_serials_once():
    serials = []
    for start, count in zip(PACK_START_SERIALS, PACK_COUNTS):
        serials.extend(range(start, start + count))
    assert serials == list(range(1, FRAME_COUNT + 1))


def test_identity_scramble_preserves_canonical_progressive_mapping():
    identity = [list(range(n)) for n in PACK_COUNTS]
    assert ordered_positions(identity) == canonical_progressive_positions()


def test_known_scrambles_are_valid_complete_permutations():
    expected_first_targets = {
        "79-BB-5159600": [192, 128, 64, 0, 96, 224, 160, 32, 176],
        "79-BT-5165227": [128, 64, 0, 192, 96, 160, 32, 224, 48],
    }
    for item_id, source in KNOWN_SOURCES.items():
        validate_scramble(source["scramble"])
        mapping = ordered_positions(source["scramble"])
        assert set(mapping.values()) == set(range(1, FRAME_COUNT + 1))
        assert [mapping[i] - 1 for i in range(1, 10)] == expected_first_targets[item_id]


def test_invalid_scramble_fails_closed():
    bad = [list(range(n)) for n in PACK_COUNTS]
    bad[-1][0] = bad[-1][1]
    with pytest.raises(ValueError, match="permutation"):
        ordered_positions(bad)
