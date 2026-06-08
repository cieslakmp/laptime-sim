"""G-G diagram: longitudinal vs lateral acceleration scatter."""

from __future__ import annotations

import numpy as np


def plot_gg_diagram(result, vehicle=None, ax=None, figsize=(6, 6)):
    """Plot G-G diagram with optional envelope overlay.

    Parameters
    ----------
    result : LapResult
    vehicle : VehicleModel, optional — draws the traction ellipse
    ax : matplotlib Axes, optional
    """
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=figsize)

    g = 9.81
    sc = ax.scatter(
        result.ay / g,
        result.ax / g,
        c=result.v * 3.6,
        cmap="plasma",
        s=4,
        alpha=0.6,
    )
    plt.colorbar(sc, ax=ax, label="Speed [km/h]")

    if vehicle is not None:
        # Draw a representative envelope at median speed
        v_rep = float(np.median(result.v))
        ay_lim = vehicle.lateral_limit(v_rep) / g
        ax_min, ax_max = vehicle.longitudinal_limits(v_rep, 0.0)
        ax_min_g = ax_min / g
        ax_max_g = ax_max / g

        theta = np.linspace(0, 2 * np.pi, 200)
        # Approximate as ellipse (different radii for accel vs brake)
        ay_e = ay_lim * np.cos(theta)
        ax_e = np.where(
            np.sin(theta) >= 0,
            ax_max_g * np.sin(theta),
            ax_min_g * np.sin(theta),
        )
        ax.plot(ay_e, ax_e, "r--", linewidth=1.5, label=f"Envelope @ {v_rep * 3.6:.0f} km/h")
        ax.legend(fontsize=8)

    ax.axhline(0, color="k", linewidth=0.5)
    ax.axvline(0, color="k", linewidth=0.5)
    ax.set_xlabel("Lateral acceleration [g]")
    ax.set_ylabel("Longitudinal acceleration [g]")
    ax.set_title("G-G Diagram")
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    return ax
