"""A modelled small crater placed into the terrain.

THIS IS A MODEL, NOT MEASURED TERRAIN. The elevation grids (10 m and 5 m)
do not resolve a crater 20 m across. To estimate what a vehicle sees from
inside one, a simple bowl is carved into a fine local copy of the terrain:

    depth below the surrounding surface = d * (1 - (r / R)^2)   for r <= R

with ``R`` the crater radius and ``d = depth_ratio * diameter``. There is no
raised rim, so the result is slightly optimistic compared with a fresh crater.
"""

from __future__ import annotations

import numpy as np

from .terrain import (
    FAR_STEP_M,
    MAX_RANGE_M,
    NEAR_RANGE_M,
    NEAR_STEP_M,
    Grid,
    HorizonMask,
    latlon_to_xy,
    mask_from_tiers,
)

LOCAL_HALF_WIDTH_M = 160.0  # size of the fine local grid around the site
LOCAL_RANGE_M = 150.0  # rays use the fine grid out to this distance
LOCAL_PIXEL_M = 0.5


def local_grid(base: Grid, lat: float, lon: float, diameter_m: float = 0.0, depth_ratio: float = 0.0,
               offset_east_m: float = 0.0, offset_north_m: float = 0.0) -> Grid:
    """Fine grid around a site: the base terrain resampled, with an optional bowl crater.

    The crater centre is at the site plus the given offset (map east / north).
    With ``diameter_m = 0`` the grid is just the resampled base terrain, which
    gives a like-for-like "no crater" case.
    """
    x0, y0 = latlon_to_xy(lat, lon)
    n = int(round(2 * LOCAL_HALF_WIDTH_M / LOCAL_PIXEL_M))
    cols = (np.arange(n) + 0.5) * LOCAL_PIXEL_M - LOCAL_HALF_WIDTH_M
    x = x0 + cols[None, :] + np.zeros((n, 1))
    y = y0 - cols[:, None] + np.zeros((1, n))
    heights = base.sample(x, y)

    if diameter_m > 0 and depth_ratio > 0:
        radius = diameter_m / 2.0
        r = np.hypot(x - (x0 + offset_east_m), y - (y0 + offset_north_m))
        heights = heights - np.where(r <= radius, depth_ratio * diameter_m * (1.0 - (r / radius) ** 2), 0.0)

    name = (f"{base.name} resampled to {LOCAL_PIXEL_M:g} m"
            + (f" + MODEL crater D={diameter_m:g} m, depth/diameter={depth_ratio:g}" if diameter_m > 0 else ""))
    return Grid(heights, x0 - LOCAL_HALF_WIDTH_M, y0 + LOCAL_HALF_WIDTH_M, LOCAL_PIXEL_M, name)


def mask_with_crater(lat: float, lon: float, observer_height_m: float, near: Grid, far: Grid,
                     diameter_m: float = 0.0, depth_ratio: float = 0.0) -> HorizonMask:
    """Horizon mask of an observer standing at the centre of a modelled crater.

    ``observer_height_m`` is measured from the crater floor (or from the
    ground when there is no crater).
    """
    fine = local_grid(near, lat, lon, diameter_m, depth_ratio)
    label = (f"MODEL crater, diameter {diameter_m:g} m, depth {depth_ratio * diameter_m:g} m"
             if diameter_m > 0 else "no crater (terrain resampled to the fine grid)")
    mask = mask_from_tiers(lat, lon, observer_height_m,
                           [(fine, LOCAL_RANGE_M, LOCAL_PIXEL_M), (near, NEAR_RANGE_M, NEAR_STEP_M),
                            (far, MAX_RANGE_M, FAR_STEP_M)], label=label)
    mask.meta["model"] = diameter_m > 0
    mask.meta["crater"] = {"diameter_m": diameter_m, "depth_ratio": depth_ratio,
                           "depth_m": depth_ratio * diameter_m, "shape": "parabolic bowl, no raised rim"}
    return mask
