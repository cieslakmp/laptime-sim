"""Minimum-curvature racing line optimiser.

Parameterises the racing line as alpha(s) ∈ [-1, 1] across the track width.
alpha = 0 → centreline, alpha = +1 → full left, alpha = -1 → full right.
Minimises integral of kappa² ds subject to boundary constraints.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from laptime.track.track import Track


class MinCurvatureOptimizer:
    def __init__(self, track: Track, n_points: int = 200) -> None:
        self._base = track.resample(track.length / n_points)
        self._n = self._base.n_points

    def optimize(
        self,
        max_iter: int = 500,
        tol: float = 1e-6,
    ) -> np.ndarray:
        """Return alpha array ∈ [-1, 1] that minimises path curvature."""
        n = self._n
        track = self._base
        s = track.s
        ds = track.length / n

        def path_from_alpha(alpha: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            # Normal vector to track centreline
            nx = -np.sin(track.heading)
            ny = np.cos(track.heading)
            offset = alpha * (track.width_left + track.width_right) / 2
            return track.x + offset * nx, track.y + offset * ny

        def curvature_from_xy(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            dx = np.gradient(x, s)
            dy = np.gradient(y, s)
            ddx = np.gradient(dx, s)
            ddy = np.gradient(dy, s)
            denom = (dx**2 + dy**2) ** 1.5
            return (dx * ddy - dy * ddx) / np.where(denom < 1e-10, 1e-10, denom)

        def objective(alpha: np.ndarray) -> float:
            x, y = path_from_alpha(alpha)
            kappa = curvature_from_xy(x, y)
            return float(np.sum(kappa**2) * ds)

        bounds = [(-1.0, 1.0)] * n
        alpha0 = np.zeros(n)

        result = minimize(
            objective,
            alpha0,
            method="SLSQP",
            bounds=bounds,
            options={"maxiter": max_iter, "ftol": tol},
        )
        return result.x

    def apply_to_track(self, alpha: np.ndarray, ds: float = 2.0,
                       path_smooth: float = 1.0) -> Track:
        """Return a new Track representing the racing line.

        The line is resampled at ``ds`` metre spacing (finer than the optimisation grid)
        so downstream consumers such as the transient driver can track it smoothly — a
        coarse path makes the path-following controller unstable.

        ``path_smooth`` is a Gaussian smoothing (in optimisation-grid stations) applied to
        the path *coordinates* before refitting. Smoothing the geometry — rather than just
        the curvature array — keeps the reported curvature consistent with the actual path,
        which both removes spline-interpolation wiggle and keeps the QSS speed achievable by
        a vehicle that physically drives the line.
        """
        from scipy.ndimage import gaussian_filter1d

        from laptime.track.track import Track

        track = self._base
        s = track.s

        # Resample alpha to match track stations
        alpha_rs = np.interp(s, np.linspace(0, track.length, len(alpha)), alpha)

        nx = -np.sin(track.heading)
        ny = np.cos(track.heading)
        half_width = (track.width_left + track.width_right) / 2
        offset = alpha_rs * half_width

        x_new = track.x + offset * nx
        y_new = track.y + offset * ny

        # Smooth the path coordinates so the refitted line is genuinely smooth.
        if path_smooth > 0:
            mode = "wrap" if track.is_closed else "nearest"
            x_new = gaussian_filter1d(x_new, path_smooth, mode=mode)
            y_new = gaussian_filter1d(y_new, path_smooth, mode=mode)

        # Recompute geometry on the new line at fine arc-length spacing. heading/curvature
        # must be evaluated at the arc-length-mapped parameter u (not a raw uniform u) so
        # they stay consistent with (x_fit, y_fit) on non-uniform parameterisations.
        from laptime.track.geometry import (
            arc_length_parameterise,
            compute_curvature,
            compute_heading,
            fit_spline,
        )

        tck, _ = fit_spline(x_new, y_new, closed=track.is_closed)
        n_out = max(self._n, int(track.length / ds))
        s_new, x_fit, y_fit, u = arc_length_parameterise(tck, n=n_out, return_u=True)
        # Light curvature denoising only — the path smoothing above already shapes the line,
        # so this must stay small to keep kappa consistent with the geometry.
        kappa_new = compute_curvature(tck, u, smooth_sigma=max(1.0, 4.0 / ds))
        heading_new = compute_heading(tck, u)

        # Carry width/banking across to the finer grid.
        width_left = np.interp(s_new, track.s, track.width_left)
        width_right = np.interp(s_new, track.s, track.width_right)
        banking = np.interp(s_new, track.s, track.banking)

        return Track(
            s=s_new,
            x=x_fit,
            y=y_fit,
            heading=heading_new,
            kappa=kappa_new,
            width_left=width_left,
            width_right=width_right,
            banking=banking,
            name=track.name + "_racing_line",
            is_closed=track.is_closed,
        )
