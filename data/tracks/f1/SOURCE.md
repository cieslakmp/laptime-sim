# F1 circuit geometry data

`f1-circuits.geojson` contains centreline traces and metadata for 40 Formula 1
circuits.

- **Source:** [bacinger/f1-circuits](https://github.com/bacinger/f1-circuits)
- **License:** Open Database License (ODbL) — the geometry is derived from
  OpenStreetMap. Attribution: © OpenStreetMap contributors.

Each GeoJSON feature is a `LineString` of `[lon, lat]` coordinates (the track
centreline) with `properties`: `id`, `Name`, `Location`, `length` (official, m),
`opened`, `firstgp`, `altitude`.

The app projects each trace onto a local tangent plane (metres) and fits the
same arc-length spline used for uploaded tracks — see
`laptime/track/library.py`.
