"""Compute and store the terrain horizon masks used by the app.

For every preset site south of 80 S a mask of 720 horizon angles is computed
for each offered height (0, 1, 2, 5 and 10 m) and written to
data/masks/<site>_h<height>m.json. The app needs only these small files, not
the elevation data. Masks that already exist are kept; --force recomputes.

    python scripts/build_masks.py
    python scripts/build_masks.py --force
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lunarnav.sites import SITES  # noqa: E402
from lunarnav.terrain import (  # noqa: E402
    MASK_HEIGHTS_M, MASKS_DIR, compute_mask, load_site_grids, mask_path, near_grid_path, terrain_available,
)


def main() -> int:
    force = "--force" in sys.argv
    sites = [site for site in SITES if site.lat <= -80.0 and terrain_available(site.lat, site.lon)]
    if not sites:
        print("No terrain data on disk. Run scripts/fetch_terrain.py first.")
        return 1
    MASKS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"{len(sites)} sites south of 80 S, heights {', '.join(f'{h:g}' for h in MASK_HEIGHTS_M)} m -> {MASKS_DIR.relative_to(ROOT)}")
    for site in sites:
        todo = [h for h in MASK_HEIGHTS_M if force or not mask_path(site.key, h).exists()]
        if not todo:
            print(f"{site.key:<30} kept")
            continue
        started = time.perf_counter()
        grids = load_site_grids(site.lat, site.lon)
        near = "10 m" if near_grid_path(site.lat, site.lon) is not None else "40 m (no 10 m window)"
        ranges = []
        for height in todo:
            mask = compute_mask(site.lat, site.lon, height, grids)
            mask.meta.update(site_key=site.key, site_name=site.name, coordinate_source=site.source)
            mask.save(mask_path(site.key, height))
            ranges.append(f"{height:g} m: {mask.mask_deg.min():+.1f}..{mask.mask_deg.max():+.1f}")
        missing = mask.meta["share_of_samples_without_data"]
        print(f"{site.key:<30} near {near:<22} no data {missing:6.1%}   " + "  ".join(ranges)
              + f"   {time.perf_counter() - started:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
