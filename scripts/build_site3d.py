"""Static data for the 3D "Site" tab, one file per site south of 80 S.

Writes data/site3d/<site key>.json (about 0.3 MB each):
    heights     3 x 3 km patch of LOLA terrain around the site, 20 m cells, axes east / north
    horizons    for every 40 m cell the horizon elevation in 36 directions (terrain out to 30 km),
                for an eye EYE_M above the ground - used by the page for the shadows and for the
                per-cell numbers

The Sun and Earth positions are not stored here: the app computes them for the
selected date and period and passes them to the page.

    python scripts/build_site3d.py            # all sites that have no file yet
    python scripts/build_site3d.py --force
"""

from __future__ import annotations

import base64
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lunarnav.ephemeris import MOON_RADIUS_M  # noqa: E402
from lunarnav.sites import SITES, SITES_BY_KEY  # noqa: E402
from lunarnav.terrain import (  # noqa: E402
    DATA_DIR, elevation_angle_deg, latlon_to_xy, load_mask, load_site_grids, near_grid_path, terrain_available,
)

OUT_DIR = DATA_DIR / "site3d"
HALF_M = 1500.0
MESH_STEP_M = 20.0
HORIZON_STEP_M = 40.0
AZIMUTHS = 36
EYE_M = 2.0  # height of the eye for the per-cell horizons; shown in the interface
RAY_MAX_M = 30_000.0
HORIZON_OFFSET_DEG, HORIZON_SCALE_DEG = -6.0, 0.08  # byte = (angle - offset) / scale


def build(site) -> dict:
    near, far = load_site_grids(site.lat, site.lon)
    x0, y0 = (float(v) for v in latlon_to_xy(site.lat, site.lon))
    lon = np.radians(site.lon)
    north = np.array([np.sin(lon), np.cos(lon)])  # away from the south pole, in map x / y
    east = np.array([np.cos(lon), -np.sin(lon)])

    def sample(e, n):
        x = x0 + e * east[0] + n * north[0]
        y = y0 + e * east[1] + n * north[1]
        h = near.sample(x, y)
        gaps = ~np.isfinite(h)
        if gaps.any():
            h[gaps] = far.sample(x[gaps], y[gaps])
        return h

    def local(lat, lon_deg):
        x, y = latlon_to_xy(lat, lon_deg)
        d = np.array([float(x) - x0, float(y) - y0])
        return round(float(d @ east), 1), round(float(d @ north), 1)

    axis = np.arange(-HALF_M, HALF_M + 1e-6, MESH_STEP_M)
    e_grid, n_grid = np.meshgrid(axis, axis[::-1])  # rows from north to south, columns from west to east
    heights = sample(e_grid, n_grid)
    low = float(np.nanmin(heights))
    heights = np.where(np.isfinite(heights), heights, low)

    h_axis = np.arange(-HALF_M, HALF_M + 1e-6, HORIZON_STEP_M)
    he, hn = np.meshgrid(h_axis, h_axis[::-1])
    ground = sample(he, hn)
    eye = MOON_RADIUS_M + np.where(np.isfinite(ground), ground, low) + EYE_M
    distances = np.unique(np.round(np.geomspace(15.0, RAY_MAX_M, 60)))
    horizons = np.empty((AZIMUTHS,) + he.shape)
    for k in range(AZIMUTHS):
        az = np.radians(k * 360.0 / AZIMUTHS)
        best = np.full(he.shape, -np.inf)
        for d in distances:
            angle = elevation_angle_deg(eye, MOON_RADIUS_M + sample(he + d * np.sin(az), hn + d * np.cos(az)), d)
            best = np.fmax(best, np.where(np.isfinite(angle), angle, -np.inf))
        horizons[k] = np.where(np.isfinite(best), best, 0.0)
    packed = np.clip(np.round((horizons - HORIZON_OFFSET_DEG) / HORIZON_SCALE_DEG), 0, 255).astype(np.uint8)

    # Check the centre cell against the 720-direction mask of the site at the same eye height.
    check = None
    stored = load_mask(site.key, EYE_M)
    if stored is not None:
        mid = he.shape[0] // 2
        diff = horizons[:, mid, mid] - stored(np.arange(AZIMUTHS) * 360.0 / AZIMUTHS)
        check = {"mean_diff_deg": round(float(diff.mean()), 3), "max_abs_diff_deg": round(float(np.abs(diff).max()), 3)}

    marks = [{"name": site.name.replace(" (Artemis III region)", ""), "note": "selected site", "e": 0.0, "n": 0.0}]
    if site.key == "im2":
        planned = SITES_BY_KEY["im2_planned"]
        e, n = local(planned.lat, planned.lon)
        marks.append({"name": "Planned point", "note": "IM-2 target", "e": e, "n": n})
        crest_file = DATA_DIR / "analysis" / "equipment_height.json"
        if crest_file.exists():
            crest = json.loads(crest_file.read_text(encoding="utf-8"))["crest"]
            e, n = local(crest["lat"], crest["lon"])
            marks.append({"name": "Crest", "note": f"{crest['height_above_athena_m']:+.0f} m", "e": e, "n": n})

    ten_m = near_grid_path(site.lat, site.lon) is not None
    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "site": {"key": site.key, "name": site.name, "lat": site.lat, "lon": site.lon},
        "terrain": ("LOLA 10 m" if ten_m else "LOLA 40 m (no 10 m data here)")
                   + " (PGDA product 90, Barker et al. 2023), resampled to 20 m",
        "half_m": HALF_M, "mesh_step_m": MESH_STEP_M, "mesh_n": int(heights.shape[0]),
        "height_min_m": round(low, 1), "height_range_m": round(float(heights.max()) - low, 1),
        "heights_dm": [int(v) for v in np.round((heights - low) * 10).ravel()],
        "horizon": {"n": int(he.shape[0]), "step_m": HORIZON_STEP_M, "azimuths": AZIMUTHS, "eye_m": EYE_M,
                    "ray_km": RAY_MAX_M / 1000, "offset_deg": HORIZON_OFFSET_DEG, "scale_deg": HORIZON_SCALE_DEG,
                    "order": "azimuth, row (north to south), column (west to east)",
                    "b64": base64.b64encode(packed.tobytes()).decode("ascii")},
        "marks": marks, "centre_check": check,
    }


def main() -> int:
    force = "--force" in sys.argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sites = [s for s in SITES if s.lat <= -80.0 and terrain_available(s.lat, s.lon)]
    if not sites:
        print("No terrain data on disk. Run scripts/fetch_terrain.py first.")
        return 1
    for site in sites:
        out = OUT_DIR / f"{site.key}.json"
        if out.exists() and not force:
            print(f"{site.key:<30} kept")
            continue
        started = time.perf_counter()
        payload = build(site)
        out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        check = payload["centre_check"]
        print(f"{site.key:<30} relief {payload['height_range_m']:5.0f} m   {out.stat().st_size / 1024:4.0f} kB   "
              + (f"centre vs mask: mean {check['mean_diff_deg']:+.2f}, max {check['max_abs_diff_deg']:.2f} deg   "
                 if check else "no mask to compare   ")
              + f"{time.perf_counter() - started:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
