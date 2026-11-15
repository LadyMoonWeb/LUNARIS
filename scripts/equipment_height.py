"""How much does the height of the panels and of the antenna matter?

Two places are compared: the Athena landing point on the plateau and the
highest ground nearby (the local crest 716 m away, 37 m higher, found in the
10 m LOLA grid). Panels and antenna are treated separately: sunlight is judged
with the horizon at the panel height, Earth visibility with the horizon at the
antenna height. Heights: 0, 1, 2, 5 and 10 m.

Metrics over one year from the Athena touchdown, 30-minute step:
    share of time with Sun and Earth together
    longest continuous gap without "Sun and Earth together"

    python scripts/equipment_height.py   ->  data/analysis/equipment_height.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lunarnav import positions  # noqa: E402
from lunarnav.compute import EARTH_MEAN_RADIUS_DEG  # noqa: E402
from lunarnav.sites import SITES_BY_KEY  # noqa: E402
from lunarnav.terrain import HORIZON_DIR, latlon_to_xy, load_site_grids, mask_from_grids, xy_to_latlon  # noqa: E402

ATHENA = SITES_BY_KEY["im2"]
HEIGHTS = [0.0, 1.0, 2.0, 5.0, 10.0]
START = pd.Timestamp("2025-03-06 17:30", tz="UTC")
DAYS = 365
STEP = "30min"
CREST_SEARCH_RADIUS_M = 5000.0


def find_crest(near) -> tuple:
    """Highest cell of the 10 m grid within the search radius of Athena."""
    x0, y0 = latlon_to_xy(ATHENA.lat, ATHENA.lon)
    rows, cols = np.indices(near.heights.shape)
    xs = near.x_left + (cols + 0.5) * near.pixel_m
    ys = near.y_top - (rows + 0.5) * near.pixel_m
    distance = np.hypot(xs - x0, ys - y0)
    r, c = np.unravel_index(np.argmax(np.where(distance <= CREST_SEARCH_RADIUS_M, near.heights, -np.inf)), near.heights.shape)
    lat, lon = xy_to_latlon(xs[r, c], ys[r, c])
    return float(lat), float(lon), float(near.heights[r, c]), float(distance[r, c])


def longest_true_run_days(flags: np.ndarray, step_days: float) -> float:
    best = run = 0
    for value in flags:
        run = run + 1 if value else 0
        best = max(best, run)
    return best * step_days


def analyse(name: str, lat: float, lon: float, near, far, times) -> dict:
    table = positions(lat, lon, times)
    radius = table["earth_radius_deg"].to_numpy() if "earth_radius_deg" in table else EARTH_MEAN_RADIUS_DEG
    step_days = pd.Timedelta(STEP) / pd.Timedelta(days=1)
    sun_up, earth_up, earth_any = {}, {}, {}
    for height in HEIGHTS:
        mask = mask_from_grids(lat, lon, height, near, far)
        mask.meta.update(site_name=name)
        mask.save(HORIZON_DIR / "models" / f"{name.lower().replace(' ', '_')}_h{height:g}m.json")
        sun_up[height] = (table["sun_alt_deg"].to_numpy() - mask(table["sun_az_deg"].to_numpy())) > 0
        earth_clear = table["earth_alt_deg"].to_numpy() - mask(table["earth_az_deg"].to_numpy())
        earth_up[height] = earth_clear > 0
        earth_any[height] = earth_clear + radius > 0

    both_pct = [[round(100 * float((sun_up[p] & earth_up[a]).mean()), 1) for a in HEIGHTS] for p in HEIGHTS]
    gap_days = [[round(longest_true_run_days(~(sun_up[p] & earth_up[a]), step_days), 1) for a in HEIGHTS] for p in HEIGHTS]
    both_any_pct = [[round(100 * float((sun_up[p] & earth_any[a]).mean()), 1) for a in HEIGHTS] for p in HEIGHTS]
    return {
        "name": name, "lat": lat, "lon": lon,
        "sun_pct_by_panel_height": {f"{h:g}": round(100 * float(sun_up[h].mean()), 1) for h in HEIGHTS},
        "earth_pct_by_antenna_height": {f"{h:g}": round(100 * float(earth_up[h].mean()), 1) for h in HEIGHTS},
        "earth_any_part_pct_by_antenna_height": {f"{h:g}": round(100 * float(earth_any[h].mean()), 1) for h in HEIGHTS},
        "longest_dark_gap_days_by_panel_height": {f"{h:g}": round(longest_true_run_days(~sun_up[h], step_days), 1) for h in HEIGHTS},
        "longest_no_earth_gap_days_by_antenna_height": {f"{h:g}": round(longest_true_run_days(~earth_up[h], step_days), 1) for h in HEIGHTS},
        "both_pct_rows_panel_cols_antenna": both_pct,
        "longest_gap_days_rows_panel_cols_antenna": gap_days,
        "both_pct_earth_any_part_rows_panel_cols_antenna": both_any_pct,
    }


def show(result: dict) -> None:
    print(f"\n{result['name']} ({result['lat']:.5f}, {result['lon']:.5f})")
    print("  Sun, % of time by panel height:      " + "  ".join(f"{h:g} m: {v:5.1f}" for h, v in zip(HEIGHTS, result["sun_pct_by_panel_height"].values())))
    print("  Earth, % of time by antenna height:  " + "  ".join(f"{h:g} m: {v:5.1f}" for h, v in zip(HEIGHTS, result["earth_pct_by_antenna_height"].values())))
    print("  longest dark gap, days:              " + "  ".join(f"{h:g} m: {v:5.1f}" for h, v in zip(HEIGHTS, result["longest_dark_gap_days_by_panel_height"].values())))
    print("  longest gap without Earth, days:     " + "  ".join(f"{h:g} m: {v:5.1f}" for h, v in zip(HEIGHTS, result["longest_no_earth_gap_days_by_antenna_height"].values())))
    print("  Sun and Earth together, % of time (rows: panel height, columns: antenna height " + ", ".join(f"{h:g}" for h in HEIGHTS) + " m)")
    for h, row in zip(HEIGHTS, result["both_pct_rows_panel_cols_antenna"]):
        print(f"    panels {h:>4g} m: " + "  ".join(f"{v:5.1f}" for v in row))
    print("  longest gap without both, days")
    for h, row in zip(HEIGHTS, result["longest_gap_days_rows_panel_cols_antenna"]):
        print(f"    panels {h:>4g} m: " + "  ".join(f"{v:5.1f}" for v in row))


def main() -> int:
    near, far = load_site_grids(ATHENA.lat, ATHENA.lon)
    times = pd.date_range(START, START + pd.Timedelta(days=DAYS), freq=STEP)
    c_lat, c_lon, c_height, c_distance = find_crest(near)
    a_height = float(near.sample(*[np.array([v]) for v in latlon_to_xy(ATHENA.lat, ATHENA.lon)])[0])
    print(f"Crest: highest 10 m cell within {CREST_SEARCH_RADIUS_M / 1000:g} km of Athena: {c_lat:.5f}, {c_lon:.5f}, "
          f"{c_distance:.0f} m away, {c_height - a_height:+.1f} m relative to Athena ({c_height:.1f} m against {a_height:.1f} m)")

    results = [analyse("Athena plateau", ATHENA.lat, ATHENA.lon, near, far, times),
               analyse("Athena nearby crest", c_lat, c_lon, near, far, times)]
    for result in results:
        show(result)

    clones = ("No. PGDA product 78 offers 100 terrain realisations ('clones') only for its 5 m site tiles; the nearest "
              "one, Site20v2 (Leibnitz beta plateau, map y up to 131 km), ends 7 km short of the Athena site "
              "(y = 138 km). No spread band can be given for this area.")
    print("\n100 PGDA terrain variants for this area: " + clones)

    out = ROOT / "data" / "analysis" / "equipment_height.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "period": {"start_utc": START.isoformat(), "days": DAYS, "step": STEP},
        "heights_m": HEIGHTS,
        "definitions": "Sun: centre of the disk above the terrain horizon at the panel height. Earth: centre of the "
                       "disk above the terrain horizon at the antenna height ('any part' given separately).",
        "crest": {"lat": c_lat, "lon": c_lon, "distance_from_athena_m": round(c_distance, 0),
                  "height_above_athena_m": round(c_height - a_height, 1),
                  "how_found": f"highest cell of the 10 m LOLA grid within {CREST_SEARCH_RADIUS_M / 1000:g} km of Athena; "
                               "a terrain feature picked from the data, not a named site"},
        "pgda_terrain_variants": clones,
        "sites": results,
    }, indent=1), encoding="utf-8")
    print(f"Written {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
