"""Parameter sweep endpoints: start, poll progress, fetch results, saved-sweep store.

A sweep runs on a background thread with a per-sweep process pool, so POST returns
immediately and the frontend polls ``GET /sweep/{id}/status``. Under ``uvicorn
--reload`` a code reload mid-sweep kills the job (dev-only caveat).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from laptime.api.schemas import (
    SavedSweepInfo,
    SweepRequest,
    SweepResult,
    SweepStartResponse,
    SweepStatusResponse,
)
from laptime.api.store import get_track
from laptime.sweep import persistence, runner
from laptime.sweep.spec import MAX_RUNS, TRANSIENT_SUPPORTED, total_points

router = APIRouter()


def _status(job: runner.SweepJob) -> SweepStatusResponse:
    return SweepStatusResponse(
        sweep_id=job.sweep_id,
        state=job.state,
        completed=job.completed,
        total=job.total,
        error=job.error,
    )


@router.post("", response_model=SweepStartResponse, status_code=202)
def start_sweep(req: SweepRequest) -> SweepStartResponse:
    """Start a parameter sweep in the background and return its id immediately."""
    try:
        track = get_track(req.track_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e

    n = total_points(req)
    cap = MAX_RUNS[req.solver]
    if n > cap:
        raise HTTPException(
            422, f"Sweep would run {n} points; the cap for solver '{req.solver}' is {cap}"
        )

    if req.solver == "transient":
        unsupported = [p.name for p in req.params if p.name not in TRANSIENT_SUPPORTED]
        if unsupported:
            raise HTTPException(
                422,
                f"Transient sweeps support only {sorted(TRANSIENT_SUPPORTED)}; "
                f"unsupported: {unsupported}",
            )

    if req.solver == "ocp":
        try:
            import casadi  # noqa: F401
        except ImportError as e:
            raise HTTPException(
                501, "CasADi is not installed. Install with: pip install laptime-sim[ocp]"
            ) from e

    job = runner.start_sweep(req, track)
    return SweepStartResponse(sweep_id=job.sweep_id, total_runs=job.total, state=job.state)


# NOTE: literal /saved routes must be declared before /{sweep_id} (same route-ordering
# gotcha as routes/tracks.py) so "saved" is not captured as a sweep id.


@router.get("/saved", response_model=list[SavedSweepInfo])
def list_saved_sweeps() -> list[SavedSweepInfo]:
    """List sweeps persisted under data/sweeps/, newest first."""
    return persistence.list_saved()


@router.get("/saved/{sweep_id}", response_model=SweepResult)
def get_saved_sweep(sweep_id: str) -> SweepResult:
    try:
        return persistence.load_saved(sweep_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.delete("/saved/{sweep_id}", status_code=204)
def delete_saved_sweep(sweep_id: str) -> Response:
    try:
        persistence.delete_saved(sweep_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return Response(status_code=204)


@router.get("/{sweep_id}/status", response_model=SweepStatusResponse)
def sweep_status(sweep_id: str) -> SweepStatusResponse:
    try:
        return _status(runner.get_job(sweep_id))
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/{sweep_id}", response_model=SweepResult)
def sweep_result(sweep_id: str) -> SweepResult:
    """Full sweep result once the job is done; 409 with the current state otherwise."""
    try:
        job = runner.get_job(sweep_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    if job.state != "done" or job.result is None:
        detail = f"Sweep '{sweep_id}' is not finished (state: {job.state}"
        if job.error:
            detail += f", error: {job.error}"
        raise HTTPException(409, detail + ")")
    return job.result


@router.post("/{sweep_id}/cancel", response_model=SweepStatusResponse)
def cancel_sweep(sweep_id: str) -> SweepStatusResponse:
    """Request cancellation; already-running points finish, queued ones are dropped."""
    try:
        return _status(runner.request_cancel(sweep_id))
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
