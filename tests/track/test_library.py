"""Tests for the built-in F1 circuit library."""

from __future__ import annotations

import pytest

from laptime.track.library import (
    build_library_track,
    list_library_tracks,
    track_metadata,
)


def test_catalog_lists_all_circuits():
    catalog = list_library_tracks()
    assert len(catalog) == 40
    # Sorted by name.
    names = [m["name"] for m in catalog]
    assert names == sorted(names)
    # Every entry carries a preview outline and core metadata.
    sample = catalog[0]
    for key in ("id", "name", "country", "flag", "measured_length_m", "outline"):
        assert key in sample
    assert len(sample["outline"]["x"]) == len(sample["outline"]["y"]) > 2


@pytest.mark.parametrize(
    "name_fragment, official_m",
    [
        ("Monza", 5793),
        ("Monaco", 3337),
        ("Silverstone", 5891),
        ("Spa", 7004),
    ],
)
def test_known_circuit_length_matches_official(name_fragment, official_m):
    catalog = list_library_tracks()
    match = next(m for m in catalog if name_fragment in m["name"])
    # Modelled length should be within 1% of the official figure.
    assert match["measured_length_m"] == pytest.approx(official_m, rel=0.01)


def test_build_track_is_closed_and_metric():
    catalog = list_library_tracks()
    track = build_library_track(catalog[0]["id"])
    assert track.is_closed
    assert track.n_points > 100
    assert track.length > 1000  # metres, not degrees


def test_country_and_flag_derived_from_id():
    meta = track_metadata("it-1922")  # Monza
    assert meta["country"] == "Italy"
    assert meta["flag"] == "\U0001f1ee\U0001f1f9"  # 🇮🇹


def test_unknown_circuit_raises():
    with pytest.raises(KeyError):
        build_library_track("does-not-exist")
