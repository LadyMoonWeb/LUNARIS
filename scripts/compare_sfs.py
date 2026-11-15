"""Compare the 5 m shape-from-shading (SFS) model with the LOLA terrain in use.

The SFS tile for Leibnitz Beta Plateau (PGDA product 104) covers map
x 65..81 km, y 110..126 km. The Athena site lies at y = 138 km, 12 km outside
it, so the tile cannot show Athena's crater. What can be compared:

1. heights of the two models where they overlap;
2. the Athena horizon mask when the SFS tile replaces LOLA along the rays that
   cross it (it lies 12 to 29 km south of the site);
3. the horizon mask of a point inside the tile, computed from each model.

    python scripts/compare_sfs.py     ->  data/analysis/sfs_comparison.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lunarnav.sites import SITES_BY_KEY  # noqa: E402
from lunarnav.terrain import (  # noqa: E402
    DEM_DIR, FAR_DEM, FAR_STEP_M, MAX_RANGE_M, NEAR_RANGE_M, NEAR_STEP_M, HORIZON_DIR,
    latlon_to_xy, load_mask, load_site_grids, mask_from_tiers, read_grid, xy_to_latlon,
)

SFS = DEM_DIR / "sfs_leibnitz_beta" / "A310_GLDELEV_005.tif"
SIGMA = DEM_DIR / "sfs_leibnitz_beta" / "A310_GLDSIGM_005.tif"
ATHENA = SITES_BY_KEY["im2"]


def stats(a) -> dict:
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    return {"mean": round(float(a.mean()), 3), "std": round(float(a.std()), 3),
            "abs_p50": round(float(np.percentile(np.abs(a), 50)), 3),
            "abs_p95": round(float(np.percentile(np.abs(a), 95)), 3), "abs_max": round(float(np.abs(a).max()), 3)}


def main() -> int:
    sfs = read_grid(SFS)
    sigma = read_grid(SIGMA)
    sigma.heights[sigma.heights < 0] = np.nan
    rows, cols = sfs.heights.shape
    x_min, x_max = sfs.x_left, sfs.x_left + cols * sfs.pixel_m
    y_max, y_min = sfs.y_top, sfs.y_top - rows * sfs.pixel_m
    ax, ay = latlon_to_xy(ATHENA.lat, ATHENA.lon)
    inside = sfs.contains(float(ax), float(ay))
    print(f"SFS tile: x {x_min/1e3:.0f}..{x_max/1e3:.0f} km, y {y_min/1e3:.0f}..{y_max/1e3:.0f} km, 5 m/pixel")
    print(f"Athena at x {ax/1e3:.2f}, y {ay/1e3:.2f} km -> inside the tile: {inside}; "
          f"distance to the tile: {(ay - y_max)/1e3:.1f} km")

    # 1. Height differences on a regular lattice of the overlap (every 25 m).
    xs = np.arange(x_min + 12.5, x_max, 25.0)
    ys = np.arange(y_min + 12.5, y_max, 25.0)
    gx, gy = np.meshgrid(xs, ys)
    far = read_grid(FAR_DEM, (x_min - 500, y_min - 500, x_max + 500, y_max + 500))
    near, far_site = load_site_grids(ATHENA.lat, ATHENA.lon)
    d_far = sfs.sample(gx, gy) - far.sample(gx, gy)
    print(f"SFS minus LOLA 40 m (whole tile):      mean {np.nanmean(d_far):+.2f} m, std {np.nanstd(d_far):.2f} m, "
          f"95 % within {np.nanpercentile(np.abs(d_far), 95):.2f} m, max {np.nanmax(np.abs(d_far)):.1f} m")
    d_near = sfs.sample(gx, gy) - near.sample(gx, gy)
    share = float(np.isfinite(d_near).mean())
    if share > 0:
        print(f"SFS minus LOLA 10 m ({share:.0%} of the tile): mean {np.nanmean(d_near):+.2f} m, "
              f"std {np.nanstd(d_near):.2f} m, 95 % within {np.nanpercentile(np.abs(d_near), 95):.2f} m")
    print(f"SFS own uncertainty map: median {np.nanmedian(sigma.heights):.2f} m, "
          f"95 % below {np.nanpercentile(sigma.heights[np.isfinite(sigma.heights)], 95):.2f} m")

    # 2. Athena mask with the SFS tile used along the rays that cross it.
    result = {"athena_masks": {}}
    for height in (0.0, 2.0):
        current = load_mask("im2", height)
        with_sfs = mask_from_tiers(ATHENA.lat, ATHENA.lon, height,
                                   [(near, 11_900.0, NEAR_STEP_M), (sfs, 30_000.0, 5.0), (far_site, MAX_RANGE_M, FAR_STEP_M)],
                                   label="LOLA 10 m to 11.9 km, SFS 5 m where it covers 11.9-30 km, LOLA 40 m elsewhere")
        diff = with_sfs.mask_deg - current.mask_deg
        changed = np.abs(diff) > 0.005
        # Azimuths whose ray crosses the tile at all.
        az = current.azimuth_deg
        print(f"Athena mask, observer {height:g} m: SFS changes {int(changed.sum())} of 720 azimuths; "
              f"largest change {diff[np.abs(diff).argmax()]:+.3f} deg at azimuth {az[np.abs(diff).argmax()]:.1f}, "
              f"mean change where changed {diff[changed].mean() if changed.any() else 0:+.3f} deg")
        with_sfs.meta.update(site_key="im2", site_name=ATHENA.name)
        with_sfs.save(HORIZON_DIR / "models" / f"im2_with_sfs_h{height:g}m.json")
        result["athena_masks"][f"{height:g}"] = {
            "azimuths_changed": int(changed.sum()), "max_change_deg": round(float(diff[np.abs(diff).argmax()]), 4),
            "azimuth_of_max_change_deg": float(az[np.abs(diff).argmax()]),
            "all": stats(diff), "changed_only": stats(diff[changed]) if changed.any() else None}

    # 3. A point inside the tile: mask from SFS (5 m) against mask from LOLA (40 m) near the point.
    cx, cy = (x_min + x_max) / 2, (y_min + y_max) / 2
    c_lat, c_lon = (float(v) for v in xy_to_latlon(cx, cy))
    reach = MAX_RANGE_M * 1.01 + 2000
    far_c = read_grid(FAR_DEM, (cx - reach, cy - reach, cx + reach, cy + reach))
    for height in (2.0,):
        m_sfs = mask_from_tiers(c_lat, c_lon, height, [(sfs, 7000.0, 5.0), (far_c, MAX_RANGE_M, FAR_STEP_M)])
        m_lola = mask_from_tiers(c_lat, c_lon, height, [(far_c, 7000.0, 10.0), (far_c, MAX_RANGE_M, FAR_STEP_M)])
        diff = m_sfs.mask_deg - m_lola.mask_deg
        print(f"Tile centre ({c_lat:.4f}, {c_lon:.4f}), observer {height:g} m: mask from SFS 5 m minus mask from "
              f"LOLA 40 m: mean {diff.mean():+.3f} deg, 95 % within {np.percentile(np.abs(diff), 95):.3f} deg, "
              f"max {np.abs(diff).max():.3f} deg")
        result["tile_centre"] = {"lat": c_lat, "lon": c_lon, "observer_height_m": height, "sfs_minus_lola40": stats(diff)}

    result.update({
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "sfs_tile_km": {"x": [x_min / 1e3, x_max / 1e3], "y": [y_min / 1e3, y_max / 1e3], "pixel_m": sfs.pixel_m},
        "athena_xy_km": [round(float(ax) / 1e3, 2), round(float(ay) / 1e3, 2)],
        "athena_inside_tile": bool(inside), "athena_distance_to_tile_km": round(float(ay - y_max) / 1e3, 2),
        "crater_visible": False,
        "crater_note": "The tile does not cover the Athena site, so its 20 m crater cannot be looked for. "
                       "At 5 m/pixel such a crater would span 4 pixels in any case.",
        "height_difference_sfs_minus_lola40_m": stats(d_far),
        "height_difference_sfs_minus_lola10_m": stats(d_near) if share > 0 else None,
        "sfs_uncertainty_m": {"median": round(float(np.nanmedian(sigma.heights)), 3),
                              "p95": round(float(np.nanpercentile(sigma.heights[np.isfinite(sigma.heights)], 95)), 3)},
    })
    out = ROOT / "data" / "analysis" / "sfs_comparison.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"Written {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
