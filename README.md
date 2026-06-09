# Lap Time Simulator

A physics-based lap time simulator and racing line optimiser with an interactive web dashboard. Upload any track geometry, tune vehicle parameters in real time, and compare four levels of modelling — from a millisecond QSS pass, through a full optimal control problem solved with CasADi + IPOPT, to a transient 7DOF time-domain simulation with a Pacejka Magic Formula tyre model.

![Dashboard](docs/img/dashboard.png)

---

## Features

- **Quasi-Steady-State (QSS) simulation** — O(N) forward/backward pass, solves a full lap in milliseconds
- **Minimum-curvature racing line** — geometric optimiser that finds the smoothest path through the track width
- **Full optimal control (OCP)** — minimum-time direct multiple shooting (CasADi + IPOPT) in curvilinear coordinates; simultaneous optimisation of racing line and velocity profile
- **Transient 7DOF + Pacejka simulation** — time-domain forward integration of a chassis with yaw, roll, pitch and heave dynamics, four wheel-spin DOF, dynamic load transfer and a simplified Pacejka Magic Formula tyre (camber thrust, self-aligning moment, combined slip). A path-following driver tracks the QSS reference, exposing transient behaviour the quasi-steady solvers cannot
- **Point-mass vehicle model** — traction ellipse with speed-dependent downforce and drag, power-limited acceleration, parametric for any category (kart, Formula, GT, …)
- **Validation & analysis tooling** — solver comparison, GGV envelope extraction, and load-transfer / yaw / roll trace plots
- **Interactive web dashboard** — dark-themed React 18 UI; adjust vehicle sliders and overlay all methods at once
- **REST API** — upload tracks, run simulations, and trigger optimisation/simulation programmatically via FastAPI
- **CSV and GPX track loading** — bring your own circuit data; GPX files are automatically geo-referenced

---

## Results at a glance

| Method | Lap time | vs QSS |
|---|---|---|
| QSS (centreline) | 50.610 s | — |
| Racing line (min-curvature) | 44.837 s | −5.773 s |
| **Full OCP** | **41.496 s** | **−9.114 s** |

*Example circuit, ~2.8 km. OCP solves in ~3 s warm-started from QSS.*

---

## Screenshots

### Dashboard

The main layout: OCP optimal path overlaid on the track map (viridis), all three velocity profiles, and the G-G diagram — updated live as vehicle sliders change.

![Dashboard](docs/img/dashboard.png)

### Three-method track map comparison

Left to right: QSS on the centreline, min-curvature racing line, and full OCP optimal path — all coloured by speed.

![Three-way comparison](docs/img/three_way_comparison.png)

### Velocity profiles overlaid

The cyan shaded region shows where OCP exceeds QSS speed. The OCP carries more speed through every corner because it simultaneously optimises the line and the throttle/brake profile.

![Velocity comparison](docs/img/velocity_comparison.png)

### OCP lateral offset and heading error

The OCP state trajectory: lateral offset `n(s)` relative to the centreline (bounded by track walls), and heading error `ψ(s)` relative to the track tangent. These are the state variables that the QSS solver cannot access.

![OCP lateral profile](docs/img/ocp_lateral_profile.png)

### G-G diagram

All three methods side by side. The OCP solution (right) fills the friction envelope more completely, particularly in the longitudinal direction, because it can simultaneously choose the corner entry/exit geometry.

![G-G comparison](docs/img/gg_comparison.png)

---

## Quick Start

### Option 1 — Docker Compose (recommended)

```bash
git clone https://github.com/cieslakmp/laptime-sim.git
cd laptime-sim
docker-compose up
```

Open **http://localhost:5173** for the web dashboard.  
API docs at **http://localhost:8000/docs**.

### Option 2 — Local development

**Backend**

