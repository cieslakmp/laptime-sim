"""Point-mass vehicle model with traction circle and aero effects."""

from __future__ import annotations

import math

from .base import VehicleModel
from .params import PointMassParams

G = 9.81  # m/s²


class PointMassVehicle(VehicleModel):
    """Point-mass model.

    The vehicle is treated as a point with:
    - Gravitational + downforce normal load
    - Traction ellipse: (ax/ax_max)² + (ay/ay_max)² ≤ 1
    - Engine: power-limited above the traction limit speed
    - Brake: constant peak force (traction-limited at low speed)
    """

    def __init__(self, params: PointMassParams) -> None:
        self._p = params

    @property
    def mass(self) -> float:
        return self._p.mass_kg

    # ------------------------------------------------------------------
    # Aerodynamic forces

    def _drag_force(self, v: float) -> float:
        return 0.5 * self._p.rho_air * self._p.cd * v**2

    def _downforce(self, v: float) -> float:
        return 0.5 * self._p.rho_air * self._p.cl * v**2

    def _normal_load(self, v: float, banking: float = 0.0) -> float:
        """Effective normal load including downforce [N]."""
        gravity_component = self._p.mass_kg * G * math.cos(banking)
        return gravity_component + self._downforce(v)

    # ------------------------------------------------------------------
    # Tyre limits

    def lateral_limit(self, v: float, kappa: float = 0.0, banking: float = 0.0) -> float:
        N = self._normal_load(v, banking)
        ay_tyre = self._p.mu_y * N / self._p.mass_kg
        # Gravity component on banked road adds/subtracts from required lateral force
        ay_gravity = G * math.sin(banking)
        return ay_tyre + ay_gravity

    def _ax_tyre_limit(self, v: float, banking: float = 0.0) -> float:
        N = self._normal_load(v, banking)
        return self._p.mu_x * N / self._p.mass_kg

    # ------------------------------------------------------------------
    # Longitudinal limits

    def longitudinal_limits(
        self,
        v: float,
        ay: float,
        kappa: float = 0.0,
        banking: float = 0.0,
    ) -> tuple[float, float]:
        v = max(v, 0.1)
        ay_abs = abs(ay)
        ay_lim = self.lateral_limit(v, kappa, banking)
        ax_tyre = self._ax_tyre_limit(v, banking)

        # Traction ellipse: remaining longitudinal capacity
        lateral_fraction = min(ay_abs / max(ay_lim, 1e-6), 1.0)
        ax_remaining = ax_tyre * math.sqrt(max(0.0, 1.0 - lateral_fraction**2))

        # Acceleration limit
        p_max_w = self._p.p_max_kw * 1000.0
        ax_engine = p_max_w / (self._p.mass_kg * v) - self._drag_force(v) / self._p.mass_kg
        ax_max = min(ax_remaining, max(0.0, ax_engine), self._p.v_max_ms - v)

        # Braking limit
        ax_brake_tyre = ax_remaining  # tyre-limited
        ax_brake_system = self._p.f_brake_max_n / self._p.mass_kg
        drag_assist = self._drag_force(v) / self._p.mass_kg
        ax_min = -(min(ax_brake_tyre, ax_brake_system) + drag_assist)

        return ax_min, max(0.0, ax_max)
