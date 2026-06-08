import React from "react";
import Plot from "react-plotly.js";
import type { TrackDetail } from "../api/client";
import type { SimResult } from "../api/client";

interface Props {
  track: TrackDetail;
  results?: { label: string; result: SimResult; color: string }[];
}

export default function TrackMap({ track, results }: Props) {
  const traces: Plotly.Data[] = [];

  if (results && results.length > 0) {
    // Colour track by primary result velocity
    const primary = results[0].result;
    // Interpolate velocity onto track x/y
    const vInterp = track.s.map((s) => {
      const idx = primary.s.findIndex((si) => si >= s);
      if (idx <= 0) return primary.v_ms[0];
      const t = (s - primary.s[idx - 1]) / (primary.s[idx] - primary.s[idx - 1] + 1e-9);
      return primary.v_ms[idx - 1] + t * (primary.v_ms[idx] - primary.v_ms[idx - 1]);
    });
    const vKmh = vInterp.map((v) => v * 3.6);

    traces.push({
      type: "scatter" as const,
      mode: "markers",
      x: track.x,
      y: track.y,
      marker: {
        color: vKmh,
        colorscale: "Plasma",
        size: 4,
        colorbar: { title: "Speed km/h", thickness: 12 },
      },
      name: "Track",
      hovertemplate: "Speed: %{marker.color:.0f} km/h<extra></extra>",
    });
  } else {
    traces.push({
      type: "scatter" as const,
      mode: "lines",
      x: track.x,
      y: track.y,
      line: { color: "#6366f1", width: 2 },
      name: track.name,
    });
  }

  // S/F marker
  traces.push({
    type: "scatter" as const,
    mode: "markers",
    x: [track.x[0]],
    y: [track.y[0]],
    marker: { color: "#22c55e", size: 12, symbol: "star" },
    name: "S/F",
    hovertemplate: "Start/Finish<extra></extra>",
  });

  return (
    <Plot
      data={traces}
      layout={{
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#e5e7eb" },
        margin: { t: 30, b: 40, l: 50, r: 20 },
        xaxis: { title: "x [m]", gridcolor: "#374151", scaleanchor: "y" },
        yaxis: { title: "y [m]", gridcolor: "#374151" },
        title: { text: track.name || "Track Map", font: { size: 14 } },
        showlegend: false,
      }}
      config={{ responsive: true, displayModeBar: false }}
      style={{ width: "100%", height: "100%" }}
    />
  );
}
