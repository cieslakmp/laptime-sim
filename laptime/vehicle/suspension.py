"""Suspension model: dynamic load transfer through roll, pitch and heave.

The sprung mass is a rigid body that rolls (φ), pitches (θ) and heaves (z) on four
corner springs/dampers plus front/rear anti-roll bars. Roll/pitch/heave are integrated
DOF driven by the inertial overturning moments and aero forces; the per-wheel vertical
loads are then reconstructed kinematically from the same φ, θ, z for the tyre model.

Conventions (body frame: x forward, y left, z up; CG at origin):
  - φ > 0 : roll right-side-down (the response to a positive/left lateral accel).
  - θ > 0 : pitch nose-down (dive, the response to braking).
  - z > 0 : sprung mass rises.
Wheel order is [FL, FR, RL, RR] everywhere.
"""

from __future__ import annotations

import numpy as np

from .dynamics_params import DynamicVehicleParams

G = 9.81  # m/s²


class SuspensionModel:
    def __init__(self, params: DynamicVehicleParams) -> None:
        self._p = params
        c = params.chassis
        s = params.suspension

        # Longitudinal CG offsets: weight_dist_front = front axle load fraction = b/L.
        L = c.wheelbase_m
        self._b = c.weight_dist_front * L          # CG → rear axle
        self._a = L - self._b                      # CG → front axle
        tf, tr = c.track_front_m, c.track_rear_m

        # Per-wheel geometry [FL, FR, RL, RR].
        self.x_wheel = np.array([self._a, self._a, -self._b, -self._b])
        self.y_wheel = np.array([tf / 2, -tf / 2, tr / 2, -tr / 2])
        self._k = np.array([s.k_spring_front_n_m, s.k_spring_front_n_m,
                            s.k_spring_rear_n_m, s.k_spring_rear_n_m])
        self._c = np.array([s.c_damp_front_ns_m, s.c_damp_front_ns_m,
                            s.c_damp_rear_ns_m, s.c_damp_rear_ns_m])

        # Static corner loads.
        W = c.mass_kg * G
        wf = W * c.weight_dist_front / 2
        wr = W * (1 - c.weight_dist_front) / 2
        self._fz_static = np.array([wf, wf, wr, wr])

        # Lumped modal stiffness / damping.
        kf, kr = s.k_spring_front_n_m, s.k_spring_rear_n_m
        cf, cr = s.c_damp_front_ns_m, s.c_damp_rear_ns_m
        self._K_heave = 2 * kf + 2 * kr
        self._C_heave = 2 * cf + 2 * cr
        self._K_roll = 0.5 * (kf * tf**2 + kr * tr**2) + s.k_arb_front_nm_rad + s.k_arb_rear_nm_rad
        self._C_roll = 0.5 * (cf * tf**2 + cr * tr**2)
        self._K_pitch = 2 * kf * self._a**2 + 2 * kr * self._b**2
        self._C_pitch = 2 * cf * self._a**2 + 2 * cr * self._b**2

        self._h_roll_arm = c.cg_height_m - c.roll_centre_h_m
        self._h_pitch_arm = c.cg_height_m - c.pitch_centre_h_m

    # ------------------------------------------------------------------

    @property
    def cg_to_front(self) -> float:
        return self._a

    @property
    def cg_to_rear(self) -> float:
        return self._b

    def static_loads(self) -> np.ndarray:
        return self._fz_static.copy()

    def equilibrium_heave(self, v: float) -> float:
        """Steady heave displacement under aero downforce at speed ``v`` (φ=θ=0)."""
        return -self._downforce(v) / self._K_heave

    # ------------------------------------------------------------------

    def _downforce(self, v: float) -> float:
        a = self._p.aero
        return 0.5 * a.rho_air * a.cl * v**2

    def wheel_loads(self, phi, phi_dot, theta, theta_dot, z, z_dot) -> np.ndarray:
        """Per-wheel vertical load Fz [N] from the current suspension state, clamped ≥ 0."""
        dz = z + self.y_wheel * phi - self.x_wheel * theta
        dz_dot = z_dot + self.y_wheel * phi_dot - self.x_wheel * theta_dot
        fz = self._fz_static - self._k * dz - self._c * dz_dot

        # Anti-roll bars: outer wheel of the rolled axle gains load.
        s = self._p.suspension
        c = self._p.chassis
        arb_f = s.k_arb_front_nm_rad * phi / c.track_front_m
        arb_r = s.k_arb_rear_nm_rad * phi / c.track_rear_m
        fz_arb = np.array([-arb_f, arb_f, -arb_r, arb_r])

        return np.maximum(fz + fz_arb, 0.0)

    def roll_pitch_heave_accels(self, ax, ay, v, phi, phi_dot, theta, theta_dot, z, z_dot):
        """Return (φ̈, θ̈, z̈) [rad/s², rad/s², m/s²] from inertial and aero loads."""
        c = self._p.chassis
        m_s = c.sprung_mass_kg

        # Roll: lateral overturning vs spring/ARB/damper and gravity jacking.
        phi_ddot = (
            m_s * ay * self._h_roll_arm
            - self._K_roll * phi
            - self._C_roll * phi_dot
            - m_s * G * self._h_roll_arm * phi
        ) / c.Ixx_kgm2

        # Pitch: braking dive (ax<0 → nose-down) plus the aero downforce balance.
        f_down = self._downforce(v)
        f_df = self._p.aero.aero_balance_front * f_down
        f_dr = (1 - self._p.aero.aero_balance_front) * f_down
        m_aero_pitch = f_df * self._a - f_dr * self._b
        theta_ddot = (
            -m_s * ax * self._h_pitch_arm
            - self._K_pitch * theta
            - self._C_pitch * theta_dot
            + m_aero_pitch
        ) / c.Iyy_kgm2

        # Heave: ride springs/dampers resist; downforce pushes the body down.
        z_ddot = (
            -self._K_heave * z
            - self._C_heave * z_dot
            - f_down
        ) / m_s

        return phi_ddot, theta_ddot, z_ddot
