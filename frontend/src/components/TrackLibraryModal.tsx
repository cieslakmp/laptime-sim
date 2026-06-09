import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Plot from "react-plotly.js";
import {
  listLibraryTracks,
  loadLibraryTrack,
  type LibraryTrack,
  type TrackInfo,
} from "../api/client";

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (info: TrackInfo, name: string) => void;
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === "") return null;
  return (
    <div className="flex justify-between gap-4">
      <span className="text-gray-400">{label}</span>
      <span className="font-mono text-gray-200">{value}</span>
    </div>
  );
}

export default function TrackLibraryModal({ open, onClose, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["library-tracks"],
    queryFn: listLibraryTracks,
    enabled: open,
    staleTime: Infinity,
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    if (!q) return data;
    return data.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.location.toLowerCase().includes(q) ||
        t.country.toLowerCase().includes(q)
    );
  }, [data, query]);

  const selected: LibraryTrack | undefined = useMemo(
    () => data?.find((t) => t.id === selectedId),
    [data, selectedId]
  );

  if (!open) return null;

  const handleLoad = async (track: LibraryTrack) => {
    setLoadingId(track.id);
    setError("");
    try {
      const info = await loadLibraryTrack(track.id);
      onSelect(info, track.name);
      onClose();
    } catch (err) {
      setError(String(err));
    } finally {
      setLoadingId(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-4xl h-[80vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-gray-800">
          <h2 className="text-base font-bold">F1 Track Library</h2>
          <span className="text-xs text-gray-500">{data?.length ?? 0} circuits</span>
          <div className="flex-1" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search circuit, city, country…"
            className="bg-gray-800 text-sm px-3 py-1.5 rounded w-64 outline-none focus:ring-1 ring-indigo-500"
          />
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-xl leading-none px-2"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Circuit list */}
          <div className="w-72 shrink-0 border-r border-gray-800 overflow-y-auto">
            {isLoading && (
              <div className="p-4 text-sm text-gray-500">Loading circuits…</div>
            )}
            {filtered.map((t) => (
              <button
                key={t.id}
                onClick={() => setSelectedId(t.id)}
                className={`w-full text-left px-4 py-2.5 border-b border-gray-800/60 transition ${
                  t.id === selectedId ? "bg-indigo-600/30" : "hover:bg-gray-800/60"
                }`}
              >
                <div className="flex items-center gap-2 text-sm font-medium">
                  <span>{t.flag}</span>
                  <span className="truncate">{t.name}</span>
                </div>
                <div className="text-xs text-gray-500">
                  {t.location}, {t.country}
                </div>
              </button>
            ))}
            {!isLoading && filtered.length === 0 && (
              <div className="p-4 text-sm text-gray-500">No circuits match “{query}”.</div>
            )}
          </div>

          {/* Detail panel */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {!selected ? (
              <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
                Select a circuit to see details
              </div>
            ) : (
              <>
                <div className="flex-1 min-h-0 p-3">
                  <Plot
                    data={[
                      {
                        type: "scatter",
                        mode: "lines",
                        x: selected.outline.x,
                        y: selected.outline.y,
                        line: { color: "#818cf8", width: 3 },
                        hoverinfo: "skip",
                      },
                      {
                        type: "scatter",
                        mode: "markers",
                        x: [selected.outline.x[0]],
                        y: [selected.outline.y[0]],
                        marker: { color: "#22c55e", size: 11, symbol: "star" },
                        name: "S/F",
                        hovertemplate: "Start/Finish<extra></extra>",
                      },
                    ]}
                    layout={{
                      paper_bgcolor: "rgba(0,0,0,0)",
                      plot_bgcolor: "rgba(0,0,0,0)",
                      margin: { t: 10, b: 10, l: 10, r: 10 },
                      xaxis: { visible: false, scaleanchor: "y" },
                      yaxis: { visible: false },
                      showlegend: false,
                    }}
                    config={{ responsive: true, displayModeBar: false }}
                    style={{ width: "100%", height: "100%" }}
                    useResizeHandler
                  />
                </div>
                <div className="border-t border-gray-800 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{selected.flag}</span>
                    <div>
                      <div className="font-semibold">{selected.name}</div>
                      <div className="text-xs text-gray-500">
                        {selected.location}, {selected.country}
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm">
                    <DetailRow
                      label="Length"
                      value={
                        selected.official_length_m
                          ? `${selected.official_length_m.toLocaleString()} m`
                          : `${selected.measured_length_m.toLocaleString()} m`
                      }
                    />
                    <DetailRow label="Modelled length" value={`${selected.measured_length_m.toLocaleString()} m`} />
                    <DetailRow label="Opened" value={selected.opened} />
                    <DetailRow label="First GP" value={selected.first_gp} />
                    <DetailRow
                      label="Altitude"
                      value={selected.altitude_m != null ? `${selected.altitude_m} m` : null}
                    />
                  </div>
                  {error && <div className="text-xs text-red-400">{error}</div>}
                  <button
                    onClick={() => handleLoad(selected)}
                    disabled={loadingId === selected.id}
                    className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-sm font-semibold px-4 py-2 rounded transition"
                  >
                    {loadingId === selected.id ? "Loading…" : "Load this track"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
