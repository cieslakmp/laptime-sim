"""Simulation result dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class LapResult:
    """Output of a QSS (or forward integration) lap simulation."""

    lap_time_s: float
    s: np.ndarray          # arc-length stations [m]
    v: np.ndarray          # velocity profile [m/s]
    ax: np.ndarray         # longitudinal acceleration [m/s²]
    ay: np.ndarray         # lateral acceleration [m/s²]
    metadata: dict = field(default_factory=dict)

    def sector_time(self, s_start: float, s_end: float) -> float:
        """Return time [s] to travel from s_start to s_end."""
        mask = (self.s >= s_start) & (self.s <= s_end)
        if not mask.any():
            return 0.0
        s_sec = self.s[mask]
        v_sec = self.v[mask]
        ds = np.diff(s_sec)
        v_avg = 0.5 * (v_sec[:-1] + v_sec[1:])
        return float(np.sum(ds / np.maximum(v_avg, 1e-6)))

    def to_dict(self) -> dict:
        return {
            "lap_time_s": self.lap_time_s,
            "s": self.s.tolist(),
            "v": self.v.tolist(),
            "ax": self.ax.tolist(),
            "ay": self.ay.tolist(),
            "metadata": self.metadata,
        }
