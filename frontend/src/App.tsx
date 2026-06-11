import React, { useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  uploadTrack,
  getTrackDetail,
  simulate,
  optimizeRacingLine,
  solveOCP,
  solveTransient,
  startSweep,
  getSweepStatus,
  getSweepResult,
  cancelSweep,
  type VehicleParams,
  type SimResult,
  type TrackInfo,
  type OptimizeResult,
  type OCPResult,
  type OCPSimResult,
  type TransientResult,
  type SweepRequestBody,
  type SweepResult,
} from "./api/client";
import VehicleForm from "./components/VehicleForm";
import TrackMap from "./components/TrackMap";
import VelocityProfile from "./components/VelocityProfile";
import GGDiagram from "./components/GGDiagram";
import TrackLibraryModal from "./components/TrackLibraryModal";
import SweepConfigModal from "./components/SweepConfigModal";
import SavedSweepsModal from "./components/SavedSweepsModal";
import LapTimeChart from "./components/LapTimeChart";

const DEFAULT_VEHICLE: VehicleParams = {
  mass_kg: 700,
  p_max_kw: 400,
  f_brake_max_n: 20000,
  mu_x: 1.6,
  mu_y: 1.8,
  cd: 0.9,
  cl: 2.5,
  aero_ref_area_m2: 1.5,
  v_max_ms: 83,
};

