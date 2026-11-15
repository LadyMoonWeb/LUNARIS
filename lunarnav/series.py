"""Cached one-year time series.

The positions for a whole calendar year with a 30-minute step are computed
once per site and stored in ``cache/`` as a parquet file. Everything the
interface shows is a slice of these yearly tables, so moving a slider never
triggers a new ephemeris computation.

Only the positions are cached. Visibility (horizon mask, observer dip) is
applied on the way out, so a new horizon mask does not invalidate the cache.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import pandas as pd

from .compute import HorizonMask, apply_visibility, positions, to_utc
from .ephemeris import FIRST_YEAR, LAST_YEAR, ROOT

CACHE_DIR = ROOT / "cache"
STEP_MINUTES = 30
STEP = pd.Timedelta(minutes=STEP_MINUTES)


CACHE_VERSION = 2  # 2: positions carry the angular radius of the Earth


def _cache_path(lat: float, lon: float, height_m: float, year: int):
    name = (f"pos_lat{lat:+09.5f}_lon{lon:+010.5f}_h{height_m:.0f}m_{year}_{STEP_MINUTES}min"
            f"_v{CACHE_VERSION}.parquet")
    return CACHE_DIR / name


@lru_cache(maxsize=64)
def _yearly_positions(lat: float, lon: float, height_m: float, year: int) -> pd.DataFrame:
    path = _cache_path(lat, lon, height_m, year)
    if path.exists():
        return pd.read_parquet(path)

    times = pd.date_range(
        pd.Timestamp(year=year, month=1, day=1, tz="UTC"),
        pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC"),
        freq=STEP,
        inclusive="left",
    )
    table = positions(lat, lon, times, height_m)

    CACHE_DIR.mkdir(exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    table.to_parquet(tmp, index=False)
    os.replace(tmp, path)  # atomic: a half-written file is never read
    return table


def yearly_positions(lat: float, lon: float, year: int, observer_height_m: float = 0.0) -> pd.DataFrame:
    """Sun and Earth positions for one calendar year, 30-minute step (cached).

    The returned table is shared between callers: do not modify it in place.
    """
    if not FIRST_YEAR <= year <= LAST_YEAR:
        raise ValueError(f"year must be between {FIRST_YEAR} and {LAST_YEAR} (DE421 coverage)")
    return _yearly_positions(round(float(lat), 5), round(float(lon), 5), round(float(observer_height_m)), int(year))


def get_series(
    lat: float,
    lon: float,
    start,
    end,
    observer_height_m: float = 0.0,
    horizon_mask: Optional[HorizonMask] = None,
    antenna_height_m: Optional[float] = None,
    antenna_horizon_mask: Optional[HorizonMask] = None,
) -> pd.DataFrame:
    """Slice of the cached yearly series between two UTC instants.

    Positions are cached for the surface point; the panel height (Sun) and the
    antenna height (Earth) only enter through the horizon.

    Same columns as ``compute()``; instants lie on the 30-minute grid.
    """
    start_utc, end_utc = to_utc(start), to_utc(end)
    if end_utc < start_utc:
        raise ValueError("end must not be earlier than start")

    parts = [
        yearly_positions(lat, lon, year, 0.0)  # parallax of a few metres of height is far below 0.001 deg
        for year in range(start_utc.year, end_utc.year + 1)
    ]
    table = parts[0] if len(parts) == 1 else pd.concat(parts, ignore_index=True)
    chosen = table[(table["time_utc"] >= start_utc) & (table["time_utc"] <= end_utc)]
    return apply_visibility(chosen.reset_index(drop=True), observer_height_m, horizon_mask,
                            antenna_height_m, antenna_horizon_mask)
