"""Full optimal control (OCP) endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from laptime.api.schemas import OCPRequest, OCPResponse, OCPSimResult, SimulateResponse
from laptime.api.store import get_track
from laptime.sim.qss import QSSSolver
from laptime.vehicle.params import PointMassParams
from laptime.vehicle.point_mass import PointMassVehicle

router = APIRouter()


@router.post("", response_model=OCPResponse)
def solve_ocp(req: OCPRequest) -> OCPResponse:
    """Run the minimum-time OCP (CasADi + IPOPT).

    Returns baseline QSS lap time alongside the OCP-optimised time and
    the full state trajectory (lateral offset, heading error, velocity).
    """
    try:
        track = get_track(req.track_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e

    try:
        from laptime.optimizer.ocp import OCPSolver
    except ImportError as e:
        raise HTTPException(
            501,
            "CasADi is not installed. Install with: pip install laptime-sim[ocp]",
        ) from e

    params = PointMassParams(**req.vehicle.model_dump())
    vehicle = PointMassVehicle(params)

    # --- Baseline: QSS on centreline ---
    qss_result = QSSSolver(track, vehicle, ds=req.ds).solve()
    baseline = SimulateResponse(
        lap_time_s=round(qss_result.lap_time_s, 4),
        track_id=req.track_id,
        s=qss_result.s.tolist(),
        v_ms=qss_result.v.tolist(),
        ax_ms2=qss_result.ax.tolist(),
        ay_ms2=qss_result.ay.tolist(),
    )

    # --- OCP solve ---
    try:
        solver = OCPSolver(track, params, N=req.n_intervals)
        ocp_result = solver.solve()
    except Exception as e:
        raise HTTPException(500, f"OCP solver failed: {e}") from e

    optimized = OCPSimResult(
        lap_time_s=round(ocp_result.lap_time_s, 4),
        track_id=req.track_id,
        s=ocp_result.s.tolist(),
        v_ms=ocp_result.v.tolist(),
        ax_ms2=ocp_result.ax.tolist(),
        ay_ms2=ocp_result.ay.tolist(),
        n_m=ocp_result.n.tolist(),
        psi_rad=ocp_result.psi.tolist(),
        x_path=ocp_result.x_path.tolist(),
        y_path=ocp_result.y_path.tolist(),
        solve_time_s=ocp_result.solve_time_s,
        solver_status=ocp_result.solver_status,
    )

    return OCPResponse(
        baseline_lap_time_s=baseline.lap_time_s,
        optimized_lap_time_s=optimized.lap_time_s,
        delta_s=round(optimized.lap_time_s - baseline.lap_time_s, 4),
        baseline=baseline,
        optimized=optimized,
    )
