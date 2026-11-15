"""Terrain horizon masks from LOLA digital elevation models (stage 2).

For a point on the Moon the horizon mask gives, for each of 720 azimuths
(0.5 degree step, from north through east), the elevation angle of the highest
terrain along a 150 km ray. It replaces the flat horizon of stage 1:

    mask = load_mask("im2", observer_height_m=2)
    compute(lat, lon, start, end, 30, observer_height_m=2, horizon_mask=mask)

Geometry
--------
* DEMs are south polar stereographic grids (true scale at the pole, reference
  sphere 1737.4 km, MOON_ME / DE421 frame), heights in metres above the sphere.
* A ray follows the great circle that leaves the site at the given azimuth.
* The elevation angle of a terrain point at ground distance ``d`` accounts for
  the curvature of the Moon: with the observer at radius ``r0 = R + site
  height + observer height`` and the terrain point at ``r1 = R + h`` separated
  by the central angle ``theta = d / R``,

      elevation = atan2(r1 * cos(theta) - r0, r1 * sin(theta))

* The mask is the maximum of that angle along the ray. Because the observer
  height is part of ``r0``, the mask already contains the horizon dip: it must
  not be lowered a second time (``includes_observer_height = True``).

Data
----
Near terrain (10 m) is used out to ``NEAR_RANGE_M``, far terrain (40 m) from
there to ``MAX_RANGE_M``. Both come from PGDA product 90 (Barker et al. 2023).
Masks are computed once and stored as JSON in ``data/horizon/``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

from .ephemeris import MOON_RADIUS_M, ROOT

DATA_DIR = ROOT / "data"
DEM_DIR = DATA_DIR / "dem"
HORIZON_DIR = DATA_DIR / "horizon"
REFERENCE_DIR = DATA_DIR / "reference"

FAR_DEM = DEM_DIR / "LDEM_80S_40MPP_ADJ.TIF"

N_AZIMUTHS = 720
AZIMUTH_STEP_DEG = 360.0 / N_AZIMUTHS
MAX_RANGE_M = 150_000.0  # length of every ray
NEAR_RANGE_M = 14_000.0  # the 10 m grid is used up to this distance
NEAR_STEP_M = 10.0
FAR_STEP_M = 40.0
NEAR_HALF_WIDTH_M = 16_000.0  # half size of the 10 m windows cut from the remote mosaic

# Centres of the 10 m windows (latitude, east longitude). A site uses the window
# that contains it; it has to lie within 2 km of the centre so that the near
# range fits inside the window.
NEAR_WINDOWS: Dict[str, Tuple[float, float]] = {
    "athena": (-84.7906, 29.1957),  # also covers the planned IM-2 point, 0.4 km away
    "connecting_ridge": (-89.47485, -137.44314),
    "shackleton_rim": (-89.68643, -162.93714),
    "de_gerlache_rim": (-88.66463, -68.39564),
}


# --------------------------------------------------------------------------
# Map projection: south polar stereographic, true scale at the pole
# --------------------------------------------------------------------------
def latlon_to_xy(lat_deg, lon_deg):
    """Latitude / east longitude (degrees) to map x, y in metres."""
    colat = np.radians(90.0 + np.asarray(lat_deg, dtype=float))
    lon = np.radians(np.asarray(lon_deg, dtype=float))
    r = 2.0 * MOON_RADIUS_M * np.tan(colat / 2.0)
    return r * np.sin(lon), r * np.cos(lon)


def xy_to_latlon(x, y):
    """Map x, y in metres to latitude / east longitude in degrees (-180..180)."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    r = np.hypot(x, y)
    lat = -90.0 + np.degrees(2.0 * np.arctan(r / (2.0 * MOON_RADIUS_M)))
    return lat, np.degrees(np.arctan2(x, y))


