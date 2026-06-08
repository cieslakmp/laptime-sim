"""Full minimum-time OCP using direct multiple shooting (CasADi + IPOPT).

Formulation
-----------
State   x = [n, psi, v]
  n   : lateral offset from centreline [m]  (+ = left)
  psi : heading error relative to track tangent [rad]
  v   : speed [m/s]

Controls u = [ax, ay]
  ax : longitudinal acceleration [m/s²]
  ay : lateral acceleration [m/s²]

Independent variable: arc-length s ∈ [0, L]

Dynamics (s-domain, exact curvilinear equations):
  dn/ds   =  tan(psi) * (1 - n·κ(s))
  dpsi/ds =  ay·(1 - n·κ(s)) / (v²·cos(psi))  −  κ(s)
  dv/ds   =  ax·(1 - n·κ(s)) / (v·cos(psi))

Objective: minimise T = ∫₀ᴸ (1 - n·κ(s)) / (v·cos(psi)) ds

Constraints:
  (ax/ax_tyre)² + (ay/ay_lat)²  ≤ 1          traction ellipse
  ax  ≤  P_max/(m·v) − F_drag/m              engine power
  ax  ≥ −(F_brake_max/m + F_drag/m)          braking system
  −w_right(s) ≤ n ≤ w_left(s)                track boundary
  v ≥ V_MIN
  Periodicity for closed circuits: x[N] = x[0]
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from laptime.sim.result import LapResult
from laptime.sim.qss import QSSSolver
from laptime.track.track import Track
from laptime.vehicle.params import PointMassParams
from laptime.vehicle.point_mass import PointMassVehicle

# Physical constants
G = 9.81       # m/s²
V_MIN = 1.0    # minimum speed floor [m/s]
PSI_MAX = 0.5  # max heading error |psi| [rad] ~28 degrees


@dataclass
class OCPResult:
    """Extended result from the OCP solver."""

    lap_time_s: float
    s: np.ndarray       # arc-length stations [m]
    v: np.ndarray       # speed [m/s]
    ax: np.ndarray      # longitudinal acceleration [m/s²]
    ay: np.ndarray      # lateral acceleration [m/s²]
    n: np.ndarray       # lateral offset from centreline [m]
    psi: np.ndarray     # heading error [rad]
    x_path: np.ndarray  # optimal path x [m]
    y_path: np.ndarray  # optimal path y [m]
    solve_time_s: float = 0.0
    solver_status: str = ""
    metadata: dict = field(default_factory=dict)

    def to_lap_result(self) -> LapResult:
        return LapResult(
            lap_time_s=self.lap_time_s,
            s=self.s,
            v=self.v,
            ax=self.ax,
            ay=self.ay,
            metadata={
                "n": self.n.tolist(),
                "psi": self.psi.tolist(),
                "x_path": self.x_path.tolist(),
                "y_path": self.y_path.tolist(),
                "solve_time_s": self.solve_time_s,
                "solver_status": self.solver_status,
                **self.metadata,
            },
        )


class OCPSolver:
    """Minimum-lap-time OCP solver using CasADi direct multiple shooting.

    Parameters
    ----------
    track : Track
        Arc-length parameterised circuit.
    params : PointMassParams
        Vehicle configuration.
    N : int
        Number of shooting intervals. Higher → more accurate but slower.
        Default 150 is a good balance (~1–3 min solve on modern hardware).
    """

    def __init__(
        self,
        track: Track,
        params: PointMassParams,
        N: int = 150,
    ) -> None:
        try:
            import casadi as ca  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "CasADi is required for the OCP solver. "
                "Install with: pip install laptime-sim[ocp]"
            ) from e

        self._track = track
        self._params = params
        self._N = N

        # Build OCP nodes: N+1 nodes, N intervals
        L = track.length
        self._s_ocp = np.linspace(0.0, L, N + 1)
        self._ds = L / N

        # Build periodic-extension interpolants for track data
        self._kappa_fn = self._make_interpolant("kappa", track.s, track.kappa)
        self._wl_fn = self._make_interpolant("wl", track.s, track.width_left)
        self._wr_fn = self._make_interpolant("wr", track.s, track.width_right)
        self._bank_fn = self._make_interpolant("bank", track.s, track.banking)
        self._x_fn = self._make_interpolant("cx", track.s, track.x)
        self._y_fn = self._make_interpolant("cy", track.s, track.y)
        self._hdg_fn = self._make_interpolant("hdg", track.s, track.heading)

    # ------------------------------------------------------------------
    # Interpolant helpers

    def _make_interpolant(
        self, name: str, s: np.ndarray, values: np.ndarray
    ):
        """Create a CasADi linear interpolant with periodic extension."""
        import casadi as ca

        L = self._track.length
        # Extend by one point for s = L
        ds_last = s[-1] - s[-2] if len(s) > 1 else 1.0
        s_ext = np.append(s, s[-1] + ds_last)
        if self._track.is_closed:
            v_ext = np.append(values, values[0])
        else:
            v_ext = np.append(values, values[-1])
        return ca.interpolant(name, "linear", [s_ext], v_ext)

    # ------------------------------------------------------------------
    # Dynamics

    def _ode(self, x, u, s_val):
        """Right-hand side of the curvilinear ODE, ds as independent variable."""
        import casadi as ca

        n_s, psi_s, v_s = x[0], x[1], x[2]
        ax_s, ay_s = u[0], u[1]

        kap = self._kappa_fn(s_val)
        sigma = 1.0 - n_s * kap          # (1 - n·κ)
        cos_psi = ca.cos(psi_s)
        sin_psi = ca.sin(psi_s)

        dn_ds = sin_psi * sigma / (cos_psi + 1e-9)
        dpsi_ds = ay_s * sigma / (v_s**2 * (cos_psi + 1e-9)) - kap
        dv_ds = ax_s * sigma / (v_s * (cos_psi + 1e-9))

        return ca.vertcat(dn_ds, dpsi_ds, dv_ds)

    def _rk4(self, x, u, s, h):
        """4th-order Runge-Kutta step (s as independent variable)."""
        k1 = self._ode(x, u, s)
        k2 = self._ode(x + 0.5 * h * k1, u, s + 0.5 * h)
        k3 = self._ode(x + 0.5 * h * k2, u, s + 0.5 * h)
        k4 = self._ode(x + h * k3, u, s + h)
        return x + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

    # ------------------------------------------------------------------
    # Warm start from QSS

    def _warm_start(self) -> tuple[np.ndarray, np.ndarray]:
        """Run QSS and interpolate its output onto the OCP grid."""
        vehicle = PointMassVehicle(self._params)
        qss = QSSSolver(self._track, vehicle, ds=self._track.length / (4 * self._N))
        res = qss.solve()

        s_ocp = self._s_ocp
        v0 = np.interp(s_ocp, res.s, res.v)
        v0 = np.maximum(v0, V_MIN)

        # State initial guess: centreline, aligned with track, QSS speed
        x0 = np.zeros((3, self._N + 1))
        x0[0, :] = 0.0           # n = 0 (centreline)
        x0[1, :] = 0.0           # psi = 0 (aligned)
        x0[2, :] = v0

        # Control initial guess: ax from QSS, ay from centripetal
        ax0 = np.interp(s_ocp[:-1], res.s, res.ax)
        kappa_ocp = np.array([float(self._kappa_fn(s)) for s in s_ocp[:-1]])
        v_ctrl = v0[:-1]
        ay0 = v_ctrl**2 * kappa_ocp

        u0 = np.vstack([ax0, ay0])
        return x0, u0

    # ------------------------------------------------------------------
    # Main solve

    def solve(self, verbose: bool = False) -> OCPResult:
        """Solve the minimum-time OCP and return an OCPResult."""
        import casadi as ca

        p = self._params
        N = self._N
        s_ocp = self._s_ocp
        h = self._ds

        t_start = time.perf_counter()

        opti = ca.Opti()

        # ---- Decision variables ----
        X = opti.variable(3, N + 1)   # [n; psi; v] at N+1 nodes
        U = opti.variable(2, N)       # [ax; ay] at N intervals

        n_var = X[0, :]
        psi_var = X[1, :]
        v_var = X[2, :]
        ax_var = U[0, :]
        ay_var = U[1, :]

        # ---- Objective: minimise lap time ----
        lap_time_expr = 0
        for k in range(N):
            s_k = float(s_ocp[k])
            kap_k = self._kappa_fn(s_k)
            sigma_k = 1.0 - n_var[k] * kap_k
            dt_ds_k = sigma_k / (v_var[k] * (ca.cos(psi_var[k]) + 1e-9))
            lap_time_expr = lap_time_expr + dt_ds_k * h
        opti.minimize(lap_time_expr)

        # ---- Shooting constraints ----
        for k in range(N):
            s_k = float(s_ocp[k])
            x_k = X[:, k]
            u_k = U[:, k]
            x_next = self._rk4(x_k, u_k, s_k, h)
            opti.subject_to(X[:, k + 1] == x_next)

        # ---- Physics constraints ----
        for k in range(N):
            s_k = float(s_ocp[k])
            v_k = v_var[k]
            ax_k = ax_var[k]
            ay_k = ay_var[k]
            bank_k = self._bank_fn(s_k)

            # Normal load (speed-dependent downforce)
            N_load = p.mass_kg * G * ca.cos(bank_k) + 0.5 * p.rho_air * p.cl * v_k**2
            ay_lim = p.mu_y * N_load / p.mass_kg + G * ca.sin(bank_k)
            ax_tyre = p.mu_x * N_load / p.mass_kg

            # Traction ellipse (combined tyre friction budget)
            opti.subject_to(
                (ax_k / (ax_tyre + 1e-3))**2 + (ay_k / (ay_lim + 1e-3))**2 <= 1.0
            )

            # Engine power limit
            F_drag = 0.5 * p.rho_air * p.cd * v_k**2
            ax_eng = p.p_max_kw * 1000.0 / (p.mass_kg * v_k + 1e-3) - F_drag / p.mass_kg
            opti.subject_to(ax_k <= ax_eng)

            # Braking system limit (drag assists braking)
            ax_brake_lim = p.f_brake_max_n / p.mass_kg + F_drag / p.mass_kg
            opti.subject_to(ax_k >= -ax_brake_lim)

            # Track boundaries
            wl_k = self._wl_fn(s_k)
            wr_k = self._wr_fn(s_k)
            opti.subject_to(n_var[k] >= -wr_k)
            opti.subject_to(n_var[k] <= wl_k)

        # Apply boundary constraints to final node too
        wl_end = self._wl_fn(float(s_ocp[-1]))
        wr_end = self._wr_fn(float(s_ocp[-1]))
        opti.subject_to(n_var[-1] >= -wr_end)
        opti.subject_to(n_var[-1] <= wl_end)

        # ---- Speed bounds ----
        opti.subject_to(v_var >= V_MIN)
        opti.subject_to(v_var <= p.v_max_ms + 10.0)

        # ---- Heading error bounds (prevents solver divergence) ----
        opti.subject_to(opti.bounded(-PSI_MAX, psi_var, PSI_MAX))

        # ---- Periodicity for closed circuits ----
        if self._track.is_closed:
            opti.subject_to(n_var[-1] == n_var[0])
            opti.subject_to(psi_var[-1] == psi_var[0])
            opti.subject_to(v_var[-1] == v_var[0])

        # ---- Warm start ----
        x0, u0 = self._warm_start()
        opti.set_initial(X, x0)
        opti.set_initial(U, u0)

        # ---- IPOPT options ----
        solver_opts = {
            "ipopt.print_level": 5 if verbose else 0,
            "ipopt.max_iter": 1000,
            "ipopt.tol": 1e-6,
            "ipopt.acceptable_tol": 1e-4,
            "ipopt.acceptable_iter": 5,
            "ipopt.warm_start_init_point": "yes",
            "ipopt.mu_strategy": "adaptive",
            "print_time": 1 if verbose else 0,
        }
        opti.solver("ipopt", solver_opts)

        # ---- Solve ----
        status = "failed"
        try:
            sol = opti.solve()
            status = "optimal"
            n_sol = np.array(sol.value(n_var)).flatten()
            psi_sol = np.array(sol.value(psi_var)).flatten()
            v_sol = np.array(sol.value(v_var)).flatten()
            ax_sol_ctrl = np.array(sol.value(ax_var)).flatten()
            ay_sol_ctrl = np.array(sol.value(ay_var)).flatten()
            lap_time_val = float(sol.value(lap_time_expr))
        except Exception:
            # Return the best infeasible solution found
            status = "infeasible/max_iter"
            n_sol = np.array(opti.debug.value(n_var)).flatten()
            psi_sol = np.array(opti.debug.value(psi_var)).flatten()
            v_sol = np.maximum(np.array(opti.debug.value(v_var)).flatten(), V_MIN)
            ax_sol_ctrl = np.array(opti.debug.value(ax_var)).flatten()
            ay_sol_ctrl = np.array(opti.debug.value(ay_var)).flatten()
            # Recompute lap time from state trajectory
            kappa_ocp = np.array([float(self._kappa_fn(s)) for s in s_ocp[:-1]])
            sigma = 1.0 - n_sol[:-1] * kappa_ocp
            dt_ds = sigma / np.maximum(v_sol[:-1] * np.cos(psi_sol[:-1]), 1e-3)
            lap_time_val = float(np.sum(dt_ds * h))

        solve_time = time.perf_counter() - t_start

        # ---- Build output arrays ----
        s_out = s_ocp                          # N+1 nodes
        v_out = np.maximum(v_sol, V_MIN)
        # Compute ax/ay at nodes (pad control arrays from N → N+1)
        ax_out = np.append(ax_sol_ctrl, ax_sol_ctrl[-1])
        ay_out = np.append(ay_sol_ctrl, ay_sol_ctrl[-1])

        # Optimal path coordinates
        x_path = np.array([float(self._x_fn(s)) for s in s_out])
        y_path = np.array([float(self._y_fn(s)) for s in s_out])
        hdg = np.array([float(self._hdg_fn(s)) for s in s_out])
        # Normal vector pointing left of track heading
        nx_track = -np.sin(hdg)
        ny_track = np.cos(hdg)
        x_path += n_sol * nx_track
        y_path += n_sol * ny_track

        return OCPResult(
            lap_time_s=lap_time_val,
            s=s_out,
            v=v_out,
            ax=ax_out,
            ay=ay_out,
            n=n_sol,
            psi=psi_sol,
            x_path=x_path,
            y_path=y_path,
            solve_time_s=round(solve_time, 2),
            solver_status=status,
        )
