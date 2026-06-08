"""Racing line optimisation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from laptime.api.schemas import OptimizeRequest, OptimizeResponse, SimulateResponse
from laptime.api.store import get_track, save_track
from laptime.optimizer.racing_line import MinCurvatureOptimizer
from laptime.sim.qss import QSSSolver
from laptime.vehicle.params import PointMassParams
from laptime.vehicle.point_mass import PointMassVehicle

router = APIRouter()


def _run(track, vehicle, ds) -> SimulateResponse:
    solver = QSSSolver(track, vehicle, ds=ds)
    result = solver.solve()
    return SimulateResponse(
        lap_time_s=round(result.lap_time_s, 4),
        track_id="",
        s=result.s.tolist(),
        v_ms=result.v.tolist(),
        ax_ms2=result.ax.tolist(),
        ay_ms2=result.ay.tolist(),
    )


@router.post("", response_model=OptimizeResponse)
def optimize_racing_line(req: OptimizeRequest) -> OptimizeResponse:
    """Optimise the racing line using the minimum-curvature approach."""
    try:
        track = get_track(req.track_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e

    params = PointMassParams(**req.vehicle.model_dump())
    vehicle = PointMassVehicle(params)

    # Baseline: simulate on centreline
    baseline_resp = _run(track, vehicle, req.ds)
    baseline_resp.track_id = req.track_id

    # Optimise racing line
    try:
        opt = MinCurvatureOptimizer(track, n_points=req.n_racing_line_points)
        alpha = opt.optimize()
        opt_track = opt.apply_to_track(alpha)
    except Exception as e:
        raise HTTPException(500, f"Optimisation failed: {e}") from e

    opt_track_id = save_track(opt_track)
    opt_resp = _run(opt_track, vehicle, req.ds)
    opt_resp.track_id = opt_track_id

    return OptimizeResponse(
        baseline_lap_time_s=baseline_resp.lap_time_s,
        optimized_lap_time_s=opt_resp.lap_time_s,
        delta_s=round(opt_resp.lap_time_s - baseline_resp.lap_time_s, 4),
        optimized_track_id=opt_track_id,
        baseline=baseline_resp,
        optimized=opt_resp,
    )
