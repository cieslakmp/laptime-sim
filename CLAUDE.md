# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Quasi-steady-state (and transient) lap time simulator: a Python physics/optimisation
library (`laptime/`) exposed through a FastAPI backend, with a React 18 + TypeScript +
Plotly dashboard (`frontend/`).

## Commands

### Backend (Python 3.11+)

```bash
pip install -e ".[dev]"            # core + dev tools (pytest, ruff, mypy, …)
pip install -e ".[ocp]"            # CasADi/IPOPT — REQUIRED for OCP solver & its tests

pytest                             # full suite
pytest tests/sim/test_transient.py # one file
pytest tests/sim/test_qss.py::test_name   # one test
ruff check laptime/                # lint (config in pyproject.toml: E,F,I,UP,B,SIM)
mypy laptime/                      # type check

uvicorn laptime.api.main:app --reload      # API on :8000  (docs at /docs)
```

OCP tests are skipped without the `[ocp]` extra installed.

### Frontend

```bash
cd frontend
npm install
npm run dev                        # Vite dev server on :5173
npm run build                      # tsc --noEmit + vite build (CI build gate)
```

`npm run build` runs `tsc`, so type errors fail the build — keep it green.

### Full stack (Docker Compose)

```bash
docker-compose up --build --force-recreate
```

The frontend's Vite proxy reaches the backend via `VITE_PROXY_TARGET`
(`http://backend:8000` inside Compose; defaults to `http://localhost:8000` for
local dev). After changing `docker-compose.yml` or pulling new commits, recreate
containers so they pick up env/code changes.

## Architecture

### Arc-length (`s`) is the universal coordinate

Every module operates on a shared arc-length axis. `track/geometry.py` fits a cubic
spline and re-parameterises to uniform `s`; `track/track.py` `Track` holds all geometry
as `s`-indexed arrays (`x, y, heading, kappa, width_left/right, banking`) with lazy
interpolation and a `resample(ds)` method. Closed circuits store **no duplicated
endpoint** (`s[-1] < length`); spline fitting re-closes the loop itself. Keeping
everything in `s` is what makes QSS, the racing line, and OCP results directly
comparable and the OCP dynamics natural.

### One vehicle interface drives three solvers

`vehicle/base.py` `VehicleModel` (ABC) exposes just `lateral_limit(v, kappa, banking)`
and `longitudinal_limits(v, ay, kappa, banking) -> (a_min, a_max)`. This is the seam
between physics and solvers:

- **`sim/qss.py` `QSSSolver`** — corner-speed limit → forward (accel) pass → backward
  (brake) pass → `min`; closed tracks iterate to convergence. Only ever calls the two
  ABC methods. O(N), milliseconds per lap.
- **`optimizer/ocp.py`** — replicates the *same* physics symbolically in CasADi for a
  full minimum-time OCP (direct multiple shooting, IPOPT), warm-started from the QSS
  profile (`n=0, ψ=0, v=v_QSS`).
- **`vehicle/dynamic_vehicle.py` `DynamicVehicle`** — the 7DOF time-domain model *also*
  implements `VehicleModel` (exposing a steady-state grip estimate of its own physics),
  so a single parameter set drives both the QSS reference and the transient sim.

When changing vehicle physics, remember the point-mass, CasADi (OCP), and 7DOF paths
may all need to stay consistent.

### Solver layers

- **QSS** (`sim/qss.py`) — quasi-steady baseline.
- **Racing line** (`optimizer/racing_line.py`) — min-curvature SLSQP within track width;
  produces a new `Track` the other solvers run on.
- **OCP** (`optimizer/ocp.py`) — globally optimal line + speed, curvilinear `s`-domain
  state `(n, ψ, v)`.
- **Transient** (`sim/transient.py` + `sim/driver.py`) — RK4 time-domain integration of
  the 7DOF `DynamicVehicle` while `PathTrackingDriver` (pure-pursuit/Stanley steer + PI
  speed control) follows the QSS racing line. The time-domain trajectory is mapped
  **back onto the `s`-grid** to produce a `LapResult`, so it drops into the same
  plotting/API consumers. All solvers return `sim/result.py` `LapResult`.

### Vehicle models

