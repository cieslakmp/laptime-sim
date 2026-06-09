"""Simplified Pacejka Magic Formula tyre model.

Pure-slip lateral/longitudinal forces with a degressive load-sensitive peak, camber
thrust, a self-aligning moment, and Magic Formula cosine combined-slip weighting (with a
friction-circle safety clamp). All force functions are stateless and vectorise over the
four wheels (numpy arrays).

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
    # Camber thrust: Fy_camber = camber_stiffness * gamma * Fz  [per rad]
    camber_stiffness: float = 0.6
    # Self-aligning moment via pneumatic trail: Mz = -trail * Fy  [m]
    pneumatic_trail_m: float = 0.04
    # Combined-slip weighting strengths (Magic Formula cosine weighting)
    B_xalpha: float = 4.0   # how strongly slip angle de-rates Fx
    B_ykappa: float = 4.0   # how strongly slip ratio de-rates Fy


def _mu_eff(d_mu: float, fz: np.ndarray, fz0: float, k_load: float) -> np.ndarray:
    """Degressive load-sensitive friction multiplier, clamped to a positive floor."""
    mu = d_mu * (1.0 - k_load * (fz / fz0 - 1.0))
    return np.maximum(mu, _MU_FLOOR_FRACTION * d_mu)


def _magic(x: np.ndarray, b: float, c: float, d: np.ndarray, e: float) -> np.ndarray:
    """Pacejka Magic Formula F = D·sin(C·atan(B·x − E·(B·x − atan(B·x))))."""
    bx = b * x
    return d * np.sin(c * np.arctan(bx - e * (bx - np.arctan(bx))))


def pure_lateral_fy(alpha, fz, c: PacejkaCoeffs, gamma=0.0) -> np.ndarray:
    """Lateral force [N] from slip angle ``alpha`` [rad] and camber ``gamma`` [rad].

    Combines the slip-generated restoring force with a camber thrust
    ``camber_stiffness · gamma · Fz`` that acts in the direction of lean.
    """
    alpha = np.asarray(alpha, dtype=float)
    fz = np.asarray(fz, dtype=float)
    gamma = np.asarray(gamma, dtype=float)
    d = _mu_eff(c.D_y_mu, fz, c.Fz0_n, c.k_load) * fz
    # Tyre force opposes slip → negative sign on the pure curve. Camber adds a thrust.
    return -_magic(alpha, c.B_y, c.C_y, d, c.E_y) + c.camber_stiffness * gamma * fz


def aligning_moment(fy, c: PacejkaCoeffs) -> np.ndarray:
    """Self-aligning moment Mz [N·m] from the lateral force via the pneumatic trail."""
    return -c.pneumatic_trail_m * np.asarray(fy, dtype=float)


def pure_longitudinal_fx(kappa, fz, c: PacejkaCoeffs) -> np.ndarray:
    """Longitudinal force [N] from slip ratio ``kappa`` [-] at vertical load ``fz`` [N]."""
    kappa = np.asarray(kappa, dtype=float)
    fz = np.asarray(fz, dtype=float)
    d = _mu_eff(c.D_x_mu, fz, c.Fz0_n, c.k_load) * fz
    return _magic(kappa, c.B_x, c.C_x, d, c.E_x)


def combined_forces(alpha, kappa, fz, c: PacejkaCoeffs, gamma=0.0) -> tuple[np.ndarray, np.ndarray]:
    """Combined-slip (Fx, Fy) [N] via Magic Formula cosine weighting.

    Each pure-slip force is de-rated by the orthogonal slip through the standard MF
    weighting ``G = cos(atan(B · other_slip))`` (Fx falls with slip angle, Fy with slip
    ratio). A friction-circle clamp is then applied as a physical safety bound so the
    resultant can never exceed the available grip.
    """
    alpha = np.asarray(alpha, dtype=float)
    kappa = np.asarray(kappa, dtype=float)
    fz = np.asarray(fz, dtype=float)
    fx0 = pure_longitudinal_fx(kappa, fz, c)
    fy0 = pure_lateral_fy(alpha, fz, c, gamma)

    # Magic Formula combined-slip weighting functions.
    g_x = np.cos(np.arctan(c.B_xalpha * alpha))
    g_y = np.cos(np.arctan(c.B_ykappa * kappa))
    fx = fx0 * g_x
    fy = fy0 * g_y

    # Friction-circle safety clamp (guarantees the resultant stays within grip).
    dx = _mu_eff(c.D_x_mu, fz, c.Fz0_n, c.k_load) * fz
    dy = _mu_eff(c.D_y_mu, fz, c.Fz0_n, c.k_load) * fz
    nx = fx / np.where(dx > 1e-9, dx, 1e-9)
    ny = fy / np.where(dy > 1e-9, dy, 1e-9)
    g = np.hypot(nx, ny)
    scale = np.where(g > 1.0, 1.0 / np.maximum(g, 1e-9), 1.0)
    return fx * scale, fy * scale
