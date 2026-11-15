"""Sun and Earth as seen from a point on the Moon.

``compute()`` is the single entry point for the time series. It is split in
two stages so that the expensive part can be cached:

1. ``positions()``  - apparent altitude / azimuth of the Sun and the Earth
   (skyfield, DE421, MOON_ME_DE421). Depends only on place and time.
2. ``apply_visibility()`` - compares the altitudes with the local horizon
   (horizon mask minus the dip caused by the observer height). Cheap, so a
   new horizon mask (terrain, stage 2) can be applied to a cached series.
"""

from __future__ import annotations

from typing import Callable, Optional, Union

import numpy as np
import pandas as pd

from .ephemeris import MOON_RADIUS_M, kernels, surface_point

HorizonMask = Callable[[np.ndarray], Union[np.ndarray, float]]
StepLike = Union[int, float, str, pd.Timedelta]

EARTH_RADIUS_KM = 6378.137  # equatorial radius, for the angular size of the Earth's disk
EARTH_MEAN_RADIUS_DEG = 0.95  # used only for tables that carry no "earth_radius_deg" column

POSITION_COLUMNS = [
    "time_utc",
    "sun_alt_deg",
    "sun_az_deg",
    "earth_alt_deg",
    "earth_az_deg",
]


# --------------------------------------------------------------------------
# Horizon
# --------------------------------------------------------------------------
def horizon_dip_deg(observer_height_m: float) -> float:
    """Depression of the horizon for an observer above the lunar sphere.

    For an eye at height h above a sphere of radius R the horizon lies
    ``arccos(R / (R + h))`` below the local horizontal plane.
    """
    h = float(observer_height_m)
    if h < 0:
        raise ValueError("observer_height_m must not be negative")
    return float(np.degrees(np.arccos(MOON_RADIUS_M / (MOON_RADIUS_M + h))))


def flat_horizon(azimuth_deg):
    """Default horizon mask: a smooth sphere, 0 degrees in every direction."""
    return np.zeros_like(np.asarray(azimuth_deg, dtype=float))


def horizon_elevation_deg(
    azimuth_deg,
    observer_height_m: float = 0.0,
    horizon_mask: Optional[HorizonMask] = None,
) -> np.ndarray:
    """Elevation of the local horizon in the given directions, in degrees.

    ``horizon_mask(azimuth_deg)`` gives the horizon elevation for an observer
    standing on the surface (0 for a smooth sphere). The dip from the observer
    height is subtracted from it.

    A terrain mask (``lunarnav.terrain.HorizonMask``) is computed for the real
    eye position, so the observer height is already in it. Such a mask carries
    ``includes_observer_height = True`` and is used as it is.
    """
    az = np.asarray(azimuth_deg, dtype=float)
    mask = flat_horizon if horizon_mask is None else horizon_mask
    try:
        elevation = np.asarray(mask(az), dtype=float)
    except (TypeError, ValueError):
        # The mask only accepts scalars: evaluate it point by point.
        elevation = np.array([float(mask(float(a))) for a in az.ravel()]).reshape(az.shape)
    elevation = np.broadcast_to(elevation, az.shape)
    if getattr(mask, "includes_observer_height", False):
        return elevation.astype(float)
    return elevation - horizon_dip_deg(observer_height_m)


# --------------------------------------------------------------------------
# Time handling
# --------------------------------------------------------------------------
def to_utc(value) -> pd.Timestamp:
    """Any datetime-like value as a timezone-aware UTC timestamp."""
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def to_timedelta(step: StepLike) -> pd.Timedelta:
    """A step given as minutes (number), a pandas offset string or a timedelta."""
    if isinstance(step, (int, float)) and not isinstance(step, bool):
        delta = pd.Timedelta(minutes=float(step))
    else:
        delta = pd.Timedelta(step)
    if delta <= pd.Timedelta(0):
        raise ValueError("step must be positive")
    return delta


