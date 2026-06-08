"""Tests for PointMassVehicle."""

import pytest
from laptime.vehicle.params import PointMassParams
from laptime.vehicle.point_mass import PointMassVehicle


@pytest.fixture
def car():
    return PointMassVehicle(PointMassParams(
        mass_kg=700, p_max_kw=400, f_brake_max_n=20000,
        mu_x=1.6, mu_y=1.8, cd=0.9, cl=2.5,
        aero_ref_area_m2=1.5, v_max_ms=83.0,
    ))


def test_lateral_limit_positive(car):
    assert car.lateral_limit(30.0) > 0


def test_lateral_limit_increases_with_speed_due_to_downforce(car):
    """Downforce increases normal load → more grip at higher speed."""
    ay_low = car.lateral_limit(20.0)
    ay_high = car.lateral_limit(60.0)
    assert ay_high > ay_low


def test_longitudinal_limits_signs(car):
    a_min, a_max = car.longitudinal_limits(30.0, 0.0)
    assert a_min < 0, "Braking limit must be negative"
    assert a_max >= 0, "Acceleration limit must be non-negative"


def test_traction_circle_respected(car):
    """With full lateral load, longitudinal capacity should shrink."""
    v = 30.0
    ay_full = car.lateral_limit(v)
    _, ax_max_no_lat = car.longitudinal_limits(v, 0.0)
    _, ax_max_full_lat = car.longitudinal_limits(v, ay_full * 0.99)
    assert ax_max_full_lat < ax_max_no_lat


def test_top_speed_cap(car):
    """At very high speed, ax_max should approach zero."""
    _, ax_max = car.longitudinal_limits(83.0, 0.0)
    assert ax_max < 2.0  # near the power/drag limit
