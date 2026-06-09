"""Generate validation/analysis figures for the transient 7DOF simulator.

Runs QSS and the transient 7DOF solver on a track, extracts the GGV envelope, and
produces three figures:
  1. velocity profiles (QSS vs transient),
  2. the transient lap's GG cloud against the steady-state GGV envelope,
  3. load transfer, yaw rate and roll time histories from the transient lap.

Usage:
    python scripts/analysis_demo.py [track.csv] [output_dir]
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from laptime.analysis import (  # noqa: E402
    compare_solvers,
    ggv_envelope,
    transient_trace,
)
from laptime.track.loader import load_csv  # noqa: E402
from laptime.vehicle.dynamic_vehicle import DynamicVehicle  # noqa: E402
from laptime.vehicle.dynamics_params import DynamicVehicleParams  # noqa: E402


def main() -> None:
    track_path = sys.argv[1] if len(sys.argv) > 1 else "data/tracks/example_circuit.csv"
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "analysis_output")
    out_dir.mkdir(parents=True, exist_ok=True)

    track = load_csv(track_path)
    vehicle = DynamicVehicle(DynamicVehicleParams())

    print(f"Track: {track.name}  ({track.length:.0f} m)")
    cmp = compare_solvers(track, vehicle, use_racing_line=True, with_ocp=True)
    print(cmp.summary())

    line = cmp.reference_line
    qss = cmp.results["qss"]
    trans = cmp.results["transient_7dof"]

    # Rich per-step trace (true body accelerations, loads, yaw, roll).
    tr = transient_trace(track, vehicle, qss, line=line)

    # --- Figure 1: velocity profiles ---
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(qss.s, qss.v, label=f"QSS ({qss.lap_time_s:.2f} s)", color="#6366f1")
    ax.plot(trans.s, trans.v, label=f"Transient 7DOF ({trans.lap_time_s:.2f} s)",
            color="#65a30d")
    ax.set_xlabel("distance [m]")
    ax.set_ylabel("speed [m/s]")
    ax.set_title("Velocity profile: QSS vs transient 7DOF")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "velocity_profile.png", dpi=110)
    plt.close(fig)

    # --- Figure 2: GG cloud vs GGV envelope ---
    ggv = ggv_envelope(vehicle)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(tr.ay_ms2 / 9.81, tr.ax_ms2 / 9.81, s=4, alpha=0.3,
               color="#65a30d", label="transient lap")
    # Envelope at the median speed.
    i = len(ggv.speed_ms) // 2
    ay, axm, axn = ggv.ay_max_ms2[i] / 9.81, ggv.ax_max_ms2[i] / 9.81, ggv.ax_min_ms2[i] / 9.81
    th = np.linspace(0, 2 * np.pi, 200)
    ax.plot(ay * np.cos(th), np.where(np.sin(th) >= 0, axm, -axn) * np.sin(th),
            color="#6366f1", lw=1.5, label=f"GGV envelope @ {ggv.speed_ms[i]:.0f} m/s")
    ax.axhline(0, color="gray", lw=0.5)
    ax.axvline(0, color="gray", lw=0.5)
    ax.set_xlabel("lateral g")
    ax.set_ylabel("longitudinal g")
    ax.set_title("GG diagram: transient lap vs GGV envelope")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "gg_diagram.png", dpi=110)
    plt.close(fig)

    # --- Figure 3: load transfer / yaw / roll time history ---
    fig, axs = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    labels = ["FL", "FR", "RL", "RR"]
    for k, lab in enumerate(labels):
        axs[0].plot(tr.t, tr.fz[:, k] / 1000.0, lw=0.8, label=lab)
    axs[0].set_ylabel("wheel load [kN]")
    axs[0].set_title("Dynamic load transfer")
    axs[0].legend(ncol=4, fontsize=8)
    axs[0].grid(alpha=0.3)

    axs[1].plot(tr.t, tr.yaw_rate, color="#0891b2", lw=0.8)
    axs[1].set_ylabel("yaw rate [rad/s]")
    axs[1].grid(alpha=0.3)

    axs[2].plot(tr.t, tr.roll_deg, color="#b45309", lw=0.8)
    axs[2].set_ylabel("roll [deg]")
    axs[2].set_xlabel("time [s]")
    axs[2].grid(alpha=0.3)
    fig.suptitle("Transient chassis response")
    fig.tight_layout()
    fig.savefig(out_dir / "chassis_response.png", dpi=110)
    plt.close(fig)

    print(f"\nFigures written to {out_dir.resolve()}/")


if __name__ == "__main__":
    main()
