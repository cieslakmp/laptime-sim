"""Integration tests for the transient 7DOF lap simulator."""

import math

import numpy as np
import pytest

from laptime.sim.qss import QSSSolver
from laptime.sim.transient import TransientSolver
from laptime.track.geometry import (
    arc_length_parameterise,
    compute_curvature,
    compute_heading,
    fit_spline,
)
from laptime.track.track import Track
from laptime.vehicle.dynamic_vehicle import I_R, I_VX, DynamicVehicle
from laptime.vehicle.dynamics_params import DynamicVehicleParams


@pytest.fixture
def circle_80() -> Track:
    """Moderate-speed constant-radius circle (R=80 m)."""
    R, n = 80.0, 240
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x, y = R * np.cos(th), R * np.sin(th)
    tck, _ = fit_spline(x, y, closed=True)
    u = np.linspace(0, 1, n, endpoint=False)
    s, xf, yf = arc_length_parameterise(tck, n=n)
    return Track(
        s=s, x=xf, y=yf, heading=compute_heading(tck, u), kappa=compute_curvature(tck, u),
        width_left=np.full(n, 6.0), width_right=np.full(n, 6.0), banking=np.zeros(n),
        name="circle_80", is_closed=True,
    )


@pytest.fixture
def dyn_vehicle() -> DynamicVehicle:
    return DynamicVehicle(DynamicVehicleParams())


def _solve(track, vehicle, dt=2.5e-3):
    qss = QSSSolver(track, vehicle, ds=2.0).solve()
    res = TransientSolver(track, vehicle, qss, racing_line=track, dt=dt).solve()
    return qss, res


def test_transient_completes_and_tracks(circle_80, dyn_vehicle):
    qss, res = _solve(circle_80, dyn_vehicle)
    assert res.metadata["completed"]
    assert not res.metadata["aborted"]
    # Stays on track (within the 6 m half-width).
    assert res.metadata["max_lateral_dev_m"] < 6.0


def test_transient_result_is_well_formed(circle_80, dyn_vehicle):
    _, res = _solve(circle_80, dyn_vehicle)
    assert res.s.shape == res.v.shape == res.ax.shape == res.ay.shape
    assert np.all(np.isfinite(res.v)) and np.all(res.v > 0)
    assert np.all(np.isfinite(res.ax)) and np.all(np.isfinite(res.ay))
    assert math.isfinite(res.lap_time_s)


def test_transient_lap_time_near_qss(circle_80, dyn_vehicle):
    """Transient car follows the QSS reference, a little slower than the ideal."""
    qss, res = _solve(circle_80, dyn_vehicle)
    ratio = res.lap_time_s / qss.lap_time_s
    assert 1.0 <= ratio <= 1.6


def test_transient_deterministic(circle_80, dyn_vehicle):
    _, res1 = _solve(circle_80, dyn_vehicle)
    _, res2 = _solve(circle_80, dyn_vehicle)
    assert res1.lap_time_s == res2.lap_time_s


def test_skidpad_steady_lateral_acceleration():
    """Open-loop: a constant steer/throttle settles into steady cornering with sane grip."""
    veh = DynamicVehicle(DynamicVehicleParams())
    R_target = 60.0
    x = veh.initial_state(25.0, 0.0)
    u = np.array([veh._p.chassis.wheelbase_m / R_target, 0.18, 0.0])
    dt, t, f = 1e-3, 0.0, veh.derivatives
    for _ in range(6000):
        k1 = f(t, x, u)
        k2 = f(t + dt / 2, x + dt / 2 * k1, u)
        k3 = f(t + dt / 2, x + dt / 2 * k2, u)
        k4 = f(t + dt, x + dt * k3, u)
        x = x + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        t += dt

    vx, r = x[I_VX], x[I_R]
    ay = vx * r
    # Turning the right way, settled on a sensible radius, with a realistic grip level.
    assert r > 0
    assert 40.0 < vx / r < 90.0
    assert 1.0 < ay / 9.81 < 2.0
    # Kinematic consistency: ay ≈ vx² / R.
    assert math.isclose(ay, vx**2 / (vx / r), rel_tol=1e-6)
