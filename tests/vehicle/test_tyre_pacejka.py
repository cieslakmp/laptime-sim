"""Tests for the simplified Pacejka tyre model."""

import numpy as np

from laptime.vehicle.tyre_pacejka import (
    PacejkaCoeffs,
    combined_forces,
    pure_lateral_fy,
    pure_longitudinal_fx,
)

FZ0 = 3500.0


def test_zero_slip_zero_force():
    c = PacejkaCoeffs()
    assert pure_lateral_fy(0.0, FZ0, c) == 0.0
    assert pure_longitudinal_fx(0.0, FZ0, c) == 0.0


def test_lateral_opposes_slip():
    """Positive slip angle must produce a restoring (negative) lateral force."""
    c = PacejkaCoeffs()
    assert pure_lateral_fy(0.05, FZ0, c) < 0.0
    assert pure_lateral_fy(-0.05, FZ0, c) > 0.0


def test_longitudinal_sign():
    c = PacejkaCoeffs()
    assert pure_longitudinal_fx(0.05, FZ0, c) > 0.0
    assert pure_longitudinal_fx(-0.05, FZ0, c) < 0.0


def test_lateral_peak_at_realistic_slip_angle():
    """Peak lateral force should occur at a realistic slip angle (~5-12 deg)."""
    c = PacejkaCoeffs()
    alpha = np.linspace(0.0, 0.6, 2000)
    fy = -pure_lateral_fy(alpha, np.full_like(alpha, FZ0), c)
    peak_alpha = alpha[int(np.argmax(fy))]
    assert np.radians(4) < peak_alpha < np.radians(13)
    # Peak force approaches the load-scaled peak D = mu * Fz (C > 1).
    assert fy.max() > 0.9 * c.D_y_mu * FZ0


def test_longitudinal_peak_at_realistic_slip_ratio():
    c = PacejkaCoeffs()
    kappa = np.linspace(0.0, 0.4, 2000)
    fx = pure_longitudinal_fx(kappa, np.full_like(kappa, FZ0), c)
    peak_kappa = kappa[int(np.argmax(fx))]
    assert 0.05 < peak_kappa < 0.20


def test_degressive_load_sensitivity():
    """Doubling load must less-than-double the peak force (mu falls with load)."""
    c = PacejkaCoeffs()
    fy_1 = -pure_lateral_fy(0.15, FZ0, c)
    fy_2 = -pure_lateral_fy(0.15, 2 * FZ0, c)
    assert fy_2 < 2 * fy_1


def test_combined_stays_inside_friction_ellipse():
    """Combined-slip resultant must not exceed the per-axis peaks (g-normalisation)."""
    c = PacejkaCoeffs()
    alpha = np.linspace(-0.4, 0.4, 41)
    kappa = np.linspace(-0.4, 0.4, 41)
    a, k = np.meshgrid(alpha, kappa)
    fx, fy = combined_forces(a.ravel(), k.ravel(), np.full(a.size, FZ0), c)
    dx, dy = c.D_x_mu * FZ0, c.D_y_mu * FZ0
    radius = np.hypot(fx / dx, fy / dy)
    assert radius.max() <= 1.0 + 1e-9


def test_combined_recovers_pure_cases():
    c = PacejkaCoeffs()
    # Pure lateral (no longitudinal slip) recovers the pure lateral curve.
    fx, fy = combined_forces(0.1, 0.0, FZ0, c)
    assert np.isclose(fy, pure_lateral_fy(0.1, FZ0, c))
    assert abs(fx) < 1e-9


def test_lift_off_wheel_carries_no_force():
    c = PacejkaCoeffs()
    fx, fy = combined_forces(0.1, 0.1, 0.0, c)
    assert abs(fx) < 1e-9 and abs(fy) < 1e-9
