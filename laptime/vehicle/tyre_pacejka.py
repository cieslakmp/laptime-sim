"""Simplified Pacejka Magic Formula tyre model.

Pure-slip lateral/longitudinal forces with a degressive load-sensitive peak and a
friction-ellipse (g-normalisation) combined-slip weighting. All force functions are
stateless and vectorise over the four wheels (numpy arrays).

Sign convention (consistent with the body frame used by ``DynamicVehicle``):
  - ``alpha`` is the slip angle [rad]; the tyre develops a lateral force that opposes
    the slip, so :func:`pure_lateral_fy` already returns the restoring force, i.e. a
    positive ``alpha`` yields a negative ``Fy``.
  - ``kappa`` is the longitudinal slip ratio [-]; a positive ``kappa`` (wheel spinning
    faster than the road) yields a positive (forward) ``Fx``.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel

from .params import Positive

# Floor on the load-sensitive friction multiplier so the peak never collapses to zero.
_MU_FLOOR_FRACTION = 0.1


class PacejkaCoeffs(BaseModel):
    """Simplified Magic Formula coefficients for a single tyre/axle."""

    # Lateral pure-slip (peak near 8.5° slip angle)
    B_y: Positive = 10.0
    C_y: Positive = 1.5
    D_y_mu: Positive = 1.7
    E_y: float = -0.5
    # Longitudinal pure-slip (peak near 11% slip ratio)
    B_x: Positive = 12.0
    C_x: Positive = 1.6
    D_x_mu: Positive = 1.6
    E_x: float = -0.5
    # Load sensitivity: mu_eff = D_mu * (1 - k_load * (Fz/Fz0 - 1))
    Fz0_n: Positive = 3500.0
    k_load: float = 0.10


def _mu_eff(d_mu: float, fz: np.ndarray, fz0: float, k_load: float) -> np.ndarray:
    """Degressive load-sensitive friction multiplier, clamped to a positive floor."""
    mu = d_mu * (1.0 - k_load * (fz / fz0 - 1.0))
    return np.maximum(mu, _MU_FLOOR_FRACTION * d_mu)


def _magic(x: np.ndarray, b: float, c: float, d: np.ndarray, e: float) -> np.ndarray:
    """Pacejka Magic Formula F = D·sin(C·atan(B·x − E·(B·x − atan(B·x))))."""
    bx = b * x
    return d * np.sin(c * np.arctan(bx - e * (bx - np.arctan(bx))))


def pure_lateral_fy(alpha, fz, c: PacejkaCoeffs) -> np.ndarray:
    """Lateral force [N] opposing slip angle ``alpha`` [rad] at vertical load ``fz`` [N]."""
    alpha = np.asarray(alpha, dtype=float)
    fz = np.asarray(fz, dtype=float)
    d = _mu_eff(c.D_y_mu, fz, c.Fz0_n, c.k_load) * fz
    # Tyre force opposes slip → negative sign on the pure curve.
    return -_magic(alpha, c.B_y, c.C_y, d, c.E_y)


def pure_longitudinal_fx(kappa, fz, c: PacejkaCoeffs) -> np.ndarray:
    """Longitudinal force [N] from slip ratio ``kappa`` [-] at vertical load ``fz`` [N]."""
    kappa = np.asarray(kappa, dtype=float)
    fz = np.asarray(fz, dtype=float)
    d = _mu_eff(c.D_x_mu, fz, c.Fz0_n, c.k_load) * fz
    return _magic(kappa, c.B_x, c.C_x, d, c.E_x)


def combined_forces(alpha, kappa, fz, c: PacejkaCoeffs) -> tuple[np.ndarray, np.ndarray]:
    """Combined-slip (Fx, Fy) [N] via friction-ellipse g-normalisation.

    Each pure-slip force is normalised by its own peak; if the combined demand
    ``g = hypot(Fx0/Dx, Fy0/Dy)`` exceeds 1 both forces are scaled by ``1/g`` so the
    resultant stays inside the friction ellipse.
    """
    fz = np.asarray(fz, dtype=float)
    fx0 = pure_longitudinal_fx(kappa, fz, c)
    fy0 = pure_lateral_fy(alpha, fz, c)

    dx = _mu_eff(c.D_x_mu, fz, c.Fz0_n, c.k_load) * fz
    dy = _mu_eff(c.D_y_mu, fz, c.Fz0_n, c.k_load) * fz
    # Avoid division by zero where a wheel has lifted (Fz≈0 → D≈0).
    nx = fx0 / np.where(dx > 1e-9, dx, 1e-9)
    ny = fy0 / np.where(dy > 1e-9, dy, 1e-9)
    g = np.hypot(nx, ny)
    scale = np.where(g > 1.0, 1.0 / np.maximum(g, 1e-9), 1.0)
    return fx0 * scale, fy0 * scale
