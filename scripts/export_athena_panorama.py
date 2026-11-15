"""Export the Athena panorama data for the art screen.

Writes data/athena_panorama.json with
    mask_deg   720 horizon elevations (azimuth 0, 0.5, ... 359.5 degrees, from
               north through east) seen from the Athena landing site
    windows    paths of the Sun and the Earth (time, azimuth, altitude) with a
               30-minute step for three time windows:
                 actual     touchdown to the declared end of the mission
                 planned    touchdown plus the planned surface operations
                 lunar_day  touchdown plus one synodic month (29.5 days)

    python scripts/export_athena_panorama.py            # observer 2 m above the ground
    python scripts/export_athena_panorama.py --height 0
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lunarnav import compute  # noqa: E402
from lunarnav.sites import SITES_BY_KEY  # noqa: E402
from lunarnav.terrain import AZIMUTH_STEP_DEG, get_mask  # noqa: E402

SITE_KEY = "im2"
OUTPUT = ROOT / "data" / "athena_panorama.json"
STEP_MINUTES = 30

# Mission dates, each with its official source.
LANDING_UTC = pd.Timestamp("2025-03-06 17:30", tz="UTC")
LANDING_SOURCE = (
    "Intuitive Machines news release, 6 Mar 2025: Athena landed 'at approximately 11:30 a.m. CST' "
    "(= 17:30 UTC); NASA release 7 Mar 2025: 'touched down at approximately 11:30 a.m. March 6'"
)
END_UTC = pd.Timestamp("2025-03-07 06:15", tz="UTC")
END_SOURCE = (
    "NASA news release, 7 Mar 2025, 'NASA Receives Some Data Before Intuitive Machines Ends Lunar Mission': "
    "'an early end of mission at 12:15 a.m. CST Friday' (= 06:15 UTC, 7 Mar 2025)"
)
PLANNED_DAYS = 10
PLANNED_SOURCE = (
    "NASA CLPS IM-2 press kit (NP-2025-02-005-JSC), Major Mission Milestones and Timeline: "
    "'Surface Operations: Approximately 10 days'"
)
LUNAR_DAY_DAYS = 29.5
LUNAR_DAY_SOURCE = "One synodic month (29.5 days) from touchdown, for animation; not a mission date."


def body_path(table: pd.DataFrame, body: str, flag: str) -> list:
    path = [
        {
            "time_utc": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "az_deg": round(float(az), 3),
            "alt_deg": round(float(alt), 3),
            "above_horizon": bool(up),
        }
        for stamp, az, alt, up in zip(table["time_utc"], table[f"{body}_az_deg"], table[f"{body}_alt_deg"], table[flag])
    ]
    if body == "earth":  # both definitions of "Earth visible", and the size of the disk for drawing it
        for point, any_part, radius in zip(path, table["earth_any_visible"], table["earth_radius_deg"]):
            point["any_part_above_horizon"] = bool(any_part)
            point["radius_deg"] = round(float(radius), 3)
    return path


def window(site, mask, height: float, end: pd.Timestamp, source: str) -> dict:
    table = compute(site.lat, site.lon, LANDING_UTC, end, STEP_MINUTES, observer_height_m=height, horizon_mask=mask)
    if table["time_utc"].iloc[-1] < end:  # the end does not fall on the 30-minute grid: add it
        last = compute(site.lat, site.lon, end, end, STEP_MINUTES, observer_height_m=height, horizon_mask=mask)
        table = pd.concat([table, last], ignore_index=True)
    return {
        "start_utc": LANDING_UTC.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_utc": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "step_minutes": STEP_MINUTES,
        "samples": int(len(table)),
        "source": source,
        "sun": body_path(table, "sun", "sunlit"),
        "earth": body_path(table, "earth", "earth_visible"),
    }


def main() -> int:
    height = 2.0
    if "--height" in sys.argv:
        height = float(sys.argv[sys.argv.index("--height") + 1])

    site = SITES_BY_KEY[SITE_KEY]
    mask = get_mask(site.key, site.lat, site.lon, height)
    if mask is None:
        print("No terrain mask for the Athena site. Run scripts/fetch_terrain.py and scripts/build_masks.py.")
        return 1

    payload = {
        "description": "Horizon mask and Sun / Earth paths seen from the IM-2 Athena landing site.",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site": {
            "name": site.name,
            "lat_deg": site.lat,
            "lon_deg": site.lon,
            "coordinate_source": site.source,
            "coordinate_source_url": site.source_url,
            "height_above_reference_sphere_m": mask.meta.get("site_height_m"),
        },
        "observer_height_m": height,
        "conventions": {
            "azimuth": "degrees from north through east, 0..360",
            "altitude": "degrees above the local horizontal plane",
            "frame": "MOON_ME_DE421 (Mean Earth / Polar Axis), JPL DE421 ephemeris, apparent positions",
            "above_horizon": "centre of the body is above the terrain horizon (mask_deg) in its direction",
            "any_part_above_horizon": "Earth only: the upper edge of the disk (alt_deg + radius_deg) is above "
                                      "the terrain horizon in the direction of its centre",
            "radius_deg": "Earth only: angular radius of the Earth's disk",
            "time": "UTC",
        },
        "mask": {
            "azimuth_start_deg": 0.0,
            "azimuth_step_deg": AZIMUTH_STEP_DEG,
            "count": len(mask.mask_deg),
            "ray_length_km": mask.meta.get("ray_length_km"),
            "near_dem": mask.meta.get("near_dem"),
            "far_dem": mask.meta.get("far_dem"),
            "dem_source": mask.meta.get("dem_source"),
            "note": "Athena rests in a crater about 20 m across. The 10 m elevation grid does not resolve "
                    "it, so the mask is the horizon of the landing area, not the view from the crater floor.",
        },
        "mask_deg": [round(float(v), 4) for v in mask.mask_deg],
        "horizon_distance_km": None if mask.distance_km is None else [round(float(v), 2) for v in mask.distance_km],
        "landing_source": LANDING_SOURCE,
        "windows": {
            "actual": window(site, mask, height, END_UTC, END_SOURCE),
            "planned": window(site, mask, height, LANDING_UTC + pd.Timedelta(days=PLANNED_DAYS), PLANNED_SOURCE),
            "lunar_day": window(site, mask, height, LANDING_UTC + pd.Timedelta(days=LUNAR_DAY_DAYS), LUNAR_DAY_SOURCE),
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"Written {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size / 1024:.0f} kB)")
    for name, data in payload["windows"].items():
        sun_up = sum(p["above_horizon"] for p in data["sun"])
        earth_up = sum(p["above_horizon"] for p in data["earth"])
        earth_any = sum(p["any_part_above_horizon"] for p in data["earth"])
        print(f"  {name:<10} {data['samples']:5d} samples   Sun above horizon {sun_up:5d}   "
              f"Earth: centre {earth_up:5d}, any part {earth_any:5d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
