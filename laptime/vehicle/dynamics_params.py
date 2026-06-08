"""Pydantic configuration models for the transient 7DOF vehicle model."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .params import Positive
from .tyre_pacejka import PacejkaCoeffs


class ChassisParams(BaseModel):
    """Inertias, geometry and mass distribution of the chassis."""

    mass_kg: Positive = Field(default=1300.0, description="Total mass [kg]")
    sprung_mass_kg: Positive = Field(default=1150.0, description="Sprung mass [kg]")
    Izz_kgm2: Positive = Field(default=1800.0, description="Yaw inertia [kg·m²]")
    Ixx_kgm2: Positive = Field(default=500.0, description="Roll inertia (sprung) [kg·m²]")
    Iyy_kgm2: Positive = Field(default=1600.0, description="Pitch inertia (sprung) [kg·m²]")
    wheelbase_m: Positive = Field(default=2.6, description="Wheelbase [m]")
    track_front_m: Positive = Field(default=1.6, description="Front track width [m]")
    track_rear_m: Positive = Field(default=1.55, description="Rear track width [m]")
    cg_height_m: Positive = Field(default=0.30, description="CG height above ground [m]")
    weight_dist_front: float = Field(default=0.47, gt=0, lt=1, description="Front weight fraction")
    roll_centre_h_m: float = Field(default=0.05, description="Roll centre height [m]")
    pitch_centre_h_m: float = Field(default=0.10, description="Pitch centre height [m]")


class SuspensionParams(BaseModel):
    """Ride spring, damper and anti-roll rates."""

    k_spring_front_n_m: Positive = Field(default=60000.0, description="Front ride rate [N/m]")
    k_spring_rear_n_m: Positive = Field(default=55000.0, description="Rear ride rate [N/m]")
    c_damp_front_ns_m: Positive = Field(default=4000.0, description="Front damping [N·s/m]")
    c_damp_rear_ns_m: Positive = Field(default=3800.0, description="Rear damping [N·s/m]")
    k_arb_front_nm_rad: float = Field(default=30000.0, description="Front anti-roll rate [N·m/rad]")
    k_arb_rear_nm_rad: float = Field(default=20000.0, description="Rear anti-roll rate [N·m/rad]")
    use_heave: bool = Field(default=True, description="Include the heave DOF")


class DrivetrainParams(BaseModel):
    """Powertrain, wheels and brakes."""

    layout: Literal["fwd", "rwd", "awd"] = Field(default="rwd", description="Drive layout")
    awd_front_bias: float = Field(default=0.0, ge=0, le=1, description="AWD front torque fraction")
    torque_max_nm: Positive = Field(default=6000.0, description="Peak wheel drive torque [N·m]")
    p_max_kw: Positive = Field(default=350.0, description="Peak power [kW]")
    wheel_radius_m: Positive = Field(default=0.33, description="Effective rolling radius [m]")
    wheel_inertia_kgm2: Positive = Field(default=1.2, description="Wheel+driveline inertia [kg·m²]")
    brake_torque_max_nm: Positive = Field(
        default=6000.0, description="Peak wheel brake torque, all wheels [N·m]")
    brake_balance_front: float = Field(default=0.62, gt=0, lt=1, description="Front brake fraction")


class DriverParams(BaseModel):
    """Path-tracking driver controller gains."""

    lookahead_min_m: Positive = Field(default=5.0, description="Minimum pure-pursuit lookahead [m]")
    lookahead_gain_s: Positive = Field(default=0.3, description="Lookahead speed gain [s]")
    steer_max_rad: Positive = Field(default=0.5, description="Steering angle limit [rad]")
    steer_rate_max_rad_s: Positive = Field(default=8.0, description="Steering rate limit [rad/s]")
    cross_track_gain: float = Field(default=0.6, ge=0, description="Cross-track steering gain")
    kp_speed: Positive = Field(default=0.8, description="Speed proportional gain")
    ki_speed: float = Field(default=0.1, ge=0, description="Speed integral gain")
    accel_ref_ms2: Positive = Field(default=10.0, description="Accel reference [m/s²]")
    speed_margin: float = Field(default=0.97, gt=0, le=1, description="Fraction of QSS speed")
    understeer_gain: float = Field(default=0.4, ge=0, description="Speed back-off per m [1/m]")
    path_deadband_m: Positive = Field(default=0.5, description="Path-error deadband [m]")


class AeroParams(BaseModel):
    """Aerodynamic drag and downforce."""

    cd: Positive = Field(default=0.8, description="Drag coefficient (Cd·A) [m²]")
    cl: float = Field(default=1.2, description="Downforce coefficient (Cl·A) [m²]")
    rho_air: Positive = Field(default=1.225, description="Air density [kg/m³]")
    aero_balance_front: float = Field(default=0.45, gt=0, lt=1, description="Front aero fraction")


class DynamicVehicleParams(BaseModel):
    """Aggregate parameter set for the transient 7DOF vehicle model."""

    chassis: ChassisParams = Field(default_factory=ChassisParams)
    suspension: SuspensionParams = Field(default_factory=SuspensionParams)
    drivetrain: DrivetrainParams = Field(default_factory=DrivetrainParams)
    driver: DriverParams = Field(default_factory=DriverParams)
    aero: AeroParams = Field(default_factory=AeroParams)
    tyre_front: PacejkaCoeffs = Field(default_factory=PacejkaCoeffs)
    tyre_rear: PacejkaCoeffs = Field(default_factory=PacejkaCoeffs)
    relax_length_m: float = Field(default=0.4, ge=0, description="Tyre relaxation length [m]")
    grip_factor: float = Field(
        default=0.82, gt=0, le=1,
        description="Derating of the steady-state (QSS) grip estimate to account for "
        "combined-slip losses and transient effects the point estimate ignores",
    )

    @classmethod
    def from_toml(cls, path: str | Path) -> DynamicVehicleParams:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**data.get("vehicle", data))
