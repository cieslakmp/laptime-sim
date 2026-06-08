"""Quasi-Steady-State lap time simulation engine.

Algorithm:
  1. Compute corner speed limit v_corner[i] = sqrt(ay_lim / |kappa|)
  2. Forward pass: propagate max speed forward limited by acceleration
  3. Backward pass: propagate max speed backward limited by braking
  4. Final velocity = min(v_corner, v_fwd, v_bwd)
  5. Lap time = sum(ds / v)
"""

from __future__ import annotations

import numpy as np

from laptime.track.track import Track
from laptime.vehicle.base import VehicleModel

from .result import LapResult

# Minimum speed floor to avoid division-by-zero [m/s]
V_MIN = 0.5


class QSSSolver:
    def __init__(self, track: Track, vehicle: VehicleModel, ds: float = 2.0) -> None:
        self._track = track.resample(ds)
        self._vehicle = vehicle
        self._ds = ds

    def solve(self) -> LapResult:
        track = self._track
        vehicle = self._vehicle
        n = track.n_points
        s = track.s
        ds = np.diff(s, append=s[-1] + (s[1] - s[0]))  # uniform spacing

        kappa = track.kappa
        banking = track.banking

        # --- Step 1: corner speed limit ---
        v_corner = np.full(n, np.inf)
        for i in range(n):
            k = abs(kappa[i])
            if k > 1e-6:
                ay_lim = vehicle.lateral_limit(50.0, kappa[i], banking[i])
                # iterative: ay_lim is speed-dependent, refine v estimate
                v_est = np.sqrt(ay_lim / k)
                for _ in range(5):
                    ay_lim = vehicle.lateral_limit(v_est, kappa[i], banking[i])
                    v_new = np.sqrt(ay_lim / k)
                    if abs(v_new - v_est) < 0.01:
                        break
                    v_est = v_new
                v_corner[i] = max(V_MIN, v_est)

        # Also apply top-speed cap from vehicle params
        v_max_cap = np.array([
            vehicle.longitudinal_limits(1e6, 0.0, kappa[i], banking[i])[1]
            for i in range(n)
        ])
        # v_max_cap from power at very high speed → use lateral limit as primary cap
        # Cap top speed via the vehicle's v_max parameter indirectly:
        # a_max ≤ 0 means we can't accelerate further → that IS the speed cap
        # Better: find v where ax_max = 0
        v_topspeed = _find_top_speed(vehicle, kappa, banking, n)
        v_corner = np.minimum(v_corner, v_topspeed)

        # --- Step 2: forward pass ---
        v_fwd = v_corner.copy()
        for i in range(n - 1):
            v_cur = v_fwd[i]
            ay = v_cur**2 * kappa[i]
            _, ax_max = vehicle.longitudinal_limits(v_cur, ay, kappa[i], banking[i])
            v_next_max = np.sqrt(max(v_cur**2 + 2.0 * ax_max * ds[i], V_MIN**2))
            v_fwd[i + 1] = min(v_corner[i + 1], v_next_max)

        # Closed track: iterate forward pass until convergence
        if track.is_closed:
            for _ in range(3):
                for i in range(n):
                    j = (i + 1) % n
                    v_cur = v_fwd[i]
                    ay = v_cur**2 * kappa[i]
                    _, ax_max = vehicle.longitudinal_limits(v_cur, ay, kappa[i], banking[i])
                    v_next_max = np.sqrt(max(v_cur**2 + 2.0 * ax_max * ds[i], V_MIN**2))
                    v_fwd[j] = min(v_fwd[j], v_corner[j], v_next_max)

        # --- Step 3: backward pass ---
        v_bwd = v_fwd.copy()
        indices = list(range(n - 1, -1, -1)) if not track.is_closed else list(range(n - 1, -1, -1))
        for _ in range(3 if track.is_closed else 1):
            for i in indices:
                j = (i + 1) % n
                v_next = v_bwd[j]
                ay = v_next**2 * kappa[j]
                ax_min, _ = vehicle.longitudinal_limits(v_next, ay, kappa[j], banking[j])
                # Braking from j to i: v_i² ≤ v_j² - 2·|ax_min|·ds
                v_prev_max = np.sqrt(max(v_next**2 - 2.0 * ax_min * ds[i], V_MIN**2))
                v_bwd[i] = min(v_bwd[i], v_corner[i], v_prev_max)

        v = np.maximum(v_bwd, V_MIN)

        # --- Step 4: lap time ---
        dt = ds / v
        lap_time = float(np.sum(dt))

        # --- Accelerations ---
        ay = v**2 * kappa
        ax = np.gradient(v, s)

        return LapResult(
            lap_time_s=lap_time,
            s=s,
            v=v,
            ax=ax,
            ay=ay,
        )


def _find_top_speed(
    vehicle: VehicleModel,
    kappa: np.ndarray,
    banking: np.ndarray,
    n: int,
) -> np.ndarray:
    """Find top speed at each station (where ax_max ≈ 0)."""
    v_top = np.full(n, 200.0)  # start with generous cap
    for i in range(n):
        # Binary search for v where ax_max = 0
        lo, hi = V_MIN, 200.0
        for _ in range(20):
            v_mid = 0.5 * (lo + hi)
            _, ax_max = vehicle.longitudinal_limits(v_mid, 0.0, kappa[i], banking[i])
            if ax_max > 0:
                lo = v_mid
            else:
                hi = v_mid
        v_top[i] = lo
    return v_top
