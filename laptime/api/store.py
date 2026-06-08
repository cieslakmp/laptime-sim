"""In-memory track registry backed by temp files."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from laptime.track.track import Track

_REGISTRY: dict[str, Track] = {}
_TMPDIR = Path(tempfile.gettempdir()) / "laptime_tracks"
_TMPDIR.mkdir(exist_ok=True)


def save_track(track: Track, track_id: str | None = None) -> str:
    if track_id is None:
        # Generate ID from track content
        content = f"{track.name}{track.length:.2f}{len(track.s)}"
        track_id = hashlib.sha256(content.encode()).hexdigest()[:12]
    _REGISTRY[track_id] = track
    return track_id


def get_track(track_id: str) -> Track:
    if track_id not in _REGISTRY:
        raise KeyError(f"Track '{track_id}' not found. Upload it first via POST /tracks")
    return _REGISTRY[track_id]


def list_tracks() -> list[dict]:
    return [
        {"id": tid, "name": t.name, "length_m": round(t.length, 1), "n_points": t.n_points}
        for tid, t in _REGISTRY.items()
    ]