def time_grid(start, end, step: StepLike) -> pd.DatetimeIndex:
    """UTC instants from start to end (both included when they fall on the grid)."""
    start_utc, end_utc = to_utc(start), to_utc(end)
    if end_utc < start_utc:
        raise ValueError("end must not be earlier than start")
    return pd.date_range(start_utc, end_utc, freq=to_timedelta(step))


def _skyfield_time(times: pd.DatetimeIndex):
    seconds = times.second + times.microsecond / 1e6
    return kernels().ts.utc(
        times.year.values,
        times.month.values,
        times.day.values,
        times.hour.values,
        times.minute.values,
        np.asarray(seconds, dtype=float),
    )


# --------------------------------------------------------------------------
# Stage 1: positions
# --------------------------------------------------------------------------
def positions(
    lat: float,
    lon: float,
    times,
    observer_height_m: float = 0.0,
) -> pd.DataFrame:
    """Apparent altitude and azimuth of the Sun and the Earth.

    ``lat`` is the selenographic latitude and ``lon`` the east longitude, in
    degrees, in the MOON_ME_DE421 frame. Azimuth is measured from north
    through east. Altitudes are relative to the local horizontal plane.
    """
    if not -90.0 <= lat <= 90.0:
        raise ValueError("lat must be between -90 and 90 degrees")
    if not -360.0 <= lon <= 360.0:
        raise ValueError("lon must be between -360 and 360 degrees")

    index = pd.DatetimeIndex(times)
    index = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")

    k = kernels()
    here = surface_point(lat, lon, observer_height_m).at(_skyfield_time(index))

    sun_alt, sun_az, _ = here.observe(k.sun).apparent().altaz()
    earth_alt, earth_az, earth_distance = here.observe(k.earth).apparent().altaz()

    return pd.DataFrame(
        {
            "time_utc": index,
            "sun_alt_deg": np.atleast_1d(sun_alt.degrees),
            "sun_az_deg": np.atleast_1d(sun_az.degrees),
            "earth_alt_deg": np.atleast_1d(earth_alt.degrees),
            "earth_az_deg": np.atleast_1d(earth_az.degrees),
            # Angular radius of the Earth's disk (about 0.9 to 1.0 degrees).
            "earth_radius_deg": np.degrees(np.arcsin(EARTH_RADIUS_KM / np.atleast_1d(earth_distance.km))),
        }
    )


# --------------------------------------------------------------------------
# Stage 2: visibility
# --------------------------------------------------------------------------
def apply_visibility(
    table: pd.DataFrame,
    observer_height_m: float = 0.0,
    horizon_mask: Optional[HorizonMask] = None,
    antenna_height_m: Optional[float] = None,
    antenna_horizon_mask: Optional[HorizonMask] = None,
) -> pd.DataFrame:
    """Add the visibility columns to a table produced by ``positions()``.

    ``observer_height_m`` / ``horizon_mask`` describe the solar panels and are
    used for the Sun. ``antenna_height_m`` / ``antenna_horizon_mask`` describe
    the antenna and are used for the Earth; when they are left out the Earth
    uses the same height and mask as the Sun.

    * ``sunlit``        - centre of the solar disk is above the local horizon
    * ``earth_visible`` - centre of the Earth is above the local horizon
      (direct line of sight for communication)
    * ``both``          - sunlit and Earth visible at the same time

    The Earth's disk is almost 2 degrees wide, so a second, looser definition
    is given alongside the strict one:

    * ``earth_any_visible`` - any part of the Earth's disk is above the horizon
      (its upper limb clears the horizon in the direction of its centre)
    * ``both_any``          - sunlit and ``earth_any_visible``

    ``*_clearance_deg`` is the altitude above the local horizon; the metrics
    use it to interpolate rise and set times between samples.
    """
    out = table.copy()
    # The Sun is judged at the height of the panels, the Earth at the height of the antenna.
    if antenna_height_m is None:
        antenna_height_m = observer_height_m
        if antenna_horizon_mask is None:
            antenna_horizon_mask = horizon_mask
    sun_horizon = horizon_elevation_deg(out["sun_az_deg"].values, observer_height_m, horizon_mask)
    earth_horizon = horizon_elevation_deg(out["earth_az_deg"].values, antenna_height_m, antenna_horizon_mask)
    earth_radius = out["earth_radius_deg"].values if "earth_radius_deg" in out else EARTH_MEAN_RADIUS_DEG

    out["sun_clearance_deg"] = out["sun_alt_deg"].values - sun_horizon
    out["earth_clearance_deg"] = out["earth_alt_deg"].values - earth_horizon
    out["both_clearance_deg"] = np.minimum(out["sun_clearance_deg"], out["earth_clearance_deg"])
    out["earth_any_clearance_deg"] = out["earth_clearance_deg"] + earth_radius
    out["both_any_clearance_deg"] = np.minimum(out["sun_clearance_deg"], out["earth_any_clearance_deg"])

    out["sunlit"] = out["sun_clearance_deg"] > 0
    out["earth_visible"] = out["earth_clearance_deg"] > 0
    out["both"] = out["sunlit"] & out["earth_visible"]
    out["earth_any_visible"] = out["earth_any_clearance_deg"] > 0
    out["both_any"] = out["sunlit"] & out["earth_any_visible"]
    return out


