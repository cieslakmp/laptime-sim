"""Simulation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from laptime.api.schemas import SimulateRequest, SimulateResponse
from laptime.api.store import get_track
from laptime.sim.qss import QSSSolver
from laptime.vehicle.params import PointMassParams
from laptime.vehicle.point_mass import PointMassVehicle

router = APIRouter()


@router.post("", response_model=SimulateResponse)
def run_simulation(req: SimulateRequest) -> SimulateResponse:
    """Run a QSS lap time simulation."""
    try:
        track = get_track(req.track_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e

    params = PointMassParams(**req.vehicle.model_dump())
    vehicle = PointMassVehicle(params)
    solver = QSSSolver(track, vehicle, ds=req.ds)

    try:
        result = solver.solve()
    except Exception as e:
        raise HTTPException(500, f"Simulation failed: {e}") from e

    return SimulateResponse(
        lap_time_s=round(result.lap_time_s, 4),
        track_id=req.track_id,
        s=result.s.tolist(),
        v_ms=result.v.tolist(),
        ax_ms2=result.ax.tolist(),
        ay_ms2=result.ay.tolist(),
    )
