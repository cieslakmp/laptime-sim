"""Tests for the racing-line optimiser output geometry."""

import math

import numpy as np
import pytest

from laptime.optimizer.racing_line import MinCurvatureOptimizer
from laptime.sim.qss import QSSSolver
from laptime.sim.transient import TransientSolver
from laptime.track.geometry import (
    arc_length_parameterise,
    compute_curvature,
    compute_heading,
    fit_spline,
)
from laptime.track.track import Track
from laptime.vehicle.dynamic_vehicle import DynamicVehicle
from laptime.vehicle.dynamics_params import DynamicVehicleParams


@pytest.fixture
def circle_track() -> Track:
    R, n = 70.0, 160
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x, y = R * np.cos(th), R * np.sin(th)
    tck, _ = fit_spline(x, y, closed=True)
    u = np.linspace(0, 1, n, endpoint=False)
    s, xf, yf = arc_length_parameterise(tck, n=n)
    return Track(
        s=s, x=xf, y=yf, heading=compute_heading(tck, u), kappa=compute_curvature(tck, u),
        width_left=np.full(n, 5.0), width_right=np.full(n, 5.0), banking=np.zeros(n),
        name="circle_70", is_closed=True,
    )


def test_racing_line_is_finely_and_consistently_sampled(circle_track):
    opt = MinCurvatureOptimizer(circle_track, n_points=80)
    rline = opt.apply_to_track(opt.optimize(), ds=2.0)

    # Fine, uniform spacing and consistent array lengths.
    assert rline.length / rline.n_points < 3.0
    assert len(rline.x) == len(rline.heading) == len(rline.kappa) == len(rline.width_left)

    # heading must agree with the actual point-to-point geometry (fine spacing => chord≈tangent).
    def chord_heading(i):
        j = (i + 1) % rline.n_points
        return math.atan2(rline.y[j] - rline.y[i], rline.x[j] - rline.x[i])

    errs = [
        abs((rline.heading[i] - chord_heading(i) + math.pi) % (2 * math.pi) - math.pi)
        for i in range(0, rline.n_points, 5)
    ]
    assert math.degrees(max(errs)) < 8.0


def test_racing_line_curvature_is_consistent_with_geometry(circle_track):
    """Total curvature integrates to 2π (turning number 1) — kappa tracks the geometry."""
    opt = MinCurvatureOptimizer(circle_track, n_points=80)
    rline = opt.apply_to_track(opt.optimize(), ds=2.0)
    ds = rline.length / rline.n_points
    total_turning = float(np.sum(rline.kappa) * ds)
    assert math.isclose(total_turning, 2 * math.pi, rel_tol=0.05)


def test_transient_follows_racing_line(circle_track):
    """The transient car can follow the optimised line without leaving the track."""
    veh = DynamicVehicle(DynamicVehicleParams())
    opt = MinCurvatureOptimizer(circle_track, n_points=80)
    rline = opt.apply_to_track(opt.optimize(), ds=2.0)
    qss = QSSSolver(rline, veh, ds=2.0).solve()
    res = TransientSolver(rline, veh, qss, racing_line=rline, dt=2.5e-3).solve()
    assert res.metadata["completed"]
    assert res.metadata["max_lateral_dev_m"] < 5.0
    assert 1.0 <= res.lap_time_s / qss.lap_time_s <= 1.6
