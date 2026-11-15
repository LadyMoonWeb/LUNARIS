"""Ephemeris and lunar reference frame loading.

Same setup as ``lunar_drill.py`` (the skyfield documentation example):
JPL DE421 ephemeris and the ``MOON_ME_DE421`` Mean Earth / Polar Axis frame.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from skyfield.api import Loader, PlanetaryConstants

# Project root: the kernels were downloaded there by lunar_drill.py.
ROOT = Path(__file__).resolve().parent.parent

FRAME_NAME = "MOON_ME_DE421"
MOON_RADIUS_M = 1_737_400.0  # reference sphere, same value as pck00008.tpc

# de421.bsp and moon_pa_de421_1900-2050.bpc both end in 2050.
FIRST_YEAR, LAST_YEAR = 1900, 2049


@lru_cache(maxsize=1)
def kernels() -> SimpleNamespace:
    """Load the timescale, the ephemeris and the lunar frame once per process."""
    load = Loader(str(ROOT), verbose=False)
    ts = load.timescale()
    eph = load("de421.bsp")

    pc = PlanetaryConstants()
    pc.read_text(load("moon_080317.tf"))
    pc.read_text(load("pck00008.tpc"))
    pc.read_binary(load("moon_pa_de421_1900-2050.bpc"))
    frame = pc.build_frame_named(FRAME_NAME)

    return SimpleNamespace(
        ts=ts,
        eph=eph,
        pc=pc,
        frame=frame,
        sun=eph["sun"],
        earth=eph["earth"],
        moon=eph["moon"],
    )


def surface_point(lat_deg: float, lon_deg: float, height_m: float = 0.0):
    """Observer on the Moon at selenographic latitude / east longitude (degrees)."""
    k = kernels()
    return k.moon + k.pc.build_latlon_degrees(
        k.frame, lat_deg, lon_deg, elevation_m=height_m
    )
