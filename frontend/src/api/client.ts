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
