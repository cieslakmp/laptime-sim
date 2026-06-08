"""Tests for the suspension / dynamic load-transfer model."""

import numpy as np

from laptime.vehicle.dynamics_params import (
    ChassisParams,
    DynamicVehicleParams,
    SuspensionParams,
)
from laptime.vehicle.suspension import G, SuspensionModel


def _model(**chassis_over) -> SuspensionModel:
    return SuspensionModel(DynamicVehicleParams(chassis=ChassisParams(**chassis_over)))


def test_static_loads_sum_to_weight():
    p = DynamicVehicleParams()
    s = SuspensionModel(p)
    fz = s.static_loads()
    assert np.isclose(fz.sum(), p.chassis.mass_kg * G)


def test_static_front_rear_split():
    p = DynamicVehicleParams(chassis=ChassisParams(weight_dist_front=0.45))
    s = SuspensionModel(p)
    fz = s.static_loads()
    front, rear = fz[0] + fz[1], fz[2] + fz[3]
    assert np.isclose(front / (front + rear), 0.45)


def test_zero_state_recovers_static():
    s = _model()
    fz = s.wheel_loads(0, 0, 0, 0, 0, 0)
    assert np.allclose(fz, s.static_loads())


def test_lateral_transfer_loads_outer_wheels():
    """Positive roll (response to a left turn) loads the right (outer) wheels."""
    p = DynamicVehicleParams()
    s = SuspensionModel(p)
    fz = s.wheel_loads(phi=0.02, phi_dot=0, theta=0, theta_dot=0, z=0, z_dot=0)
    # [FL, FR, RL, RR]: outer (right) FR/RR gain, inner (left) FL/RL lose.
    assert fz[1] > fz[0] and fz[3] > fz[2]
    # Vertical load is conserved under pure roll.
    assert np.isclose(fz.sum(), p.chassis.mass_kg * G)


def test_downforce_increases_total_load():
    p = DynamicVehicleParams()
    s = SuspensionModel(p)
    z_eq = s.equilibrium_heave(60.0)
    assert z_eq < 0  # body squats under downforce
    fz = s.wheel_loads(0, 0, 0, 0, z_eq, 0)
    assert fz.sum() > p.chassis.mass_kg * G


def test_stiffer_antiroll_resists_roll_more():
    """A stiffer anti-roll bar gives a larger restoring roll moment for the same roll."""
    soft = SuspensionModel(DynamicVehicleParams(
        suspension=SuspensionParams(k_arb_front_nm_rad=5000, k_arb_rear_nm_rad=5000)))
    stiff = SuspensionModel(DynamicVehicleParams(
        suspension=SuspensionParams(k_arb_front_nm_rad=80000, k_arb_rear_nm_rad=80000)))
    phi = 0.03
    soft_acc = soft.roll_pitch_heave_accels(0, 0, 40, phi, 0, 0, 0, 0, 0)[0]
    stiff_acc = stiff.roll_pitch_heave_accels(0, 0, 40, phi, 0, 0, 0, 0, 0)[0]
    # Both restore toward zero (negative); the stiff bar restores harder.
    assert stiff_acc < soft_acc < 0


def test_roll_responds_to_lateral_accel():
    s = _model()
    phi_dd = s.roll_pitch_heave_accels(ax=0, ay=10.0, v=40, phi=0, phi_dot=0,
                                       theta=0, theta_dot=0, z=0, z_dot=0)[0]
    assert phi_dd > 0  # positive lateral accel rolls the body into the turn
