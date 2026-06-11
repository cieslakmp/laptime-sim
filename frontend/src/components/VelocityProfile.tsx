import React from "react";
import Plot from "react-plotly.js";
import type { SimResult } from "../api/client";

interface Series {
  result: SimResult;
  label: string;
  color: string;
}

export interface VelocityBand {
  s: number[];
  vMin: number[];
  vMax: number[];
  color: string;
  label: string;
}

interface Props {
  series: Series[];
  band?: VelocityBand;
}

export default function VelocityProfile({ series, band }: Props) {
  const traces: Plotly.Data[] = [];

  if (band) {
    // Lower edge first, then the upper edge filled down to it (tonexty).
    traces.push({
      type: "scatter" as const,
      mode: "lines",
      x: band.s,
      y: band.vMin.map((v) => v * 3.6),
      line: { width: 0 },
      hoverinfo: "skip" as const,
      showlegend: false,
    });
    traces.push({
      type: "scatter" as const,
      mode: "lines",
      x: band.s,
      y: band.vMax.map((v) => v * 3.6),
      fill: "tonexty" as const,
      fillcolor: "rgba(99, 102, 241, 0.18)",
      line: { width: 0 },
      name: band.label,
      hovertemplate: "max: %{y:.0f} km/h<extra></extra>",
    });
  }

  series.forEach(({ result, label, color }) => {
    traces.push({
      type: "scatter" as const,
      mode: "lines",
      x: result.s,
      y: result.v_ms.map((v) => v * 3.6),
      name: `${label} — ${result.lap_time_s.toFixed(3)}s`,
      line: { color, width: 2 },
    });
  });

  return (
    <Plot
      data={traces}
      layout={{
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#e5e7eb" },
        margin: { t: 30, b: 50, l: 60, r: 20 },
        xaxis: { title: { text: "Arc-length [m]" }, gridcolor: "#374151" },
        yaxis: { title: { text: "Speed [km/h]" }, gridcolor: "#374151" },
        title: { text: "Velocity Profile", font: { size: 14 } },
        legend: { bgcolor: "rgba(0,0,0,0)", font: { size: 11 } },
      }}
      config={{ responsive: true, displayModeBar: false }}
      style={{ width: "100%", height: "100%" }}
    />
  );
}