- `vehicle/point_mass.py` — traction ellipse + speed-dependent aero + power/brake limits;
  flat params in `vehicle/params.py`.
- 7DOF stack: `tyre_pacejka.py` (simplified Magic Formula: load-sensitive peak, lateral
  relaxation length as ODE states, camber thrust, self-aligning moment, combined-slip),
  `suspension.py` (roll/pitch/heave dynamic load transfer), `dynamic_vehicle.py` (chassis
  derivatives), configured by the **nested TOML** `vehicle/dynamics_params.py`
  `DynamicVehicleParams.from_toml(...)` (see `data/vehicles/gt_car_dynamic.toml`).

### API (`laptime/api/`)

`main.py` mounts routers under `/tracks`, `/simulate`, `/optimize`, `/ocp`, `/transient`,
`/sweep`. Tracks live in an **in-memory registry** (`api/store.py`) keyed by a content
hash `track_id`; every solve takes a `track_id` plus a vehicle param block
(`api/schemas.py`, Pydantic). The transient route accepts the nested
`DynamicVehicleParams`; the others take the flat point-mass `VehicleParamsRequest`.

Route-ordering gotcha in `routes/tracks.py`: literal paths (`/library`,
`/library/{circuit_id}`) are declared **before** `/{track_id}` so they aren't captured as
an id. Same pattern in `routes/sweep.py` (`/saved` before `/{sweep_id}`).

### Parameter sweep (`laptime/sweep/`)

`POST /sweep` expands parameter ranges (`spec.py`: `grid` = cartesian product, **last
param varies fastest** — the frontend heatmap reshapes row-major on this contract; or
`one_at_a_time` for tornado sensitivity) and runs them on a background thread driving a
per-sweep `ProcessPoolExecutor` (`runner.py`). The worker `run_sweep_point` is
**module-level and receives only plain dicts/numpy arrays** (Windows spawn: no pydantic
models or scipy interpolators cross the process boundary; `Track` is rebuilt from arrays
in the child). The racing line is vehicle-independent, so `solver="racing_line"`
optimises it once and runs QSS per point on the shared line. Progress is polled via
`GET /sweep/{id}/status`; on completion results aggregate onto a common s-grid (velocity
envelope min/max/spread, pooled G-G convex hull) and auto-save to `data/sweeps/{id}.json`
(`persistence.py`) as **standalone** files embedding display-line geometry — saved sweeps
list/load/render without the in-memory track registry surviving a restart. Env overrides:
`LAPTIME_SWEEP_EXECUTOR=thread` (used by tests to avoid spawn cost), `LAPTIME_SWEEPS_DIR`.

### Built-in F1 track library

`track/library.py` loads a bundled GeoJSON of 40 real circuits
(`data/tracks/f1/f1-circuits.geojson`, ODbL — see its `SOURCE.md`), projects lon/lat to
local metres via `pyproj`, and feeds the **same** spline pipeline as uploaded tracks.
`GET /tracks/library` lists circuits (metadata + preview outline); `POST
/tracks/library/{id}` registers one and returns a `track_id` exactly like an upload, so
all solvers work unchanged. Data files are located relative to the package
(`Path(__file__).parents[2] / "data"`), so they must ship alongside the code.

### Frontend ↔ backend

`frontend/src/api/client.ts` is the single API layer; `App.tsx` owns all state and
composes the Plotly components (`TrackMap`, `VelocityProfile`, `GGDiagram`,
`LapTimeChart`) plus `VehicleForm` and the modals (`TrackLibraryModal`,
`SweepConfigModal`, `SavedSweepsModal`). Sweep progress is polled with a react-query
`refetchInterval`. All requests are same-origin relative paths routed through the Vite
proxy (see `vite.config.ts`) — new API prefixes must be added there.

## Conventions

- Physics/units: SI throughout (m, m/s, rad, N, kg); curvature `kappa` is signed [1/m];
  speeds converted to km/h only at the view layer.
- Python: `from __future__ import annotations`, dataclasses for state, type hints; line
  length 100 (ruff).
- Tests live under `tests/<package>/` mirroring `laptime/<package>/`; `tests/conftest.py`
  holds shared fixtures.
