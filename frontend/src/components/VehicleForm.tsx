import React from "react";
import type { VehicleParams } from "../api/client";

interface Props {
  value: VehicleParams;
  onChange: (v: VehicleParams) => void;
}

interface SliderDef {
  key: keyof VehicleParams;
  label: string;
  min: number;
  max: number;
  step: number;
  unit: string;
}

const SLIDERS: SliderDef[] = [
  { key: "mass_kg", label: "Mass", min: 200, max: 1500, step: 10, unit: "kg" },
  { key: "p_max_kw", label: "Peak Power", min: 50, max: 1000, step: 10, unit: "kW" },
  { key: "f_brake_max_n", label: "Brake Force", min: 5000, max: 50000, step: 500, unit: "N" },
  { key: "mu_y", label: "Lateral Friction (μy)", min: 0.8, max: 3.0, step: 0.05, unit: "g" },
  { key: "mu_x", label: "Long. Friction (μx)", min: 0.8, max: 3.0, step: 0.05, unit: "g" },
  { key: "cl", label: "Downforce Coeff (Cl·A)", min: 0, max: 8, step: 0.1, unit: "m²" },
  { key: "cd", label: "Drag Coeff (Cd·A)", min: 0.2, max: 3.0, step: 0.05, unit: "m²" },
  { key: "v_max_ms", label: "Top Speed", min: 30, max: 120, step: 1, unit: "m/s" },
];

export default function VehicleForm({ value, onChange }: Props) {
  const set = (key: keyof VehicleParams, v: number) =>
    onChange({ ...value, [key]: v });

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
        Vehicle Parameters
      </h2>
      {SLIDERS.map(({ key, label, min, max, step, unit }) => (
        <div key={key}>
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>{label}</span>
            <span className="font-mono text-gray-200">
              {(value[key] as number).toFixed(step < 1 ? 2 : 0)} {unit}
            </span>
          </div>
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={value[key] as number}
            onChange={(e) => set(key, parseFloat(e.target.value))}
            className="w-full h-1.5 rounded bg-gray-700 accent-indigo-400"
          />
        </div>
      ))}
    </div>
  );
}
