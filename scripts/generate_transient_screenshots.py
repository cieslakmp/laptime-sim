"""Render dashboard-style figures of the transient 7DOF overlay.

Produces dark-themed panels matching the web dashboard layout (track map coloured by
speed, velocity-profile overlay, G-G diagram) from the simulator data, for documentation.

Usage:
    python scripts/generate_transient_screenshots.py [track.csv] [docs/img]
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

from laptime.analysis import transient_trace  # noqa: E402
from laptime.optimizer.racing_line import MinCurvatureOptimizer  # noqa: E402
from laptime.sim.qss import QSSSolver  # noqa: E402
from laptime.sim.transient import TransientSolver  # noqa: E402
from laptime.track.loader import load_csv  # noqa: E402
from laptime.vehicle.dynamic_vehicle import DynamicVehicle  # noqa: E402
from laptime.vehicle.dynamics_params import DynamicVehicleParams  # noqa: E402

BG = "#0b0f1a"        # page background (gray-950-ish)
PANEL = "#111827"     # panel background (gray-900)
FG = "#e5e7eb"        # text
QSS_C = "#6366f1"     # indigo
RL_C = "#f97316"      # orange
TR_C = "#a3e635"      # lime


def _style(ax):
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_color("#374151")
    ax.tick_params(colors="#9ca3af", labelsize=8)
    ax.xaxis.label.set_color(FG)
    ax.yaxis.label.set_color(FG)
    ax.title.set_color(FG)
    ax.grid(alpha=0.15, color="#6b7280")


def _speed_line(ax, x, y, v, title):
    pts = np.array([x, y]).T.reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    lc = LineCollection(segs, cmap="viridis", linewidth=3.2)
    lc.set_array(v[:-1])
    ax.add_collection(lc)
    ax.set_xlim(x.min() - 30, x.max() + 30)
    ax.set_ylim(y.min() - 30, y.max() + 30)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=11)
    ax.set_xticks([])
    ax.set_yticks([])
    cbar = plt.colorbar(lc, ax=ax, fraction=0.04, pad=0.02)
    cbar.set_label("speed [m/s]", color=FG, fontsize=8)
    cbar.ax.yaxis.set_tick_params(color="#9ca3af", labelsize=7)
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="#9ca3af")


def main() -> None:
    track_path = sys.argv[1] if len(sys.argv) > 1 else "data/tracks/example_circuit.csv"
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/img")
    out_dir.mkdir(parents=True, exist_ok=True)

    track = load_csv(track_path)
    vehicle = DynamicVehicle(DynamicVehicleParams())

    qss_centre = QSSSolver(track, vehicle, ds=2.0).solve()
    opt = MinCurvatureOptimizer(track)
    line = opt.apply_to_track(opt.optimize())
    qss_line = QSSSolver(line, vehicle, ds=2.0).solve()
    trans = TransientSolver(line, vehicle, qss_line, racing_line=line, dt=2.5e-3).solve()
    tr = transient_trace(track, vehicle, qss_line, line=line)

    # Path coordinates of the followed (transient) line at the result stations.
    pts = line.at(np.asarray(trans.s))
    px = np.array([p.x for p in pts])
    py = np.array([p.y for p in pts])

    lap = {
        "QSS (centreline)": (qss_centre.lap_time_s, QSS_C),
        "Racing line": (qss_line.lap_time_s, RL_C),
        "Transient 7DOF": (trans.lap_time_s, TR_C),
    }

    # ---- Composite dashboard ----
    fig = plt.figure(figsize=(14, 7.5), facecolor=BG)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.25, 1], height_ratios=[1, 1],
                          hspace=0.22, wspace=0.16,
                          left=0.04, right=0.97, top=0.84, bottom=0.08)

    # Header with lap times
    fig.text(0.04, 0.95, "Lap Time Simulator — Transient 7DOF overlay",
             color=FG, fontsize=15, fontweight="bold")
    xcur = 0.04
    for label, (t, col) in lap.items():
        fig.text(xcur, 0.90, f"● {label}: {t:.2f} s", color=col, fontsize=10.5)
        xcur += 0.235

    ax_map = fig.add_subplot(gs[:, 0])
    _style(ax_map)
    _speed_line(ax_map, px, py, trans.v, "Track map — transient path (coloured by speed)")

    ax_v = fig.add_subplot(gs[0, 1])
    _style(ax_v)
    ax_v.plot(qss_centre.s, qss_centre.v, color=QSS_C, lw=1.4, label="QSS")
    ax_v.plot(qss_line.s, qss_line.v, color=RL_C, lw=1.4, label="Racing line")
    ax_v.plot(trans.s, trans.v, color=TR_C, lw=1.6, label="Transient 7DOF")
    ax_v.set_xlabel("distance [m]")
    ax_v.set_ylabel("speed [m/s]")
    ax_v.set_title("Velocity profile")
    leg = ax_v.legend(fontsize=8, facecolor=PANEL, edgecolor="#374151", labelcolor=FG)
    leg.get_frame().set_alpha(0.9)

    ax_gg = fig.add_subplot(gs[1, 1])
    _style(ax_gg)
    ax_gg.scatter(tr.ay_ms2 / 9.81, tr.ax_ms2 / 9.81, s=5, alpha=0.35, color=TR_C,
                  label="transient lap")
    ax_gg.axhline(0, color="#4b5563", lw=0.5)
    ax_gg.axvline(0, color="#4b5563", lw=0.5)
    ax_gg.set_xlabel("lateral g")
    ax_gg.set_ylabel("longitudinal g")
    ax_gg.set_title("G-G diagram")
    ax_gg.set_aspect("equal")

    out = out_dir / "transient_dashboard.png"
    fig.savefig(out, dpi=120, facecolor=BG)
    plt.close(fig)

    # ---- Standalone velocity overlay ----
    fig, ax = plt.subplots(figsize=(11, 4), facecolor=BG)
    _style(ax)
    ax.plot(qss_centre.s, qss_centre.v, color=QSS_C, lw=1.5,
            label=f"QSS  ({qss_centre.lap_time_s:.2f} s)")
    ax.plot(qss_line.s, qss_line.v, color=RL_C, lw=1.5,
            label=f"Racing line  ({qss_line.lap_time_s:.2f} s)")
    ax.plot(trans.s, trans.v, color=TR_C, lw=1.8,
            label=f"Transient 7DOF  ({trans.lap_time_s:.2f} s)")
    ax.set_xlabel("distance [m]")
    ax.set_ylabel("speed [m/s]")
    ax.set_title("Velocity profile — transient 7DOF vs quasi-steady")
    leg = ax.legend(fontsize=9, facecolor=PANEL, edgecolor="#374151", labelcolor=FG)
    leg.get_frame().set_alpha(0.9)
    fig.tight_layout()
    fig.savefig(out_dir / "transient_velocity_overlay.png", dpi=120, facecolor=BG)
    plt.close(fig)

    print(f"Wrote figures to {out_dir.resolve()}/")
    for label, (t, _) in lap.items():
        print(f"  {label:20s} {t:7.2f} s")


if __name__ == "__main__":
    main()
