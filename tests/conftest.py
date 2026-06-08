"""Shared pytest fixtures."""

import math
import numpy as np
import pytest

from laptime.track.track import Track
from laptime.track.geometry import fit_spline, arc_length_parameterise, compute_curvature, compute_heading
from laptime.vehicle.params import PointMassParams
from laptime.vehicle.point_mass import PointMassVehicle


@pytest.fixture
def circular_track() -> Track:
    """Perfect circle, radius=200 m, 360 stations."""
    R = 200.0
    n = 360
    theta = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x = R * np.cos(theta)
    y = R * np.sin(theta)

    tck, _ = fit_spline(x, y, closed=True)
    u = np.linspace(0, 1, n, endpoint=False)
    s, x_fit, y_fit = arc_length_parameterise(tck, n=n)
    kappa = compute_curvature(tck, u)
    heading = compute_heading(tck, u)

    return Track(
        s=s,
        x=x_fit,
        y=y_fit,
        heading=heading,
        kappa=kappa,
        width_left=np.full(n, 5.0),
        width_right=np.full(n, 5.0),
        banking=np.zeros(n),
        name="circle_200m",
        is_closed=True,
    )


@pytest.fixture
def straight_track() -> Track:
    """1 km straight."""
    n = 200
    s = np.linspace(0, 1000, n)
    x = s.copy()
    y = np.zeros(n)
    heading = np.zeros(n)
    kappa = np.zeros(n)

    return Track(
        s=s,
        x=x,
        y=y,
        heading=heading,
        kappa=kappa,
        width_left=np.full(n, 5.0),
        width_right=np.full(n, 5.0),
        banking=np.zeros(n),
        name="straight_1km",
        is_closed=False,
    )


@pytest.fixture
def fs_vehicle() -> PointMassVehicle:
    """Typical Formula Student car."""
    params = PointMassParams(
        mass_kg=300.0,
        p_max_kw=80.0,
        f_brake_max_n=8000.0,
        mu_x=1.6,
        mu_y=1.8,
        cd=0.5,
        cl=1.5,
        aero_ref_area_m2=1.2,
        v_max_ms=40.0,
    )
    return PointMassVehicle(params)
