import React from "react";
import Plot from "react-plotly.js";
import type { SimResult } from "../api/client";

interface Series {
  result: SimResult;
  label: string;
  color: string;
}

interface Props {
  series: Series[];
}

export default function VelocityProfile({ series }: Props) {
  const traces: Plotly.Data[] = series.map(({ result, label, color }) => ({
    type: "scatter" as const,
    mode: "lines",
    x: result.s,
    y: result.v_ms.map((v) => v * 3.6),
    name: `${label} — ${result.lap_time_s.toFixed(3)}s`,
    line: { color, width: 2 },
  }));

  return (
    <Plot
      data={traces}
      layout={{
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#e5e7eb" },
        margin: { t: 30, b: 50, l: 60, r: 20 },
        xaxis: { title: "Arc-length [m]", gridcolor: "#374151" },
        yaxis: { title: "Speed [km/h]", gridcolor: "#374151" },
        title: { text: "Velocity Profile", font: { size: 14 } },
        legend: { bgcolor: "rgba(0,0,0,0)", font: { size: 11 } },
      }}
      config={{ responsive: true, displayModeBar: false }}
      style={{ width: "100%", height: "100%" }}
    />
  );
}
