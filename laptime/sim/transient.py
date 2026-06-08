"""Transient time-domain lap simulation engine.

Forward-integrates the :class:`DynamicVehicle` 7DOF model with an RK4 fixed step while a
:class:`PathTrackingDriver` follows the QSS reference (racing line + speed profile). The
time-domain trajectory is mapped back to the arc-length grid to produce a :class:`LapResult`
that drops straight into the existing plotting / API / sector-time consumers.
"""

from __future__ import annotations

import math

import numpy as np

from laptime.track.track import Track
from laptime.vehicle.dynamic_vehicle import (
    I_VX,
    I_VY,
    I_X,
    I_Y,
    DynamicVehicle,
)

from .driver import PathTrackingDriver
from .result import LapResult


class TransientSolver:
    def __init__(
        self,
        track: Track,
        vehicle: DynamicVehicle,
        qss_reference: LapResult,
        racing_line: Track,
        dt: float = 1e-3,
    ) -> None:
        self._track = track
        self._vehicle = vehicle
        self._qss = qss_reference
        self._line = racing_line
        self._dt = dt

    def _rk4_step(self, x: np.ndarray, u: np.ndarray, t: float) -> np.ndarray:
        f = self._vehicle.derivatives
        dt = self._dt
        k1 = f(t, x, u)
        k2 = f(t + dt / 2, x + dt / 2 * k1, u)
        k3 = f(t + dt / 2, x + dt / 2 * k2, u)
        k4 = f(t + dt, x + dt * k3, u)
        return x + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)

    def solve(self) -> LapResult:
        vehicle, line, dt = self._vehicle, self._line, self._dt
        length = line.length
        closed = line.is_closed
        qss_lap = self._qss.lap_time_s

        driver = PathTrackingDriver(line, self._qss, vehicle, vehicle._p.driver)

        # Initial state at the start of the racing line, settled at the QSS entry speed.
        v0 = float(np.interp(0.0, self._qss.s, self._qss.v))
        x = vehicle.initial_state(
            v0, float(line.kappa[0]), float(line.x[0]), float(line.y[0]), float(line.heading[0])
        )

        s_prev, _ = driver.project(x[I_X], x[I_Y])
        s_cum, t = 0.0, 0.0
        warmup = 0.0 if not closed else min(150.0, 0.25 * length)
        timing, t0, s_timing0 = not closed, 0.0, 0.0

        abort_threshold = float(max(line.width_left.max(), line.width_right.max())) + 5.0
        max_steps = int((qss_lap * 4 + 30) / dt)

        t_log: list[float] = []
        s_log: list[float] = []
        v_log: list[float] = []
        max_dev, aborted = 0.0, False

        for _ in range(max_steps):
            u, s_now = driver.command(x, dt)

            # Cumulative arc-length progress (handle closed-track wraparound).
            ds = s_now - s_prev
            if closed and ds < -length / 2:
                ds += length
            elif closed and ds > length / 2:
                ds -= length
            s_cum += ds
            s_prev = s_now

            idx = driver._prev_idx
            dev = math.hypot(x[I_X] - line.x[idx], x[I_Y] - line.y[idx])
            max_dev = max(max_dev, dev)
            if dev > abort_threshold:
                aborted = True
                break

            if not timing and s_cum >= warmup:
                timing, t0, s_timing0 = True, t, s_cum

            if timing:
                prog = s_cum - s_timing0
                t_log.append(t - t0)
                s_log.append(prog)
                v_log.append(math.hypot(x[I_VX], x[I_VY]))
                if prog >= length:
                    break

            x = self._rk4_step(x, u, t)
            t += dt

        return self._build_result(
            np.array(t_log), np.array(s_log), np.array(v_log), max_dev, aborted, qss_lap
        )

    def _build_result(self, t_log, s_log, v_log, max_dev, aborted, qss_lap) -> LapResult:
        completed = bool((not aborted) and s_log.size >= 2 and s_log[-1] >= self._line.length)
        s_grid = self._qss.s

        if s_log.size >= 2:
            s_mono = np.maximum.accumulate(s_log)  # guard against hairpin back-tracking
            lap_time = float(np.interp(self._line.length, s_mono, t_log))
            v_grid = np.interp(s_grid, s_mono, v_log)
        else:
            lap_time = float("inf")
            v_grid = np.zeros_like(s_grid)

        if not completed:
            lap_time = max(lap_time, 3.0 * qss_lap)

        pts = self._track.at(s_grid)
        kappa_grid = np.array([p.kappa for p in pts])
        ax = np.gradient(v_grid, s_grid)
        ay = v_grid**2 * kappa_grid

        return LapResult(
            lap_time_s=lap_time,
            s=s_grid,
            v=v_grid,
            ax=ax,
            ay=ay,
            metadata={
                "solver": "transient",
                "dt": self._dt,
                "qss_lap_time_s": qss_lap,
                "max_lateral_dev_m": max_dev,
                "completed": completed,
                "aborted": aborted,
            },
        )
