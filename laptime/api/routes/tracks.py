"""Track upload and retrieval endpoints."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from laptime.api.schemas import TrackUploadResponse
from laptime.api.store import get_track, list_tracks, save_track
from laptime.track.loader import load_csv, load_gpx

router = APIRouter()


@router.post("", response_model=TrackUploadResponse)
async def upload_track(file: UploadFile) -> TrackUploadResponse:
    """Upload a CSV or GPX track file."""
    suffix = Path(file.filename or "track.csv").suffix.lower()
    if suffix not in {".csv", ".gpx"}:
        raise HTTPException(400, "Only .csv and .gpx files are supported")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        name = Path(file.filename or "track").stem
        if suffix == ".csv":
            track = load_csv(tmp_path, name=name)
        else:
            track = load_gpx(tmp_path, name=name)
    except Exception as e:
        raise HTTPException(422, f"Failed to parse track file: {e}") from e
    finally:
        tmp_path.unlink(missing_ok=True)

    track_id = save_track(track)
    return TrackUploadResponse(
        track_id=track_id,
        name=track.name,
        length_m=round(track.length, 1),
        n_points=track.n_points,
    )


@router.get("")
def list_all_tracks() -> list[dict]:
    return list_tracks()


@router.get("/{track_id}")
def get_track_info(track_id: str) -> dict:
    try:
        track = get_track(track_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return {
        "id": track_id,
        "name": track.name,
        "length_m": round(track.length, 1),
        "n_points": track.n_points,
        "x": track.x.tolist(),
        "y": track.y.tolist(),
        "s": track.s.tolist(),
        "kappa": track.kappa.tolist(),
    }
