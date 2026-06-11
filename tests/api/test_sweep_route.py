"""Tests for the /sweep API endpoints."""

import math
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from laptime.api.main import app
from laptime.api.store import save_track
from laptime.track.geometry import (
    arc_length_parameterise,
    compute_curvature,
    compute_heading,
    fit_spline,
)
from laptime.track.track import Track


@pytest.fixture(autouse=True)
def sweep_env(monkeypatch, tmp_path):
    """Thread executor (no process-spawn cost) and an isolated sweeps dir."""
    monkeypatch.setenv("LAPTIME_SWEEP_EXECUTOR", "thread")
    monkeypatch.setenv("LAPTIME_SWEEPS_DIR", str(tmp_path / "sweeps"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def track_id() -> str:
    R, n = 70.0, 160
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x, y = R * np.cos(th), R * np.sin(th)
    tck, _ = fit_spline(x, y, closed=True)
    u = np.linspace(0, 1, n, endpoint=False)
    s, xf, yf = arc_length_parameterise(tck, n=n)
    track = Track(
        s=s, x=xf, y=yf, heading=compute_heading(tck, u), kappa=compute_curvature(tck, u),
        width_left=np.full(n, 5.0), width_right=np.full(n, 5.0), banking=np.zeros(n),
        name="sweep_circle", is_closed=True,
    )
    return save_track(track, "sweep_test_track")


def _base_request(track_id: str, **overrides) -> dict:
    req = {
        "track_id": track_id,
        "vehicle": {},
        "params": [{"name": "mass_kg", "min": 600, "max": 800, "steps": 3}],
        "mode": "grid",
        "solver": "qss",
    }
    req.update(overrides)
    return req


def wait_done(client: TestClient, sweep_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"/sweep/{sweep_id}/status").json()
        if status["state"] in ("done", "failed", "cancelled"):
            return status
        time.sleep(0.05)
    pytest.fail(f"Sweep {sweep_id} did not finish within {timeout}s (last: {status})")


def test_sweep_unknown_track_returns_404(client):
    resp = client.post("/sweep", json=_base_request("does-not-exist"))
    assert resp.status_code == 404


def test_sweep_unknown_param_returns_422(client, track_id):
    req = _base_request(track_id, params=[{"name": "nope", "min": 0, "max": 1, "steps": 2}])
    assert client.post("/sweep", json=req).status_code == 422


def test_sweep_min_not_below_max_returns_422(client, track_id):
    req = _base_request(track_id, params=[{"name": "mass_kg", "min": 800, "max": 600, "steps": 2}])
    assert client.post("/sweep", json=req).status_code == 422


def test_sweep_over_cap_returns_422(client, track_id):
    params = [
        {"name": "mass_kg", "min": 600, "max": 800, "steps": 30},
        {"name": "p_max_kw", "min": 200, "max": 400, "steps": 30},
    ]
    resp = client.post("/sweep", json=_base_request(track_id, params=params))
    assert resp.status_code == 422
    assert "cap" in resp.json()["detail"]


def test_transient_sweep_unsupported_param_returns_422(client, track_id):
    req = _base_request(
        track_id,
        solver="transient",
        params=[{"name": "mu_x", "min": 1.2, "max": 1.8, "steps": 2}],
    )
    resp = client.post("/sweep", json=req)
    assert resp.status_code == 422
    assert "mu_x" in resp.json()["detail"]


def test_grid_sweep_runs_to_completion(client, track_id):
    params = [
        {"name": "mass_kg", "min": 600, "max": 800, "steps": 3},
        {"name": "p_max_kw", "min": 200, "max": 400, "steps": 4},
    ]
    resp = client.post("/sweep", json=_base_request(track_id, params=params))
    assert resp.status_code == 202
    start = resp.json()
    assert start["total_runs"] == 13  # 3*4 grid + baseline

    status = wait_done(client, start["sweep_id"])
    assert status["state"] == "done"
    assert status["completed"] == status["total"] == 13

    result = client.get(f"/sweep/{start['sweep_id']}").json()
    runs = result["runs"]
    assert [r["index"] for r in runs] == list(range(13))
    assert runs[0]["param_values"] == {} and runs[0]["varied_param"] is None
    assert all(r["ok"] for r in runs)

    # Physics sanity: at fixed mass, more power -> faster (or equal) lap.
    by_mass: dict[float, list[tuple[float, float]]] = {}
    for r in runs[1:]:
        by_mass.setdefault(r["param_values"]["mass_kg"], []).append(
            (r["param_values"]["p_max_kw"], r["lap_time_s"])
        )
    for points in by_mass.values():
        points.sort()
        laps = [lap for _, lap in points]
        assert all(a >= b - 1e-6 for a, b in zip(laps, laps[1:]))

    agg = result["aggregates"]
    n = len(agg["s"])
    assert n > 0
    for key in ("x", "y", "v_min", "v_max", "v_spread", "v_baseline"):
        assert len(agg[key]) == n
    v_min, v_max = np.array(agg["v_min"]), np.array(agg["v_max"])
    assert np.all(v_min <= v_max + 1e-9)
    assert np.allclose(np.array(agg["v_spread"]), v_max - v_min)
    assert result["baseline_lap_time_s"] > 0


def test_oat_sweep_total_and_baseline_record(client, track_id):
    params = [
        {"name": "mass_kg", "min": 600, "max": 800, "steps": 5},
        {"name": "cd", "min": 0.5, "max": 1.5, "steps": 5},
    ]
    resp = client.post(
        "/sweep", json=_base_request(track_id, params=params, mode="one_at_a_time")
    )
    start = resp.json()
    assert start["total_runs"] == 11  # 5 + 5 + baseline

    assert wait_done(client, start["sweep_id"])["state"] == "done"
    result = client.get(f"/sweep/{start['sweep_id']}").json()

    assert result["runs"][0]["varied_param"] is None
    varied = [r["varied_param"] for r in result["runs"][1:]]
    assert varied.count("mass_kg") == 5 and varied.count("cd") == 5
    for r in result["runs"][1:]:
        assert set(r["param_values"]) == {r["varied_param"]}


def test_status_unknown_sweep_returns_404(client):
    assert client.get("/sweep/000000000000/status").status_code == 404


def test_persistence_round_trip(client, track_id):
    resp = client.post("/sweep", json=_base_request(track_id))
    sweep_id = resp.json()["sweep_id"]
    assert wait_done(client, sweep_id)["state"] == "done"

    in_memory = client.get(f"/sweep/{sweep_id}").json()

    listed = client.get("/sweep/saved").json()
    assert any(info["sweep_id"] == sweep_id for info in listed)
    info = next(i for i in listed if i["sweep_id"] == sweep_id)
    assert info["track_name"] == "sweep_circle"
    assert info["param_names"] == ["mass_kg"]
    assert info["best_lap_time_s"] is not None

    saved = client.get(f"/sweep/saved/{sweep_id}").json()
    assert saved == in_memory

    assert client.delete(f"/sweep/saved/{sweep_id}").status_code == 204
    assert client.get(f"/sweep/saved/{sweep_id}").status_code == 404
