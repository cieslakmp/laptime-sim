"""Tests for sweep point expansion."""

import pytest

from laptime.api.schemas import SweepParamSpec, SweepRequest
from laptime.sweep.spec import expand_grid, expand_oat, total_points


def _spec(name: str, lo: float, hi: float, steps: int) -> SweepParamSpec:
    return SweepParamSpec(name=name, min=lo, max=hi, steps=steps)


def test_grid_count_is_product_and_last_param_fastest():
    params = [_spec("mass_kg", 600, 800, 3), _spec("p_max_kw", 200, 400, 2)]
    points = expand_grid(params)

    assert len(points) == 6
    assert all(varied is None for varied, _ in points)
    # Last param (p_max_kw) varies fastest — row-major contract for the heatmap.
    masses = [ov["mass_kg"] for _, ov in points]
    powers = [ov["p_max_kw"] for _, ov in points]
    assert masses == [600, 600, 700, 700, 800, 800]
    assert powers == [200, 400, 200, 400, 200, 400]


def test_grid_linspace_endpoints_exact():
    points = expand_grid([_spec("mu_y", 1.5, 2.0, 6)])
    values = [ov["mu_y"] for _, ov in points]
    assert values[0] == pytest.approx(1.5)
    assert values[-1] == pytest.approx(2.0)
    assert len(values) == 6


def test_oat_count_is_sum_and_varies_one_param():
    params = [_spec("mass_kg", 600, 800, 5), _spec("cd", 0.5, 1.5, 3)]
    points = expand_oat(params)

    assert len(points) == 8
    for varied, ov in points:
        assert varied is not None
        assert set(ov) == {varied}


def test_total_points_matches_mode():
    params = [_spec("mass_kg", 600, 800, 4), _spec("cd", 0.5, 1.5, 5)]
    grid = SweepRequest(track_id="t", vehicle={}, params=params, mode="grid")
    oat = SweepRequest(track_id="t", vehicle={}, params=params, mode="one_at_a_time")
    assert total_points(grid) == 20
    assert total_points(oat) == 9


def test_param_spec_rejects_unknown_name():
    with pytest.raises(ValueError, match="Unknown vehicle parameter"):
        _spec("warp_drive", 0, 1, 2)


def test_param_spec_rejects_min_not_below_max():
    with pytest.raises(ValueError, match="min .* must be < max"):
        _spec("mass_kg", 800, 800, 2)


def test_request_rejects_duplicate_param_names():
    with pytest.raises(ValueError, match="Duplicate"):
        SweepRequest(
            track_id="t",
            vehicle={},
            params=[_spec("mass_kg", 600, 800, 2), _spec("mass_kg", 500, 900, 2)],
        )
