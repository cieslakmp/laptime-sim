"""Sweep point expansion — pure functions, no I/O."""

from __future__ import annotations

import itertools

import numpy as np

from laptime.api.schemas import SweepParamSpec, SweepRequest

# Hard caps on expanded sweep points (excluding the baseline run) per solver,
# sized to keep a full sweep within interactive time on a multi-core machine.
MAX_RUNS = {"qss": 500, "racing_line": 200, "transient": 24, "ocp": 8}

# Flat point-mass params the transient 7DOF model consumes (see the flat→nested
# mapping in runner.py); sweeping anything else with solver="transient" is a 422.
TRANSIENT_SUPPORTED = {"mass_kg", "p_max_kw", "cd", "cl"}


def _values(p: SweepParamSpec) -> list[float]:
    return [float(v) for v in np.linspace(p.min, p.max, p.steps)]


def expand_grid(params: list[SweepParamSpec]) -> list[tuple[str | None, dict[str, float]]]:
    """Cartesian product in request order — the LAST parameter varies fastest."""
    names = [p.name for p in params]
    axes = [_values(p) for p in params]
    return [(None, dict(zip(names, combo, strict=True))) for combo in itertools.product(*axes)]


def expand_oat(params: list[SweepParamSpec]) -> list[tuple[str | None, dict[str, float]]]:
    """One-at-a-time: each parameter varied alone, others at baseline."""
    return [(p.name, {p.name: v}) for p in params for v in _values(p)]


def expand_points(req: SweepRequest) -> list[tuple[str | None, dict[str, float]]]:
    """Expanded (varied_param, overrides) points — baseline run NOT included."""
    if req.mode == "grid":
        return expand_grid(req.params)
    return expand_oat(req.params)


def total_points(req: SweepRequest) -> int:
    """Number of expanded sweep points, excluding the baseline run."""
    if req.mode == "grid":
        n = 1
        for p in req.params:
            n *= p.steps
        return n
    return sum(p.steps for p in req.params)
