import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteSavedSweep,
  getSavedSweep,
  listSavedSweeps,
  type SweepResult,
} from "../api/client";

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (result: SweepResult) => void;
}

export default function SavedSweepsModal({ open, onClose, onSelect }: Props) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error: queryError } = useQuery({
    queryKey: ["saved-sweeps"],
    queryFn: listSavedSweeps,
    enabled: open,
  });

  if (!open) return null;

  const handleLoad = async (sweepId: string) => {
    setBusyId(sweepId);
    setError("");
    try {
      onSelect(await getSavedSweep(sweepId));
      onClose();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (sweepId: string) => {
    setBusyId(sweepId);
    setError("");
    try {
      await deleteSavedSweep(sweepId);
      queryClient.invalidateQueries({ queryKey: ["saved-sweeps"] });
    } catch (err) {
      setError(String(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-5 py-3 border-b border-gray-800">
          <h2 className="text-base font-bold">Saved Sweeps</h2>
          <span className="text-xs text-gray-500">{data?.length ?? 0} saved</span>
          <div className="flex-1" />
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-xl leading-none px-2"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading && <div className="p-4 text-sm text-gray-500">Loading…</div>}
          {isError && (
            <div className="p-4 text-sm text-red-400">
              Failed to list saved sweeps.
              <div className="mt-1 text-xs text-red-300/80 break-words">{String(queryError)}</div>
            </div>
          )}
          {data?.map((info) => (
            <div
              key={info.sweep_id}
              className="flex items-center gap-4 px-5 py-3 border-b border-gray-800/60 hover:bg-gray-800/40 transition"
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">
                  {info.track_name}
                  <span className="text-gray-500 font-normal"> · {info.param_names.join(", ")}</span>
                </div>
                <div className="text-xs text-gray-500">
                  {new Date(info.created_at).toLocaleString()} · {info.solver} ·{" "}
                  {info.mode === "grid" ? "grid" : "one-at-a-time"} · {info.n_runs} runs
                  {info.best_lap_time_s != null && (
                    <span className="text-green-400"> · best {info.best_lap_time_s.toFixed(3)} s</span>
                  )}
                </div>
              </div>
              <button
                onClick={() => handleLoad(info.sweep_id)}
                disabled={busyId === info.sweep_id}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-xs font-semibold px-3 py-1.5 rounded transition"
              >
                Load
              </button>
              <button
                onClick={() => handleDelete(info.sweep_id)}
                disabled={busyId === info.sweep_id}
                className="bg-gray-800 hover:bg-red-900/60 text-gray-400 hover:text-red-300 text-xs px-3 py-1.5 rounded transition"
                title="Delete this saved sweep"
              >
                Delete
              </button>
            </div>
          ))}
          {data && data.length === 0 && (
            <div className="p-4 text-sm text-gray-500">
              No saved sweeps yet — run a parameter sweep and it will be saved automatically.
            </div>
          )}
        </div>

        {error && <div className="px-5 py-2 text-xs text-red-400 border-t border-gray-800">{error}</div>}
      </div>
    </div>
  );
}
