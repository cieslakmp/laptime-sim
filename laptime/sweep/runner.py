"""Sweep execution: parallel worker, in-memory job registry, background thread.

The worker function is module-level and receives only plain dicts / numpy arrays so
it crosses the Windows ``spawn`` process boundary cleanly (no closures, no pydantic
models, no scipy interpolators). Set ``LAPTIME_SWEEP_EXECUTOR=thread`` to run sweep
points on threads instead of processes (used by the test suite to avoid spawn cost).
"""

from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import (
    Executor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from laptime.optimizer.ocp import OCPResult
    from laptime.sim.result import LapResult
    from laptime.vehicle.dynamics_params import DynamicVehicleParams

from laptime.api.schemas import (
    SweepAggregates,
    SweepRequest,
    SweepResult,
    SweepRunRecord,
    SweepState,
)
from laptime.sweep import persistence
from laptime.sweep.spec import expand_points
from laptime.track.track import Track

G = 9.81

_TRACK_ARRAYS = ("s", "x", "y", "heading", "kappa", "width_left", "width_right", "banking")


def _track_payload(track: Track) -> dict:
    payload: dict = {k: getattr(track, k) for k in _TRACK_ARRAYS}
    payload["name"] = track.name
    payload["is_closed"] = track.is_closed
    return payload


def _track_from_payload(payload: dict) -> Track:
    return Track(**payload)


def _dynamic_params_from_flat(vehicle: dict) -> DynamicVehicleParams:
    """Map flat point-mass params onto the nested 7DOF set (mirrors the frontend)."""
    from laptime.vehicle.dynamics_params import DynamicVehicleParams

    return DynamicVehicleParams.model_validate({
        "chassis": {"mass_kg": vehicle["mass_kg"]},
        "drivetrain": {"p_max_kw": vehicle["p_max_kw"]},
        "aero": {"cd": vehicle["cd"], "cl": max(vehicle["cl"], 0.0)},
    })


def run_sweep_point(
    track_payload: dict,
    solver: str,
    vehicle: dict,
    ds: float,
    n_intervals: int,
    index: int,
) -> dict:
    """Run one solve in a worker. Never raises — errors come back as records."""
    try:
        from laptime.sim.qss import QSSSolver
        from laptime.vehicle.params import PointMassParams
        from laptime.vehicle.point_mass import PointMassVehicle

        track = _track_from_payload(track_payload)

        res: LapResult | OCPResult
        if solver in ("qss", "racing_line"):
            # For racing_line sweeps the payload already IS the optimised line.
            pm = PointMassVehicle(PointMassParams(**vehicle))
            res = QSSSolver(track, pm, ds=ds).solve()
        elif solver == "transient":
            from laptime.sim.transient import TransientSolver
            from laptime.vehicle.dynamic_vehicle import DynamicVehicle

            veh = DynamicVehicle(_dynamic_params_from_flat(vehicle))
            qss = QSSSolver(track, veh, ds=ds).solve()
            res = TransientSolver(track, veh, qss, racing_line=track, dt=2.5e-3).solve()
        elif solver == "ocp":
            from laptime.optimizer.ocp import OCPSolver

            res = OCPSolver(track, PointMassParams(**vehicle), N=n_intervals).solve()
        else:
            raise ValueError(f"Unknown solver '{solver}'")

        return {
            "index": index,
            "lap_time_s": float(res.lap_time_s),
            "s": np.asarray(res.s),
            "v": np.asarray(res.v),
            "ax": np.asarray(res.ax),
            "ay": np.asarray(res.ay),
        }
    except Exception as e:  # noqa: BLE001 — a failed point must not kill the sweep
        return {"index": index, "error": f"{type(e).__name__}: {e}"}


@dataclass
class SweepJob:
    sweep_id: str
    request: SweepRequest
    total: int                          # incl. baseline run
    created_at: datetime
    state: SweepState = "pending"
    completed: int = 0
    error: str | None = None
    result: SweepResult | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


_JOBS: dict[str, SweepJob] = {}
_LOCK = threading.Lock()
_MAX_JOBS = 20


def get_job(sweep_id: str) -> SweepJob:
    with _LOCK:
        if sweep_id not in _JOBS:
            raise KeyError(f"Sweep '{sweep_id}' not found")
        return _JOBS[sweep_id]


def request_cancel(sweep_id: str) -> SweepJob:
    job = get_job(sweep_id)
    job.cancel_event.set()
    return job


def _evict_old_jobs() -> None:
    """Keep at most _MAX_JOBS entries; drop the oldest finished jobs first."""
    with _LOCK:
        if len(_JOBS) <= _MAX_JOBS:
            return
        terminal = [j for j in _JOBS.values() if j.state in ("done", "failed", "cancelled")]
        terminal.sort(key=lambda j: j.created_at)
        for j in terminal[: len(_JOBS) - _MAX_JOBS]:
            del _JOBS[j.sweep_id]


def start_sweep(req: SweepRequest, track: Track) -> SweepJob:
    points = expand_points(req)
    job = SweepJob(
        sweep_id=uuid.uuid4().hex[:12],
        request=req,
        total=len(points) + 1,  # + baseline
        created_at=datetime.now(UTC),
    )
    with _LOCK:
        _JOBS[job.sweep_id] = job
    _evict_old_jobs()
    thread = threading.Thread(target=_run_job, args=(job, track, points), daemon=True)
    thread.start()
    return job


def _make_executor(n_tasks: int) -> Executor:
    kind = os.environ.get("LAPTIME_SWEEP_EXECUTOR", "process")
    workers = max(1, min(os.cpu_count() or 1, n_tasks))
    if kind == "thread":
        return ThreadPoolExecutor(max_workers=workers)
    return ProcessPoolExecutor(max_workers=workers)


def _run_job(
    job: SweepJob, track: Track, points: list[tuple[str | None, dict[str, float]]]
) -> None:
    try:
        req = job.request
        job.state = "running"

        # Racing line is vehicle-independent → optimise once, share across all points.
        line = track
        if req.solver == "racing_line" or (req.solver == "transient" and req.use_racing_line):
            from laptime.optimizer.racing_line import MinCurvatureOptimizer

            opt = MinCurvatureOptimizer(track)
            line = opt.apply_to_track(opt.optimize(), ds=req.ds)
        if job.cancel_event.is_set():
            job.state = "cancelled"
            return

        baseline_vehicle = req.vehicle.model_dump()
        # Baseline at index 0, then the expanded points.
        runs: list[tuple[str | None, dict[str, float]]] = [(None, {})] + points
        vehicles = [{**baseline_vehicle, **overrides} for _, overrides in runs]

        payload = _track_payload(line)
        results: list[dict | None] = [None] * len(runs)
        executor = _make_executor(len(runs))
        cancelled = False
        try:
            futures = {
                executor.submit(
                    run_sweep_point, payload, req.solver, veh, req.ds, req.n_intervals, i
                ): i
                for i, veh in enumerate(vehicles)
            }
            for fut in as_completed(futures):
                try:
                    rec = fut.result()
                except Exception as e:  # noqa: BLE001 — e.g. BrokenProcessPool
                    rec = {"index": futures[fut], "error": f"{type(e).__name__}: {e}"}
                results[rec["index"]] = rec
                with _LOCK:
                    job.completed += 1
                if job.cancel_event.is_set():
                    cancelled = True
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
        finally:
            if not cancelled:
                executor.shutdown(wait=True)
        if cancelled:
            job.state = "cancelled"
            return

        job.result = _build_result(job, line, runs, results)
        persistence.save_sweep(job.result)
        job.state = "done"
    except Exception as e:  # noqa: BLE001 — surface the failure via the status endpoint
        job.error = f"{type(e).__name__}: {e}"
        job.state = "failed"


def _build_result(
    job: SweepJob,
    line: Track,
    runs: list[tuple[str | None, dict[str, float]]],
    results: list[dict | None],
) -> SweepResult:
    req = job.request
    baseline = results[0]
    if baseline is None or "error" in baseline:
        detail = baseline["error"] if baseline else "missing"
        raise RuntimeError(f"Baseline run failed: {detail}")

    records = []
    for i, (varied, overrides) in enumerate(runs):
        rec = results[i]
        if rec is None or "error" in rec:
            records.append(SweepRunRecord(
                index=i, param_values=overrides, varied_param=varied,
                ok=False, error=rec["error"] if rec else "not run",
            ))
        else:
            records.append(SweepRunRecord(
                index=i, param_values=overrides, varied_param=varied,
                lap_time_s=round(float(rec["lap_time_s"]), 4),
            ))

    # Common grid = the display line resampled at ds (matches the QSS result grid);
    # every run's velocity is interpolated onto it so transient/OCP grids align too.
    disp = line.resample(req.ds)
    s_ref = disp.s
    ok = [r for r in results if r is not None and "error" not in r]

    def _on_ref(rec: dict, key: str) -> np.ndarray:
        if len(rec["s"]) == len(s_ref) and np.allclose(rec["s"], s_ref):
            return np.asarray(rec[key], dtype=float)
        return np.interp(s_ref, rec["s"], rec[key])

    v_stack = np.stack([_on_ref(r, "v") for r in ok])
    v_min = v_stack.min(axis=0)
    v_max = v_stack.max(axis=0)
    v_baseline = _on_ref(baseline, "v")

    # Pooled G-G convex hull across all runs [g].
    ay_all = np.concatenate([np.asarray(r["ay"]) for r in ok]) / G
    ax_all = np.concatenate([np.asarray(r["ax"]) for r in ok]) / G
    hull_ay, hull_ax = _gg_hull(ay_all, ax_all)

    # Baseline G-G decimated to <= 500 points.
    n_b = len(baseline["ay"])
    step = max(1, -(-n_b // 500))
    gg_b_ay = (np.asarray(baseline["ay"]) / G)[::step]
    gg_b_ax = (np.asarray(baseline["ax"]) / G)[::step]

    return SweepResult(
        sweep_id=job.sweep_id,
        created_at=job.created_at.isoformat(),
        state="done",
        config=req,
        track_name=line.name,
        track_length_m=round(line.length, 1),
        baseline_lap_time_s=round(float(baseline["lap_time_s"]), 4),
        runs=records,
        aggregates=SweepAggregates(
            s=s_ref.tolist(),
            x=disp.x.tolist(),
            y=disp.y.tolist(),
            v_min=v_min.tolist(),
            v_max=v_max.tolist(),
            v_spread=(v_max - v_min).tolist(),
            v_baseline=v_baseline.tolist(),
            gg_hull_ay_g=hull_ay,
            gg_hull_ax_g=hull_ax,
            gg_baseline_ay_g=gg_b_ay.tolist(),
            gg_baseline_ax_g=gg_b_ax.tolist(),
        ),
    )


def _gg_hull(ay_g: np.ndarray, ax_g: np.ndarray) -> tuple[list[float], list[float]]:
    """Convex hull of the pooled G-G cloud as a closed polygon; [] if degenerate."""
    pts = np.unique(np.column_stack([ay_g, ax_g]), axis=0)
    if len(pts) < 3:
        return [], []
    try:
        from scipy.spatial import ConvexHull

        hull = ConvexHull(pts)
        verts = np.append(hull.vertices, hull.vertices[0])  # close the polygon
        return pts[verts, 0].tolist(), pts[verts, 1].tolist()
    except Exception:  # noqa: BLE001 — QhullError on collinear input
        return [], []
