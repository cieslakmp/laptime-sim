"""Velocity vs arc-length profile plot."""

from __future__ import annotations


def plot_velocity_profile(result, ax=None, label=None, figsize=(12, 4)):
    """Plot velocity profile vs arc-length.

    Parameters
    ----------
    result : LapResult
    ax : matplotlib Axes, optional
    label : str, optional — legend label
    """
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=figsize)

    v_kmh = result.v * 3.6
    ax.plot(result.s, v_kmh, label=label or f"{result.lap_time_s:.2f} s")
    ax.set_xlabel("Arc-length [m]")
    ax.set_ylabel("Speed [km/h]")
    ax.set_title("Velocity Profile")
    ax.grid(True, alpha=0.3)
    if label:
        ax.legend()
    return ax
