"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from laptime.vehicle.dynamics_params import DynamicVehicleParams


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


class OCPRequest(BaseModel):
    track_id: str
    vehicle: VehicleParamsRequest
    ds: float = Field(default=2.0, gt=0)
    n_intervals: int = Field(default=150, gt=20, description="Number of OCP shooting intervals")


class OCPSimResult(SimulateResponse):
    """SimulateResponse extended with OCP-specific state trajectory."""
    n_m: list[float]           # lateral offset [m]
    psi_rad: list[float]       # heading error [rad]
    x_path: list[float]        # optimal path x coordinates [m]
    y_path: list[float]        # optimal path y coordinates [m]
    solve_time_s: float
    solver_status: str


class OCPResponse(BaseModel):
    baseline_lap_time_s: float
    optimized_lap_time_s: float
    delta_s: float
    baseline: SimulateResponse
    optimized: OCPSimResult


class TransientRequest(BaseModel):
    track_id: str
    vehicle: DynamicVehicleParams = Field(default_factory=DynamicVehicleParams)
    ds: float = Field(default=2.0, gt=0, description="QSS reference resolution [m]")
    dt: float = Field(default=2.5e-3, gt=0, description="Time-domain integration step [s]")
    use_racing_line: bool = Field(default=True, description="Track the min-curvature racing line")


class TransientSimResult(SimulateResponse):
    """SimulateResponse extended with the transient path and run diagnostics."""
    x_path: list[float]                # followed-line x coordinates [m]
    y_path: list[float]                # followed-line y coordinates [m]
    completed: bool
    aborted: bool
    max_lateral_dev_m: float


class TransientResponse(BaseModel):
    qss_lap_time_s: float
    transient_lap_time_s: float
    delta_s: float
    completed: bool
    baseline: SimulateResponse         # QSS on the reference line
    transient: TransientSimResult


# --------------------------------------------------------------------------
# Parameter sweep
# --------------------------------------------------------------------------

SweepSolver = Literal["qss", "racing_line", "transient", "ocp"]
SweepMode = Literal["grid", "one_at_a_time"]
SweepState = Literal["pending", "running", "done", "failed", "cancelled"]


class SweepParamSpec(BaseModel):
    """Range specification for one swept vehicle parameter."""

    name: str
    min: float
    max: float
    steps: int = Field(ge=2, le=50, description="Number of values incl. both endpoints")

    @field_validator("name")
    @classmethod
    def _known_param(cls, v: str) -> str:
        if v not in VehicleParamsRequest.model_fields:
            valid = ", ".join(VehicleParamsRequest.model_fields)
            raise ValueError(f"Unknown vehicle parameter '{v}'. Valid: {valid}")
        return v

    @model_validator(mode="after")
    def _min_below_max(self) -> SweepParamSpec:
        if not self.min < self.max:
            raise ValueError(
                f"Parameter '{self.name}': min ({self.min}) must be < max ({self.max})"
            )
        return self


class SweepRequest(BaseModel):
    """Start a parameter sweep.

    ``grid`` mode runs the cartesian product of all parameter ranges; values are
    expanded with ``itertools.product`` in request order, so the LAST parameter
    varies fastest (row-major — the frontend heatmap relies on this contract).
    ``one_at_a_time`` varies each parameter alone with the others held at the
    baseline ``vehicle`` values (sensitivity / tornado analysis).
    A baseline run at the unmodified ``vehicle`` values is always added at index 0.
    """

    track_id: str
    vehicle: VehicleParamsRequest
    params: list[SweepParamSpec] = Field(min_length=1, max_length=3)
    mode: SweepMode = "grid"
    solver: SweepSolver = "qss"
    ds: float = Field(default=2.0, gt=0, description="Simulation spatial resolution [m]")
    use_racing_line: bool = Field(default=True, description="Transient only: track the racing line")
    n_intervals: int = Field(default=150, gt=20, description="OCP only: shooting intervals")

    @field_validator("params")
    @classmethod
    def _unique_names(cls, v: list[SweepParamSpec]) -> list[SweepParamSpec]:
        names = [p.name for p in v]
        if len(set(names)) != len(names):
            raise ValueError(f"Duplicate swept parameter names: {names}")
        return v


class SweepStartResponse(BaseModel):
    sweep_id: str
    total_runs: int                    # incl. the baseline run
    state: SweepState


class SweepStatusResponse(BaseModel):
    sweep_id: str
    state: SweepState
    completed: int
    total: int
    error: str | None = None


class SweepRunRecord(BaseModel):
    """One sweep point: the swept parameter values and the resulting lap time."""

    index: int
    param_values: dict[str, float]     # swept params only; {} for the baseline run
    varied_param: str | None = None    # one_at_a_time mode; None for grid/baseline
    lap_time_s: float | None = None
    ok: bool = True
    error: str | None = None


class SweepAggregates(BaseModel):
    """Range data on the common s-grid, embedded so saved sweeps render standalone."""

    s: list[float]
    x: list[float]                     # display line (centreline or racing line)
    y: list[float]
    v_min: list[float]                 # envelope across all successful runs [m/s]
    v_max: list[float]
    v_spread: list[float]              # v_max - v_min [m/s]
    v_baseline: list[float]
    gg_hull_ay_g: list[float]          # pooled G-G convex hull, closed polygon [g]
    gg_hull_ax_g: list[float]
    gg_baseline_ay_g: list[float]      # baseline G-G points, decimated [g]
    gg_baseline_ax_g: list[float]


class SweepResult(BaseModel):
    schema_version: int = 1
    sweep_id: str
    created_at: str                    # ISO 8601
    state: SweepState
    config: SweepRequest
    track_name: str
    track_length_m: float
    baseline_lap_time_s: float
    runs: list[SweepRunRecord]         # ordered by index; baseline at index 0
    aggregates: SweepAggregates


class SavedSweepInfo(BaseModel):
    sweep_id: str
    created_at: str
    track_name: str
    solver: str
    mode: str
    n_runs: int
    param_names: list[str]
    best_lap_time_s: float | None = None
