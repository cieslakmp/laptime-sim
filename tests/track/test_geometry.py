"""Tests for track geometry module."""

import math
import numpy as np
import pytest

from laptime.track.geometry import (
    arc_length_parameterise,
    compute_curvature,
    compute_heading,
    fit_spline,
)


def test_circle_curvature():
    """Curvature of a circle of radius R should be ≈ 1/R everywhere."""
    R = 100.0
    n = 500
    theta = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x = R * np.cos(theta)
    y = R * np.sin(theta)

    tck, _ = fit_spline(x, y, closed=True)
    u = np.linspace(0, 1, n, endpoint=False)
    kappa = compute_curvature(tck, u)

    expected = 1.0 / R
    assert np.abs(np.abs(kappa) - expected).max() < 0.002, (
        f"Curvature should be {expected:.4f} but got range "
        f"[{np.abs(kappa).min():.4f}, {np.abs(kappa).max():.4f}]"
    )


def test_straight_curvature_near_zero():
    """Curvature of a straight line should be near zero."""
    n = 100
    x = np.linspace(0, 500, n)
    y = np.zeros(n)

    tck, _ = fit_spline(x, y, closed=False)
    u = np.linspace(0, 1, n)
    kappa = compute_curvature(tck, u)

    assert np.abs(kappa[10:-10]).max() < 1e-4


def test_arc_length_monotonic():
    """Arc-length array must be strictly increasing."""
    R = 150.0
    n = 200
    theta = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x = R * np.cos(theta)
    y = R * np.sin(theta)

    tck, _ = fit_spline(x, y, closed=True)
    s, _, _ = arc_length_parameterise(tck, n=n)

    assert np.all(np.diff(s) > 0)


def test_arc_length_total():
    """Total arc-length of a circle should match 2πR within 1%."""
    R = 200.0
    n = 500
    theta = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x = R * np.cos(theta)
    y = R * np.sin(theta)

    tck, _ = fit_spline(x, y, closed=True)
    s, _, _ = arc_length_parameterise(tck, n=n)

    ds = s[1] - s[0]
    total = s[-1] + ds
    expected = 2 * math.pi * R
    assert abs(total - expected) / expected < 0.01
