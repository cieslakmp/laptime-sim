"""Tests for the full OCP solver."""

import math
import numpy as np
import pytest

from laptime.optimizer.ocp import OCPSolver, OCPResult
from laptime.vehicle.params import PointMassParams
from laptime.vehicle.point_mass import PointMassVehicle
from laptime.sim.qss import QSSSolver


def make_params(**overrides) -> PointMassParams:
    defaults = dict(
        mass_kg=300,
        p_max_kw=200,
        f_brake_max_n=8000,
        mu_x=1.6,
        mu_y=1.8,
        cd=0.3,
        cl=0.0,
        aero_ref_area_m2=1.2,
        v_max_ms=80.0,
    )
    defaults.update(overrides)
    return PointMassParams(**defaults)


def _make_circular_track(R: float = 200.0, n: int = 360):
    """Build a circular Track with radius R without relying on conftest fixtures."""
    from laptime.track.geometry import (
        arc_length_parameterise, compute_curvature, compute_heading, fit_spline,
    )
    from laptime.track.track import Track

    theta = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x = R * np.cos(theta)
    y = R * np.sin(theta)
    tck, _ = fit_spline(x, y, closed=True)
    u = np.linspace(0, 1, n, endpoint=False)
    s, x_fit, y_fit = arc_length_parameterise(tck, n=n)
    return Track(
        s=s, x=x_fit, y=y_fit,
        heading=compute_heading(tck, u),
        kappa=compute_curvature(tck, u),
        width_left=np.full(n, 5.0),
        width_right=np.full(n, 5.0),
        banking=np.zeros(n),
        name="circle_200m",
        is_closed=True,
    )


@pytest.fixture(scope="module")
def ocp_result_circle():
    """OCP solution on the 200m radius circle — computed once for all tests."""
    track = _make_circular_track()
    params = make_params()
    solver = OCPSolver(track, params, N=60)
    return solver.solve(), track, params


def test_ocp_returns_result(ocp_result_circle):
    result, _, _ = ocp_result_circle
    assert isinstance(result, OCPResult)


def test_ocp_lap_time_positive(ocp_result_circle):
    result, _, _ = ocp_result_circle
    assert result.lap_time_s > 0


def test_ocp_velocity_non_negative(ocp_result_circle):
    result, _, _ = ocp_result_circle
    assert (result.v >= 0).all()


def test_ocp_improves_on_qss(ocp_result_circle):
    """OCP lap time must be <= QSS lap time (QSS is a feasible but suboptimal point)."""
    result, track, params = ocp_result_circle
    vehicle = PointMassVehicle(params)
    qss_time = QSSSolver(track, vehicle, ds=5.0).solve().lap_time_s
    # OCP should not be worse than QSS (it optimises, not constrains)
    # Allow small tolerance for numerical differences
    assert result.lap_time_s <= qss_time + 0.5, (
        f"OCP time {result.lap_time_s:.3f} s should not exceed QSS time {qss_time:.3f} s"
    )


def test_ocp_lateral_offset_within_bounds(ocp_result_circle):
    """Lateral offset n must stay within track width."""
    result, track, _ = ocp_result_circle
    # All stations should stay within ±width_left/right
    wl = track.width_left[0]
    wr = track.width_right[0]
    assert (result.n >= -wr - 0.1).all(), "n violates right boundary"
    assert (result.n <= wl + 0.1).all(), "n violates left boundary"


def test_ocp_path_coordinates_shape(ocp_result_circle):
    """x_path and y_path must have the same length as s."""
    result, _, _ = ocp_result_circle
    assert len(result.x_path) == len(result.s)
    assert len(result.y_path) == len(result.s)


def test_ocp_to_lap_result(ocp_result_circle):
    """to_lap_result() must return a valid LapResult with metadata."""
    from laptime.sim.result import LapResult
    result, _, _ = ocp_result_circle
    lr = result.to_lap_result()
    assert isinstance(lr, LapResult)
    assert lr.lap_time_s == result.lap_time_s
    assert "n" in lr.metadata
    assert "x_path" in lr.metadata
