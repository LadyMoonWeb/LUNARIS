"""Cut 10 m terrain windows for every preset site south of 80 S.

Each window is 32 x 32 km around a site, read from the remote cloud-optimised
GeoTIFF LDEM_83S_10MPP_ADJ.TIF (PGDA product 90) with HTTP range requests, about
20 MB per site. Sites already covered by a stored window are skipped; sites
outside the 10 m mosaic (north of about 83 S) are listed and later use the 40 m
grid for the near range as well.

    python scripts/fetch_near_windows.py            # prints the plan, then fetches
    python scripts/fetch_near_windows.py --dry-run
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_terrain import cut_near_window  # noqa: E402
from lunarnav.sites import SITES  # noqa: E402
from lunarnav.terrain import NEAR_HALF_WIDTH_M, latlon_to_xy, near_grid_path  # noqa: E402

MOSAIC_HALF_EXTENT_M = 216_400.0  # LDEM_83S_10MPP_ADJ.TIF covers +/- 216.4 km around the pole
BUDGET_BYTES = 600_000_000


def main() -> int:
    todo, outside, covered = [], [], []
    for site in SITES:
        if site.lat > -80.0:
            continue
        x, y = (float(v) for v in latlon_to_xy(site.lat, site.lon))
        if near_grid_path(site.lat, site.lon) is not None:
            covered.append(site.key)
        elif max(abs(x), abs(y)) + NEAR_HALF_WIDTH_M > MOSAIC_HALF_EXTENT_M:
            outside.append(site.key)
        else:
            todo.append(site)
    estimate = len(todo) * 25_000_000
    print(f"Already covered: {len(covered)}; outside the 10 m mosaic: {outside or 'none'}")
    print(f"To fetch: {len(todo)} windows, about {estimate / 1e6:.0f} MB in total: {[s.key for s in todo]}")
    if estimate > BUDGET_BYTES:
        print("Over the budget - nothing fetched.")
        return 1
    if "--dry-run" in sys.argv or not todo:
        return 0

    def fetch(site):
        path, size = cut_near_window(site.key, site.lat, site.lon)
        return f"  {path.name:<44} {size / 1e6:6.1f} MB"

    with ThreadPoolExecutor(4) as pool:
        for line in pool.map(fetch, todo):
            print(line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