```bash
# Python 3.11+ required
pip install -e ".[dev]"         # core + dev tools
pip install -e ".[ocp]"         # CasADi for the OCP solver (optional)
uvicorn laptime.api.main:app --reload
# → http://localhost:8000
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## Using the Dashboard

1. **Upload a track** — click *Upload Track (CSV/GPX)* and select a file. The track map renders immediately.
2. **Adjust vehicle parameters** — sliders for mass, power, tyre friction, downforce, and drag.
3. **QSS Simulate** — millisecond lap time on the centreline. Good starting point.
4. **Racing Line** — minimum-curvature optimiser (~20–30 s). Overlays optimised path on the track map.
5. **Full OCP** — CasADi + IPOPT optimal control (~1–3 min). Returns the globally optimal velocity and path profile. The sidebar shows all lap times and the best delta vs QSS.
6. **Transient 7DOF** — time-domain Pacejka simulation (~30–60 s) that drives the racing line with a path-following controller. Overlays the transient velocity profile and reports whether the lap stayed on track.

---

## Track File Formats

### CSV

```
# columns: x_m, y_m[, width_left_m, width_right_m, banking_rad]
0.0,   0.0,   7.0, 7.0, 0.0
100.0, 5.0,   7.0, 7.0, 0.0
...
```

`width_left_m`, `width_right_m`, `banking_rad` are optional (defaults: 5 m, 5 m, 0 rad). The loader fits a periodic cubic spline and resamples at 2 m resolution.

### GPX

Standard GPS exchange format. First track segment used. Lat/lon converted via transverse Mercator projection centred on the track centroid.

### Bundled examples

| File | Description |
|---|---|
| `data/tracks/example_oval.csv` | Oval circuit, ~1.9 km |
| `data/tracks/example_circuit.csv` | Mixed circuit with hairpins, ~2.8 km |

---

## Vehicle Parameters

| Parameter | Default | Description |
|---|---|---|
| `mass_kg` | 700 | Total mass [kg] |
| `p_max_kw` | 400 | Peak engine power [kW] |
| `f_brake_max_n` | 20 000 | Peak brake force [N] |
| `mu_y` | 1.8 | Peak lateral tyre friction |
| `mu_x` | 1.6 | Peak longitudinal tyre friction |
| `cl` | 2.5 | Downforce coefficient Cl·A [m²] |
| `cd` | 0.9 | Drag coefficient Cd·A [m²] |
| `v_max_ms` | 83 | Top speed cap [m/s] |

TOML configs are also supported — see `data/vehicles/`.

---

## REST API

### Upload a track

```bash
curl -X POST http://localhost:8000/tracks \
     -F "file=@data/tracks/example_circuit.csv"
# → {"track_id": "a3f9c2b1d4e8", "length_m": 2783.4, ...}
```

### QSS simulation

```bash
curl -X POST http://localhost:8000/simulate \
     -H "Content-Type: application/json" \
     -d '{"track_id": "a3f9c2b1d4e8", "vehicle": {"mass_kg": 700, "p_max_kw": 400, "mu_y": 1.8, "cl": 2.5, "cd": 0.9, "v_max_ms": 83}}'
# → {"lap_time_s": 50.61, ...}
```

### Min-curvature racing line

```bash
curl -X POST http://localhost:8000/optimize \
     -H "Content-Type: application/json" \
     -d '{"track_id": "a3f9c2b1d4e8", "vehicle": {...}}'
# → {"baseline_lap_time_s": 50.61, "optimized_lap_time_s": 44.84, "delta_s": -5.77, ...}
```

### Full OCP

```bash
curl -X POST http://localhost:8000/ocp \
     -H "Content-Type: application/json" \
     -d '{"track_id": "a3f9c2b1d4e8", "vehicle": {...}, "n_intervals": 150}'
# → {"baseline_lap_time_s": 50.61, "optimized_lap_time_s": 41.50,
#    "delta_s": -9.11,
#    "optimized": {"n_m": [...], "psi_rad": [...], "x_path": [...], "y_path": [...],
#                  "solve_time_s": 3.1, "solver_status": "optimal", ...}}
```

### Transient 7DOF simulation

```bash
curl -X POST http://localhost:8000/transient \
     -H "Content-Type: application/json" \
     -d '{"track_id": "a3f9c2b1d4e8", "use_racing_line": true,
          "vehicle": {"chassis": {"mass_kg": 1300}, "drivetrain": {"p_max_kw": 350}}}'
# → {"qss_lap_time_s": 62.25, "transient_lap_time_s": 75.71, "delta_s": 13.46,
#    "completed": true,
#    "transient": {"x_path": [...], "y_path": [...], "v_ms": [...],
#                  "max_lateral_dev_m": 1.12, "aborted": false, ...}}
```

The `vehicle` field accepts the nested `DynamicVehicleParams`; any omitted sub-fields fall back to defaults.

---

## Python Library

```python
from laptime.track.loader import load_csv
from laptime.vehicle.params import PointMassParams
from laptime.vehicle.point_mass import PointMassVehicle
from laptime.sim.qss import QSSSolver
from laptime.optimizer.ocp import OCPSolver

track   = load_csv("data/tracks/example_circuit.csv")
params  = PointMassParams(mass_kg=700, p_max_kw=400, mu_y=1.8, cl=2.5, cd=0.9)

