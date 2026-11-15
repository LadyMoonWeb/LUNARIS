"""Fetch the shape-from-shading (SFS) elevation model for Leibnitz Beta Plateau.

Source: PGDA product 104, Bertone et al., "Enhanced Topography Models for
selected Lunar South Pole regions with Shape-from-Shading", Zenodo
doi:10.5281/zenodo.17954508, archive A3CLR22_10_Leibnitz_Beta_Plateau.zip
(1.05 GB). Only the files that are needed are pulled out of the remote zip
with HTTP range requests (elevation, uncertainty, mask, readme: about 50 MB),
so the rest of the archive (slope, roughness and image maps) is not downloaded.

    python scripts/fetch_sfs.py            # prints sizes, then fetches
    python scripts/fetch_sfs.py --dry-run
"""

from __future__ import annotations

import json
import struct
import sys
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lunarnav.terrain import DEM_DIR  # noqa: E402

RECORD = "https://zenodo.org/api/records/17954508"
ARCHIVE = "A3CLR22_10_Leibnitz_Beta_Plateau.zip"
LIMIT_BYTES = 3_000_000_000  # owner's limit for this archive
WANTED = ("A310_GLDELEV_005.tif", "A310_GLDSIGM_005.tif", "A310_GLDMASK_005.tif", "README.txt")
TARGET_DIR = DEM_DIR / "sfs_leibnitz_beta"
CITATION = ("Bertone, S., McKenna, T. E., Barker, M. K., Mazarico, E., Beyer, R. A., Petro, N. (2025). Archived "
            "Dataset for 'Enhanced Topography Models for selected Lunar South Pole regions with Shape-from-Shading'. "
            "Zenodo, doi:10.5281/zenodo.17954508 (PGDA product 104)")


def _get(url: str, first: int | None = None, last: int | None = None) -> bytes:
    headers = {"User-Agent": "python-urllib"}
    if first is not None:
        headers["Range"] = f"bytes={first}-{last}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=300) as response:
        return response.read()


def zip_directory(url: str, size: int) -> list:
    """Entries of a remote zip: (name, method, compressed size, size, local header offset)."""
    tail = _get(url, size - 200_000, size - 1)
    end = tail.rfind(b"PK\x05\x06")
    cd_size, cd_offset = struct.unpack("<II", tail[end + 12:end + 20])
    cd = _get(url, cd_offset, cd_offset + cd_size - 1)
    entries, p = [], 0
    while cd[p:p + 4] == b"PK\x01\x02":
        method, = struct.unpack("<H", cd[p + 10:p + 12])
        csize, usize, nlen, elen, clen = struct.unpack("<IIHHH", cd[p + 20:p + 34])
        offset, = struct.unpack("<I", cd[p + 42:p + 46])
        entries.append((cd[p + 46:p + 46 + nlen].decode("utf-8", "replace"), method, csize, usize, offset))
        p += 46 + nlen + elen + clen
    return entries


def extract(url: str, entry: tuple) -> bytes:
    name, method, csize, usize, offset = entry
    header = _get(url, offset, offset + 29)
    nlen, elen = struct.unpack("<HH", header[26:30])
    raw = _get(url, offset + 30 + nlen + elen, offset + 30 + nlen + elen + csize - 1)
    data = raw if method == 0 else zlib.decompress(raw, -15)
    if len(data) != usize:
        raise RuntimeError(f"{name}: got {len(data)} bytes, expected {usize}")
    return data


def main() -> int:
    record = json.loads(_get(RECORD))
    info = next(f for f in record["files"] if f["key"] == ARCHIVE)
    url, size = info["links"]["self"], int(info["size"])
    print(f"{ARCHIVE}: {size / 1e9:.2f} GB on Zenodo (limit {LIMIT_BYTES / 1e9:.0f} GB)")
    if size > LIMIT_BYTES:
        print("Larger than the limit - not downloaded.")
        return 1
    entries = [e for e in zip_directory(url, size) if e[0].rsplit("/", 1)[-1] in WANTED and "__MACOSX" not in e[0]]
    for name, _, csize, usize, _ in entries:
        print(f"  {name.rsplit('/', 1)[-1]:<28} {csize / 1e6:7.1f} MB in the archive, {usize / 1e6:7.1f} MB unpacked")
    print(f"Fetching {sum(e[2] for e in entries) / 1e6:.0f} MB instead of the whole archive.")
    if "--dry-run" in sys.argv:
        return 0

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    for entry in entries:
        target = TARGET_DIR / entry[0].rsplit("/", 1)[-1]
        if not target.exists():
            target.write_bytes(extract(url, entry))
        records.append({"file": str(target.relative_to(ROOT)).replace("\\", "/"), "bytes": target.stat().st_size,
                        "archive": ARCHIVE, "member": entry[0], "url": url, "citation": CITATION})
        print(f"  saved {target.relative_to(ROOT)}")
    (TARGET_DIR / "sources.json").write_text(json.dumps(
        {"fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "record": RECORD,
         "doi": "10.5281/zenodo.17954508", "files": records}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
