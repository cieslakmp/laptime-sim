"""Tests for the /transient API endpoint."""

import math

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
        name="api_circle", is_closed=True,
    )
    return save_track(track, "api_test_track")


def test_transient_unknown_track_returns_404(client):
    resp = client.post("/transient", json={"track_id": "does-not-exist"})
    assert resp.status_code == 404


def test_transient_endpoint_runs(client, track_id):
    resp = client.post(
        "/transient",
        json={"track_id": track_id, "use_racing_line": False, "dt": 3e-3},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["qss_lap_time_s"] > 0
    assert data["transient_lap_time_s"] > 0
    assert data["completed"] is True
    assert data["delta_s"] == pytest.approx(
        data["transient_lap_time_s"] - data["qss_lap_time_s"], abs=1e-3
    )

    tr = data["transient"]
    assert len(tr["x_path"]) == len(tr["y_path"]) == len(tr["v_ms"])
    assert tr["max_lateral_dev_m"] < 5.0
