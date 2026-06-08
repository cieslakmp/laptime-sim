"""Pydantic configuration models for vehicle parameters."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field

Positive = Annotated[float, Field(gt=0)]


class PointMassParams(BaseModel):
    """Parameters for the point-mass vehicle model."""

    mass_kg: Positive = Field(default=700.0, description="Total mass including driver [kg]")
    p_max_kw: Positive = Field(default=400.0, description="Peak engine power [kW]")
    f_brake_max_n: Positive = Field(default=20000.0, description="Peak brake force [N]")
    mu_x: Positive = Field(default=1.6, description="Peak longitudinal tyre friction coefficient")
    mu_y: Positive = Field(default=1.8, description="Peak lateral tyre friction coefficient")
    cd: Positive = Field(default=0.9, description="Aerodynamic drag coefficient (Cd·A) [m²]")
    cl: float = Field(default=2.5, description="Aerodynamic downforce coefficient (Cl·A) [m²]")
    aero_ref_area_m2: Positive = Field(default=1.5, description="Aerodynamic reference area [m²]")
    v_max_ms: Positive = Field(default=83.0, description="Top speed limit [m/s] (~300 km/h)")
    rho_air: Positive = Field(default=1.225, description="Air density [kg/m³]")

    @classmethod
    def from_toml(cls, path: str | Path) -> "PointMassParams":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**data.get("vehicle", data))
