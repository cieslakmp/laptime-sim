"""Track dataclass — arc-length parameterised circuit geometry."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.interpolate import interp1d


@dataclass
class TrackPoint:
    """Interpolated track properties at a single arc-length station."""

    s: float
    x: float
    y: float
    heading: float   # [rad]
    kappa: float     # signed curvature [1/m]
    width_left: float
    width_right: float
    banking: float   # [rad]


@dataclass
class Track:
    """Arc-length parameterised circuit.

    All arrays have shape (N,) and are indexed by station index.
    The arc-length axis s starts at 0 and increases monotonically.
    For closed circuits s[-1] < total_length (no duplicated endpoint).
    """

    s: np.ndarray            # arc-length [m]
    x: np.ndarray            # Cartesian x [m]
    y: np.ndarray            # Cartesian y [m]
    heading: np.ndarray      # track heading [rad]
    kappa: np.ndarray        # signed curvature [1/m]
    width_left: np.ndarray   # half-width left of centreline [m]
    width_right: np.ndarray  # half-width right of centreline [m]
    banking: np.ndarray      # banking angle [rad], positive = right-side up
    name: str = ""
    is_closed: bool = True

    # Lazy interpolators — built on first use
    _interp: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def length(self) -> float:
        """Total arc-length of the circuit [m]."""
        if self.is_closed:
            ds = np.mean(np.diff(self.s))
            return float(self.s[-1] + ds)
        return float(self.s[-1])

    @property
    def n_points(self) -> int:
        return len(self.s)

    def _build_interp(self) -> None:
        if self._interp:
            return
        period = self.length if self.is_closed else None
        kwargs = dict(assume_sorted=True, bounds_error=False)
        if period:
            s_ext = np.append(self.s, self.s[-1] + (self.s[1] - self.s[0]))
        else:
            s_ext = self.s

        def _wrap(arr: np.ndarray) -> interp1d:
            if period:
                arr_ext = np.append(arr, arr[0])
            else:
                arr_ext = arr
            return interp1d(s_ext, arr_ext, kind="linear", **kwargs)

        self._interp = {
            "x": _wrap(self.x),
            "y": _wrap(self.y),
            "heading": _wrap(self.heading),
            "kappa": _wrap(self.kappa),
            "width_left": _wrap(self.width_left),
            "width_right": _wrap(self.width_right),
            "banking": _wrap(self.banking),
        }

    def at(self, s: float | np.ndarray) -> TrackPoint | list[TrackPoint]:
        """Return interpolated TrackPoint(s) at arc-length position(s)."""
        self._build_interp()
        scalar = np.isscalar(s)
        s = np.atleast_1d(np.asarray(s, dtype=float))
        if self.is_closed:
            s = s % self.length
        pts = [
            TrackPoint(
                s=float(si),
                x=float(self._interp["x"](si)),
                y=float(self._interp["y"](si)),
                heading=float(self._interp["heading"](si)),
                kappa=float(self._interp["kappa"](si)),
                width_left=float(self._interp["width_left"](si)),
                width_right=float(self._interp["width_right"](si)),
                banking=float(self._interp["banking"](si)),
            )
            for si in s
        ]
        return pts[0] if scalar else pts

    def resample(self, ds: float) -> "Track":
        """Return a new Track with uniform station spacing ds [m]."""
        self._build_interp()
        n = max(2, int(self.length / ds))
        s_new = np.linspace(0, self.length, n, endpoint=not self.is_closed)
        if self.is_closed:
            s_new = s_new[: n - (1 if np.isclose(s_new[-1], self.length) else 0)]

        def _interp(key: str) -> np.ndarray:
            return np.array([self._interp[key](si) for si in s_new])

        return Track(
            s=s_new,
            x=_interp("x"),
            y=_interp("y"),
            heading=_interp("heading"),
            kappa=_interp("kappa"),
            width_left=_interp("width_left"),
            width_right=_interp("width_right"),
            banking=_interp("banking"),
            name=self.name,
            is_closed=self.is_closed,
        )