# QSS baseline
qss_result = QSSSolver(track, PointMassVehicle(params)).solve()
print(f"QSS: {qss_result.lap_time_s:.3f} s")     # → 50.610 s

# Full OCP
ocp_result = OCPSolver(track, params, N=150).solve()
print(f"OCP: {ocp_result.lap_time_s:.3f} s")     # → 41.496 s
print(f"  Solve time: {ocp_result.solve_time_s:.1f} s")
print(f"  Status: {ocp_result.solver_status}")

# OCP state trajectory
print(f"  n range: [{ocp_result.n.min():.2f}, {ocp_result.n.max():.2f}] m")
print(f"  |ψ| max: {abs(ocp_result.psi).max():.3f} rad")
```

---

## OCP Formulation

The optimal control problem is posed in **curvilinear track coordinates** with arc-length `s` as the independent variable:

**State** `x = [n, ψ, v]`
- `n` — lateral offset from centreline [m]
- `ψ` — heading error relative to track tangent [rad]
- `v` — speed [m/s]

**Controls** `u = [ax, ay]` — longitudinal and lateral acceleration [m/s²]

**Objective** — minimise total lap time:

```
T = ∫₀ᴸ (1 − n·κ(s)) / (v·cos ψ) ds
```

**Dynamics** (exact curvilinear equations, `s`-domain):

```
dn/ds   =  tan(ψ) · (1 − n·κ)
dψ/ds   =  ay·(1 − n·κ) / (v²·cos ψ)  −  κ
dv/ds   =  ax·(1 − n·κ) / (v·cos ψ)
```

**Constraints:**

| Constraint | Expression |
|---|---|
| Traction ellipse | `(ax/ax_tyre)² + (ay/ay_lat)² ≤ 1` |
| Engine power | `ax ≤ P_max/(m·v) − F_drag/m` |
| Brake system | `ax ≥ −(F_brake_max/m + F_drag/m)` |
| Track boundary | `−w_right(s) ≤ n ≤ w_left(s)` |
| Speed floor | `v ≥ 1 m/s` |
| Periodicity | `n[L] = n[0],  ψ[L] = ψ[0],  v[L] = v[0]` |

Discretised with **direct multiple shooting** (N = 150 intervals, RK4 integration per interval). Solved with IPOPT, warm-started from the QSS velocity profile on the centreline.

---

## Transient 7DOF + Pacejka Simulation

Where QSS and OCP are *quasi-steady* (they assume the vehicle is always in instantaneous equilibrium), the transient solver integrates the vehicle's equations of motion **in the time domain**, revealing yaw response, weight-transfer settling and individual-wheel saturation.

**Model** — a rigid sprung mass on four corner springs/dampers and anti-roll bars:

- **Chassis** — longitudinal, lateral and yaw motion
- **Suspension DOF** — roll, pitch and heave, so load transfer is *dynamic* (spring/damper), not algebraic
- **Wheels** — four wheel-spin DOF driven by engine/brake torque and tyre reaction
- **Tyres** — a simplified **Pacejka Magic Formula**: load-sensitive peak, lateral relaxation length (as ODE states), camber thrust from body roll, a self-aligning moment via the pneumatic trail, and Magic Formula cosine combined-slip weighting

A **path-following driver** (pure-pursuit + Stanley steering, PI speed control with braking preview and traction budgeting) tracks the QSS racing line and velocity profile, so the transient lap time is directly comparable to the quasi-steady baseline — typically a little slower, as a real driver tracking the line would be.

![Transient 7DOF overlay](docs/img/transient_dashboard.png)

The transient velocity profile overlaid on the quasi-steady baselines — the time-domain car carries slightly less speed through the corners as the driver tracks the line:

![Transient velocity overlay](docs/img/transient_velocity_overlay.png)

```python
from laptime.track.loader import load_csv
from laptime.optimizer.racing_line import MinCurvatureOptimizer
from laptime.sim.qss import QSSSolver
from laptime.sim.transient import TransientSolver
from laptime.vehicle.dynamic_vehicle import DynamicVehicle
from laptime.vehicle.dynamics_params import DynamicVehicleParams

track   = load_csv("data/tracks/example_circuit.csv")
vehicle = DynamicVehicle(DynamicVehicleParams.from_toml("data/vehicles/gt_car_dynamic.toml"))

opt  = MinCurvatureOptimizer(track)
line = opt.apply_to_track(opt.optimize())          # the reference racing line
qss  = QSSSolver(line, vehicle, ds=2.0).solve()    # reference speed target

result = TransientSolver(line, vehicle, qss, racing_line=line).solve()
print(f"Transient lap: {result.lap_time_s:.3f} s  "
      f"(completed={result.metadata['completed']}, "
      f"max dev {result.metadata['max_lateral_dev_m']:.2f} m)")
