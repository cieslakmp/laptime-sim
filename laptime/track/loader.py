"""Track loaders: CSV and GPX → Track."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .geometry import (
    arc_length_parameterise,
    compute_curvature,
    compute_heading,
    fit_spline,
)
from .track import Track

# Default track resolution in metres
DEFAULT_DS = 2.0
# Default smoothing sigma for curvature (stations)
DEFAULT_SMOOTH = 2.0


def load_csv(
    path: str | Path,
    ds: float = DEFAULT_DS,
    smooth_sigma: float = DEFAULT_SMOOTH,
    name: str = "",
    closed: bool = True,
) -> Track:
    """Load a track from a CSV file.

    Expected columns (header optional):
        x_m, y_m[, width_left_m, width_right_m, banking_rad]

    Lines starting with '#' are ignored.
    """
    path = Path(path)
    data: list[list[float]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                # Skip header row
                float(line.split(",")[0])
            except ValueError:
                continue
            data.append([float(v) for v in line.split(",")])

    arr = np.array(data)
    x_raw = arr[:, 0]
    y_raw = arr[:, 1]
    width_left_raw = arr[:, 2] if arr.shape[1] > 2 else np.full(len(x_raw), 5.0)
    width_right_raw = arr[:, 3] if arr.shape[1] > 3 else np.full(len(x_raw), 5.0)
    banking_raw = arr[:, 4] if arr.shape[1] > 4 else np.zeros(len(x_raw))

    return _build_track(
        x_raw,
        y_raw,
        width_left_raw,
        width_right_raw,
        banking_raw,
        ds=ds,
        smooth_sigma=smooth_sigma,
        name=name or path.stem,
        closed=closed,
    )


def load_gpx(
    path: str | Path,
    ds: float = DEFAULT_DS,
    smooth_sigma: float = DEFAULT_SMOOTH,
    name: str = "",
    closed: bool = True,
    width: float = 5.0,
) -> Track:
    """Load a track from a GPX file (uses gpxpy + pyproj).

    The first track segment's track points are used.
    Lat/lon is converted to local Cartesian via a tangent plane at the centroid.
    """
    import gpxpy
    from pyproj import Proj

    path = Path(path)
    with path.open() as f:
        gpx = gpxpy.parse(f)

    lats, lons = [], []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                lats.append(pt.latitude)
                lons.append(pt.longitude)
            break
        break

    if not lats:
        raise ValueError(f"No track points found in {path}")

    lat0 = np.mean(lats)
    lon0 = np.mean(lons)
    proj = Proj(proj="tmerc", lat_0=lat0, lon_0=lon0, units="m")
    x_raw, y_raw = proj(lons, lats)
    x_raw = np.array(x_raw)
    y_raw = np.array(y_raw)

    width_left_raw = np.full(len(x_raw), width)
    width_right_raw = np.full(len(x_raw), width)
    banking_raw = np.zeros(len(x_raw))

    return _build_track(
        x_raw,
        y_raw,
        width_left_raw,
        width_right_raw,
        banking_raw,
        ds=ds,
        smooth_sigma=smooth_sigma,
        name=name or path.stem,
        closed=closed,
    )


def _build_track(
    x_raw: np.ndarray,
    y_raw: np.ndarray,
    width_left_raw: np.ndarray,
    width_right_raw: np.ndarray,
    banking_raw: np.ndarray,
    ds: float,
    smooth_sigma: float,
    name: str,
    closed: bool,
) -> Track:
    tck, _ = fit_spline(x_raw, y_raw, closed=closed)
    n = max(50, int(sum(np.sqrt(np.diff(x_raw) ** 2 + np.diff(y_raw) ** 2)) / ds))
    u_uniform = np.linspace(0, 1, n, endpoint=False)
    s, x, y = arc_length_parameterise(tck, n=n)
    kappa = compute_curvature(tck, u_uniform, smooth_sigma=smooth_sigma)
    heading = compute_heading(tck, u_uniform)

    # Resample width/banking arrays to match the new n stations
    s_raw = np.linspace(0, s[-1], len(x_raw))
    width_left = np.interp(s, s_raw, width_left_raw, period=s[-1] + (s[1] - s[0]) if closed else None)
    width_right = np.interp(s, s_raw, width_right_raw)
    banking = np.interp(s, s_raw, banking_raw)

    return Track(
        s=s,
        x=x,
        y=y,
        heading=heading,
        kappa=kappa,
        width_left=width_left,
        width_right=width_right,
        banking=banking,
        name=name,
        is_closed=closed,
    )