def destination(lat_deg: float, lon_deg: float, azimuth_deg, distance_m):
    """Point reached from (lat, lon) along a great circle; arrays broadcast."""
    lat1, lon1 = np.radians(lat_deg), np.radians(lon_deg)
    az = np.radians(np.asarray(azimuth_deg, dtype=float))
    delta = np.asarray(distance_m, dtype=float) / MOON_RADIUS_M
    sin_lat2 = np.sin(lat1) * np.cos(delta) + np.cos(lat1) * np.sin(delta) * np.cos(az)
    lat2 = np.arcsin(np.clip(sin_lat2, -1.0, 1.0))
    lon2 = lon1 + np.arctan2(np.sin(az) * np.sin(delta) * np.cos(lat1), np.cos(delta) - np.sin(lat1) * sin_lat2)
    return np.degrees(lat2), np.degrees(lon2)


# --------------------------------------------------------------------------
# Elevation grids
# --------------------------------------------------------------------------
@dataclass
class Grid:
    """A north-up elevation raster in map coordinates (pixel centres sampled)."""

    heights: np.ndarray  # float32, metres above the 1737.4 km sphere, NaN = no data
    x_left: float  # map x of the left edge of the first column
    y_top: float  # map y of the top edge of the first row
    pixel_m: float
    name: str = ""

    def contains(self, x: float, y: float, margin_m: float = 0.0) -> bool:
        rows, cols = self.heights.shape
        return (self.x_left + margin_m <= x <= self.x_left + cols * self.pixel_m - margin_m
                and self.y_top - rows * self.pixel_m + margin_m <= y <= self.y_top - margin_m)

    def sample(self, x, y) -> np.ndarray:
        """Bilinear height at map points; NaN outside the grid or next to missing data."""
        from scipy.ndimage import map_coordinates

        col = (np.asarray(x, dtype=float) - self.x_left) / self.pixel_m - 0.5
        row = (self.y_top - np.asarray(y, dtype=float)) / self.pixel_m - 0.5
        out = map_coordinates(self.heights, [row.ravel(), col.ravel()], output=np.float64, order=1,
                              mode="constant", cval=np.nan)
        return out.reshape(col.shape)


def read_grid(path: Path, bounds: Optional[Tuple[float, float, float, float]] = None) -> Grid:
    """Read a GeoTIFF (or the part inside ``bounds`` = x_min, y_min, x_max, y_max)."""
    import rasterio
    from rasterio.windows import from_bounds

    with rasterio.open(path) as src:
        if bounds is None:
            window = None
            transform = src.transform
        else:
            x_min, y_min, x_max, y_max = bounds
            full = src.bounds
            window = from_bounds(max(x_min, full.left), max(y_min, full.bottom), min(x_max, full.right),
                                 min(y_max, full.top), src.transform).round_offsets().round_lengths()
            transform = src.window_transform(window)
        data = src.read(1, window=window).astype(np.float32)
        if src.nodata is not None:
            data[data == np.float32(src.nodata)] = np.nan
    data[~np.isfinite(data) | (np.abs(data) > 30_000)] = np.nan
    return Grid(data, transform.c, transform.f, abs(transform.a), Path(path).name)


_NEAR_BOUNDS: Dict[str, Tuple[float, float, float, float]] = {}


def near_grid_path(lat: float, lon: float) -> Optional[Path]:
    """The stored 10 m window that serves this point, if there is one.

    Any ``data/dem/near_*_10m.tif`` whose extent contains the point with room
    for the near range on every side qualifies; the best centred one wins.
    """
    import rasterio

    x, y = (float(v) for v in latlon_to_xy(lat, lon))
    best, best_margin = None, NEAR_RANGE_M
    for path in sorted(DEM_DIR.glob("near_*_10m.tif")):
        if path.name not in _NEAR_BOUNDS:
            with rasterio.open(path) as src:
                _NEAR_BOUNDS[path.name] = tuple(src.bounds)
        left, bottom, right, top = _NEAR_BOUNDS[path.name]
        margin = min(x - left, right - x, y - bottom, top - y)
        if margin >= best_margin:
            best, best_margin = path, margin
    return best


FAR_HALF_EXTENT_M = 304_000.0  # the 40 m grid covers a square of +/- 304 km around the pole


def terrain_available(lat: float, lon: float) -> bool:
    """True when a mask can be computed here: the 40 m grid is on disk and contains the point."""
    x, y = (float(v) for v in latlon_to_xy(lat, lon))
    return FAR_DEM.exists() and lat < 0 and max(abs(x), abs(y)) < FAR_HALF_EXTENT_M - 1000.0


