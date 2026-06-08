"""Tests for QSS simulation engine."""

import math
import pytest
import numpy as np

from laptime.sim.qss import QSSSolver


def test_circular_track_lap_time(circular_track, fs_vehicle):
    """Lap time on a circle should be >= circumference / v_max."""
    solver = QSSSolver(circular_track, fs_vehicle, ds=5.0)
    result = solver.solve()

    # Physics lower bound: can't be faster than if we teleported
    R = 200.0
    circumference = 2 * math.pi * R
    v_max = fs_vehicle._p.v_max_ms
    t_min = circumference / v_max

    assert result.lap_time_s > t_min, "Lap time cannot be shorter than distance/v_max"
    assert result.lap_time_s < 300.0, "Lap time is unreasonably long"


def test_velocity_non_negative(circular_track, fs_vehicle):
    solver = QSSSolver(circular_track, fs_vehicle, ds=5.0)
    result = solver.solve()
    assert (result.v >= 0).all()


def test_lateral_accel_within_limit(circular_track, fs_vehicle):
    """ay at each station must not exceed lateral_limit (with small tolerance)."""
    solver = QSSSolver(circular_track, fs_vehicle, ds=5.0)
    result = solver.solve()

    for i in range(len(result.s)):
        s_val = result.s[i]
        pt = circular_track.at(s_val)
        ay_lim = fs_vehicle.lateral_limit(float(result.v[i]), pt.kappa, pt.banking)
        assert abs(result.ay[i]) <= ay_lim + 0.5, (
            f"Lateral accel {result.ay[i]:.2f} exceeds limit {ay_lim:.2f} at s={s_val:.1f}"
        )


def test_lap_time_improves_with_more_grip():
    """More lateral grip → shorter lap time on a grip-limited tight circle."""
    from laptime.track.geometry import fit_spline, arc_length_parameterise, compute_curvature, compute_heading
    from laptime.track.track import Track
    from laptime.vehicle.params import PointMassParams
    from laptime.vehicle.point_mass import PointMassVehicle

    # R=50m: corner speed limit with mu_y=1.2 is ~24 m/s, well below v_max=80 → grip-limited
    R = 50.0
    n = 200
    theta = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x = R * np.cos(theta)
    y = R * np.sin(theta)
    tck, _ = fit_spline(x, y, closed=True)
    u = np.linspace(0, 1, n, endpoint=False)
    s, xf, yf = arc_length_parameterise(tck, n=n)
    tight_circle = Track(
        s=s, x=xf, y=yf,
        heading=compute_heading(tck, u),
        kappa=compute_curvature(tck, u),
        width_left=np.full(n, 5.0), width_right=np.full(n, 5.0),
        banking=np.zeros(n), name="tight_circle", is_closed=True,
    )

    def make_vehicle(mu_y: float) -> PointMassVehicle:
        return PointMassVehicle(PointMassParams(
            mass_kg=300, p_max_kw=200, f_brake_max_n=8000,
            mu_x=1.6, mu_y=mu_y, cd=0.3, cl=0.0,
            aero_ref_area_m2=1.2, v_max_ms=80.0,
        ))

    t_low = QSSSolver(tight_circle, make_vehicle(1.2), ds=2.0).solve().lap_time_s
    t_high = QSSSolver(tight_circle, make_vehicle(2.0), ds=2.0).solve().lap_time_s
    assert t_high < t_low, f"Higher grip should produce faster lap time ({t_high:.3f} vs {t_low:.3f})"
