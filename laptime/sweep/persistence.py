"""JSON persistence for completed sweeps under data/sweeps/."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from laptime.api.schemas import SavedSweepInfo, SweepResult

_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def _sweeps_dir() -> Path:
    env = os.environ.get("LAPTIME_SWEEPS_DIR")
    base = Path(env) if env else Path(__file__).parents[2] / "data" / "sweeps"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _path_for(sweep_id: str) -> Path:
    if not _ID_RE.match(sweep_id):
        raise KeyError(f"Invalid sweep id '{sweep_id}'")
    return _sweeps_dir() / f"{sweep_id}.json"


def save_sweep(result: SweepResult) -> Path:
    path = _sweeps_dir() / f"{result.sweep_id}.json"
    path.write_text(result.model_dump_json(), encoding="utf-8")
    return path


def list_saved() -> list[SavedSweepInfo]:
    infos = []
    for path in _sweeps_dir().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            laps = [r["lap_time_s"] for r in data["runs"] if r.get("lap_time_s") is not None]
            infos.append(SavedSweepInfo(
                sweep_id=data["sweep_id"],
                created_at=data["created_at"],
                track_name=data["track_name"],
                solver=data["config"]["solver"],
                mode=data["config"]["mode"],
                n_runs=len(data["runs"]),
                param_names=[p["name"] for p in data["config"]["params"]],
                best_lap_time_s=min(laps) if laps else None,
            ))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue  # skip corrupt files rather than break the listing
    return sorted(infos, key=lambda i: i.created_at, reverse=True)


def load_saved(sweep_id: str) -> SweepResult:
    path = _path_for(sweep_id)
    if not path.exists():
        raise KeyError(f"Saved sweep '{sweep_id}' not found")
    return SweepResult.model_validate_json(path.read_text(encoding="utf-8"))


def delete_saved(sweep_id: str) -> None:
    path = _path_for(sweep_id)
    if not path.exists():
        raise KeyError(f"Saved sweep '{sweep_id}' not found")
    path.unlink()