EARTH_DEFINITIONS = ("centre", "any")


def with_earth_definition(table: pd.DataFrame, definition: str = "centre") -> pd.DataFrame:
    """Choose what "Earth visible" means for everything computed from the table.

    ``"centre"`` (default, strict) keeps the table as it is: the centre of the
    Earth has to be above the horizon. ``"any"`` returns a copy in which
    ``earth_visible``, ``both`` and their clearances follow the looser
    definition (any part of the disk above the horizon), so the metrics, which
    read those columns, need no changes.
    """
    if definition not in EARTH_DEFINITIONS:
        raise ValueError(f"earth definition must be one of {EARTH_DEFINITIONS}")
    if definition == "centre":
        return table
    out = table.copy()
    out["earth_clearance_deg"] = out["earth_any_clearance_deg"]
    out["earth_visible"] = out["earth_any_visible"]
    out["both_clearance_deg"] = out["both_any_clearance_deg"]
    out["both"] = out["both_any"]
    return out


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def compute(
    lat: float,
    lon: float,
    start,
    end,
    step: StepLike,
    observer_height_m: float = 0.0,
    horizon_mask: Optional[HorizonMask] = None,
    antenna_height_m: Optional[float] = None,
    antenna_horizon_mask: Optional[HorizonMask] = None,
) -> pd.DataFrame:
    """Time series of the Sun and the Earth for a point on the Moon.

    ``observer_height_m`` and ``horizon_mask`` apply to the solar panels (Sun).
    The optional ``antenna_height_m`` and ``antenna_horizon_mask`` apply to the
    antenna (Earth); without them the Earth uses the panel values.

    Parameters
    ----------
    lat, lon : selenographic latitude and east longitude in degrees
        (MOON_ME_DE421; west longitudes are negative).
    start, end : UTC instants (datetime, pandas Timestamp or ISO string).
    step : number of minutes, a pandas offset string ("30min") or a timedelta.
    observer_height_m : height of the eye / antenna above the lunar sphere.
        It lowers the horizon by the corresponding dip.
    horizon_mask : function "azimuth in degrees -> horizon elevation in degrees".
        ``None`` means 0 everywhere (smooth sphere). Terrain plugs in here.

    Returns
    -------
    DataFrame with one row per instant:
    ``time_utc, sun_alt_deg, sun_az_deg, earth_alt_deg, earth_az_deg,
    sunlit, earth_visible, both`` plus the ``*_clearance_deg`` helper columns,
    ``earth_radius_deg`` and the looser Earth columns ``earth_any_visible`` and
    ``both_any`` (see ``apply_visibility`` and ``with_earth_definition``).
    """
    table = positions(lat, lon, time_grid(start, end, step), observer_height_m)
    return apply_visibility(table, observer_height_m, horizon_mask, antenna_height_m, antenna_horizon_mask)
