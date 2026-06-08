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

const G = 9.81;

export default function GGDiagram({ series }: Props) {
  const traces: Plotly.Data[] = series.map(({ result, label }) => ({
    type: "scatter" as const,
    mode: "markers",
    x: result.ay_ms2.map((a) => a / G),
    y: result.ax_ms2.map((a) => a / G),
    marker: {
      color: result.v_ms.map((v) => v * 3.6),
      colorscale: "Plasma",
      size: 3,
      opacity: 0.7,
      colorbar: label === series[0].label ? { title: "km/h", thickness: 12 } : undefined,
    },
    name: label,
    hovertemplate: "ay: %{x:.2f}g  ax: %{y:.2f}g<extra></extra>",
  }));

  return (
    <Plot
      data={traces}
      layout={{
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#e5e7eb" },
        margin: { t: 30, b: 50, l: 60, r: 20 },
        xaxis: { title: "Lateral [g]", gridcolor: "#374151", zeroline: true, zerolinecolor: "#6b7280" },
        yaxis: { title: "Longitudinal [g]", gridcolor: "#374151", zeroline: true, zerolinecolor: "#6b7280", scaleanchor: "x" },
        title: { text: "G-G Diagram", font: { size: 14 } },
      }}
      config={{ responsive: true, displayModeBar: false }}
      style={{ width: "100%", height: "100%" }}
    />
  );
}
