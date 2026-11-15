"""Athena in its crater: horizon and days of sunlight (MODEL).

LROC reports that Athena "ended up on its side within a 20-meter diameter
crater" (https://lroc.im-ldi.com/images/1408). No official source gives the
depth, so a bowl with depth / diameter = 0.1 and 0.2 is carved into a fine copy
of the terrain (see lunarnav/crater.py). Everything in the "crater" rows is a
model, not measured terrain.

    python scripts/athena_crater.py

Writes data/analysis/athena_crater.json and stores the masks in data/horizon/.
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

from lunarnav import apply_visibility, positions  # noqa: E402
from lunarnav.crater import mask_with_crater  # noqa: E402
from lunarnav.energy import sunlit_days  # noqa: E402
from lunarnav.sites import SITES_BY_KEY  # noqa: E402
from lunarnav.terrain import HORIZON_DIR, load_site_grids  # noqa: E402

SITE = SITES_BY_KEY["im2"]
CRATER_DIAMETER_M = 20.0
CRATER_SOURCE = "LROC, 'IM-2 Athena Seen Obliquely' (10 Mar 2025): 'within a 20-meter diameter crater'"
DEPTH_RATIOS = [0.1, 0.2]  # assumed; no official depth was found

# Heights above the crater floor (or above the ground on the plateau).
HEIGHTS = {
    0.0: "on the floor",
    0.8: "lander on its side, mid-body (width 1.57 m)",
    1.6: "lander on its side, upper side",
    4.0: "lander upright, top deck (height 4.0 m)",
}
LANDER_SIZE_SOURCE = ("NASA NSSDC entry for IM-1 as returned by web search ('hexagonal cylinder, 4.0 meters tall and "
                      "1.57 meters wide'); the NSSDC page itself returned an error when read directly")

LANDING = pd.Timestamp("2025-03-06 17:30", tz="UTC")
WINDOWS = {
    "actual (12.75 h)": pd.Timestamp("2025-03-07 06:15", tz="UTC"),
    "planned (10 d)": LANDING + pd.Timedelta(days=10),
    "lunar day (29.5 d)": LANDING + pd.Timedelta(days=29.5),
}
STEP = "10min"


def main() -> int:
    near, far = load_site_grids(SITE.lat, SITE.lon)
    times = pd.date_range(LANDING, max(WINDOWS.values()), freq=STEP)
    base = positions(SITE.lat, SITE.lon, times)

    cases = [("plateau, no crater", 0.0)] + [(f"MODEL crater, depth/diameter {r:g} (depth {r * CRATER_DIAMETER_M:g} m)", r)
                                             for r in DEPTH_RATIOS]
    rows = []
    print(f"Site: {SITE.name} ({SITE.lat}, {SITE.lon}). Crater diameter {CRATER_DIAMETER_M:g} m: {CRATER_SOURCE}")
    print(f"{'case':<46} {'height':>6}  {'horizon min/mean/max, deg':>26}  " + "  ".join(f"{w:>18}" for w in WINDOWS))
    for label, ratio in cases:
        for height, meaning in HEIGHTS.items():
            mask = mask_with_crater(SITE.lat, SITE.lon, height, near, far,
                                    CRATER_DIAMETER_M if ratio else 0.0, ratio)
            mask.meta.update(site_key=SITE.key, site_name=SITE.name)
            tag = f"crater{ratio:g}".replace(".", "p") if ratio else "plateau_fine"
            mask.save(HORIZON_DIR / "models" / f"im2_{tag}_h{height:g}m.json")
            table = apply_visibility(base, height, mask)
            days = {}
            for name, end in WINDOWS.items():
                part = table[table["time_utc"] <= end]
                days[name] = {"centre_days": round(sunlit_days(part), 3),
                              "disk_weighted_days": round(sunlit_days(part, weighted=True), 3)}
            rows.append({
                "case": label, "model": bool(ratio), "depth_ratio": ratio, "depth_m": ratio * CRATER_DIAMETER_M,
                "observer_height_m": height, "height_meaning": meaning,
                "horizon_min_deg": round(float(mask.mask_deg.min()), 2),
                "horizon_mean_deg": round(float(mask.mask_deg.mean()), 2),
                "horizon_max_deg": round(float(mask.mask_deg.max()), 2),
                "sun_days": days,
            })
            print(f"{label:<46} {height:>5g}m  {mask.mask_deg.min():>7.2f} {mask.mask_deg.mean():>7.2f} {mask.mask_deg.max():>7.2f}   "
                  + "  ".join(f"{days[w]['centre_days']:>8.2f} /{days[w]['disk_weighted_days']:>7.2f}" for w in WINDOWS))

    sun = base[base["time_utc"] <= WINDOWS["lunar day (29.5 d)"]]["sun_alt_deg"]
    print(f"\nSun altitude over the lunar day from touchdown: {sun.min():.2f} .. {sun.max():.2f} deg "
          f"(at touchdown {sun.iloc[0]:.2f} deg). Days: centre of the disk above the horizon / disk-weighted.")

    out = ROOT / "data" / "analysis" / "athena_crater.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "warning": "The crater rows are a MODEL: a parabolic bowl without a raised rim carved into the terrain. "
                   "Only the 20 m diameter is from an official source; the depth is assumed.",
        "site": {"name": SITE.name, "lat": SITE.lat, "lon": SITE.lon},
        "crater_diameter_m": CRATER_DIAMETER_M, "crater_diameter_source": CRATER_SOURCE,
        "depth_ratios_assumed": DEPTH_RATIOS, "lander_size_source": LANDER_SIZE_SOURCE,
        "landing_utc": LANDING.isoformat(), "windows_end_utc": {k: v.isoformat() for k, v in WINDOWS.items()},
        "step": STEP, "sun_altitude_range_lunar_day_deg": [round(float(sun.min()), 2), round(float(sun.max()), 2)],
        "rows": rows,
    }, indent=1), encoding="utf-8")
    print(f"Written {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
