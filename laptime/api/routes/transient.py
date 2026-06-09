"""Transient 7DOF time-domain lap simulation endpoint."""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException

from laptime.api.schemas import (
    SimulateResponse,
    TransientRequest,
    TransientResponse,
    TransientSimResult,
)
from laptime.api.store import get_track
from laptime.optimizer.racing_line import MinCurvatureOptimizer
from laptime.sim.qss import QSSSolver
from laptime.sim.transient import TransientSolver
from laptime.vehicle.dynamic_vehicle import DynamicVehicle

router = APIRouter()


@router.post("", response_model=TransientResponse)
def solve_transient(req: TransientRequest) -> TransientResponse:
    """Run the transient 7DOF + Pacejka simulation tracking the QSS reference.

    Returns the QSS reference lap time alongside the transient lap time, the followed
    path and run diagnostics (whether the lap completed and the peak lateral deviation).
    """
    try:
        track = get_track(req.track_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e

    vehicle = DynamicVehicle(req.vehicle)

    # Reference line the driver tracks: optimised racing line or the centreline.
    try:
        if req.use_racing_line:
            opt = MinCurvatureOptimizer(track)
            line = opt.apply_to_track(opt.optimize())
        else:
            line = track
    except Exception as e:
        raise HTTPException(500, f"Racing-line optimisation failed: {e}") from e

    # QSS reference (uses the dynamic vehicle's steady-state grip estimate).
    qss = QSSSolver(line, vehicle, ds=req.ds).solve()
    baseline = SimulateResponse(
        lap_time_s=round(qss.lap_time_s, 4),
        track_id=req.track_id,
        s=qss.s.tolist(),
        v_ms=qss.v.tolist(),
        ax_ms2=qss.ax.tolist(),
        ay_ms2=qss.ay.tolist(),
    )

    # Transient time-domain solve.
    try:
        res = TransientSolver(line, vehicle, qss, racing_line=line, dt=req.dt).solve()
    except Exception as e:
        raise HTTPException(500, f"Transient solver failed: {e}") from e

    pts = line.at(np.asarray(res.s))
    transient = TransientSimResult(
        lap_time_s=round(res.lap_time_s, 4),
        track_id=req.track_id,
        s=res.s.tolist(),
        v_ms=res.v.tolist(),
        ax_ms2=res.ax.tolist(),
        ay_ms2=res.ay.tolist(),
        x_path=[p.x for p in pts],
        y_path=[p.y for p in pts],
        completed=bool(res.metadata["completed"]),
        aborted=bool(res.metadata["aborted"]),
        max_lateral_dev_m=round(float(res.metadata["max_lateral_dev_m"]), 3),
    )

    return TransientResponse(
        qss_lap_time_s=baseline.lap_time_s,
        transient_lap_time_s=transient.lap_time_s,
        delta_s=round(transient.lap_time_s - baseline.lap_time_s, 4),
        completed=transient.completed,
        baseline=baseline,
        transient=transient,
    )
