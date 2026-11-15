"""Download the terrain and reference data for stage 2.

Sizes are printed before anything is fetched and the script refuses to go over
the budget. Nothing is ever deleted; files that already exist are kept.

    python scripts/fetch_terrain.py            # show the plan and download
    python scripts/fetch_terrain.py --dry-run  # only show sizes

What is fetched
    data/dem/LDEM_80S_40MPP_ADJ.TIF      far terrain, 40 m, whole 80-90 S square
    data/dem/near_<name>_10m.tif         near terrain, 10 m windows cut out of
                                         LDEM_83S_10MPP_ADJ.TIF over HTTP range requests
    data/reference/AVGVISIB_*.TIF        PGDA product 69 illumination / Earth visibility
    data/reference/WAC_POLE_ILL_PCT_*    LROC WAC percentage-based illumination map, 88-90 S

Sources and sizes of everything fetched are recorded in data/sources.json.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lunarnav.terrain import DEM_DIR, NEAR_HALF_WIDTH_M, NEAR_WINDOWS, REFERENCE_DIR, latlon_to_xy  # noqa: E402

BUDGET_BYTES = 2_000_000_000
PGDA = "https://pgda.gsfc.nasa.gov/data/"
NEAR_SOURCE = PGDA + "LOLA_20mpp/LDEM_83S_10MPP_ADJ.TIF"
_LROC = "https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/"
LROC_DATA = _LROC + "DATA/BDR/WAC_POLE/WAC_POLE_ILL_PCT_SOUTH/"
LROC_BROWSE = _LROC + "EXTRAS/BROWSE/WAC_POLE/WAC_POLE_ILL_PCT_SOUTH/"

# (url, destination, citation)
FULL_FILES = [
    (PGDA + "LOLA_20mpp/LDEM_80S_40MPP_ADJ.TIF", DEM_DIR / "LDEM_80S_40MPP_ADJ.TIF",
     "Barker et al. 2023, Planet. Sci. J. 4, 183 (PGDA product 90)"),
    (PGDA + "MoonIllumination/AVGVISIB_75S_120M_201608.TIF", REFERENCE_DIR / "AVGVISIB_75S_120M_201608.TIF",
     "Mazarico et al. 2011, Icarus 211, 1066-1081 (PGDA product 69)"),
    (PGDA + "MoonIllumination/AVGVISIB_85S_060M_201608.TIF", REFERENCE_DIR / "AVGVISIB_85S_060M_201608.TIF",
     "Mazarico et al. 2011, Icarus 211, 1066-1081 (PGDA product 69)"),
    (PGDA + "MoonIllumination/AVGVISIB_75S_120M_201608_EARTH.TIF", REFERENCE_DIR / "AVGVISIB_75S_120M_201608_EARTH.TIF",
     "Mazarico et al. 2011, Icarus 211, 1066-1081 (PGDA product 69)"),
    (PGDA + "MoonIllumination/AVGVISIB_85S_060M_201608_EARTH.TIF", REFERENCE_DIR / "AVGVISIB_85S_060M_201608_EARTH.TIF",
     "Mazarico et al. 2011, Icarus 211, 1066-1081 (PGDA product 69)"),
    (LROC_DATA + "WAC_POLE_ILL_PCT_SOUTH_100M.IMG", REFERENCE_DIR / "WAC_POLE_ILL_PCT_SOUTH_100M.IMG",
     "Speyerer and Robinson 2013, Icarus 222, 122-136 (LROC RDR WAC_POLE_ILL_PCT_SOUTH)"),
    (LROC_BROWSE + "WAC_POLE_ILL_PCT_SOUTH_100M.TIF", REFERENCE_DIR / "WAC_POLE_ILL_PCT_SOUTH_100M.TIF",
     "Speyerer and Robinson 2013, Icarus 222, 122-136 (LROC RDR WAC_POLE_ILL_PCT_SOUTH, 8-bit GeoTIFF)"),
    (LROC_DATA + "WAC_POLE_ILL_PCT_SOUTH_README.TXT", REFERENCE_DIR / "WAC_POLE_ILL_PCT_SOUTH_README.TXT",
     "LROC RDR product description"),
]


def remote_size(url: str) -> int:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "python-urllib"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return int(response.headers["Content-Length"])


CONNECTIONS = 4  # the server gives about 0.5 MB/s per connection


def _fetch_range(url: str, first: int, last: int, path: Path) -> None:
    """Bytes first..last of the URL into ``path``; resumes after dropped connections."""
    import time

    wanted = last - first + 1
    for _ in range(60):
        done = path.stat().st_size if path.exists() else 0
        if done >= wanted:
            return
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "python-urllib", "Range": f"bytes={first + done}-{last}"})
            with urllib.request.urlopen(request, timeout=120) as response, open(path, "ab") as out:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    out.write(block)
        except OSError as error:
            print(f"    connection lost ({error}); resuming", flush=True)
            time.sleep(5)
    raise RuntimeError(f"{path.name}: gave up after repeated connection losses")


def download(url: str, target: Path, size: int, connections: int = CONNECTIONS) -> None:
    """Download with resume into '<name>.part', renamed when complete.

    What is already in the .part file is kept; the rest is split into segments
    fetched over a few parallel connections and appended in order.
    """
    from concurrent.futures import ThreadPoolExecutor

    part = target.with_suffix(target.suffix + ".part")
    done = part.stat().st_size if part.exists() else 0
    if done < size:
        remaining = size - done
        count = max(1, min(connections, remaining // (8 * 1024 * 1024) + 1))
        edges = [done + remaining * i // count for i in range(count + 1)]
        segments = [(edges[i], edges[i + 1] - 1, part.with_name(f"{part.name}.seg{i}_{edges[i]}"))
                    for i in range(count)]
        with ThreadPoolExecutor(count) as pool:
            list(pool.map(lambda seg: _fetch_range(url, *seg), segments))
        with open(part, "ab") as out:
            for _, _, path in segments:
                with open(path, "rb") as piece:
                    while True:
                        block = piece.read(8 * 1024 * 1024)
                        if not block:
                            break
                        out.write(block)
        # The segment files are left in place (nothing is deleted); they can be removed by hand.
    done = part.stat().st_size
    if done != size:
        raise RuntimeError(f"{target.name}: got {done} bytes, expected {size}")
    part.rename(target)


def cut_near_window(name: str, lat: float, lon: float) -> tuple[Path, int]:
    """Read a 10 m window around a point from the remote cloud-optimised GeoTIFF."""
    import rasterio
    from rasterio.windows import from_bounds

    target = DEM_DIR / f"near_{name}_10m.tif"
    if target.exists():
        return target, target.stat().st_size
    x, y = latlon_to_xy(lat, lon)
    half = NEAR_HALF_WIDTH_M
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF"):
        with rasterio.open("/vsicurl/" + NEAR_SOURCE) as src:
            window = from_bounds(x - half, y - half, x + half, y + half, src.transform).round_offsets().round_lengths()
            data = src.read(1, window=window)
            profile = src.profile.copy()
            profile.update(width=data.shape[1], height=data.shape[0], transform=src.window_transform(window),
                           compress="deflate", predictor=3, tiled=True, blockxsize=512, blockysize=512,
                           BIGTIFF="NO")
            profile.pop("copy_src_overviews", None)
    with rasterio.open(target, "w", **profile) as dst:
        dst.write(data, 1)
    return target, target.stat().st_size


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    DEM_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    print("Full files:")
    plan, total = [], 0
    for url, target, citation in FULL_FILES:
        size = remote_size(url)
        total += size
        state = "already here" if target.exists() else "to download"
        print(f"  {target.name:<44} {size / 1e6:8.1f} MB   {state}")
        plan.append((url, target, citation, size))
    pixels = (2 * NEAR_HALF_WIDTH_M / 10) ** 2
    near_estimate = int(len(NEAR_WINDOWS) * pixels * 4)  # uncompressed float32 upper bound
    total += near_estimate
    print(f"Near windows: {len(NEAR_WINDOWS)} x +/-{NEAR_HALF_WIDTH_M / 1000:.0f} km at 10 m from "
          f"{NEAR_SOURCE.rsplit('/', 1)[1]}: at most {near_estimate / 1e6:.0f} MB")
    print(f"Total: at most {total / 1e9:.2f} GB (budget {BUDGET_BYTES / 1e9:.1f} GB)")
    if total > BUDGET_BYTES:
        print("Over budget - nothing downloaded.")
        return 1
    if dry_run:
        return 0

    records = []
    for url, target, citation, size in plan:
        if not target.exists():
            print(f"  downloading {target.name}")
            download(url, target, size)
        records.append({"file": str(target.relative_to(ROOT)).replace("\\", "/"), "url": url,
                        "bytes": target.stat().st_size, "citation": citation})
    for name, (lat, lon) in NEAR_WINDOWS.items():
        print(f"  cutting near window '{name}' ({lat:.4f}, {lon:.4f})")
        target, size = cut_near_window(name, lat, lon)
        records.append({"file": str(target.relative_to(ROOT)).replace("\\", "/"), "url": NEAR_SOURCE,
                        "bytes": size, "window_centre": [lat, lon], "half_width_m": NEAR_HALF_WIDTH_M,
                        "citation": "Barker et al. 2023, Planet. Sci. J. 4, 183 (PGDA product 90)"})

    manifest = ROOT / "data" / "sources.json"
    manifest.write_text(json.dumps({"fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                                    "files": records}, indent=2), encoding="utf-8")
    print(f"Done: {sum(r['bytes'] for r in records) / 1e6:.0f} MB on disk. Manifest: {manifest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
