import React, { useState, useCallback } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  uploadTrack,
  getTrackDetail,
  simulate,
  optimizeRacingLine,
  type VehicleParams,
  type SimResult,
  type TrackInfo,
  type OptimizeResult,
} from "./api/client";
import VehicleForm from "./components/VehicleForm";
import TrackMap from "./components/TrackMap";
import VelocityProfile from "./components/VelocityProfile";
import GGDiagram from "./components/GGDiagram";

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
  const [status, setStatus] = useState<string>("");
  const [error, setError] = useState<string>("");

  const { data: trackDetail } = useQuery({
    queryKey: ["track", trackInfo?.track_id],
    queryFn: () => getTrackDetail(trackInfo!.track_id),
    enabled: !!trackInfo,
  });

  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setStatus("Uploading track...");
    setSimResult(null);
    setOptResult(null);
    try {
      const info = await uploadTrack(file);
      setTrackInfo(info);
      setStatus(`Track loaded: ${info.name} (${info.length_m.toFixed(0)} m)`);
    } catch (err) {
      setError(String(err));
      setStatus("");
    }
  }, []);

  const handleSimulate = useCallback(async () => {
    if (!trackInfo) return;
    setError("");
    setStatus("Running simulation...");
    setOptResult(null);
    try {
      const result = await simulate(trackInfo.track_id, vehicle);
      setSimResult(result);
      setStatus(`Lap time: ${result.lap_time_s.toFixed(3)} s`);
    } catch (err) {
      setError(String(err));
      setStatus("");
    }
  }, [trackInfo, vehicle]);

  const handleOptimize = useCallback(async () => {
    if (!trackInfo) return;
    setError("");
    setStatus("Optimising racing line (may take ~30s)...");
    try {
      const result = await optimizeRacingLine(trackInfo.track_id, vehicle);
      setOptResult(result);
      setSimResult(result.baseline);
      setStatus(
        `Optimised: ${result.optimized_lap_time_s.toFixed(3)} s  (Δ ${result.delta_s.toFixed(3)} s vs centreline)`
      );
    } catch (err) {
      setError(String(err));
      setStatus("");
    }
  }, [trackInfo, vehicle]);

  const series = [];
  if (simResult && !optResult) {
    series.push({ result: simResult, label: "Centreline", color: "#6366f1" });
  }
  if (optResult) {
    series.push({ result: optResult.baseline, label: "Centreline", color: "#6366f1" });
    series.push({ result: optResult.optimized, label: "Racing Line", color: "#f97316" });
  }

  const primaryResult = optResult ? optResult.optimized : simResult;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center gap-4">
        <h1 className="text-lg font-bold tracking-tight">Lap Time Simulator</h1>
        <div className="flex-1" />
        <label className="cursor-pointer bg-gray-800 hover:bg-gray-700 text-sm px-4 py-1.5 rounded transition">
          Upload Track (CSV/GPX)
          <input type="file" accept=".csv,.gpx" onChange={handleUpload} className="hidden" />
        </label>
        <button
          onClick={handleSimulate}
          disabled={!trackInfo}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-sm px-4 py-1.5 rounded transition"
        >
          Simulate
        </button>
        <button
          onClick={handleOptimize}
          disabled={!trackInfo}
          className="bg-orange-600 hover:bg-orange-500 disabled:opacity-40 text-sm px-4 py-1.5 rounded transition"
        >
          Optimise Line
        </button>
      </header>

      {/* Status bar */}
      {(status || error) && (
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
              <div className="text-gray-400">{trackInfo.length_m.toFixed(0)} m · {trackInfo.n_points} pts</div>
              {simResult && (
                <div className="text-indigo-300 font-mono text-sm pt-1">
                  {simResult.lap_time_s.toFixed(3)} s
                </div>
              )}
              {optResult && (
                <div className="text-orange-300 font-mono text-sm">
                  {optResult.optimized_lap_time_s.toFixed(3)} s (opt)
                  <span className="text-gray-400 ml-1 text-xs">
                    Δ {optResult.delta_s.toFixed(3)} s
                  </span>
                </div>
              )}
            </div>
          )}
          <VehicleForm value={vehicle} onChange={setVehicle} />
        </aside>

        {/* Main content */}
        <main className="flex-1 grid grid-rows-2 grid-cols-2 gap-2 p-2 bg-gray-950 overflow-hidden">
          {/* Track map */}
          <div className="bg-gray-900 rounded-lg row-span-2 col-span-1 overflow-hidden">
            {trackDetail ? (
              <TrackMap
                track={trackDetail}
                results={primaryResult ? [{ label: "sim", result: primaryResult, color: "#6366f1" }] : undefined}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-gray-600 text-sm">
                Upload a track to get started
              </div>
            )}
          </div>

          {/* Velocity profile */}
          <div className="bg-gray-900 rounded-lg overflow-hidden">
            {series.length > 0 ? (
              <VelocityProfile series={series} />
            ) : (
              <div className="h-full flex items-center justify-center text-gray-600 text-sm">
                Run a simulation to see the velocity profile
              </div>
            )}
          </div>

          {/* G-G diagram */}
          <div className="bg-gray-900 rounded-lg overflow-hidden">
            {series.length > 0 ? (
              <GGDiagram series={series} />
            ) : (
              <div className="h-full flex items-center justify-center text-gray-600 text-sm">
                Run a simulation to see the G-G diagram
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
