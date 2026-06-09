"""Built-in F1 circuit library.

Loads real Formula 1 circuit geometry bundled with the app (an ODbL GeoJSON
dataset of centreline traces) and exposes it as :class:`Track` objects, so the
user can pick a known circuit instead of uploading their own CSV/GPX.

Source: ``bacinger/f1-circuits`` — see ``data/tracks/f1/SOURCE.md``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .loader import DEFAULT_DS, DEFAULT_SMOOTH, _build_track
from .track import Track

# GeoJSON dataset bundled in the repository.
_DATA_FILE = (
    Path(__file__).resolve().parents[2] / "data" / "tracks" / "f1" / "f1-circuits.geojson"
)

# Number of points in the lightweight outline returned by the list endpoint
# (enough to render a recognisable shape in the picker modal without a full
# spline build).
_OUTLINE_POINTS = 160

# ISO 3166-1 alpha-2 prefix (from the circuit id) → country display name.
_COUNTRY_NAMES = {
    "ae": "United Arab Emirates", "ar": "Argentina", "at": "Austria",
    "au": "Australia", "az": "Azerbaijan", "be": "Belgium", "bh": "Bahrain",
    "br": "Brazil", "ca": "Canada", "cn": "China", "de": "Germany",
    "es": "Spain", "fr": "France", "gb": "United Kingdom", "hu": "Hungary",
    "it": "Italy", "jp": "Japan", "mc": "Monaco", "mx": "Mexico",
    "my": "Malaysia", "nl": "Netherlands", "pt": "Portugal", "qa": "Qatar",
    "ru": "Russia", "sa": "Saudi Arabia", "sg": "Singapore", "tr": "Türkiye",
    "us": "United States", "za": "South Africa",
}


def _flag_emoji(country_code: str) -> str:
    """Map a 2-letter country code to its regional-indicator flag emoji."""
    cc = country_code.lower()
    if len(cc) != 2 or not cc.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("a")) for c in cc)


def _project_local(lons: np.ndarray, lats: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Project lon/lat to a local tangent-plane in metres centred on the trace."""
    from pyproj import Proj

    proj = Proj(proj="tmerc", lat_0=float(np.mean(lats)), lon_0=float(np.mean(lons)), units="m")
    x, y = proj(lons, lats)
    return np.asarray(x), np.asarray(y)


def _load_geojson() -> dict:
    if not _DATA_FILE.exists():
        raise FileNotFoundError(
            f"F1 circuit dataset not found at {_DATA_FILE}. "
            "It should be bundled under data/tracks/f1/."
        )
    with _DATA_FILE.open() as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _features_by_id() -> dict[str, dict]:
    """Map circuit id → raw GeoJSON feature."""
    fc = _load_geojson()
    return {ft["properties"]["id"]: ft for ft in fc["features"]}


@lru_cache(maxsize=64)
def build_library_track(
    circuit_id: str,
    ds: float = DEFAULT_DS,
    smooth_sigma: float = DEFAULT_SMOOTH,
) -> Track:
    """Build a :class:`Track` for the given F1 circuit id."""
    feature = _features_by_id().get(circuit_id)
    if feature is None:
        raise KeyError(f"Unknown F1 circuit '{circuit_id}'")

    coords = np.asarray(feature["geometry"]["coordinates"], dtype=float)
    lons, lats = coords[:, 0], coords[:, 1]
    x, y = _project_local(lons, lats)

    # GeoJSON closed rings duplicate the first point at the end; fit_spline
    # re-closes the loop itself, so drop the duplicate.
    if x[0] == x[-1] and y[0] == y[-1]:
        x, y = x[:-1], y[:-1]

    # Drop consecutive duplicate points — zero-length segments break splprep.
    keep = np.concatenate([[True], np.hypot(np.diff(x), np.diff(y)) > 1e-6])
    x, y = x[keep], y[keep]

    width = np.full(len(x), 6.0)  # F1 tracks are wide; centreline-only dataset
    banking = np.zeros(len(x))
    return _build_track(
        x, y, width, width, banking,
        ds=ds, smooth_sigma=smooth_sigma,
        name=feature["properties"].get("Name", circuit_id), closed=True,
    )


def track_metadata(circuit_id: str) -> dict:
    """Return display metadata + computed geometry stats for one circuit."""
    feature = _features_by_id().get(circuit_id)
    if feature is None:
        raise KeyError(f"Unknown F1 circuit '{circuit_id}'")
    props = feature["properties"]
    cc = circuit_id.split("-")[0]
    track = build_library_track(circuit_id)
    return {
        "id": circuit_id,
        "name": props.get("Name", circuit_id),
        "location": props.get("Location", ""),
        "country": _COUNTRY_NAMES.get(cc, cc.upper()),
        "country_code": cc,
        "flag": _flag_emoji(cc),
        "official_length_m": props.get("length"),
        "measured_length_m": round(track.length, 1),
        "opened": props.get("opened"),
        "first_gp": props.get("firstgp"),
        "altitude_m": props.get("altitude"),
    }


def _outline(circuit_id: str) -> dict[str, list[float]]:
    """Downsampled centreline (local metres) for the picker preview."""
    track = build_library_track(circuit_id)
    n = track.n_points
    step = max(1, n // _OUTLINE_POINTS)
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    # Close the loop visually.
    idx.append(0)
    return {"x": [round(float(track.x[i]), 2) for i in idx],
            "y": [round(float(track.y[i]), 2) for i in idx]}


@lru_cache(maxsize=1)
def list_library_tracks() -> list[dict]:
    """List all bundled F1 circuits with metadata and a preview outline.

    Sorted by circuit name. The result is cached; the first call builds every
    track's spline (a few seconds) so subsequent calls are instant.
    """
    catalog = []
    for circuit_id in _features_by_id():
        meta = track_metadata(circuit_id)
        meta["outline"] = _outline(circuit_id)
        catalog.append(meta)
    catalog.sort(key=lambda m: m["name"])
    return catalog
