"""Validation and analysis utilities for the lap-time simulator.

Tools to compare the solvers (QSS, transient 7DOF, and optionally the OCP), to extract a
GGV (lateral/longitudinal acceleration vs speed) envelope from a vehicle model, and to
capture rich per-step traces (load transfer, yaw rate, roll) from a transient lap.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from laptime.optimizer.racing_line import MinCurvatureOptimizer
from laptime.sim.driver import PathTrackingDriver
from laptime.sim.qss import QSSSolver
from laptime.sim.result import LapResult
from laptime.sim.transient import TransientSolver
from laptime.track.track import Track
from laptime.vehicle.base import VehicleModel
from laptime.vehicle.dynamic_vehicle import (
    I_PHI,
    I_PHID,
    I_R,
    I_THETA,
    I_THETAD,
    I_VX,
    I_VY,
    I_X,
    I_Y,
    I_Z,
    I_ZD,
    DynamicVehicle,
)

# ----------------------------------------------------------------------------------------
# GGV envelope

@dataclass
class GGVEnvelope:
    """Steady-state acceleration envelope sampled across speed."""

    speed_ms: np.ndarray
    ay_max_ms2: np.ndarray       # peak lateral accel [m/s²]
    ax_max_ms2: np.ndarray       # peak traction/acceleration [m/s²]
    ax_min_ms2: np.ndarray       # peak braking (negative) [m/s²]


def ggv_envelope(vehicle: VehicleModel, speeds: np.ndarray | None = None) -> GGVEnvelope:
    """Extract the steady-state GGV envelope from any ``VehicleModel``.

    Uses the model's quasi-steady limits (lateral_limit / longitudinal_limits) — the same
    surface the QSS solver consumes — so it characterises the grip the vehicle exposes.
    """
    if speeds is None:
        speeds = np.linspace(10.0, 80.0, 15)
    ay_max, ax_max, ax_min = [], [], []
    for v in speeds:
        ay_max.append(vehicle.lateral_limit(float(v)))
        lo, hi = vehicle.longitudinal_limits(float(v), 0.0)
        ax_min.append(lo)
        ax_max.append(hi)
    return GGVEnvelope(
        speed_ms=np.asarray(speeds),
        ay_max_ms2=np.asarray(ay_max),
        ax_max_ms2=np.asarray(ax_max),
        ax_min_ms2=np.asarray(ax_min),
    )


# ----------------------------------------------------------------------------------------
# Solver comparison

@dataclass
class SolverComparison:
    """Lap times and velocity traces from each available solver."""

    lap_times_s: dict[str, float] = field(default_factory=dict)
    results: dict[str, LapResult] = field(default_factory=dict)
    reference_line: Track | None = None

    def summary(self) -> str:
        base = self.lap_times_s.get("qss")
        rows = []
        for name, t in self.lap_times_s.items():
            delta = "" if base is None or name == "qss" else f"  (Δ {t - base:+.3f} s vs QSS)"
            rows.append(f"  {name:18s} {t:8.3f} s{delta}")
        return "Lap times:\n" + "\n".join(rows)


def compare_solvers(
    track: Track,
    vehicle: DynamicVehicle,
    ds: float = 2.0,
    dt: float = 2.5e-3,
    use_racing_line: bool = True,
    with_ocp: bool = False,
) -> SolverComparison:
    """Run QSS and the transient 7DOF solver (and optionally the OCP) on one track."""
    line = track
    if use_racing_line:
        opt = MinCurvatureOptimizer(track)
        line = opt.apply_to_track(opt.optimize())

    cmp = SolverComparison(reference_line=line)

    qss = QSSSolver(line, vehicle, ds=ds).solve()
    cmp.lap_times_s["qss"] = qss.lap_time_s
    cmp.results["qss"] = qss

    transient = TransientSolver(line, vehicle, qss, racing_line=line, dt=dt).solve()
    cmp.lap_times_s["transient_7dof"] = transient.lap_time_s
    cmp.results["transient_7dof"] = transient

    if with_ocp:
        try:
            from laptime.optimizer.ocp import OCPSolver
            from laptime.vehicle.params import PointMassParams

            # OCP runs on the point-mass model; mirror the dynamic vehicle's gross params.
            p = PointMassParams(
                mass_kg=vehicle.mass,
                p_max_kw=vehicle._p.drivetrain.p_max_kw,
            )
            ocp = OCPSolver(line, p).solve()
            cmp.lap_times_s["ocp"] = ocp.lap_time_s
            cmp.results["ocp"] = ocp
        except Exception:
            pass  # CasADi not installed or solve failed — skip OCP silently.

    return cmp


# ----------------------------------------------------------------------------------------
# Transient trace (load transfer, yaw, roll)

@dataclass
class TransientTrace:
    """Per-step time history from a transient lap."""

    t: np.ndarray
    s: np.ndarray
    v: np.ndarray
    ax_ms2: np.ndarray
    ay_ms2: np.ndarray
    yaw_rate: np.ndarray         # [rad/s]
    roll_deg: np.ndarray         # [deg]
    fz: np.ndarray               # (N, 4) per-wheel vertical load [N], order [FL, FR, RL, RR]


def transient_trace(
    track: Track,
    vehicle: DynamicVehicle,
    qss: LapResult,
    line: Track | None = None,
    dt: float = 2.5e-3,
    max_time_factor: float = 4.0,
) -> TransientTrace:
    """Integrate one transient lap, capturing rich per-step diagnostics for plotting."""
    line = line if line is not None else track
    driver = PathTrackingDriver(line, qss, vehicle, vehicle._p.driver)

    v0 = float(np.interp(0.0, qss.s, qss.v))
    x = vehicle.initial_state(
        v0, float(line.kappa[0]), float(line.x[0]), float(line.y[0]), float(line.heading[0])
    )
    length = line.length
    closed = line.is_closed
    s_prev, _ = driver.project(x[I_X], x[I_Y])
    s_cum, t = 0.0, 0.0
    f = vehicle.derivatives
    max_steps = int(max_time_factor * qss.lap_time_s / dt)

    logs: list[tuple] = []
    for _ in range(max_steps):
        u, s_now = driver.command(x, dt)
        ds = s_now - s_prev
        if closed and ds < -length / 2:
            ds += length
        elif closed and ds > length / 2:
            ds -= length
        s_cum += ds
        s_prev = s_now

        vx, vy, r, phi = x[I_VX], x[I_VY], x[I_R], x[I_PHI]
        fz = vehicle.susp.wheel_loads(
            phi, x[I_PHID], x[I_THETA], x[I_THETAD], x[I_Z], x[I_ZD]
        )
        logs.append((t, s_cum, float(np.hypot(vx, vy)), float(vx * r), r, phi, *fz))

        if s_cum >= length:
            break
        # RK4 step
        k1 = f(t, x, u)
        k2 = f(t + dt / 2, x + dt / 2 * k1, u)
        k3 = f(t + dt / 2, x + dt / 2 * k2, u)
        k4 = f(t + dt, x + dt * k3, u)
        x = x + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        t += dt

    arr = np.asarray(logs)
    t_a, s_a, v_a, ay_a, r_a, phi_a = (arr[:, i] for i in range(6))
    fz_a = arr[:, 6:10]
    ax_a = np.gradient(v_a, t_a)
    return TransientTrace(
        t=t_a, s=s_a, v=v_a, ax_ms2=ax_a, ay_ms2=ay_a,
        yaw_rate=r_a, roll_deg=np.degrees(phi_a), fz=fz_a,
    )
