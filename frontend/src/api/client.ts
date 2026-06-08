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

export async function simulate(trackId: string, vehicle: VehicleParams, ds = 2): Promise<SimResult> {
  const res = await fetch(`${BASE}/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ track_id: trackId, vehicle, ds }),
  });
  return json<SimResult>(res);
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
