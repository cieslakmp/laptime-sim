const BASE = "";

export interface VehicleParams {
  mass_kg: number;
  p_max_kw: number;
  f_brake_max_n: number;
  mu_x: number;
  mu_y: number;
  cd: number;
  cl: number;
  aero_ref_area_m2: number;
  v_max_ms: number;
}

export interface TrackInfo {
  track_id: string;
  name: string;
  length_m: number;
  n_points: number;
}

export interface LibraryTrack {
  id: string;
  name: string;
  location: string;
  country: string;
  country_code: string;
  flag: string;
  official_length_m: number | null;
  measured_length_m: number;
  opened: number | null;
  first_gp: number | null;
  altitude_m: number | null;
  outline: { x: number[]; y: number[] };
}

export interface TrackDetail extends TrackInfo {
  id: string;
  x: number[];
  y: number[];
  s: number[];
  kappa: number[];
}

export interface SimResult {
  lap_time_s: number;
  track_id: string;
  s: number[];
  v_ms: number[];
  ax_ms2: number[];
  ay_ms2: number[];
}

export interface OptimizeResult {
  baseline_lap_time_s: number;
  optimized_lap_time_s: number;
  delta_s: number;
  optimized_track_id: string;
  baseline: SimResult;
  optimized: SimResult;
}

export interface OCPSimResult extends SimResult {
  n_m: number[];
  psi_rad: number[];
  x_path: number[];
  y_path: number[];
  solve_time_s: number;
  solver_status: string;
}

export interface OCPResult {
  baseline_lap_time_s: number;
  optimized_lap_time_s: number;
  delta_s: number;
  baseline: SimResult;
  optimized: OCPSimResult;
}

export interface TransientSimResult extends SimResult {
  x_path: number[];
  y_path: number[];
  completed: boolean;
  aborted: boolean;
  max_lateral_dev_m: number;
}

export interface TransientResult {
  qss_lap_time_s: number;
  transient_lap_time_s: number;
  delta_s: number;
  completed: boolean;
  baseline: SimResult;
  transient: TransientSimResult;
}

export type SweepSolver = "qss" | "racing_line" | "transient" | "ocp";
export type SweepMode = "grid" | "one_at_a_time";
export type SweepState = "pending" | "running" | "done" | "failed" | "cancelled";

export interface SweepParamSpec {
  name: keyof VehicleParams;
  min: number;
  max: number;
  steps: number;
}

export interface SweepRequestBody {
  track_id: string;
  vehicle: VehicleParams;
  params: SweepParamSpec[];
  mode: SweepMode;
  solver: SweepSolver;
  ds?: number;
}

export interface SweepStart {
  sweep_id: string;
  total_runs: number;
  state: SweepState;
}

export interface SweepStatus {
  sweep_id: string;
  state: SweepState;
  completed: number;
  total: number;
  error: string | null;
}

export interface SweepRunRecord {
  index: number;
  param_values: Record<string, number>;
  varied_param: string | null;
  lap_time_s: number | null;
  ok: boolean;
  error: string | null;
}

export interface SweepAggregates {
  s: number[];
  x: number[];
  y: number[];
  v_min: number[];
  v_max: number[];
  v_spread: number[];
  v_baseline: number[];
  gg_hull_ay_g: number[];
  gg_hull_ax_g: number[];
  gg_baseline_ay_g: number[];
  gg_baseline_ax_g: number[];
}

export interface SweepResult {
  schema_version: number;
  sweep_id: string;
  created_at: string;
  state: SweepState;
  config: SweepRequestBody;
  track_name: string;
  track_length_m: number;
  baseline_lap_time_s: number;
  runs: SweepRunRecord[];
  aggregates: SweepAggregates;
}

export interface SavedSweepInfo {
  sweep_id: string;
  created_at: string;
  track_name: string;
  solver: string;
  mode: string;
  n_runs: number;
  param_names: string[];
  best_lap_time_s: number | null;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

export async function uploadTrack(file: File): Promise<TrackInfo> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/tracks`, { method: "POST", body: form });
  return json<TrackInfo>(res);
}

export async function getTrackDetail(trackId: string): Promise<TrackDetail> {
  const res = await fetch(`${BASE}/tracks/${trackId}`);
  return json<TrackDetail>(res);
}

export async function listLibraryTracks(): Promise<LibraryTrack[]> {
  const res = await fetch(`${BASE}/tracks/library`);
  return json<LibraryTrack[]>(res);
}

export async function loadLibraryTrack(circuitId: string): Promise<TrackInfo> {
  const res = await fetch(`${BASE}/tracks/library/${circuitId}`, { method: "POST" });
  return json<TrackInfo>(res);
}

export async function simulate(trackId: string, vehicle: VehicleParams, ds = 2): Promise<SimResult> {
  const res = await fetch(`${BASE}/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ track_id: trackId, vehicle, ds }),
  });
  return json<SimResult>(res);
}

export async function solveOCP(
  trackId: string,
  vehicle: VehicleParams,
  ds = 2,
  nIntervals = 150
): Promise<OCPResult> {
  const res = await fetch(`${BASE}/ocp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ track_id: trackId, vehicle, ds, n_intervals: nIntervals }),
  });
  return json<OCPResult>(res);
}

export async function optimizeRacingLine(
  trackId: string,
  vehicle: VehicleParams,
  ds = 2,
  nPoints = 200
): Promise<OptimizeResult> {
  const res = await fetch(`${BASE}/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ track_id: trackId, vehicle, ds, n_racing_line_points: nPoints }),
  });
  return json<OptimizeResult>(res);
}

export async function solveTransient(
  trackId: string,
  vehicle: VehicleParams,
  useRacingLine = true
): Promise<TransientResult> {
  // Map the shared point-mass form fields onto the nested 7DOF parameter set;
  // the backend fills the remaining suspension/tyre/driver fields from defaults.
  const body = {
    track_id: trackId,
    use_racing_line: useRacingLine,
    vehicle: {
      chassis: { mass_kg: vehicle.mass_kg },
      drivetrain: { p_max_kw: vehicle.p_max_kw },
      aero: { cd: vehicle.cd, cl: Math.max(vehicle.cl, 0) },
    },
  };
  const res = await fetch(`${BASE}/transient`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json<TransientResult>(res);
}

export async function startSweep(body: SweepRequestBody): Promise<SweepStart> {
  const res = await fetch(`${BASE}/sweep`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json<SweepStart>(res);
}

export async function getSweepStatus(sweepId: string): Promise<SweepStatus> {
  const res = await fetch(`${BASE}/sweep/${sweepId}/status`);
  return json<SweepStatus>(res);
}

export async function getSweepResult(sweepId: string): Promise<SweepResult> {
  const res = await fetch(`${BASE}/sweep/${sweepId}`);
  return json<SweepResult>(res);
}

export async function cancelSweep(sweepId: string): Promise<SweepStatus> {
  const res = await fetch(`${BASE}/sweep/${sweepId}/cancel`, { method: "POST" });
  return json<SweepStatus>(res);
}

export async function listSavedSweeps(): Promise<SavedSweepInfo[]> {
  const res = await fetch(`${BASE}/sweep/saved`);
  return json<SavedSweepInfo[]>(res);
}

export async function getSavedSweep(sweepId: string): Promise<SweepResult> {
  const res = await fetch(`${BASE}/sweep/saved/${sweepId}`);
  return json<SweepResult>(res);
}

export async function deleteSavedSweep(sweepId: string): Promise<void> {
  const res = await fetch(`${BASE}/sweep/saved/${sweepId}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(`${res.status}: ${await res.text()}`);
  }
}
