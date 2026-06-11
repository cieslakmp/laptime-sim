import React from "react";
import Plot from "react-plotly.js";
import type { SweepResult } from "../api/client";

interface Props {
  result: SweepResult;
}

const LAYOUT_BASE: Partial<Plotly.Layout> = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#e5e7eb" },
  margin: { t: 30, b: 50, l: 70, r: 20 },
};

function linspace(min: number, max: number, steps: number): number[] {
  if (steps === 1) return [min];
  const out: number[] = [];
  for (let i = 0; i < steps; i++) out.push(min + ((max - min) * i) / (steps - 1));
  return out;
}

/** Lap time vs swept parameter: line (1D grid), heatmap (2D grid) or tornado (OAT). */
export default function LapTimeChart({ result }: Props) {
  const { config, runs, baseline_lap_time_s } = result;
  const points = runs.slice(1); // index 0 is the baseline run

  if (config.mode === "one_at_a_time") {
    // Tornado: per parameter, lap-time swing relative to the baseline.
    const bars = config.params
      .map((p) => {
        const laps = points
          .filter((r) => r.varied_param === p.name && r.lap_time_s != null)
          .map((r) => r.lap_time_s as number);
        const lo = Math.min(...laps) - baseline_lap_time_s;
        const hi = Math.max(...laps) - baseline_lap_time_s;
        return { name: p.name, lo, hi, swing: hi - lo };
      })
      .filter((b) => isFinite(b.swing))
      .sort((a, b) => a.swing - b.swing); // largest swing at the top

    return (
      <Plot
        data={[
          // `base` is valid for bar traces but missing from the bundled Plotly typings.
          {
            type: "bar" as const,
            orientation: "h" as const,
            y: bars.map((b) => b.name),
            x: bars.map((b) => b.swing),
            base: bars.map((b) => b.lo),
            marker: { color: "#6366f1" },
            hovertemplate:
              "%{y}: %{base:+.3f} s … %{customdata:+.3f} s vs baseline<extra></extra>",
            customdata: bars.map((b) => b.hi),
          } as unknown as Plotly.Data,
        ]}
        layout={{
          ...LAYOUT_BASE,
          title: { text: "Lap Time Sensitivity (Δ vs baseline)", font: { size: 14 } },
          xaxis: { title: { text: "Δ lap time [s]" }, gridcolor: "#374151", zeroline: true, zerolinecolor: "#9ca3af" },
          yaxis: { gridcolor: "#374151", automargin: true },
          showlegend: false,
        }}
        config={{ responsive: true, displayModeBar: false }}
        style={{ width: "100%", height: "100%" }}
      />
    );
  }

  if (config.params.length === 1) {
    const p = config.params[0];
    return (
      <Plot
        data={[
          {
            type: "scatter" as const,
            mode: "lines+markers" as const,
            x: points.map((r) => r.param_values[p.name]),
            y: points.map((r) => r.lap_time_s),
            line: { color: "#6366f1", width: 2 },
            marker: { size: 6 },
            name: "lap time",
            hovertemplate: `${p.name}: %{x:.3g}  lap: %{y:.3f} s<extra></extra>`,
          },
          {
            type: "scatter" as const,
            mode: "lines" as const,
            x: [p.min, p.max],
            y: [baseline_lap_time_s, baseline_lap_time_s],
            line: { color: "#9ca3af", width: 1, dash: "dash" },
            name: "baseline",
            hoverinfo: "skip" as const,
          },
        ]}
        layout={{
          ...LAYOUT_BASE,
          title: { text: "Lap Time vs Parameter", font: { size: 14 } },
          xaxis: { title: { text: p.name }, gridcolor: "#374151" },
          yaxis: { title: { text: "Lap time [s]" }, gridcolor: "#374151" },
          legend: { bgcolor: "rgba(0,0,0,0)", font: { size: 11 } },
        }}
        config={{ responsive: true, displayModeBar: false }}
        style={{ width: "100%", height: "100%" }}
      />
    );
  }

  if (config.params.length === 2) {
    // Grid contract: itertools.product in request order, LAST param fastest —
    // so rows (y) follow params[0] and columns (x) follow params[1], row-major.
    const [p0, p1] = config.params;
    const yVals = linspace(p0.min, p0.max, p0.steps);
    const xVals = linspace(p1.min, p1.max, p1.steps);
    const z: (number | null)[][] = [];
    for (let i = 0; i < p0.steps; i++) {
      z.push(points.slice(i * p1.steps, (i + 1) * p1.steps).map((r) => r.lap_time_s));
    }
    return (
      <Plot
        data={[
          {
            type: "heatmap" as const,
            x: xVals,
            y: yVals,
            z,
            colorscale: "Viridis",
            reversescale: true, // fastest lap = brightest
            colorbar: { title: { text: "Lap [s]" }, thickness: 12 },
            hovertemplate: `${p1.name}: %{x:.3g}  ${p0.name}: %{y:.3g}  lap: %{z:.3f} s<extra></extra>`,
          },
        ]}
        layout={{
          ...LAYOUT_BASE,
          title: { text: "Lap Time Map", font: { size: 14 } },
          xaxis: { title: { text: p1.name }, gridcolor: "#374151" },
          yaxis: { title: { text: p0.name }, gridcolor: "#374151" },
        }}
        config={{ responsive: true, displayModeBar: false }}
        style={{ width: "100%", height: "100%" }}
      />
    );
  }

  // Fallback (e.g. a 3-parameter grid): lap time per run index.
  return (
    <Plot
      data={[
        {
          type: "scatter" as const,
          mode: "markers" as const,
          x: points.map((r) => r.index),
          y: points.map((r) => r.lap_time_s),
          marker: { color: "#6366f1", size: 5 },
          hovertemplate: "run %{x}: %{y:.3f} s<extra></extra>",
        },
      ]}
      layout={{
        ...LAYOUT_BASE,
        title: { text: "Lap Time per Run", font: { size: 14 } },
        xaxis: { title: { text: "Run index" }, gridcolor: "#374151" },
        yaxis: { title: { text: "Lap time [s]" }, gridcolor: "#374151" },
        showlegend: false,
      }}
      config={{ responsive: true, displayModeBar: false }}
      style={{ width: "100%", height: "100%" }}
    />
  );
}
