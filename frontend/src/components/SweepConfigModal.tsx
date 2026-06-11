import React, { useMemo, useState } from "react";
import {
  type SweepMode,
  type SweepParamSpec,
  type SweepRequestBody,
  type SweepSolver,
  type VehicleParams,
} from "../api/client";
import { SLIDERS } from "./VehicleForm";

interface Props {
  open: boolean;
  vehicle: VehicleParams;
  trackId: string | null;
  onClose: () => void;
  onStart: (body: SweepRequestBody) => void;
}

interface RangeState {
  enabled: boolean;
  min: number;
  max: number;
  steps: number;
}

// Per-solver run caps — mirror MAX_RUNS in laptime/sweep/spec.py.
const SOLVER_INFO: { id: SweepSolver; label: string; hint: string; cap: number }[] = [
  { id: "qss", label: "QSS", hint: "~ms per run", cap: 500 },
  { id: "racing_line", label: "QSS on racing line", hint: "one-time ~30 s, then ~ms per run", cap: 200 },
  { id: "transient", label: "Transient 7DOF", hint: "~30–60 s per run", cap: 24 },
  { id: "ocp", label: "Full OCP", hint: "1–3 min per run, needs CasADi", cap: 8 },
];

// Flat params the transient 7DOF model consumes — mirror TRANSIENT_SUPPORTED in spec.py.
const TRANSIENT_SUPPORTED = new Set(["mass_kg", "p_max_kw", "cd", "cl"]);

function defaultRanges(vehicle: VehicleParams): Record<string, RangeState> {
  const ranges: Record<string, RangeState> = {};
  for (const s of SLIDERS) {
    // Default range: ±20% around the current value, clamped to the slider bounds.
    const v = vehicle[s.key];
    const lo = Math.max(s.min, v * 0.8);
    const hi = Math.min(s.max, v * 1.2);
    ranges[s.key] = {
      enabled: false,
      min: lo < hi ? lo : s.min,
      max: lo < hi ? hi : s.max,
      steps: 5,
    };
  }
  return ranges;
}