```

The full 7DOF parameter set (chassis inertias, suspension rates, drivetrain, tyre coefficients, driver gains) is configured via nested TOML — see `data/vehicles/gt_car_dynamic.toml`.

### Validation & analysis

`laptime/analysis.py` and `scripts/analysis_demo.py` provide tooling to compare the solvers and inspect the transient dynamics:

```bash
python scripts/analysis_demo.py data/tracks/example_circuit.csv analysis_output/
```

This renders a QSS-vs-transient velocity profile, the transient lap's **GG cloud against the steady-state GGV envelope**, and a chassis-response time history (per-wheel load transfer, yaw rate, roll).

---

## Architecture

```
laptime-sim/
├── laptime/
│   ├── track/
│   │   ├── geometry.py        Cubic spline, arc-length, analytical curvature
│   │   ├── track.py           Track dataclass — everything in s-domain
│   │   └── loader.py          CSV / GPX → Track
│   ├── vehicle/
│   │   ├── base.py            VehicleModel ABC
│   │   ├── point_mass.py      Traction ellipse + aero + powertrain
│   │   ├── tyre_pacejka.py    Simplified Pacejka Magic Formula tyre
│   │   ├── suspension.py      Roll/pitch/heave dynamic load transfer
│   │   ├── dynamic_vehicle.py 7DOF chassis derivatives + steady-state shim
│   │   └── dynamics_params.py Nested 7DOF parameter set (TOML)
│   ├── sim/
│   │   ├── qss.py             QSS forward/backward solver
│   │   ├── driver.py          Path-following driver model
│   │   └── transient.py       Transient 7DOF time-domain solver
│   ├── optimizer/
│   │   ├── racing_line.py     Min-curvature SLSQP
│   │   └── ocp.py             Full OCP — CasADi + IPOPT
│   ├── analysis.py            GGV envelope, solver comparison, traces
│   ├── viz/                   Matplotlib helpers
│   └── api/
│       ├── main.py            FastAPI app
│       └── routes/
│           ├── tracks.py      POST /tracks, GET /tracks/{id}
│           ├── simulate.py    POST /simulate
│           ├── optimize.py    POST /optimize
│           ├── ocp.py         POST /ocp
│           └── transient.py   POST /transient
├── frontend/                  React 18 + TypeScript
│   └── src/
│       ├── App.tsx
│       ├── api/client.ts
│       └── components/
│           ├── TrackMap.tsx       OCP path overlay
│           ├── VelocityProfile.tsx
│           ├── GGDiagram.tsx
│           └── VehicleForm.tsx
├── scripts/                   analysis_demo.py — comparison & trace figures
├── tests/                     45 pytest cases
├── data/                      Example tracks + vehicle configs
└── docker-compose.yml
```

### Key design decisions

**Arc-length as the universal coordinate** — all modules share the `s`-axis. This makes the OCP dynamics natural and keeps the QSS, racing line, and OCP results directly comparable.

**`VehicleModel` ABC** — the QSS solver only calls `lateral_limit(v)` and `longitudinal_limits(v, ay)`. The OCP replicates the same physics symbolically in CasADi. The transient `DynamicVehicle` *also* implements this ABC (exposing a steady-state grip estimate of its own 7DOF physics), so a single parameter set drives both the QSS reference and the time-domain simulation.

**QSS warm-start for the OCP** — the OCP is warm-started from the QSS velocity profile (`n=0`, `ψ=0`, `v=v_QSS`). This typically achieves convergence in one IPOPT pass.

---

## Development

```bash
pytest                          # 45 tests (OCP tests need the optional [ocp] extra)
pytest tests/sim/test_transient.py   # transient 7DOF tests only
ruff check laptime/
mypy laptime/
```

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| 1 — Core library | ✅ Done | Track geometry, point-mass vehicle, QSS solver |
| 2 — REST API | ✅ Done | FastAPI: tracks, simulate, optimise endpoints |
| 3 — Web dashboard | ✅ Done | React 18 + Plotly dark UI |
| 4 — Full OCP | ✅ Done | CasADi + IPOPT direct multiple shooting |
| 5 — Transient 7DOF + Pacejka | ✅ Done | Time-domain simulation with Magic Formula tyres and a path-following driver |
| 6 — Validation & analysis | ✅ Done | Solver comparison, GGV envelope, load-transfer/yaw/roll traces |
| 7 — Parameter sweep | Planned | Vectorised setup sensitivity / tornado plots |

---

## License

MIT
