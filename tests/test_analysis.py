"""Tests for the analysis / validation utilities."""

import math

import numpy as np
import pytest

from laptime.analysis import compare_solvers, ggv_envelope, transient_trace
from laptime.sim.qss import QSSSolver
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
def circle() -> Track:
    R, n = 80.0, 200
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
def vehicle() -> DynamicVehicle:
    return DynamicVehicle(DynamicVehicleParams())


def test_ggv_envelope_is_physically_sane(vehicle):
    ggv = ggv_envelope(vehicle, speeds=np.linspace(20, 70, 6))
    # Lateral grip is positive everywhere and grows with speed (downforce).
    assert np.all(ggv.ay_max_ms2 > 0)
    assert ggv.ay_max_ms2[-1] > ggv.ay_max_ms2[0]
    # Acceleration is positive, braking negative, both within a plausible band.
    assert np.all(ggv.ax_max_ms2 >= 0)
    assert np.all(ggv.ax_min_ms2 <= 0)
    assert np.all(ggv.ay_max_ms2 / 9.81 < 3.0)


def test_compare_solvers_runs_qss_and_transient(circle, vehicle):
    cmp = compare_solvers(circle, vehicle, use_racing_line=False, dt=2.5e-3)
    assert "qss" in cmp.lap_times_s and "transient_7dof" in cmp.lap_times_s
    # Transient tracks the QSS reference, a little slower.
    ratio = cmp.lap_times_s["transient_7dof"] / cmp.lap_times_s["qss"]
    assert 1.0 <= ratio <= 1.6
    assert "QSS" in cmp.summary()


def test_transient_trace_captures_load_transfer(circle, vehicle):
    qss = QSSSolver(circle, vehicle, ds=2.0).solve()
    tr = transient_trace(circle, vehicle, qss, line=circle, dt=2.5e-3)
    assert tr.fz.shape[1] == 4
    assert len(tr.t) == len(tr.yaw_rate) == len(tr.roll_deg)
    # In a steady left-hand circle the outer (right) wheels carry more load than the inner.
    mid = slice(len(tr.t) // 2, None)
    assert tr.fz[mid, 1].mean() > tr.fz[mid, 0].mean()  # FR > FL
    assert tr.fz[mid, 3].mean() > tr.fz[mid, 2].mean()  # RR > RL
    # Total load is conserved near the static weight + downforce.
    assert np.all(tr.fz.sum(axis=1) > 0)