export default function SweepConfigModal({ open, vehicle, trackId, onClose, onStart }: Props) {
  const [mode, setMode] = useState<SweepMode>("grid");
  const [solver, setSolver] = useState<SweepSolver>("qss");
  const [ranges, setRanges] = useState<Record<string, RangeState>>(() => defaultRanges(vehicle));

  const setRange = (key: string, patch: Partial<RangeState>) =>
    setRanges((r) => ({ ...r, [key]: { ...r[key], ...patch } }));

  const enabled = SLIDERS.filter((s) => ranges[s.key]?.enabled);
  const maxParams = mode === "grid" ? 2 : 3;
  const solverInfo = SOLVER_INFO.find((s) => s.id === solver)!;

  const totalRuns = useMemo(() => {
    if (enabled.length === 0) return 0;
    if (mode === "grid") {
      return enabled.reduce((acc, s) => acc * ranges[s.key].steps, 1);
    }
    return enabled.reduce((acc, s) => acc + ranges[s.key].steps, 0);
  }, [enabled, mode, ranges]);

  const problems: string[] = [];
  if (enabled.length === 0) problems.push("Select at least one parameter to sweep.");
  if (enabled.length > maxParams)
    problems.push(`${mode === "grid" ? "Grid" : "One-at-a-time"} mode supports at most ${maxParams} parameters.`);
  if (totalRuns > solverInfo.cap)
    problems.push(`${totalRuns} runs exceeds the ${solverInfo.label} cap of ${solverInfo.cap}.`);
  for (const s of enabled) {
    const r = ranges[s.key];
    if (!(r.min < r.max)) problems.push(`${s.label}: min must be below max.`);
    if (solver === "transient" && !TRANSIENT_SUPPORTED.has(s.key))
      problems.push(`Transient sweeps cannot vary ${s.label} (only mass, power, drag, downforce).`);
  }

  if (!open) return null;

  const handleStart = () => {
    if (!trackId || problems.length > 0) return;
    const params: SweepParamSpec[] = enabled.map((s) => ({
      name: s.key,
      min: ranges[s.key].min,
      max: ranges[s.key].max,
      steps: ranges[s.key].steps,
    }));
    onStart({ track_id: trackId, vehicle, params, mode, solver });
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-gray-800">
          <h2 className="text-base font-bold">Parameter Sweep</h2>
          <div className="flex-1" />
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-xl leading-none px-2"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Mode + solver */}
          <div className="flex gap-6">
            <div>
              <div className="text-xs text-gray-400 uppercase tracking-wider mb-1.5">Mode</div>
              <div className="flex rounded overflow-hidden border border-gray-700">
                {(
                  [
                    ["grid", "Grid"],
                    ["one_at_a_time", "One-at-a-time"],
                  ] as [SweepMode, string][]
                ).map(([m, label]) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={`px-3 py-1.5 text-sm transition ${
                      mode === m ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-300 hover:bg-gray-700"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {mode === "grid"
                  ? "All combinations (≤2 params, heatmap for 2)"
                  : "Each param varied alone — sensitivity / tornado"}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400 uppercase tracking-wider mb-1.5">Solver</div>
              <select
                value={solver}
                onChange={(e) => setSolver(e.target.value as SweepSolver)}
                className="bg-gray-800 border border-gray-700 text-sm px-3 py-1.5 rounded outline-none focus:ring-1 ring-indigo-500"
              >
                {SOLVER_INFO.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
              <div className="text-xs text-gray-500 mt-1">
                {solverInfo.hint} · cap {solverInfo.cap} runs
              </div>
            </div>
          </div>

          {/* Parameter ranges */}
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-2">
              Parameters ({enabled.length}/{maxParams})
            </div>
            <div className="space-y-1.5">
              {SLIDERS.map((s) => {
                const r = ranges[s.key];
                const disabled = !r.enabled;
                return (
                  <div
                    key={s.key}
                    className={`flex items-center gap-3 px-3 py-2 rounded border ${
                      r.enabled ? "border-indigo-700 bg-indigo-950/30" : "border-gray-800 bg-gray-800/40"
                    }`}
                  >
                    <label className="flex items-center gap-2 w-52 shrink-0 cursor-pointer text-sm">
                      <input
                        type="checkbox"
                        checked={r.enabled}
                        onChange={(e) => setRange(s.key, { enabled: e.target.checked })}
                        className="accent-indigo-500"
                      />
                      <span className={r.enabled ? "text-gray-100" : "text-gray-400"}>
                        {s.label}
                      </span>
                    </label>
                    <div className="flex items-center gap-2 text-xs text-gray-400 flex-1">
                      <span>min</span>
                      <input
                        type="number"
                        value={r.min}
                        step={s.step}
                        disabled={disabled}
                        onChange={(e) => setRange(s.key, { min: parseFloat(e.target.value) })}
                        className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 font-mono text-gray-200 disabled:opacity-40"
                      />
                      <span>max</span>
                      <input
                        type="number"
                        value={r.max}
                        step={s.step}
                        disabled={disabled}
                        onChange={(e) => setRange(s.key, { max: parseFloat(e.target.value) })}
                        className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 font-mono text-gray-200 disabled:opacity-40"
                      />
                      <span>steps</span>
                      <input
                        type="number"
                        value={r.steps}
                        min={2}
                        max={50}
                        disabled={disabled}
                        onChange={(e) =>
                          setRange(s.key, { steps: Math.max(2, Math.min(50, parseInt(e.target.value) || 2)) })
                        }
                        className="w-14 bg-gray-800 border border-gray-700 rounded px-2 py-1 font-mono text-gray-200 disabled:opacity-40"
                      />
                      <span className="ml-auto text-gray-500">{s.unit}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {problems.length > 0 && (
            <ul className="text-xs text-amber-400 space-y-0.5">
              {problems.map((p) => (
                <li key={p}>• {p}</li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-3 px-5 py-3 border-t border-gray-800">
          <div className="text-sm text-gray-400">
            <span className="font-mono text-gray-200">{totalRuns}</span> sweep runs + baseline
          </div>
          <div className="flex-1" />
          <button
            onClick={handleStart}
            disabled={!trackId || problems.length > 0}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-sm font-semibold px-5 py-2 rounded transition"
          >
            Run Sweep
          </button>
        </div>
      </div>
    </div>
  );
}
