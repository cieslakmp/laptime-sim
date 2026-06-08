"""Track map coloured by velocity."""

from __future__ import annotations

import numpy as np


def plot_track_map(track, result=None, ax=None, figsize=(10, 8)):
    """Plot 2-D track map, optionally coloured by velocity.

    Parameters
    ----------
    track : Track
    result : LapResult, optional
    ax : matplotlib Axes, optional
    """
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    if ax is None:
        _, ax = plt.subplots(figsize=figsize)

    if result is not None:
        # Colour line segments by velocity
        points = np.array([track.x, track.y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        v_interp = np.interp(track.s, result.s, result.v)
        lc = LineCollection(segments, cmap="plasma", linewidth=2)
        lc.set_array(v_interp)
        ax.add_collection(lc)
        plt.colorbar(lc, ax=ax, label="Speed [m/s]")
    else:
        ax.plot(track.x, track.y, "b-", linewidth=2)

    # Draw start/finish marker
    ax.plot(track.x[0], track.y[0], "go", markersize=10, label="S/F", zorder=5)

    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(track.name or "Track Map")
    ax.legend()
    return ax
