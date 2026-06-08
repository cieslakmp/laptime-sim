"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VehicleParamsRequest(BaseModel):
    mass_kg: float = Field(default=700.0, gt=0)
    p_max_kw: float = Field(default=400.0, gt=0)
    f_brake_max_n: float = Field(default=20000.0, gt=0)
    mu_x: float = Field(default=1.6, gt=0)
    mu_y: float = Field(default=1.8, gt=0)
    cd: float = Field(default=0.9, gt=0)
    cl: float = Field(default=2.5)
    aero_ref_area_m2: float = Field(default=1.5, gt=0)
    v_max_ms: float = Field(default=83.0, gt=0)


class TrackUploadResponse(BaseModel):
    track_id: str
    name: str
    length_m: float
    n_points: int


class SimulateRequest(BaseModel):
    track_id: str
    vehicle: VehicleParamsRequest
    ds: float = Field(default=2.0, gt=0, description="Simulation spatial resolution [m]")


class SimulateResponse(BaseModel):
    lap_time_s: float
    track_id: str
    s: list[float]
    v_ms: list[float]
    ax_ms2: list[float]
    ay_ms2: list[float]


class OptimizeRequest(BaseModel):
    track_id: str
    vehicle: VehicleParamsRequest
    ds: float = Field(default=2.0, gt=0)
    n_racing_line_points: int = Field(default=200, gt=10)


class OptimizeResponse(BaseModel):
    baseline_lap_time_s: float
    optimized_lap_time_s: float
    delta_s: float
    optimized_track_id: str
    baseline: SimulateResponse
    optimized: SimulateResponse
