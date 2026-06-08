"""Track geometry: spline fitting, arc-length parameterisation, curvature."""

from __future__ import annotations

import numpy as np
from scipy.interpolate import splev, splprep
from scipy.ndimage import gaussian_filter1d


def fit_spline(
    x: np.ndarray,
    y: np.ndarray,
    closed: bool = True,
    smooth: float = 0.0,
) -> tuple:
    """Fit a parametric cubic spline through (x, y) points.

    Returns (tck, u) as from scipy.interpolate.splprep.
    For closed tracks the first and last point should NOT be duplicated.
    """
    if closed:
        # Append first point to close the loop
        x = np.append(x, x[0])
        y = np.append(y, y[0])

    tck, u = splprep([x, y], s=smooth, per=closed, k=3)
    return tck, u


def arc_length_parameterise(
    tck: tuple,
    n: int = 1000,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sample spline at n uniform arc-length stations.

    Returns (s, x, y) arrays of shape (n,).
    s is cumulative arc-length in metres starting at 0.
    """
    # Sample densely first to compute arc-length accurately
    u_dense = np.linspace(0, 1, 10 * n)
    xd, yd = splev(u_dense, tck)
    ds = np.sqrt(np.diff(xd) ** 2 + np.diff(yd) ** 2)
    s_dense = np.concatenate([[0.0], np.cumsum(ds)])

    # Re-parameterise to uniform arc-length spacing
    s_uniform = np.linspace(0, s_dense[-1], n, endpoint=False)
    u_uniform = np.interp(s_uniform, s_dense, u_dense)

    x, y = splev(u_uniform, tck)
    return s_uniform, x, y


def compute_curvature(
    tck: tuple,
    u: np.ndarray,
    smooth_sigma: float = 0.0,
) -> np.ndarray:
    """Compute signed curvature κ at parametric positions u.

    κ = (x'y'' - y'x'') / (x'² + y'²)^(3/2)
    Positive κ = left turn (anti-clockwise).
    """
    xp, yp = splev(u, tck, der=1)
    xpp, ypp = splev(u, tck, der=2)

    denom = (xp**2 + yp**2) ** 1.5
    # Avoid division by zero on perfectly straight sections
    denom = np.where(denom < 1e-10, 1e-10, denom)
    kappa = (xp * ypp - yp * xpp) / denom

    if smooth_sigma > 0:
        kappa = gaussian_filter1d(kappa, sigma=smooth_sigma, mode="wrap")

    return kappa


def compute_heading(tck: tuple, u: np.ndarray) -> np.ndarray:
    """Compute track heading angle [rad] at parametric positions u."""
    xp, yp = splev(u, tck, der=1)
    return np.arctan2(yp, xp)