export default function App() {
  const [vehicle, setVehicle] = useState<VehicleParams>(DEFAULT_VEHICLE);
  const [trackInfo, setTrackInfo] = useState<TrackInfo | null>(null);
  const [simResult, setSimResult] = useState<SimResult | null>(null);
  const [optResult, setOptResult] = useState<OptimizeResult | null>(null);
  const [ocpResult, setOcpResult] = useState<OCPResult | null>(null);
  const [transientResult, setTransientResult] = useState<TransientResult | null>(null);
  const [status, setStatus] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [sweepOpen, setSweepOpen] = useState(false);
  const [savedSweepsOpen, setSavedSweepsOpen] = useState(false);
  const [sweepId, setSweepId] = useState<string | null>(null);
  const [sweepResult, setSweepResult] = useState<SweepResult | null>(null);
  const [mapMode, setMapMode] = useState<"speed" | "spread">("speed");

  const { data: trackDetail } = useQuery({
    queryKey: ["track", trackInfo?.track_id],
    queryFn: () => getTrackDetail(trackInfo!.track_id),
    enabled: !!trackInfo,
  });

  const clearResults = () => {
    setSimResult(null);
    setOptResult(null);
    setOcpResult(null);
    setTransientResult(null);
    setSweepId(null);
    setSweepResult(null);
    setMapMode("speed");
    setError("");
  };

  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    clearResults();
    setStatus("Uploading track...");
    try {
      const info = await uploadTrack(file);
      setTrackInfo(info);
      setStatus(`Track loaded: ${info.name} (${info.length_m.toFixed(0)} m)`);
    } catch (err) {
      setError(String(err));
      setStatus("");
    }
  }, []);

  const handleLibrarySelect = useCallback((info: TrackInfo, name: string) => {
    clearResults();
    setTrackInfo(info);
    setStatus(`Track loaded: ${name} (${info.length_m.toFixed(0)} m)`);
  }, []);

  const handleSimulate = useCallback(async () => {
    if (!trackInfo) return;
    clearResults();
    setStatus("Running QSS simulation...");
    try {
      const result = await simulate(trackInfo.track_id, vehicle);
      setSimResult(result);
      setStatus(`QSS lap time: ${result.lap_time_s.toFixed(3)} s`);
    } catch (err) {
      setError(String(err));
      setStatus("");
    }
  }, [trackInfo, vehicle]);

  const handleOptimize = useCallback(async () => {
    if (!trackInfo) return;
    clearResults();
    setStatus("Optimising racing line (min-curvature, ~30 s)...");
    try {
      const result = await optimizeRacingLine(trackInfo.track_id, vehicle);
      setOptResult(result);
      setSimResult(result.baseline);
      setStatus(
        `Racing line: ${result.optimized_lap_time_s.toFixed(3)} s  (Δ ${result.delta_s.toFixed(3)} s vs centreline)`
      );
    } catch (err) {
      setError(String(err));
      setStatus("");
    }
  }, [trackInfo, vehicle]);

  const handleOCP = useCallback(async () => {
    if (!trackInfo) return;
    clearResults();
    setStatus("Solving full OCP (CasADi + IPOPT — 1–3 min)...");
    try {
      const result = await solveOCP(trackInfo.track_id, vehicle);
      setOcpResult(result);
      setSimResult(result.baseline);
      const ocpSim = result.optimized as OCPSimResult;
      setStatus(
        `OCP optimal: ${result.optimized_lap_time_s.toFixed(3)} s  ` +
        `(Δ ${result.delta_s.toFixed(3)} s vs QSS)  ·  ` +
        `${ocpSim.solve_time_s.toFixed(1)} s solve  ·  ${ocpSim.solver_status}`
      );
    } catch (err) {
      setError(String(err));
      setStatus("");
    }
  }, [trackInfo, vehicle]);

  const handleTransient = useCallback(async () => {
    if (!trackInfo) return;
    clearResults();
    setStatus("Running transient 7DOF simulation (~30–60 s)...");
    try {
      const result = await solveTransient(trackInfo.track_id, vehicle);
      setTransientResult(result);
      setSimResult(result.baseline);
      const offTrack = result.completed ? "" : "  ·  ⚠ lap did not complete (ran wide)";
      setStatus(
        `Transient 7DOF: ${result.transient_lap_time_s.toFixed(3)} s  ` +
        `(Δ ${result.delta_s.toFixed(3)} s vs QSS)  ·  ` +
        `max dev ${result.transient.max_lateral_dev_m.toFixed(2)} m${offTrack}`
      );
    } catch (err) {
      setError(String(err));
      setStatus("");
    }
  }, [trackInfo, vehicle]);

  const handleSweepStart = useCallback(async (body: SweepRequestBody) => {
    clearResults();
    setStatus("Starting parameter sweep...");
    try {
      const start = await startSweep(body);
      setSweepId(start.sweep_id);
      setStatus(`Sweep running: ${start.total_runs} runs`);
    } catch (err) {
      setError(String(err));
      setStatus("");
    }
  }, []);

  // Poll sweep progress while pending/running; stop once it reaches a terminal state.
  const { data: sweepStatus } = useQuery({
    queryKey: ["sweep-status", sweepId],
    queryFn: () => getSweepStatus(sweepId!),
    enabled: !!sweepId && !sweepResult,
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === "pending" || state === "running" || state === undefined ? 500 : false;
    },
  });

  useEffect(() => {
    if (!sweepId || !sweepStatus || sweepResult) return;
    if (sweepStatus.state === "done") {
      getSweepResult(sweepId)
        .then((result) => {
          setSweepResult(result);
          const laps = result.runs
            .filter((r) => r.lap_time_s != null)
            .map((r) => r.lap_time_s as number);
          setStatus(
            `Sweep done: ${result.runs.length} runs  ·  ` +
            `best ${Math.min(...laps).toFixed(3)} s  ·  worst ${Math.max(...laps).toFixed(3)} s  ·  ` +
            `baseline ${result.baseline_lap_time_s.toFixed(3)} s`
          );
        })
        .catch((err) => setError(String(err)));
    } else if (sweepStatus.state === "failed") {
      setError(`Sweep failed: ${sweepStatus.error ?? "unknown error"}`);
      setStatus("");
      setSweepId(null);
    } else if (sweepStatus.state === "cancelled") {
      setStatus("Sweep cancelled.");
      setSweepId(null);
    }
  }, [sweepId, sweepStatus, sweepResult]);

  const handleCancelSweep = useCallback(() => {
    if (sweepId) cancelSweep(sweepId).catch(() => undefined);
  }, [sweepId]);

  const handleSavedSweepLoad = useCallback((result: SweepResult) => {
    clearResults();
    setSweepResult(result);
    const laps = result.runs.filter((r) => r.lap_time_s != null).map((r) => r.lap_time_s as number);
    setStatus(
      `Loaded sweep on ${result.track_name}: ${result.runs.length} runs  ·  ` +
      `best ${Math.min(...laps).toFixed(3)} s  ·  baseline ${result.baseline_lap_time_s.toFixed(3)} s`
    );
  }, []);

  const sweepRunning =
    !!sweepId && !sweepResult &&
    (sweepStatus == null || sweepStatus.state === "pending" || sweepStatus.state === "running");

  // Build velocity-profile series
  const series: { result: SimResult; label: string; color: string }[] = [];
  if (simResult) {
    series.push({ result: simResult, label: "QSS", color: "#6366f1" });
  }
  if (optResult) {
    series.push({ result: optResult.optimized, label: "Racing Line", color: "#f97316" });
  }
  if (ocpResult) {
    series.push({ result: ocpResult.optimized, label: "OCP optimal", color: "#22d3ee" });
  }
  if (transientResult) {
    series.push({ result: transientResult.transient, label: "Transient 7DOF", color: "#a3e635" });
  }
  // Sweep baseline rides the same velocity-profile series mechanism.
  if (sweepResult) {
    series.push({
      result: {
        lap_time_s: sweepResult.baseline_lap_time_s,
        track_id: "",
        s: sweepResult.aggregates.s,
        v_ms: sweepResult.aggregates.v_baseline,
        ax_ms2: [],
        ay_ms2: [],
      },
      label: "Sweep baseline",
      color: "#6366f1",
    });
  }

  const velocityBand = sweepResult
    ? {
        s: sweepResult.aggregates.s,
        vMin: sweepResult.aggregates.v_min,
        vMax: sweepResult.aggregates.v_max,
        color: "#6366f1",
        label: "Sweep range",
      }
    : undefined;
  const ggEnvelope =
    sweepResult && sweepResult.aggregates.gg_hull_ay_g.length > 2
      ? {
          ayG: sweepResult.aggregates.gg_hull_ay_g,
          axG: sweepResult.aggregates.gg_hull_ax_g,
          label: "Sweep envelope",
        }
      : undefined;
  const ggExtraPoints = sweepResult
    ? {
        ayG: sweepResult.aggregates.gg_baseline_ay_g,
        axG: sweepResult.aggregates.gg_baseline_ax_g,
        label: "Sweep baseline",
      }
    : undefined;
  const sweepSpread =
    sweepResult && mapMode === "spread"
      ? {
          x: sweepResult.aggregates.x,
          y: sweepResult.aggregates.y,
          spread: sweepResult.aggregates.v_spread,
        }
      : undefined;

  // Primary result for track map colouring
  const primaryResult =
    transientResult?.transient ?? ocpResult?.optimized ?? optResult?.optimized ?? simResult;
  const ocpSim = ocpResult ? (ocpResult.optimized as OCPSimResult) : undefined;

  // Sidebar lap time rows
  const lapTimes: { label: string; time: number; color: string }[] = [];
  if (simResult) lapTimes.push({ label: "QSS", time: simResult.lap_time_s, color: "text-indigo-300" });
  if (optResult) lapTimes.push({ label: "Racing line", time: optResult.optimized_lap_time_s, color: "text-orange-300" });
  if (ocpResult) lapTimes.push({ label: "OCP optimal", time: ocpResult.optimized_lap_time_s, color: "text-cyan-300" });
  if (transientResult) lapTimes.push({ label: "Transient 7DOF", time: transientResult.transient_lap_time_s, color: "text-lime-300" });

  const sweepLaps = sweepResult
    ? sweepResult.runs.filter((r) => r.lap_time_s != null).map((r) => r.lap_time_s as number)
    : [];

  return (
    <div className="min-h-screen flex flex-col">
      <TrackLibraryModal
        open={libraryOpen}
        onClose={() => setLibraryOpen(false)}
        onSelect={handleLibrarySelect}
      />
      <SweepConfigModal
        open={sweepOpen}
        vehicle={vehicle}
        trackId={trackInfo?.track_id ?? null}
        onClose={() => setSweepOpen(false)}
        onStart={handleSweepStart}
      />
      <SavedSweepsModal
        open={savedSweepsOpen}
        onClose={() => setSavedSweepsOpen(false)}
        onSelect={handleSavedSweepLoad}
      />
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center gap-3">
        <h1 className="text-lg font-bold tracking-tight">Lap Time Simulator</h1>
        <div className="flex-1" />
        <button
          onClick={() => setLibraryOpen(true)}
          className="bg-gray-800 hover:bg-gray-700 text-sm px-4 py-1.5 rounded transition"
        >
          F1 Track Library
        </button>
        <label className="cursor-pointer bg-gray-800 hover:bg-gray-700 text-sm px-4 py-1.5 rounded transition">
          Upload Track (CSV/GPX)
          <input type="file" accept=".csv,.gpx" onChange={handleUpload} className="hidden" />
        </label>
        <button
          onClick={handleSimulate}
          disabled={!trackInfo}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-sm px-4 py-1.5 rounded transition"
        >
          QSS Simulate
        </button>
        <button
          onClick={handleOptimize}
          disabled={!trackInfo}
          className="bg-orange-600 hover:bg-orange-500 disabled:opacity-40 text-sm px-4 py-1.5 rounded transition"
        >
          Racing Line
        </button>
        <button
          onClick={handleOCP}
          disabled={!trackInfo}
          className="bg-cyan-700 hover:bg-cyan-600 disabled:opacity-40 text-sm px-4 py-1.5 rounded transition font-semibold"
          title="Full optimal control problem (CasADi + IPOPT) — takes 1–3 minutes"
        >
          Full OCP
        </button>
        <button
          onClick={handleTransient}
          disabled={!trackInfo}
          className="bg-lime-700 hover:bg-lime-600 disabled:opacity-40 text-sm px-4 py-1.5 rounded transition font-semibold"
          title="Transient 7DOF + Pacejka time-domain simulation — takes ~30–60 s"
        >
          Transient 7DOF
        </button>
        <button
          onClick={() => setSweepOpen(true)}
          disabled={!trackInfo || sweepRunning}
          className="bg-purple-700 hover:bg-purple-600 disabled:opacity-40 text-sm px-4 py-1.5 rounded transition font-semibold"
          title="Sweep one or more vehicle parameters over ranges"
        >
          Parameter Sweep
        </button>
        <button
          onClick={() => setSavedSweepsOpen(true)}
          className="bg-gray-800 hover:bg-gray-700 text-sm px-4 py-1.5 rounded transition"
          title="Load a previously saved sweep"
        >
          Saved Sweeps
        </button>
      </header>

      {/* Sweep progress bar */}
      {sweepRunning && (
        <div className="px-6 py-2 bg-gray-800 flex items-center gap-3">
          <div className="text-sm text-gray-300 shrink-0">
            Sweep: {sweepStatus?.completed ?? 0}/{sweepStatus?.total ?? "…"} runs
          </div>
          <div className="flex-1 h-2 bg-gray-700 rounded overflow-hidden">
            <div
              className="h-full bg-purple-500 transition-all duration-300"
              style={{
                width: sweepStatus?.total
                  ? `${(100 * sweepStatus.completed) / sweepStatus.total}%`
                  : "0%",
              }}
            />
          </div>
          <div className="text-xs text-gray-400 font-mono shrink-0 w-10 text-right">
            {sweepStatus?.total
              ? `${Math.round((100 * sweepStatus.completed) / sweepStatus.total)}%`
              : "…"}
          </div>
          <button
            onClick={handleCancelSweep}
            className="text-xs px-3 py-1 rounded bg-gray-700 hover:bg-red-900/70 text-gray-300 hover:text-red-300 transition shrink-0"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Status bar */}
      {(status || error) && !sweepRunning && (
        <div className={`px-6 py-2 text-sm ${error ? "bg-red-900/50 text-red-300" : "bg-gray-800 text-gray-300"}`}>
          {error || status}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-72 shrink-0 bg-gray-900 border-r border-gray-800 p-4 overflow-y-auto">
          {trackInfo && (
            <div className="mb-4 p-3 bg-gray-800 rounded text-xs space-y-1">
              <div className="font-semibold text-gray-200">{trackInfo.name}</div>
              <div className="text-gray-400">{trackInfo.length_m.toFixed(0)} m</div>
              {lapTimes.map(({ label, time, color }) => (
                <div key={label} className="flex justify-between">
                  <span className="text-gray-400">{label}</span>
                  <span className={`font-mono ${color}`}>{time.toFixed(3)} s</span>
                </div>
              ))}
              {lapTimes.length > 1 && (
                <div className="border-t border-gray-700 pt-1 text-gray-500">
                  best Δ vs QSS:{" "}
                  <span className="text-green-400 font-mono">
                    {(
                      Math.min(...lapTimes.slice(1).map((x) => x.time)) - lapTimes[0].time
                    ).toFixed(3)}{" "}
                    s
                  </span>
                </div>
              )}
            </div>
          )}
          {sweepResult && sweepLaps.length > 0 && (
            <div className="mb-4 p-3 bg-gray-800 rounded text-xs space-y-1">
              <div className="font-semibold text-purple-300">
                Sweep · {sweepResult.config.params.map((p) => p.name).join(" × ")}
              </div>
              <div className="text-gray-400">
                {sweepResult.runs.length} runs · {sweepResult.config.solver} ·{" "}
                {sweepResult.config.mode === "grid" ? "grid" : "one-at-a-time"}
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">best</span>
                <span className="font-mono text-green-400">{Math.min(...sweepLaps).toFixed(3)} s</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">baseline</span>
                <span className="font-mono text-gray-200">{sweepResult.baseline_lap_time_s.toFixed(3)} s</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">worst</span>
                <span className="font-mono text-red-400">{Math.max(...sweepLaps).toFixed(3)} s</span>
              </div>
              <button
                onClick={() => setMapMode(mapMode === "speed" ? "spread" : "speed")}
                className="mt-1 w-full bg-gray-700 hover:bg-gray-600 text-gray-200 px-2 py-1 rounded transition"
              >
                Map: {mapMode === "speed" ? "Speed → show sweep Δv" : "Sweep Δv → show speed"}
              </button>
            </div>
          )}
          <VehicleForm value={vehicle} onChange={setVehicle} />
        </aside>

        {/* Main content */}
        <main
          className={`flex-1 grid ${sweepResult ? "grid-rows-3" : "grid-rows-2"} grid-cols-2 gap-2 p-2 bg-gray-950 overflow-hidden`}
        >
          {/* Track map */}
          <div className={`bg-gray-900 rounded-lg ${sweepResult ? "row-span-3" : "row-span-2"} col-span-1 overflow-hidden`}>
            {trackDetail || sweepResult ? (
              trackDetail ? (
                <TrackMap
                  track={trackDetail}
                  results={primaryResult ? [{ label: "sim", result: primaryResult, color: "#6366f1" }] : undefined}
                  ocpResult={ocpSim}
                  sweepSpread={sweepSpread}
                />
              ) : (
                // Saved sweep loaded with no track in session — render from the sweep's own geometry.
                <TrackMap
                  track={{
                    track_id: "",
                    id: "",
                    name: sweepResult!.track_name,
                    length_m: sweepResult!.track_length_m,
                    n_points: sweepResult!.aggregates.s.length,
                    x: sweepResult!.aggregates.x,
                    y: sweepResult!.aggregates.y,
                    s: sweepResult!.aggregates.s,
                    kappa: [],
                  }}
                  sweepSpread={{
                    x: sweepResult!.aggregates.x,
                    y: sweepResult!.aggregates.y,
                    spread: sweepResult!.aggregates.v_spread,
                  }}
                />
              )
            ) : (
              <div className="h-full flex items-center justify-center text-gray-600 text-sm">
                Upload a track to get started
              </div>
            )}
          </div>

          {/* Velocity profile */}
          <div className="bg-gray-900 rounded-lg overflow-hidden">
            {series.length > 0 ? (
              <VelocityProfile series={series} band={velocityBand} />
            ) : (
              <div className="h-full flex items-center justify-center text-gray-600 text-sm">
                Run a simulation to see the velocity profile
              </div>
            )}
          </div>

          {/* G-G diagram */}
          <div className="bg-gray-900 rounded-lg overflow-hidden">
            {series.length > 0 || sweepResult ? (
              <GGDiagram
                series={series.filter((s) => s.result.ay_ms2.length > 0)}
                envelope={ggEnvelope}
                extraPoints={ggExtraPoints}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-gray-600 text-sm">
                Run a simulation to see the G-G diagram
              </div>
            )}
          </div>

          {/* Lap time vs parameter (sweep only) */}
          {sweepResult && (
            <div className="bg-gray-900 rounded-lg overflow-hidden">
              <LapTimeChart result={sweepResult} />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
