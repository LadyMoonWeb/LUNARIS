# Lunar Landing Site Navigator

Project for NASA Space Apps 2026, challenge "Lunar Landing Site Navigator".
Stage 1 is a working foundation without terrain. Stage 2 adds terrain (a real
horizon mask and a real panorama picture).

## Rules

- Python and Streamlit only.
- All user interface text, code comments and the README are in English.
  (Chat with the project owner is in Russian.)
- Calculations use skyfield with `de421.bsp` and the `MOON_ME_DE421` frame,
  exactly as in `lunar_drill.py`. The reference for correctness is JPL Horizons
  queried through astroquery.
- Never delete anything and never publish anything (git push, deploy, upload,
  share) without the owner's explicit confirmation.
- No NASA logos or insignia anywhere in the product.
- The README keeps an "AI assistance" section stating that the code was written
  with the help of Claude Code.
- After every step give a short report: what was done, what was checked, what
  comes next.
- After every stage append an entry to `LOG.md`: start and end time, what broke,
  and where the owner's input was needed.
- Site coordinates come only from official sources, and every site carries its
  source in the code. If no official source is found, say so instead of guessing.
- Order of work: calculation and validation first, interface second.

## Layout

| Path | Owner agent | Contents |
| --- | --- | --- |
| `lunarnav/` | calculator | ephemeris, `compute()`, metrics, yearly cache, site list, terrain masks, crater model, energy, radio link |
| `validation/` | verifier | `horizons_check.py`, `illumination_check.py` and their results |
| `data/` | calculator | terrain (`dem/`, not in the repository), horizon masks used by the app (`masks/`; `horizon/` is the older set), 3D patches per site (`site3d/`), reference maps (`reference/`, not in the repository), analysis results, exports |
| `scripts/` | calculator | data download, mask building, 3D patches, export scripts |
| `app.py`, `ui/`, `assets/` | interface | Streamlit app (tabs Sky, Compare, Launch slip, Site, Research, Validation), panorama background, `plate-embed.html` plate (owner's file, do not edit; `galileo-horizon.html` is its earlier version, no longer used), `site3d.html` |
| `REQUIREMENTS.md` | — | checklist against the official challenge text; update statuses when features change |
| `lunar_drill.py` | — | original skyfield documentation example, kept as reference |

Ephemeris kernels (`de421.bsp`, `moon_080317.tf`, `pck00008.tpc`,
`moon_pa_de421_1900-2050.bpc`) live in the project root and are loaded from there.

## Subagents (`.claude/agents/`)

- `calculator` — calculations only (`lunarnav/`).
- `interface` — interface only (`app.py`, `ui/`, `assets/`); never touches calculations.
- `verifier` — only comparisons with independent references: Horizons and published
  illumination maps (`validation/`); never edits product code.

## Key conventions

- `compute(lat, lon, start, end, step, observer_height_m=0, horizon_mask=None,
  antenna_height_m=None, antenna_horizon_mask=None)` is the single entry point for the time series.
- Two heights, both sidebar settings, no hidden defaults: the Sun is judged at the **panel
  height** (`observer_height_m`, `horizon_mask`), the Earth at the **antenna height**
  (`antenna_height_m`, `antenna_horizon_mask`). Without the antenna arguments the Earth
  follows the panel values.
- One scenario (site, landing time, period, two heights, Earth definition) drives every tab,
  the Plate and the 3D view. Defaults: IM-2 Athena, 14 days. The Athena 2025 story lives
  only in the Research tab. A site without terrain never shows another site's terrain.
- Verdict against 6-6.5 days: meets / marginal / short, and "N/A: period shorter than
  requirement" when the analysis period is under 6 days.
- "Sunlit" means the centre of the solar disk is above the local horizon.
- "Earth visible" has two definitions, both always computed: `earth_visible` (centre of the
  disk above the horizon, strict, the default) and `earth_any_visible` (any part of the disk).
  `with_earth_definition(table, "any")` switches a table to the looser one; the sidebar has the choice.
- `horizon_mask` is a pluggable function "azimuth (deg) -> horizon elevation (deg)".
  It defaults to 0 (smooth sphere). Terrain masks come from `lunarnav/terrain.py`
  (720 values, LOLA data, stored in `data/masks/<site key>_h<height>m.json` for every
  preset south of 80 S at heights 0, 1, 2, 5, 10 m); they already contain the observer
  height, so no dip is subtracted from them. Every tab uses them; the sidebar caption
  always says which horizon is in use.
- The app must run without `data/dem/` and with `requirements.txt` only (rasterio and
  scipy are imported lazily and listed in `requirements-dev.txt`); no file in the
  repository may exceed 100 MB.
- In the Site tab the time strip uses the 720-direction masks; shadows, the cell card,
  the ellipse and the Earth ray use per-cell horizons (36 directions, 30 km, eye 2 m)
  and are a visualisation. The caption says so.
- Terrain arithmetic stays in float64: radius plus height in float32 rounds to 0.125 m.
- The horizon is lowered by the dip that corresponds to the observer height above
  the lunar sphere (radius 1737.4 km).
- The one-year series with a 30-minute step is computed once per site and cached
  on disk in `cache/`.
- Validation tolerance against Horizons: 0.01 degrees. If exceeded, stop and
  report to the owner.

## Commands

```bash
streamlit run app.py
python validation/horizons_check.py
python validation/illumination_check.py
python scripts/fetch_terrain.py && python scripts/fetch_near_windows.py
python scripts/build_masks.py && python scripts/build_site3d.py
python scripts/export_athena_panorama.py
python -m pytest tests
```
