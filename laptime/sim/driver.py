"""Path-tracking driver model for the transient simulator.

Follows a reference racing line (geometry) and the QSS velocity profile (target speed):
  - lateral: pure-pursuit steering toward a speed-dependent lookahead point;
  - longitudinal: PI speed control with the QSS speed as feed-forward.

The driver is intentionally simple — its only job is to *track* the QSS reference, which
is what makes the transient lap time directly comparable to the QSS baseline.
"""

from __future__ import annotations

import math

import numpy as np

from laptime.track.track import Track
from laptime.vehicle.dynamics_params import DriverParams

from .result import LapResult


class PathTrackingDriver:
    def __init__(self, racing_line: Track, qss_result: LapResult,
                 vehicle, params: DriverParams) -> None:
        self._line = racing_line
        self._vehicle = vehicle
        self._wheelbase = vehicle._p.chassis.wheelbase_m
        self._p = params
        self._qss_s = qss_result.s
        self._qss_v = qss_result.v

        self._xs = racing_line.x
        self._ys = racing_line.y
        self._ss = racing_line.s
        self._n = racing_line.n_points
        self._closed = racing_line.is_closed
        self._length = racing_line.length

        # Controller state
        self._prev_idx = 0
        self._prev_delta = 0.0
        self._speed_int = 0.0

    # ------------------------------------------------------------------

    def project(self, X: float, Y: float) -> tuple[float, int]:
        """Nearest-point projection of (X, Y) onto the reference line → (s, index)."""
        window = 60
        idxs = (self._prev_idx + np.arange(-5, window)) % self._n
        d2 = (self._xs[idxs] - X) ** 2 + (self._ys[idxs] - Y) ** 2
        best = idxs[int(np.argmin(d2))]
        self._prev_idx = int(best)
        return float(self._ss[best]), int(best)

    def _target_speed(self, s: float, vx: float) -> float:
        """Lowest QSS speed over a braking-preview window ahead, so the driver brakes early."""
        preview = max(30.0, vx * vx / 16.0)  # ~ braking distance at ≈8 m/s²
        s_window = s + np.linspace(0.0, preview, 16)
        if self._closed:
            s_window = s_window % self._length
        v_window = np.interp(s_window, self._qss_s, self._qss_v)
        return self._p.speed_margin * float(np.min(v_window))

    def command(self, x_state: np.ndarray, dt: float) -> tuple[np.ndarray, float]:
        """Return (u=[delta, throttle, brake], s_now) for the current chassis state."""
        from laptime.vehicle.dynamic_vehicle import I_PSI, I_R, I_VX, I_X, I_Y

        X, Y, psi = x_state[I_X], x_state[I_Y], x_state[I_PSI]
        vx, r = x_state[I_VX], x_state[I_R]
        s_now, idx = self.project(X, Y)
        path_error = math.hypot(X - self._xs[idx], Y - self._ys[idx])

        # --- lateral: pure pursuit ---
        ld = max(self._p.lookahead_min_m, self._p.lookahead_gain_s * vx)
        s_target = s_now + ld
        if self._closed:
            s_target = s_target % self._length
        tp = self._line.at(s_target)
        dx, dy = tp.x - X, tp.y - Y
        ex = dx * math.cos(psi) + dy * math.sin(psi)
        ey = -dx * math.sin(psi) + dy * math.cos(psi)
        ld_actual = max(math.hypot(ex, ey), 1e-3)
        alpha_pp = math.atan2(ey, ex)
        delta = math.atan2(2 * self._wheelbase * math.sin(alpha_pp), ld_actual)

        # Stanley-style cross-track correction at the nearest point tightens the line.
        hl = self._line.heading[idx]
        ey_left = -(X - self._xs[idx]) * math.sin(hl) + (Y - self._ys[idx]) * math.cos(hl)
        delta -= math.atan2(self._p.cross_track_gain * ey_left, max(vx, 2.0))

        delta = max(-self._p.steer_max_rad, min(self._p.steer_max_rad, delta))
        # Steering rate limit
        d_max = self._p.steer_rate_max_rad_s * dt
        delta = max(self._prev_delta - d_max, min(self._prev_delta + d_max, delta))
        self._prev_delta = delta

        # --- longitudinal: PI on speed error with QSS feed-forward target ---
        # Back off the target when running wide (the driver lifts to recover the line).
        slow = max(0.0, path_error - self._p.path_deadband_m)
        v_target = self._target_speed(s_now, vx) * max(0.4, 1.0 - self._p.understeer_gain * slow)
        e = v_target - vx
        self._speed_int += e * dt
        # Anti-windup clamp on the integral term.
        int_clamp = self._p.accel_ref_ms2 / max(self._p.ki_speed, 1e-6)
        self._speed_int = max(-int_clamp, min(int_clamp, self._speed_int))
        a_cmd = self._p.kp_speed * e + self._p.ki_speed * self._speed_int

        a_ref = self._p.accel_ref_ms2
        if a_cmd >= 0:
            throttle, brake = min(a_cmd / a_ref, 1.0), 0.0
        else:
            throttle, brake = 0.0, min(-a_cmd / a_ref, 1.0)

        # Traction budgeting: lift off the pedals when the tyres are busy cornering, so the
        # driver never demands longitudinal force the lateral-loaded tyres cannot deliver.
        ay_used = abs(vx * r)
        ay_lim = max(self._vehicle.lateral_limit(max(vx, 1.0)), 1e-3)
        long_cap = math.sqrt(max(0.0, 1.0 - min(ay_used / ay_lim, 1.0) ** 2))
        throttle *= long_cap
        brake *= long_cap

        return np.array([delta, throttle, brake]), s_now
