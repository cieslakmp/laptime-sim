"""Transient 7DOF (+roll/pitch/heave) vehicle model.

Assembles the time-domain state-derivative function consumed by ``TransientSolver`` and
also implements the quasi-steady :class:`VehicleModel` interface so the *same* parameter
set drives the QSS reference run.

State vector (length :data:`NUM_STATES`), wheel order [FL, FR, RL, RR]::

    0  vx      body longitudinal velocity        [m/s]
    1  vy      body lateral velocity             [m/s]
    2  r       yaw rate                          [rad/s]
    3  phi     roll angle                        [rad]
    4  phi_d   roll rate                         [rad/s]
    5  theta   pitch angle                       [rad]
    6  theta_d pitch rate                        [rad/s]
    7  z       heave                             [m]
    8  z_d     heave rate                        [m/s]
    9-12 omega 4 wheel spin speeds               [rad/s]
    13 X       global X position                 [m]
    14 Y       global Y position                 [m]
    15 psi     global heading                    [rad]
    16-19 alpha_lag  relaxed slip angles         [rad]

Control input ``u = [delta, throttle, brake]`` (front steer [rad], pedals in [0, 1]).
"""

from __future__ import annotations

import math

import numpy as np

from .base import VehicleModel
from .dynamics_params import DynamicVehicleParams
from .suspension import G, SuspensionModel
from .tyre_pacejka import PacejkaCoeffs, aligning_moment, combined_forces

# State layout
I_VX, I_VY, I_R = 0, 1, 2
I_PHI, I_PHID, I_THETA, I_THETAD, I_Z, I_ZD = 3, 4, 5, 6, 7, 8
I_OMEGA = slice(9, 13)
I_X, I_Y, I_PSI = 13, 14, 15
I_ALPHA_LAG = slice(16, 20)
NUM_STATES = 20

# Regularisation floors
V_EPS = 1.0          # m/s — guards slip-ratio/angle singularities at low speed
OMEGA_BRAKE_EPS = 2.0  # rad/s — smooths the brake-torque sign reversal