# --------------------------------------------------------------------------
# Horizon mask
# --------------------------------------------------------------------------
class HorizonMask:
    """Callable "azimuth (deg) -> horizon elevation (deg)" with 720 stored values."""

    # The observer height is already part of the geometry: compute() must not
    # subtract the smooth-sphere horizon dip from this mask again.
    includes_observer_height = True

    def __init__(self, mask_deg, meta: Optional[dict] = None, distance_km=None):
        self.mask_deg = np.asarray(mask_deg, dtype=float)
        if self.mask_deg.shape != (N_AZIMUTHS,):
            raise ValueError(f"a horizon mask needs {N_AZIMUTHS} values")
        self.azimuth_deg = np.arange(N_AZIMUTHS) * AZIMUTH_STEP_DEG
        self.distance_km = None if distance_km is None else np.asarray(distance_km, dtype=float)
        self.meta = dict(meta or {})

    def __call__(self, azimuth_deg):
        az = np.mod(np.asarray(azimuth_deg, dtype=float), 360.0)
        return np.interp(az, self.azimuth_deg, self.mask_deg, period=360.0)

    def to_dict(self) -> dict:
        out = dict(self.meta)
        out["azimuth_start_deg"] = 0.0
        out["azimuth_step_deg"] = AZIMUTH_STEP_DEG
        out["mask_deg"] = [round(float(v), 4) for v in self.mask_deg]
        if self.distance_km is not None:
            out["horizon_distance_km"] = [round(float(v), 3) for v in self.distance_km]
        return out

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "HorizonMask":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        mask = raw.pop("mask_deg")
        distance = raw.pop("horizon_distance_km", None)
        return cls(mask, raw, distance)


def _ray_distances(near_range_m: float, max_range_m: float, near_step_m: float, far_step_m: float) -> np.ndarray:
    near = np.arange(near_step_m, near_range_m + near_step_m / 2, near_step_m)
    far = np.arange(near_range_m + far_step_m, max_range_m + far_step_m / 2, far_step_m)
    return np.concatenate([near, far])


def elevation_angle_deg(observer_radius_m, terrain_radius_m, distance_m):
    """Elevation of a terrain point seen from the observer, with curvature."""
    theta = np.asarray(distance_m, dtype=float) / MOON_RADIUS_M
    return np.degrees(np.arctan2(terrain_radius_m * np.cos(theta) - observer_radius_m,
                                 terrain_radius_m * np.sin(theta)))


def mask_from_grids(
    lat: float,
    lon: float,
    observer_height_m: float,
    near: Grid,
    far: Grid,
    near_range_m: float = NEAR_RANGE_M,
    max_range_m: float = MAX_RANGE_M,
    near_step_m: float = NEAR_STEP_M,
    far_step_m: float = FAR_STEP_M,
) -> HorizonMask:
    """Horizon mask for a point, from a fine near grid and a coarse far grid."""
    x0, y0 = latlon_to_xy(lat, lon)
    site_height = float(near.sample(np.array([x0]), np.array([y0]))[0])
    if not np.isfinite(site_height):
        raise ValueError("the site lies outside the near terrain grid")
    observer_radius = MOON_RADIUS_M + site_height + float(observer_height_m)

    distances = _ray_distances(near_range_m, max_range_m, near_step_m, far_step_m)
    is_near = distances <= near_range_m + 1e-6
    azimuths = np.arange(N_AZIMUTHS) * AZIMUTH_STEP_DEG

    mask = np.empty(N_AZIMUTHS)
    horizon_distance = np.empty(N_AZIMUTHS)
    missing = 0
    for start in range(0, N_AZIMUTHS, 90):  # chunks keep the memory use small
        az = azimuths[start:start + 90, None]
        lat2, lon2 = destination(lat, lon, az, distances[None, :])
        x, y = latlon_to_xy(lat2, lon2)
        # float64 on purpose: radius + height in float32 would round to 0.125 m,
        # which is 0.36 degrees for terrain 10 m away.
        heights = np.empty(x.shape, dtype=np.float64)
        heights[:, is_near] = near.sample(x[:, is_near], y[:, is_near])
        heights[:, ~is_near] = far.sample(x[:, ~is_near], y[:, ~is_near])
        # A near sample without data falls back to the far grid.
        gaps = ~np.isfinite(heights) & is_near[None, :]
        if gaps.any():
            heights[gaps] = far.sample(x[gaps], y[gaps])
        missing += int((~np.isfinite(heights)).sum())
        angles = elevation_angle_deg(observer_radius, MOON_RADIUS_M + heights, distances[None, :])
        angles = np.where(np.isfinite(angles), angles, -np.inf)
        best = angles.argmax(axis=1)
        mask[start:start + 90] = angles[np.arange(len(best)), best]
        horizon_distance[start:start + 90] = distances[best] / 1000.0

    meta = {
        "lat": lat,
        "lon": lon,
        "observer_height_m": float(observer_height_m),
        "site_height_m": round(site_height, 2),
        "reference_radius_m": MOON_RADIUS_M,
        "azimuth_convention": "degrees from north through east",
        "ray_length_km": max_range_m / 1000.0,
        "near_dem": {"file": near.name, "pixel_m": near.pixel_m, "used_to_km": near_range_m / 1000.0,
                     "step_m": near_step_m},
        "far_dem": {"file": far.name, "pixel_m": far.pixel_m, "step_m": far_step_m},
        "dem_source": "PGDA product 90, Barker et al. 2023 (LOLA, MOON_ME / DE421, south polar stereographic)",
        "samples_without_data": missing,
        "computed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    }
    return HorizonMask(mask, meta, horizon_distance)


def mask_from_tiers(
    lat: float,
    lon: float,
    observer_height_m: float,
    tiers,
    label: str = "",
) -> HorizonMask:
    """Horizon mask from any number of nested grids.

    ``tiers`` is a list of ``(grid, range_m, step_m)``, finest first: each grid
    is sampled every ``step_m`` from where the previous tier stopped out to
    ``range_m``. A sample without data falls back to the next coarser grid.
    Used for analyses that add a finer local grid (for example a modelled
    crater) in front of the usual near and far grids.
    """
    x0, y0 = latlon_to_xy(lat, lon)
    site_height = float(tiers[0][0].sample(np.array([x0]), np.array([y0]))[0])
    if not np.isfinite(site_height):
        raise ValueError("the site lies outside the finest terrain grid")
    observer_radius = MOON_RADIUS_M + site_height + float(observer_height_m)

    pieces, owner, start = [], [], 0.0
    for index, (_, range_m, step_m) in enumerate(tiers):
        part = np.arange(start + step_m, range_m + step_m / 2, step_m)
        pieces.append(part)
        owner.append(np.full(part.shape, index))
        start = range_m
    distances, owner = np.concatenate(pieces), np.concatenate(owner)
    azimuths = np.arange(N_AZIMUTHS) * AZIMUTH_STEP_DEG

    mask = np.empty(N_AZIMUTHS)
    horizon_distance = np.empty(N_AZIMUTHS)
    missing = 0
    for first in range(0, N_AZIMUTHS, 60):
        az = azimuths[first:first + 60, None]
        lat2, lon2 = destination(lat, lon, az, distances[None, :])
        x, y = latlon_to_xy(lat2, lon2)
        heights = np.full(x.shape, np.nan, dtype=np.float64)  # float64: see mask_from_grids
        for index, (grid, _, _) in enumerate(tiers):
            todo = ~np.isfinite(heights) & (owner <= index)[None, :]
            if todo.any():
                heights[todo] = grid.sample(x[todo], y[todo])
        missing += int((~np.isfinite(heights)).sum())
        angles = elevation_angle_deg(observer_radius, MOON_RADIUS_M + heights, distances[None, :])
        angles = np.where(np.isfinite(angles), angles, -np.inf)
        best = angles.argmax(axis=1)
        mask[first:first + 60] = angles[np.arange(len(best)), best]
        horizon_distance[first:first + 60] = distances[best] / 1000.0

    meta = {
        "lat": lat,
        "lon": lon,
        "observer_height_m": float(observer_height_m),
        "site_height_m": round(site_height, 2),
        "reference_radius_m": MOON_RADIUS_M,
        "azimuth_convention": "degrees from north through east",
        "ray_length_km": float(tiers[-1][1]) / 1000.0,
        "tiers": [{"file": grid.name, "pixel_m": grid.pixel_m, "used_to_km": range_m / 1000.0, "step_m": step_m}
                  for grid, range_m, step_m in tiers],
        "label": label,
        "samples_without_data": missing,
        "computed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    }
    return HorizonMask(mask, meta, horizon_distance)


def load_site_grids(lat: float, lon: float) -> Tuple[Grid, Grid]:
    """The near and far grids that serve a point.

    The near grid is a stored 10 m window when one covers the point; otherwise
    the 40 m grid is used for the near range as well (coarser, and recorded
    as such in the mask).
    """
    if not terrain_available(lat, lon):
        raise FileNotFoundError("terrain data for this point is not available; run scripts/fetch_terrain.py")
    x0, y0 = (float(v) for v in latlon_to_xy(lat, lon))
    reach = MAX_RANGE_M * 1.01 + 2000.0  # stereographic scale is slightly above 1 away from the pole
    far = read_grid(FAR_DEM, (x0 - reach, y0 - reach, x0 + reach, y0 + reach))
    near_path = near_grid_path(lat, lon)
    if near_path is not None:
        return read_grid(near_path), far
    half = NEAR_HALF_WIDTH_M
    return read_grid(FAR_DEM, (x0 - half, y0 - half, x0 + half, y0 + half)), far


def compute_mask(lat: float, lon: float, observer_height_m: float = 0.0, grids=None) -> HorizonMask:
    """Horizon mask from the downloaded LOLA grids (takes a few seconds)."""
    near, far = grids if grids is not None else load_site_grids(lat, lon)
    mask = mask_from_grids(lat, lon, observer_height_m, near, far)
    samples = N_AZIMUTHS * len(_ray_distances(NEAR_RANGE_M, MAX_RANGE_M, NEAR_STEP_M, FAR_STEP_M))
    mask.meta["share_of_samples_without_data"] = round(mask.meta["samples_without_data"] / samples, 4)
    return mask


# --------------------------------------------------------------------------
# Stored masks
# --------------------------------------------------------------------------
MASKS_DIR = DATA_DIR / "masks"  # masks used by the app: <site key>_h<height>m.json
MASK_HEIGHTS_M = (0.0, 1.0, 2.0, 5.0, 10.0)  # heights offered for panels and antenna


def mask_path(key: str, observer_height_m: float) -> Path:
    return MASKS_DIR / f"{key}_h{float(observer_height_m):g}m.json"


def custom_key(lat: float, lon: float) -> str:
    """Key under which the mask of a hand-entered point is stored."""
    return f"custom_{lat:+08.4f}_{lon:+09.4f}".replace("+", "p").replace("-", "m").replace(".", "d")


def load_mask(key: str, observer_height_m: float = 0.0) -> Optional[HorizonMask]:
    """Stored mask of a site for an observer height, or None if it was never computed."""
    for folder in (MASKS_DIR, HORIZON_DIR):  # HORIZON_DIR: masks written before data/masks existed
        path = folder / f"{key}_h{float(observer_height_m):g}m.json"
        if path.exists():
            return HorizonMask.load(path)
    return None


def get_mask(key: str, lat: float, lon: float, observer_height_m: float = 0.0) -> Optional[HorizonMask]:
    """Stored mask; computed and stored first if the terrain data is on disk."""
    stored = load_mask(key, observer_height_m)
    if stored is not None:
        return stored
    if not terrain_available(lat, lon):
        return None
    mask = compute_mask(lat, lon, observer_height_m)
    mask.meta["site_key"] = key
    mask.save(mask_path(key, observer_height_m))
    return mask


def stored_heights(key: str) -> list:
    """Observer heights (m) for which a mask of this site is stored."""
    heights = set()
    for folder in (MASKS_DIR, HORIZON_DIR):
        for path in folder.glob(f"{key}_h*m.json"):
            try:
                heights.add(float(path.stem[len(key) + 2:-1]))
            except ValueError:
                continue
    return sorted(heights)


def has_all_heights(key: str) -> bool:
    """True when masks for every offered height are stored for this site."""
    return set(MASK_HEIGHTS_M) <= set(stored_heights(key))