class DynamicVehicle(VehicleModel):
    def __init__(self, params: DynamicVehicleParams) -> None:
        self._p = params
        self.susp = SuspensionModel(params)
        self.x_wheel = self.susp.x_wheel
        self.y_wheel = self.susp.y_wheel
        self._tyres: list[PacejkaCoeffs] = [
            params.tyre_front, params.tyre_front, params.tyre_rear, params.tyre_rear
        ]
        self._R = params.drivetrain.wheel_radius_m

    # ------------------------------------------------------------------
    # Aerodynamics

    def _drag_force(self, vx: float) -> float:
        a = self._p.aero
        return 0.5 * a.rho_air * a.cd * vx * abs(vx)

    def _downforce(self, v: float) -> float:
        a = self._p.aero
        return 0.5 * a.rho_air * a.cl * v**2

    # ------------------------------------------------------------------
    # Initial state helper

    def initial_state(self, v0: float, kappa0: float = 0.0,
                      x0: float = 0.0, y0: float = 0.0, psi0: float = 0.0) -> np.ndarray:
        """Build a settled initial state at speed ``v0`` on curvature ``kappa0``."""
        x = np.zeros(NUM_STATES)
        x[I_VX] = max(v0, V_EPS)
        x[I_R] = v0 * kappa0
        x[I_Z] = self.susp.equilibrium_heave(v0)
        x[I_OMEGA] = max(v0, V_EPS) / self._R
        x[I_X], x[I_Y], x[I_PSI] = x0, y0, psi0
        return x

    # ------------------------------------------------------------------
    # Time-domain dynamics

    def wheel_slips(self, x: np.ndarray, delta: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (alpha_raw, kappa, vx_wheel) per wheel from the chassis state."""
        vx, vy, r = x[I_VX], x[I_VY], x[I_R]
        omega = x[I_OMEGA]
        delta_w = np.array([delta, delta, 0.0, 0.0])

        # Contact-point velocities in the body frame, then rotated into each wheel frame.
        vx_i = vx - r * self.y_wheel
        vy_i = vy + r * self.x_wheel
        cos_d, sin_d = np.cos(delta_w), np.sin(delta_w)
        vx_w = vx_i * cos_d + vy_i * sin_d
        vy_w = -vx_i * sin_d + vy_i * cos_d

        vx_safe = np.maximum(np.abs(vx_w), V_EPS)
        alpha = np.arctan2(vy_w, vx_safe)
        kappa = (omega * self._R - vx_w) / vx_safe
        return alpha, kappa, vx_w

    def derivatives(self, t: float, x: np.ndarray, u: np.ndarray) -> np.ndarray:
        p = self._p
        delta, throttle, brake = float(u[0]), float(u[1]), float(u[2])
        vx, vy, r = x[I_VX], x[I_VY], x[I_R]
        phi, phi_d = x[I_PHI], x[I_PHID]
        theta, theta_d = x[I_THETA], x[I_THETAD]
        z, z_d = x[I_Z], x[I_ZD]
        psi = x[I_PSI]
        v = math.hypot(vx, vy)

        # --- vertical loads and slips ---
        fz = self.susp.wheel_loads(phi, phi_d, theta, theta_d, z, z_d)
        alpha_raw, kappa, _ = self.wheel_slips(x, delta)

        # Tyre lateral relaxation lag (first-order, relaxation length sigma).
        sigma = p.relax_length_m
        if sigma > 0:
            alpha_eff = x[I_ALPHA_LAG]
            rate = (max(abs(vx), V_EPS) / sigma) * (alpha_raw - alpha_eff)
        else:
            alpha_eff = alpha_raw
            rate = np.zeros(4)

        # Roll-induced camber (same lean for all wheels relative to the road).
        gamma = p.suspension.camber_gain_per_roll * phi * np.ones(4)

        # --- tyre forces (wheel frame), front and rear coefficient sets ---
        fx_f, fy_f = combined_forces(alpha_eff[:2], kappa[:2], fz[:2], p.tyre_front, gamma[:2])
        fx_r, fy_r = combined_forces(alpha_eff[2:], kappa[2:], fz[2:], p.tyre_rear, gamma[2:])
        fx_w = np.concatenate([fx_f, fx_r])
        fy_w = np.concatenate([fy_f, fy_r])

        # Self-aligning moments about each tyre's vertical axis (pneumatic trail).
        mz_align = float(np.sum(aligning_moment(fy_f, p.tyre_front))
                         + np.sum(aligning_moment(fy_r, p.tyre_rear)))

        # Rotate tyre forces back into the body frame (front wheels by +delta).
        delta_w = np.array([delta, delta, 0.0, 0.0])
        cos_d, sin_d = np.cos(delta_w), np.sin(delta_w)
        fx_b = fx_w * cos_d - fy_w * sin_d
        fy_b = fx_w * sin_d + fy_w * cos_d

        # --- chassis planar dynamics ---
        m = p.chassis.mass_kg
        sum_fx = float(np.sum(fx_b)) - self._drag_force(vx)
        sum_fy = float(np.sum(fy_b))
        mz = float(np.sum(self.x_wheel * fy_b - self.y_wheel * fx_b)) + mz_align
        ax_spec = sum_fx / m
        ay_spec = sum_fy / m

        vx_dot = ax_spec + vy * r
        vy_dot = ay_spec - vx * r
        r_dot = mz / p.chassis.Izz_kgm2

        # --- suspension DOF ---
        phi_dd, theta_dd, z_dd = self.susp.roll_pitch_heave_accels(
            ax_spec, ay_spec, v, phi, phi_d, theta, theta_d, z, z_d
        )
        if not p.suspension.use_heave:
            z_d, z_dd = 0.0, 0.0

        # --- wheel spin dynamics ---
        omega = x[I_OMEGA]
        t_drive = self._drive_torque(throttle, vx)
        t_brake = self._brake_torque(brake)
        i_w = p.drivetrain.wheel_inertia_kgm2
        omega_dot = (t_drive - t_brake * np.tanh(omega / OMEGA_BRAKE_EPS) - fx_w * self._R) / i_w

        # --- global pose ---
        x_dot = vx * math.cos(psi) - vy * math.sin(psi)
        y_dot = vx * math.sin(psi) + vy * math.cos(psi)

        dx = np.zeros(NUM_STATES)
        dx[I_VX], dx[I_VY], dx[I_R] = vx_dot, vy_dot, r_dot
        dx[I_PHI], dx[I_PHID] = phi_d, phi_dd
        dx[I_THETA], dx[I_THETAD] = theta_d, theta_dd
        dx[I_Z], dx[I_ZD] = z_d, z_dd
        dx[I_OMEGA] = omega_dot
        dx[I_X], dx[I_Y], dx[I_PSI] = x_dot, y_dot, r
        dx[I_ALPHA_LAG] = rate
        return dx

    def _drive_torque(self, throttle: float, vx: float) -> np.ndarray:
        """Per-wheel drive torque [N·m] for the given throttle, split by drivetrain layout."""
        d = self._p.drivetrain
        omega_ref = max(abs(vx), V_EPS) / self._R
        t_avail = min(d.torque_max_nm, d.p_max_kw * 1000.0 / omega_ref)
        t_total = max(throttle, 0.0) * t_avail

        t = np.zeros(4)
        if d.layout == "rwd":
            t[2] = t[3] = t_total / 2
        elif d.layout == "fwd":
            t[0] = t[1] = t_total / 2
        else:  # awd
            t[0] = t[1] = d.awd_front_bias * t_total / 2
            t[2] = t[3] = (1 - d.awd_front_bias) * t_total / 2
        return t

    def _brake_torque(self, brake: float) -> np.ndarray:
        """Per-wheel brake torque magnitude [N·m], split front/rear by balance."""
        d = self._p.drivetrain
        t_total = max(brake, 0.0) * d.brake_torque_max_nm
        bf = d.brake_balance_front
        return np.array([bf * t_total / 2, bf * t_total / 2,
                        (1 - bf) * t_total / 2, (1 - bf) * t_total / 2])

    # ------------------------------------------------------------------
    # VehicleModel ABC — steady-state limits for the QSS reference run

    @property
    def mass(self) -> float:
        return self._p.chassis.mass_kg

    def _axle_loads(self, v: float, banking: float) -> tuple[float, float]:
        """Steady per-wheel vertical load (front, rear) including downforce."""
        m = self._p.chassis.mass_kg
        wd = self._p.chassis.weight_dist_front
        n_total = m * G * math.cos(banking) + self._downforce(v)
        return n_total * wd / 2, n_total * (1 - wd) / 2

    def _peak(self, coeffs: PacejkaCoeffs, fz: float, lateral: bool) -> float:
        """Derated peak tyre force [N] at vertical load ``fz`` for the QSS estimate."""
        d_mu = coeffs.D_y_mu if lateral else coeffs.D_x_mu
        mu = max(d_mu * (1 - coeffs.k_load * (fz / coeffs.Fz0_n - 1)), 0.1 * d_mu)
        return self._p.grip_factor * mu * fz

    def _lateral_capacity(self, ay: float, v: float, banking: float) -> float:
        """Total lateral tyre force [N] available at lateral accel ``ay`` (with load transfer)."""
        c = self._p.chassis
        m = c.mass_kg
        fz_f, fz_r = self._axle_loads(v, banking)
        # Quasi-static lateral load transfer per axle (roll neglected for the limit estimate).
        d_f = m * c.weight_dist_front * ay * c.cg_height_m / c.track_front_m / 2
        d_r = m * (1 - c.weight_dist_front) * ay * c.cg_height_m / c.track_rear_m / 2
        fy = (
            self._peak(self._p.tyre_front, max(fz_f + d_f, 0.0), True)
            + self._peak(self._p.tyre_front, max(fz_f - d_f, 0.0), True)
            + self._peak(self._p.tyre_rear, max(fz_r + d_r, 0.0), True)
            + self._peak(self._p.tyre_rear, max(fz_r - d_r, 0.0), True)
        )
        return fy

    def lateral_limit(self, v: float, kappa: float = 0.0, banking: float = 0.0) -> float:
        # Self-consistent: grip drops as load transfer overloads the outer tyres.
        m = self._p.chassis.mass_kg
        ay = self._lateral_capacity(0.0, v, banking) / m
        for _ in range(6):
            ay = self._lateral_capacity(ay, v, banking) / m
        return ay + G * math.sin(banking)

    def longitudinal_limits(self, v: float, ay: float, kappa: float = 0.0,
                           banking: float = 0.0) -> tuple[float, float]:
        v = max(v, 0.1)
        m = self._p.chassis.mass_kg
        fz_f, fz_r = self._axle_loads(v, banking)
        fx_max = (2 * self._peak(self._p.tyre_front, fz_f, False)
                  + 2 * self._peak(self._p.tyre_rear, fz_r, False))
        ax_tyre = fx_max / m

        ay_lim = self.lateral_limit(v, kappa, banking)
        lateral_fraction = min(abs(ay) / max(ay_lim, 1e-6), 1.0)
        ax_remaining = ax_tyre * math.sqrt(max(0.0, 1.0 - lateral_fraction**2))

        d = self._p.drivetrain
        ax_engine = d.p_max_kw * 1000.0 / (m * v) - self._drag_force(v) / m
        ax_max = min(ax_remaining, max(0.0, ax_engine))

        ax_brake_system = d.brake_torque_max_nm / self._R / m
        drag_assist = self._drag_force(v) / m
        ax_min = -(min(ax_remaining, ax_brake_system) + drag_assist)
        return ax_min, max(0.0, ax_max)
