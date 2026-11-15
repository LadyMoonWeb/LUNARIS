"""Illumination check of the terrain horizon masks against published maps.

The long-term share of time with the Sun (and the Earth) above the terrain
horizon, computed with the stored horizon masks of ``lunarnav.terrain``, is
compared with two published products that are already on disk:

* PGDA product 69 (Mazarico et al. 2011): average solar illumination and
  average Earth visibility, hourly steps over 18.6 years, Sun as a disk.
* LROC WAC percentage-based illumination map (Speyerer and Robinson 2013):
  share of WAC images, 15 Feb 2010 to 5 Feb 2011, in which a pixel was lit.

There is no pass threshold. The differences are reported as they are, in
percentage points (this project minus the map). Nothing is downloaded and
nothing outside ``validation/results/`` is written.

For every site and both stored observer heights (0 m and 2 m), with
``margin = body altitude - mask(body azimuth)``:

    centre  share of instants with margin > 0 (the project's "sunlit")
    disc    mean visible fraction of the solar disk, horizon taken as a
            straight horizontal line at the mask elevation
    any     share of instants with margin > -(angular radius of the body)

Two further masks are built here with independent code (own great-circle
march, own sampling of the LOLA GeoTIFFs, ``lunarnav.terrain.mask_from_grids``
is not called) and run through the same percentages:

    independent  same sampling plan as the product, double precision
    coarse       as "independent", but the terrain within 14 km is first
                 averaged to the pixel size of the reference map (60 m or
                 120 m); a sensitivity test, not a copy of the map's method

The geometry spot check compares the stored mask of one site with the
independent mask in eight directions.

Outputs, in ``validation/results/``:
    illumination_summary.json   one row per site (0 m masks), notes, spot check
    illumination_samples.csv    one line per site x observer height x reference
    illumination_check.png      chart of reference and computed percentages

Run from the project root:  python validation/illumination_check.py
Redraw the chart only:      python validation/illumination_check.py --replot
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lunarnav import positions  # noqa: E402
from lunarnav.sites import SITES_BY_KEY  # noqa: E402
from lunarnav.terrain import latlon_to_xy as product_latlon_to_xy  # noqa: E402
from lunarnav.terrain import load_mask  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
REFERENCE = ROOT / "data" / "reference"
DEM = ROOT / "data" / "dem"

SITE_KEYS = ["check_connecting_ridge", "check_shackleton_rim", "check_de_gerlache_rim", "im2", "im2_planned"]
HEIGHTS_M = [0.0, 2.0]

MOON_RADIUS_M = 1_737_400.0
SUN_RADIUS_DEG = 0.2665  # mean angular radius of the Sun seen from the Moon
EARTH_RADIUS_DEG = 0.95  # approximate angular radius of the Earth seen from the Moon (diagnostic only)

# PGDA product 69: hourly steps over 18.6 years (one lunar nodal cycle).
LONG_START = pd.Timestamp("2010-01-01", tz="UTC")
LONG_DAYS = 6794
# LROC WAC map: images from 15 Feb 2010 to 5 Feb 2011 (both days included here).
LROC_START = pd.Timestamp("2010-02-15", tz="UTC")
LROC_END = pd.Timestamp("2011-02-06", tz="UTC")  # exclusive
LROC_MIN_LAT = -88.0  # the map covers 88 S to 90 S only

PGDA_SUN = ["AVGVISIB_85S_060M_201608.TIF", "AVGVISIB_75S_120M_201608.TIF"]  # finest first
PGDA_EARTH = ["AVGVISIB_85S_060M_201608_EARTH.TIF", "AVGVISIB_75S_120M_201608_EARTH.TIF"]
PGDA_SCALE = 0.00004  # int16 -> fraction of time
PGDA_FINE_MIN_LAT = -85.0  # the 60 m maps are valid south of 85 S
LROC_IMG = "WAC_POLE_ILL_PCT_SOUTH_100M.IMG"
LROC_TIF = "WAC_POLE_ILL_PCT_SOUTH_100M.TIF"

# Terrain files and the sampling plan of the product (repeated here on purpose:
# the independent mask must not import them from lunarnav.terrain).
FAR_DEM = "LDEM_80S_40MPP_ADJ.TIF"
NEAR_DEMS = {
    "check_connecting_ridge": "near_connecting_ridge_10m.tif",
    "check_shackleton_rim": "near_shackleton_rim_10m.tif",
    "check_de_gerlache_rim": "near_de_gerlache_rim_10m.tif",
    "im2": "near_athena_10m.tif",
    "im2_planned": "near_athena_10m.tif",
}
N_AZIMUTHS = 720
NEAR_RANGE_M, MAX_RANGE_M = 14_000.0, 150_000.0
NEAR_STEP_M, FAR_STEP_M = 10.0, 40.0

SPOT_SITE = "im2"
SPOT_AZIMUTHS = [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]
SPOT_LONG_RANGE_M = 300_000.0


# --------------------------------------------------------------------------
# Map projection (written here independently of lunarnav.terrain)
# --------------------------------------------------------------------------
def to_map_xy(lat_deg, lon_deg):
    """South polar stereographic, true scale at the pole, sphere 1737.4 km.

    Longitude 0 points to +y and longitude 90 E to +x, as in the GeoTIFFs.
    """
    lat, lon = np.radians(np.asarray(lat_deg, dtype=float)), np.radians(np.asarray(lon_deg, dtype=float))
    r = 2.0 * MOON_RADIUS_M * np.tan((np.pi / 2.0 + lat) / 2.0)
    return r * np.sin(lon), r * np.cos(lon)


# --------------------------------------------------------------------------
# Reference maps
# --------------------------------------------------------------------------
def pgda_value(files, lat: float, lon: float) -> dict:
    """Percent of time from the PGDA map pixel that contains the point.

    The 60 m map is used where the site is south of 85 S and the pixel holds
    data, otherwise the 120 m map.
    """
    import rasterio
    from rasterio.windows import Window

    x, y = to_map_xy(lat, lon)
    for name in files:
        if "85S" in name and lat > PGDA_FINE_MIN_LAT:
            continue
        with rasterio.open(REFERENCE / name) as src:
            row, col = src.index(float(x), float(y))
            if not (1 <= row < src.height - 1 and 1 <= col < src.width - 1):
                continue
            raw = src.read(1, window=Window(col - 1, row - 1, 3, 3)).astype(float)
            raw[raw == src.nodata] = np.nan
            pixel_m = abs(src.transform.a)
            centre_x, centre_y = src.xy(row, col)
        percent = raw * PGDA_SCALE * 100.0
        if not np.isfinite(percent[1, 1]):
            continue
        return {"file": name, "pixel_m": pixel_m, "row": int(row), "col": int(col),
                "pct": float(percent[1, 1]), "min_3x3": float(np.nanmin(percent)), "max_3x3": float(np.nanmax(percent)),
                "offset_from_pixel_centre_m": float(np.hypot(x - centre_x, y - centre_y))}
    return {"file": None, "pixel_m": None, "row": None, "col": None, "pct": np.nan, "min_3x3": np.nan,
            "max_3x3": np.nan, "offset_from_pixel_centre_m": np.nan}


def read_lroc() -> dict:
    """The LROC WAC map as float percent, with its geometry from the attached PDS label.

    The 8-bit GeoTIFF of the same map is opened only to confirm the geometry:
    its geotransform has to give the same pixel grid as the label, and its
    values have to follow the float values (same orientation and byte order).
    """
    import rasterio

    path = REFERENCE / LROC_IMG
    with open(path, "rb") as handle:
        head = handle.read(20000).decode("latin-1")

    def label(key: str) -> float:
        return float(re.search(rf"^\s*\^?{key}\s*=\s*([-+0-9.eE]+)", head, re.MULTILINE).group(1))

    record_bytes, label_records = int(label("RECORD_BYTES")), int(label("LABEL_RECORDS"))
    lines, samples = int(label("LINES")), int(label("LINE_SAMPLES"))
    scale = label("MAP_SCALE")
    line_offset, sample_offset = label("LINE_PROJECTION_OFFSET"), label("SAMPLE_PROJECTION_OFFSET")

    data = np.fromfile(path, dtype="<f4", count=lines * samples, offset=record_bytes * label_records)
    data = data.reshape(lines, samples).astype(float)
    data[data < -1e30] = np.nan  # PDS special values (null, saturation) are all near -3.4e38

    # The offsets count pixels from the centre of the first pixel to the pole,
    # so the outer edge of the first pixel is half a pixel further out.
    x_left = -(sample_offset + 0.5) * scale
    y_top = (line_offset + 0.5) * scale

    with rasterio.open(REFERENCE / LROC_TIF) as src:
        transform = src.transform
        browse = src.read(1).astype(float)
    same_grid = bool(browse.shape == data.shape and abs(transform.c - x_left) < 1e-6 and abs(transform.f - y_top) < 1e-6
                     and abs(transform.a - scale) < 1e-9 and abs(transform.e + scale) < 1e-9)
    if not same_grid:
        raise RuntimeError("the LROC IMG label and the GeoTIFF geotransform describe different pixel grids")
    valid = np.isfinite(data)
    return {"data": data, "browse": browse, "x_left": x_left, "y_top": y_top, "pixel_m": scale,
            "same_grid_as_geotiff": same_grid,
            "correlation_with_geotiff": float(np.corrcoef(data[valid], browse[valid])[0, 1]),
            "correlation_with_flipped_geotiff": float(np.corrcoef(data[valid], browse[::-1][valid])[0, 1])}


def lroc_value(lroc: dict, lat: float, lon: float) -> dict:
    empty = {"file": None, "pixel_m": None, "row": None, "col": None, "pct": np.nan, "min_3x3": np.nan,
             "max_3x3": np.nan, "offset_from_pixel_centre_m": np.nan}
    if lat > LROC_MIN_LAT:
        return empty
    x, y = to_map_xy(lat, lon)
    data, pixel = lroc["data"], lroc["pixel_m"]
    col = int(np.floor((x - lroc["x_left"]) / pixel))
    row = int(np.floor((lroc["y_top"] - y) / pixel))
    if not (1 <= row < data.shape[0] - 1 and 1 <= col < data.shape[1] - 1) or not np.isfinite(data[row, col]):
        return empty
    block = data[row - 1:row + 2, col - 1:col + 2]
    centre_x, centre_y = lroc["x_left"] + (col + 0.5) * pixel, lroc["y_top"] - (row + 0.5) * pixel
    return {"file": LROC_IMG, "pixel_m": pixel, "row": row, "col": col, "pct": float(data[row, col]),
            "min_3x3": float(np.nanmin(block)), "max_3x3": float(np.nanmax(block)),
            "offset_from_pixel_centre_m": float(np.hypot(x - centre_x, y - centre_y))}


# --------------------------------------------------------------------------
# Percentages from a series of margins above the horizon
# --------------------------------------------------------------------------
def disc_fraction(margin_deg: np.ndarray, radius_deg: float) -> np.ndarray:
    """Visible fraction of a disk cut by a straight horizontal horizon line."""
    s = np.clip(np.asarray(margin_deg, dtype=float) / radius_deg, -1.0, 1.0)
    return (np.arccos(-s) + s * np.sqrt(1.0 - s * s)) / np.pi


def percentages(margin_deg: np.ndarray, radius_deg: float) -> dict:
    return {
        "centre": 100.0 * float(np.mean(margin_deg > 0.0)),
        "disc": 100.0 * float(np.mean(disc_fraction(margin_deg, radius_deg))),
        "any": 100.0 * float(np.mean(margin_deg > -radius_deg)),
    }


def as_function(mask_deg: np.ndarray):
    """720 horizon elevations as a function of azimuth (linear, periodic), like the product's mask."""
    azimuth = np.arange(N_AZIMUTHS) * (360.0 / N_AZIMUTHS)
    return lambda az: np.interp(np.mod(az, 360.0), azimuth, mask_deg, period=360.0)


# --------------------------------------------------------------------------
# Independent horizon mask (does not use lunarnav.terrain)
# --------------------------------------------------------------------------
def read_box(path: Path, x_min: float, y_min: float, x_max: float, y_max: float):
    """Part of a north-up GeoTIFF covering a box: (heights, left edge, top edge, pixel size)."""
    import rasterio
    from rasterio.windows import Window

    with rasterio.open(path) as src:
        t = src.transform
        pixel = t.a
        col0 = max(int(np.floor((x_min - t.c) / pixel)), 0)
        col1 = min(int(np.ceil((x_max - t.c) / pixel)), src.width)
        row0 = max(int(np.floor((t.f - y_max) / pixel)), 0)
        row1 = min(int(np.ceil((t.f - y_min) / pixel)), src.height)
        heights = src.read(1, window=Window(col0, row0, col1 - col0, row1 - row0))
        if src.nodata is not None and not np.isnan(src.nodata):
            heights = np.where(heights == src.nodata, np.nan, heights)
    return heights.astype(np.float32), t.c + col0 * pixel, t.f - row0 * pixel, pixel


def bilinear(box, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Height at map points from the four surrounding pixel centres (float64); NaN off the box."""
    heights, x_left, y_top, pixel = box
    col = (np.asarray(x, dtype=float) - x_left) / pixel - 0.5
    row = (y_top - np.asarray(y, dtype=float)) / pixel - 0.5
    c0, r0 = np.floor(col).astype(np.int64), np.floor(row).astype(np.int64)
    inside = (c0 >= 0) & (r0 >= 0) & (c0 + 1 < heights.shape[1]) & (r0 + 1 < heights.shape[0])
    c0, r0 = np.where(inside, c0, 0), np.where(inside, r0, 0)
    fc, fr = col - c0, row - r0
    value = (heights[r0, c0].astype(float) * (1 - fc) * (1 - fr) + heights[r0, c0 + 1].astype(float) * fc * (1 - fr)
             + heights[r0 + 1, c0].astype(float) * (1 - fc) * fr + heights[r0 + 1, c0 + 1].astype(float) * fc * fr)
    return np.where(inside, value, np.nan)


def block_average(box, pixel_out: float):
    """Average a grid to a coarser pixel size; block edges fall on multiples of that size.

    The PGDA maps have their pixel edges on multiples of the pixel size, so the
    averaged cells coincide with the map pixels.
    """
    heights, x_left, y_top, pixel = box
    factor = int(round(pixel_out / pixel))
    skip_cols = int(round((np.ceil(x_left / pixel_out) * pixel_out - x_left) / pixel))
    skip_rows = int(round((y_top - np.floor(y_top / pixel_out) * pixel_out) / pixel))
    rows = (heights.shape[0] - skip_rows) // factor
    cols = (heights.shape[1] - skip_cols) // factor
    part = heights[skip_rows:skip_rows + rows * factor, skip_cols:skip_cols + cols * factor].astype(float)
    coarse = part.reshape(rows, factor, cols, factor).mean(axis=(1, 3))  # NaN if any cell of a block is missing
    return coarse.astype(np.float32), x_left + skip_cols * pixel, y_top - skip_rows * pixel, pixel_out


def ray_points(lat_deg: float, lon_deg: float, azimuth_deg: np.ndarray, distance_m: np.ndarray):
    """Map x, y along great circles, shape (azimuths, distances), by rotating 3-D unit vectors."""
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    az = np.radians(np.asarray(azimuth_deg, dtype=float))[:, None, None]
    up = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    east = np.array([-np.sin(lon), np.cos(lon), 0.0])
    north = np.array([-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)])
    heading = north * np.cos(az) + east * np.sin(az)  # (azimuths, 1, 3)
    theta = (np.asarray(distance_m, dtype=float) / MOON_RADIUS_M)[None, :, None]
    point = up * np.cos(theta) + heading * np.sin(theta)  # (azimuths, distances, 3)
    lat2 = np.degrees(np.arcsin(np.clip(point[..., 2], -1.0, 1.0)))
    lon2 = np.degrees(np.arctan2(point[..., 1], point[..., 0]))
    return to_map_xy(lat2, lon2)


def ray_distances(near_step: float = NEAR_STEP_M, far_step: float = FAR_STEP_M, max_range: float = MAX_RANGE_M):
    near = np.arange(near_step, NEAR_RANGE_M + near_step / 2, near_step)
    far = np.arange(NEAR_RANGE_M + far_step, max_range + far_step / 2, far_step)
    return near, far


def terrain_profiles(site, near_box, far_box, azimuths, near_step: float = NEAR_STEP_M, far_step: float = FAR_STEP_M):
    """Terrain heights along the rays: distances (m) and heights (azimuths x distances)."""
    near_d, far_d = ray_distances(near_step, far_step)
    azimuths = np.asarray(azimuths, dtype=float)
    heights = np.empty((len(azimuths), len(near_d) + len(far_d)))
    for first in range(0, len(azimuths), 60):  # chunks keep the memory use small
        chunk = azimuths[first:first + 60]
        x, y = ray_points(site.lat, site.lon, chunk, near_d)
        near_h = bilinear(near_box, x, y)
        holes = ~np.isfinite(near_h)
        if holes.any():  # outside the fine grid: take the coarse one, as the product does
            near_h[holes] = bilinear(far_box, x[holes], y[holes])
        x, y = ray_points(site.lat, site.lon, chunk, far_d)
        heights[first:first + 60] = np.concatenate([near_h, bilinear(far_box, x, y)], axis=1)
    return np.concatenate([near_d, far_d]), heights


def elevation_deg(distance_m, height_m, observer_radius_m: float, single_precision: bool = False):
    """Elevation angle of terrain points seen from the observer, with the curvature of the Moon.

    ``single_precision=True`` reproduces one detail of lunarnav.terrain: there
    the terrain radius is formed as ``MOON_RADIUS_M + heights`` on a float32
    array, which rounds it to the float32 spacing at 1.74e6 m, i.e. 0.125 m.
    """
    terrain_radius = MOON_RADIUS_M + np.asarray(height_m, dtype=float)
    if single_precision:
        terrain_radius = (np.float32(MOON_RADIUS_M) + np.asarray(height_m, dtype=np.float32)).astype(float)
    theta = np.asarray(distance_m, dtype=float) / MOON_RADIUS_M
    return np.degrees(np.arctan2(terrain_radius * np.cos(theta) - observer_radius_m, terrain_radius * np.sin(theta)))


def horizon_from_profiles(distance_m, heights, observer_radius_m: float, single_precision: bool = False):
    """Mask (deg) and horizon distance (km) per azimuth: the highest angle along each ray."""
    angle = elevation_deg(distance_m[None, :], heights, observer_radius_m, single_precision)
    angle = np.where(np.isfinite(angle), angle, -np.inf)
    best = angle.argmax(axis=1)
    return angle[np.arange(len(best)), best], distance_m[best] / 1000.0


class SiteTerrain:
    """Terrain around a site, read once, and the masks derived from it by this script."""

    def __init__(self, key: str, coarse_pixel_m: float):
        self.site = SITES_BY_KEY[key]
        self.x0, self.y0 = (float(v) for v in to_map_xy(self.site.lat, self.site.lon))
        reach = MAX_RANGE_M * 1.01 + 2000.0  # map scale is up to 0.8 % above 1 at 80 S
        with_margin = (self.x0 - reach, self.y0 - reach, self.x0 + reach, self.y0 + reach)
        self.far_box = read_box(DEM / FAR_DEM, *with_margin)
        self.near_box = read_box(DEM / NEAR_DEMS[key], -1e9, -1e9, 1e9, 1e9)  # the whole 10 m window
        azimuths = np.arange(N_AZIMUTHS) * (360.0 / N_AZIMUTHS)

        self.site_height = float(bilinear(self.near_box, np.array([self.x0]), np.array([self.y0]))[0])
        self.distance, self.heights = terrain_profiles(self.site, self.near_box, self.far_box, azimuths)

        self.coarse_pixel_m = coarse_pixel_m
        coarse_box = block_average(self.near_box, coarse_pixel_m)
        self.coarse_site_height = float(bilinear(coarse_box, np.array([self.x0]), np.array([self.y0]))[0])
        _, self.coarse_heights = terrain_profiles(self.site, coarse_box, self.far_box, azimuths)

    def mask(self, observer_height_m: float, single_precision: bool = False):
        return horizon_from_profiles(self.distance, self.heights, MOON_RADIUS_M + self.site_height + observer_height_m,
                                     single_precision)

    def coarse_mask(self, observer_height_m: float):
        return horizon_from_profiles(self.distance, self.coarse_heights,
                                     MOON_RADIUS_M + self.coarse_site_height + observer_height_m)


# --------------------------------------------------------------------------
# One site
# --------------------------------------------------------------------------
def check_site(key: str, lroc: dict):
    """All comparisons of one site: records (height x reference) and its terrain."""
    site = SITES_BY_KEY[key]
    x, y = to_map_xy(site.lat, site.lon)
    px, py = product_latlon_to_xy(site.lat, site.lon)
    if np.hypot(x - px, y - py) > 0.01:
        raise RuntimeError(f"{key}: this script and lunarnav.terrain disagree on the map coordinates "
                           f"({x:.3f}, {y:.3f}) vs ({float(px):.3f}, {float(py):.3f})")

    times = pd.date_range(LONG_START, periods=LONG_DAYS * 24, freq="h")
    table = positions(site.lat, site.lon, times)
    everything = np.ones(len(table), dtype=bool)
    in_lroc = ((table["time_utc"] >= LROC_START) & (table["time_utc"] < LROC_END)).values
    alt = {"sun": table["sun_alt_deg"].values, "earth": table["earth_alt_deg"].values}
    az = {"sun": table["sun_az_deg"].values, "earth": table["earth_az_deg"].values}
    radius = {"sun": SUN_RADIUS_DEG, "earth": EARTH_RADIUS_DEG}

    comparisons = {  # reference -> (map value, body, instants used, first instant, last instant)
        "pgda_sun": (pgda_value(PGDA_SUN, site.lat, site.lon), "sun", everything, LONG_START, times[-1]),
        "lroc_sun": (lroc_value(lroc, site.lat, site.lon), "sun", in_lroc, LROC_START, LROC_END - pd.Timedelta(hours=1)),
        "pgda_earth": (pgda_value(PGDA_EARTH, site.lat, site.lon), "earth", everything, LONG_START, times[-1]),
    }
    terrain = SiteTerrain(key, comparisons["pgda_sun"][0]["pixel_m"] or 60.0)

    records = []
    for height in HEIGHTS_M:
        stored = load_mask(key, height)
        if stored is None:
            raise FileNotFoundError(f"no stored horizon mask for {key} at {height:g} m")
        own, _ = terrain.mask(height)
        own_single, _ = terrain.mask(height, single_precision=True)
        coarse, _ = terrain.coarse_mask(height)
        masks = {"ours": stored, "indep": as_function(own), "coarse": as_function(coarse)}
        near_share = None if stored.distance_km is None else 100.0 * float(np.mean(stored.distance_km <= 0.0201))

        for name, (reference, body, chosen, first, last) in comparisons.items():
            record = {
                "key": key, "name": site.name, "lat": site.lat, "lon": site.lon, "map_x_m": float(x), "map_y_m": float(y),
                "observer_height_m": height, "site_height_m": stored.meta.get("site_height_m"),
                "reference": name, "reference_file": reference["file"], "reference_pixel_m": reference["pixel_m"],
                "reference_row": reference["row"], "reference_col": reference["col"],
                "site_offset_from_pixel_centre_m": reference["offset_from_pixel_centre_m"],
                "period_start_utc": first.strftime("%Y-%m-%d %H:%M"), "period_end_utc": last.strftime("%Y-%m-%d %H:%M"),
                "instants": int(chosen.sum()),
                "reference_pct": reference["pct"], "reference_min_3x3": reference["min_3x3"],
                "reference_max_3x3": reference["max_3x3"],
            }
            for label, mask in masks.items():
                got = percentages(alt[body][chosen] - mask(az[body][chosen]), radius[body])
                for kind in ("centre", "disc", "any"):
                    record[f"{label}_{kind}_pct"] = got[kind]
            for kind in ("centre", "disc", "any"):
                record[f"diff_{kind}_pp"] = record[f"ours_{kind}_pct"] - reference["pct"]  # NaN without a map value
            record.update({
                "stored_mask_min_deg": float(stored.mask_deg.min()), "stored_mask_mean_deg": float(stored.mask_deg.mean()),
                "stored_mask_max_deg": float(stored.mask_deg.max()),
                "stored_mask_horizon_within_20m_pct_of_azimuths": near_share,
                "stored_vs_indep_mask_max_abs_deg": float(np.abs(stored.mask_deg - own).max()),
                "stored_vs_indep_mask_mean_abs_deg": float(np.abs(stored.mask_deg - own).mean()),
                "stored_vs_indep_single_precision_max_abs_deg": float(np.abs(stored.mask_deg - own_single).max()),
                "coarse_terrain_pixel_m": terrain.coarse_pixel_m,
            })
            records.append(record)
    return records, terrain


# --------------------------------------------------------------------------
# Geometry spot check of one stored mask
# --------------------------------------------------------------------------
def beyond_the_ray(site, azimuth: float, observer_radius: float):
    """Highest elevation between 150 km and 300 km (or the edge of the 40 m grid) in one direction."""
    distance = np.arange(MAX_RANGE_M + FAR_STEP_M, SPOT_LONG_RANGE_M + FAR_STEP_M / 2, FAR_STEP_M)
    x, y = ray_points(site.lat, site.lon, np.array([azimuth]), distance)
    box = read_box(DEM / FAR_DEM, x.min() - 200.0, y.min() - 200.0, x.max() + 200.0, y.max() + 200.0)
    height = bilinear(box, x, y)[0]
    usable = np.isfinite(height)
    if not usable.any():
        return -np.inf, MAX_RANGE_M
    angle = elevation_deg(distance[usable], height[usable], observer_radius)
    return float(angle.max()), float(distance[usable].max())


def geometry_spot_check(terrain: SiteTerrain, samples: pd.DataFrame) -> dict:
    """Stored mask of one site against the independent mask in eight directions."""
    site = terrain.site
    azimuths = np.arange(N_AZIMUTHS) * (360.0 / N_AZIMUTHS)
    half_distance, half_heights = terrain_profiles(site, terrain.near_box, terrain.far_box, SPOT_AZIMUTHS,
                                                   NEAR_STEP_M / 2, FAR_STEP_M / 2)
    rows = []
    for height in HEIGHTS_M:
        stored = load_mask(SPOT_SITE, height)
        observer_radius = MOON_RADIUS_M + terrain.site_height + height
        own, own_km = terrain.mask(height)
        single, _ = terrain.mask(height, single_precision=True)
        half, _ = horizon_from_profiles(half_distance, half_heights, observer_radius)
        for number, azimuth in enumerate(SPOT_AZIMUTHS):
            i = int(np.argmin(np.abs(azimuths - azimuth)))
            beyond, reach = beyond_the_ray(site, azimuth, observer_radius)
            rows.append({
                "azimuth_deg": azimuth, "observer_height_m": height,
                "stored_mask_deg": round(float(stored.mask_deg[i]), 4),
                "recomputed_deg": round(float(own[i]), 4),
                "diff_deg": round(float(own[i] - stored.mask_deg[i]), 4),
                "stored_horizon_km": None if stored.distance_km is None else round(float(stored.distance_km[i]), 3),
                "recomputed_horizon_km": round(float(own_km[i]), 3),
                "recomputed_single_precision_deg": round(float(single[i]), 4),
                "diff_single_precision_deg": round(float(single[i] - stored.mask_deg[i]), 4),
                "recomputed_half_step_deg": round(float(half[number]), 4),
                "highest_beyond_150km_deg": None if not np.isfinite(beyond) else round(beyond, 4),
                "terrain_data_reach_km": round(reach / 1000.0, 1),
                "anything_higher_beyond_150km": bool(beyond > own[i]),
            })

    def worst(column: str, height=None) -> float:
        return round(max(abs(r[column]) for r in rows if height is None or r["observer_height_m"] == height), 4)

    all_azimuths = []
    for key in SITE_KEYS:
        for height in HEIGHTS_M:
            row = samples[(samples["key"] == key) & (samples["observer_height_m"] == height)
                          & (samples["reference"] == "pgda_sun")].iloc[0]
            all_azimuths.append({
                "key": key, "observer_height_m": height,
                "max_abs_diff_deg": round(float(row["stored_vs_indep_mask_max_abs_deg"]), 4),
                "mean_abs_diff_deg": round(float(row["stored_vs_indep_mask_mean_abs_deg"]), 4),
                "max_abs_diff_single_precision_deg": round(float(row["stored_vs_indep_single_precision_max_abs_deg"]), 4),
                "stored_horizon_within_20m_pct_of_azimuths": _r1(row["stored_mask_horizon_within_20m_pct_of_azimuths"]),
                "sun_disc_pct_18y_stored": round(float(row["ours_disc_pct"]), 2),
                "sun_disc_pct_18y_recomputed": round(float(row["indep_disc_pct"]), 2),
                "sun_disc_pct_18y_coarse_terrain": round(float(row["coarse_disc_pct"]), 2),
                "coarse_terrain_pixel_m": float(row["coarse_terrain_pixel_m"]),
            })

    def over_all(column: str, height: float) -> float:
        return max(entry[column] for entry in all_azimuths if entry["observer_height_m"] == height)

    explanation = (
        "Measured: over all 720 azimuths of all five sites the stored masks differ from the double-precision "
        f"recomputation by up to {over_all('max_abs_diff_deg', 0.0):.2f} deg at 0 m and "
        f"{over_all('max_abs_diff_deg', 2.0):.2f} deg at 2 m; when the recomputation rounds the terrain radius to "
        "single precision the largest difference falls to "
        f"{max(entry['max_abs_diff_single_precision_deg'] for entry in all_azimuths):.4f} deg. "
        "Cause: in lunarnav/terrain.py, mask_from_grids evaluates 'MOON_RADIUS_M + heights' on a float32 array, so the "
        "terrain radius is rounded to 0.125 m (the float32 spacing at 1.74e6 m) while the observer radius stays in "
        "double precision. A height error of up to 0.0625 m is 0.36 deg for terrain 10 m away, 0.036 deg at 100 m and "
        "0.004 deg at 1 km, so it matters where the horizon is the ground next to the observer (0 m masks). "
        "Effect on the 18.6-year Sun percentage (disk fraction): at most "
        f"{max(abs(e['sun_disc_pct_18y_stored'] - e['sun_disc_pct_18y_recomputed']) for e in all_azimuths if e['observer_height_m'] == 0.0):.1f}"
        " points at 0 m and "
        f"{max(abs(e['sun_disc_pct_18y_stored'] - e['sun_disc_pct_18y_recomputed']) for e in all_azimuths if e['observer_height_m'] == 2.0):.1f}"
        " points at 2 m.")

    return {
        "site_key": SPOT_SITE, "site_name": site.name, "lat": site.lat, "lon": site.lon,
        "method": "Independent code in validation/illumination_check.py: great circle by rotating 3-D unit vectors, "
                  "own bilinear sampling of the LOLA GeoTIFFs read with rasterio, elevation = atan2(r1 cos(theta) - r0, "
                  "r1 sin(theta)) with r0 = R + site height + observer height, r1 = R + h, theta = d / R, double "
                  "precision, same sampling plan as the product (10 m steps on the 10 m grid to 14 km, 40 m steps on "
                  "the 40 m grid to 150 km). lunarnav.terrain.mask_from_grids is not called.",
        "site_height_m_recomputed": round(terrain.site_height, 2),
        "site_height_m_in_mask": load_mask(SPOT_SITE, 0.0).meta.get("site_height_m"),
        "azimuths_deg": SPOT_AZIMUTHS, "observer_heights_m": HEIGHTS_M,
        "max_abs_diff_deg": worst("diff_deg"),
        "max_abs_diff_deg_h0m": worst("diff_deg", 0.0),
        "max_abs_diff_deg_h2m": worst("diff_deg", 2.0),
        "mean_abs_diff_deg": round(float(np.mean([abs(r["diff_deg"]) for r in rows])), 4),
        "max_abs_diff_single_precision_deg": worst("diff_single_precision_deg"),
        "max_abs_change_half_step_deg": round(max(abs(r["recomputed_half_step_deg"] - r["recomputed_deg"]) for r in rows), 4),
        "anything_higher_beyond_150km": bool(any(r["anything_higher_beyond_150km"] for r in rows)),
        "explanation_of_the_difference": explanation,
        "rows": rows,
        "all_sites_all_720_azimuths": all_azimuths,
    }


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
def _r1(value):
    """Round to one decimal; None for missing values."""
    return None if value is None or not np.isfinite(value) else round(float(value), 1)


def pick(samples: pd.DataFrame, key: str, reference: str, height: float) -> pd.Series:
    chosen = samples[(samples["key"] == key) & (samples["reference"] == reference)
                     & (samples["observer_height_m"] == height)]
    return chosen.iloc[0]


def summary_rows(samples: pd.DataFrame) -> list:
    rows = []
    for key in SITE_KEYS:
        pgda, lroc, earth = (pick(samples, key, name, 0.0) for name in ("pgda_sun", "lroc_sun", "pgda_earth"))
        pgda2, lroc2 = pick(samples, key, "pgda_sun", 2.0), pick(samples, key, "lroc_sun", 2.0)
        has_lroc = bool(np.isfinite(lroc["reference_pct"]))
        rows.append({
            "key": key, "name": pgda["name"], "lat": float(pgda["lat"]), "lon": round(float(pgda["lon"]), 5),
            "pgda_pct": _r1(pgda["reference_pct"]), "pgda_min_3x3": _r1(pgda["reference_min_3x3"]),
            "pgda_max_3x3": _r1(pgda["reference_max_3x3"]),
            "ours_disc_pct_18y": _r1(pgda["ours_disc_pct"]), "ours_centre_pct_18y": _r1(pgda["ours_centre_pct"]),
            "diff_disc_vs_pgda_pp": _r1(pgda["diff_disc_pp"]),
            "lroc_pct": _r1(lroc["reference_pct"]), "lroc_min_3x3": _r1(lroc["reference_min_3x3"]),
            "lroc_max_3x3": _r1(lroc["reference_max_3x3"]),
            "ours_centre_pct_2010": _r1(lroc["ours_centre_pct"]) if has_lroc else None,
            "diff_vs_lroc_pp": _r1(lroc["diff_centre_pp"]),
            "earth_pgda_pct": _r1(earth["reference_pct"]), "earth_ours_pct_18y": _r1(earth["ours_centre_pct"]),
            "diff_earth_pp": _r1(earth["diff_centre_pp"]),
            "ours_disc_pct_18y_h2m": _r1(pgda2["ours_disc_pct"]),
            "ours_centre_pct_2010_h2m": _r1(lroc2["ours_centre_pct"]) if has_lroc else None,
        })
    return rows


def _span(values, signed: bool = False) -> str:
    """'43.2 to 54.3' (or one number when both ends round to the same value)."""
    low, high = float(np.min(values)), float(np.max(values))
    form = "{:+.1f}" if signed else "{:.1f}"
    return form.format(low) if round(low, 1) == round(high, 1) else f"{form.format(low)} to {form.format(high)}"


def write_notes(samples: pd.DataFrame, spot: dict) -> list:
    """Plain-English notes. Every number is taken from the results of this run;
    the explanations are worded as "likely" wherever the cause was not demonstrated."""
    def rows(reference: str, height: float, group: str) -> pd.DataFrame:
        chosen = samples[(samples["reference"] == reference) & (samples["observer_height_m"] == height)]
        is_check = chosen["key"].str.startswith("check_")
        return chosen[is_check] if group == "check" else chosen[~is_check] if group == "landing" else chosen

    land0, land2 = rows("pgda_sun", 0.0, "landing"), rows("pgda_sun", 2.0, "landing")
    peak0, peak2 = rows("pgda_sun", 0.0, "check"), rows("pgda_sun", 2.0, "check")
    lroc0, lroc2 = rows("lroc_sun", 0.0, "check"), rows("lroc_sun", 2.0, "check")
    sun = samples[samples["reference"] != "pgda_earth"]
    sun_long = samples[samples["reference"] == "pgda_sun"]
    earth0, earth2 = rows("pgda_earth", 0.0, "all"), rows("pgda_earth", 2.0, "all")
    sun2 = rows("pgda_sun", 2.0, "all")
    one_year = samples[samples["reference"] == "lroc_sun"]["ours_centre_pct"].values
    all_years = sun_long["ours_centre_pct"].values  # same site x height order as one_year
    stored_vs_own = [abs(e["sun_disc_pct_18y_stored"] - e["sun_disc_pct_18y_recomputed"])
                     for e in spot["all_sites_all_720_azimuths"]]

    def worst_mask(height: float) -> float:
        return max(e["max_abs_diff_deg"] for e in spot["all_sites_all_720_azimuths"] if e["observer_height_m"] == height)

    return [
        "Differences are this project minus the map, in percentage points of time. At the two IM-2 points this project "
        f"gives {_span(land0['ours_disc_pct'])} % of time in sunlight over 18.6 years at 0 m and "
        f"{_span(land2['ours_disc_pct'])} % at 2 m, against {_span(land0['reference_pct'])} % in the PGDA map "
        f"({_span(land0['diff_disc_pp'], True)} points at 0 m, {_span(land2['diff_disc_pp'], True)} at 2 m).",

        "At the three polar check points, which are sharp summits, the answer depends strongly on the height above the "
        f"ground: at 0 m this project gives {_span(peak0['ours_disc_pct'])} % against {_span(peak0['reference_pct'])} % "
        f"in the PGDA map ({_span(peak0['diff_disc_pp'], True)} points), at 2 m it gives "
        f"{_span(peak2['ours_disc_pct'])} % ({_span(peak2['diff_disc_pp'], True)} points).",

        "The 0 m gap is likely a matter of scale rather than of the Sun's position: on the 10 m terrain the horizon of "
        f"an observer at 0 m is the ground within 20 m in "
        f"{_span(peak0['stored_mask_horizon_within_20m_pct_of_azimuths'])} % of directions, detail that a 60 m map pixel "
        "cannot hold. As a test, averaging the terrain around each point to the 60 m pixel of the map raises the 0 m "
        f"result to {_span(peak0['coarse_disc_pct'])} %; a different version of the elevation model (the map dates from "
        "2016, our terrain from 2023) may explain part of the rest, which was not tested.",

        f"The LROC map, made from photographs of the surface in 2010-2011, shows {_span(lroc0['reference_pct'])} % at "
        f"the same three points: this project's 0 m values differ from it by {_span(lroc0['diff_centre_pp'], True)} "
        f"points and its 2 m values by {_span(lroc2['diff_centre_pp'], True)} points. This is consistent with a camera "
        "recording whether the ground itself is lit, but the LROC pixel is 100 m and its brightness threshold is "
        "conservative, so the agreement is indicative only.",

        "The definition of 'lit' matters little for the Sun: the visible fraction of the disk and the disk centre differ "
        f"by at most {np.abs(sun['ours_disc_pct'] - sun['ours_centre_pct']).max():.1f} points and one year (2010-2011) "
        f"differs from 18.6 years by at most {np.abs(one_year - all_years).max():.1f} points, while counting any visible "
        f"part of the disk adds {_span(sun_long['ours_any_pct'] - sun_long['ours_centre_pct'])} points. For the Earth "
        f"this project (centre of the Earth above the horizon, 0 m) is {_span(earth0['diff_centre_pp'], True)} points "
        "from the PGDA Earth map; counting a body as visible when any part of its disk shows, for an observer at 2 m, "
        f"comes within {np.abs(earth2['diff_any_pp']).max():.1f} points of the Earth map and "
        f"{np.abs(sun2['diff_any_pp']).max():.1f} points of the Sun map at all five points. This suggests that the maps "
        "count partial visibility, which we could not confirm beyond the product page.",

        # Wording added by the main session after the rounding bug was fixed: the first
        # run of this check found differences of up to 0.36 degrees at 0 m.
        ("An independent recomputation of the horizon from the same elevation data reproduces the stored masks to "
         f"within {worst_mask(2.0):.3f} degrees at 2 m and {worst_mask(0.0):.3f} degrees at 0 m. The first run of "
         "this check found differences of up to 0.36 degrees at 0 m, caused by single-precision rounding of terrain "
         "heights inside the mask calculation; that was fixed and the masks were rebuilt."
         if max(worst_mask(2.0), worst_mask(0.0)) < 0.01 else
         "An independent recomputation of the horizon from the same elevation data reproduces the stored masks to "
         f"within {worst_mask(2.0):.2f} degrees at 2 m and {worst_mask(0.0):.2f} degrees at 0 m; the difference comes "
         "from the rounding of terrain heights to 0.125 m inside the mask calculation and changes the 18.6-year Sun "
         f"percentages by at most {max(stored_vs_own):.1f} points."),
    ]


def build_references(samples: pd.DataFrame, lroc: dict) -> dict:
    files = {name: sorted(set(samples.loc[samples["reference"] == name, "reference_file"].dropna()))
             for name in ("pgda_sun", "pgda_earth", "lroc_sun")}
    return {
        "sign_convention": "All differences are this project minus the reference map, in percentage points of time.",
        "rows": "The rows use the stored 0 m masks; keys ending in _h2m use the stored 2 m masks. Differences are "
                "computed from unrounded values and then rounded to one decimal.",
        "pgda_sun": {
            "product": "PGDA product 69, average solar illumination", "url": "https://pgda.gsfc.nasa.gov/products/69",
            "citation": "Mazarico, E., Neumann, G. A., Smith, D. E., Zuber, M. T., Torrence, M. H. (2011). Illumination "
                        "conditions of the lunar polar regions using LOLA topography. Icarus, 211, 1066-1081. "
                        "doi:10.1016/j.icarus.2010.10.030",
            "files_used": files["pgda_sun"],
            "value": "int16 x 0.00004 = fraction of time; the pixel containing the site (60 m map south of 85 S where "
                     "it holds data, otherwise the 120 m map) and the lowest / highest of the 3 x 3 pixels around it",
            "definition_as_described_in_data_SOURCES_md": "hourly steps over 18.6 years, Sun treated as a disk",
            "compared_with": "ours_disc_pct_18y (mean visible fraction of the solar disk)",
        },
        "pgda_earth": {
            "product": "PGDA product 69, average Earth visibility", "url": "https://pgda.gsfc.nasa.gov/products/69",
            "files_used": files["pgda_earth"],
            "definition": "not known to us beyond the product page",
            "compared_with": "earth_ours_pct_18y (centre of the Earth above the mask); illumination_samples.csv also "
                             f"holds the disk-fraction and any-part values for an Earth radius of {EARTH_RADIUS_DEG} deg",
        },
        "lroc_sun": {
            "product": "LROC WAC percentage-based illumination map WAC_POLE_ILL_PCT_SOUTH_100M (88 S to 90 S, 100 m)",
            "url": "https://data.lroc.im-ldi.com/lroc/view_rdr/WAC_POLE_ILL_PCT_SOUTH",
            "citation": "Speyerer, E. J., Robinson, M. S. (2013). Persistently illuminated regions at the lunar poles: "
                        "Ideal sites for future exploration. Icarus, 222, 122-136. doi:10.1016/j.icarus.2012.10.010",
            "files_used": files["lroc_sun"],
            "value": "float32 percent from the IMG file; (times a pixel was seen lit) / (times it was imaged) in WAC "
                     "images from 15 Feb 2010 to 5 Feb 2011, conservative brightness threshold",
            "compared_with": "ours_centre_pct_2010 (centre of the solar disk above the mask)",
            "geometry_check": {
                "pixel_grid_from_label_equals_geotiff_geotransform": lroc["same_grid_as_geotiff"],
                "correlation_of_img_values_with_8bit_geotiff": round(lroc["correlation_with_geotiff"], 4),
                "correlation_with_geotiff_flipped_north_south": round(lroc["correlation_with_flipped_geotiff"], 4),
            },
        },
        "this_project": {
            "masks": "data/horizon/<key>_h0m.json and <key>_h2m.json, read with lunarnav.terrain.load_mask",
            "positions": "lunarnav.positions (skyfield, DE421, MOON_ME_DE421, apparent); checked against JPL Horizons "
                         "in validation/results/horizons_summary.json",
            "period_18y": f"hourly, {LONG_START:%Y-%m-%d} 00:00 UTC + {LONG_DAYS} days ({LONG_DAYS * 24} instants)",
            "period_2010": f"hourly, {LROC_START:%Y-%m-%d} 00:00 UTC to {LROC_END - pd.Timedelta(hours=1):%Y-%m-%d %H:%M} UTC",
            "centre": "share of instants with altitude - mask(azimuth) > 0",
            "disc": f"mean visible fraction of a disk of radius {SUN_RADIUS_DEG} deg cut by a straight horizontal "
                    "horizon line at the mask elevation",
            "any": "share of instants with any part of the disk above the mask",
        },
        "samples_file": "illumination_samples.csv: one line per site x observer height x reference. ours_* use the "
                        "stored masks; indep_* use the mask recomputed here in double precision; coarse_* use the "
                        "recomputed mask with the terrain within 14 km averaged to the reference map pixel size "
                        "(a sensitivity test, not the method of the maps).",
    }


# --------------------------------------------------------------------------
# Chart
# --------------------------------------------------------------------------
def plot(samples: pd.DataFrame, path: Path) -> None:
    """Reference and computed percentages per site: three panels of horizontal bars."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    ink, muted, grid, surface = "#0b0b0b", "#6f6e69", "#e1e0d9", "#fcfcfb"
    reference_colour, project_colour = "#a09f98", "#2a78d6"  # one colour per source
    panels = [
        ("pgda_sun", "ours_disc_pct", "Sun, 18.6 years", "PGDA map  vs  mean visible fraction of the solar disk"),
        ("lroc_sun", "ours_centre_pct", "Sun, Feb 2010 to Feb 2011", "LROC WAC map  vs  disk centre above the horizon"),
        ("pgda_earth", "ours_centre_pct", "Earth, 18.6 years", "PGDA Earth map  vs  Earth centre above the horizon"),
    ]
    keys = [key for key in SITE_KEYS if (samples["key"] == key).any()]
    labels = []
    for key in keys:
        first = samples[samples["key"] == key].iloc[0]
        labels.append("{}\n{:.2f}° S".format(str(first["name"]).replace("Check point: ", ""), abs(float(first["lat"]))))

    fig, axes = plt.subplots(1, 3, figsize=(14.5, 6.6), sharey=True, facecolor=surface)
    thickness, shift = 0.24, 0.27
    for ax, (reference, column, title, subtitle) in zip(axes, panels):
        ax.set_facecolor(surface)
        for row, key in enumerate(keys):
            ground, raised = pick(samples, key, reference, 0.0), pick(samples, key, reference, 2.0)
            if not np.isfinite(ground["reference_pct"]):
                ax.text(2, row, "outside this map\n(it covers 88° S to 90° S)", ha="left", va="center", fontsize=9,
                        color=muted)
                continue
            low, high, value = ground["reference_min_3x3"], ground["reference_max_3x3"], ground["reference_pct"]
            ax.barh(row - shift, value, height=thickness, color=reference_colour)
            ax.plot([low, high], [row - shift] * 2, color=ink, linewidth=1.1, solid_capstyle="butt")
            for end in (low, high):
                ax.plot([end, end], [row - shift - 0.06, row - shift + 0.06], color=ink, linewidth=1.1)
            ax.text(max(value, high) + 1.5, row - shift, f"{value:.1f}", ha="left", va="center", fontsize=9, color=ink)

            ax.barh(row, ground[column], height=thickness, color=project_colour)
            ax.text(ground[column] + 1.5, row, f"{ground[column]:.1f}", ha="left", va="center", fontsize=9, color=ink)
            ax.barh(row + shift, raised[column], height=thickness - 0.03, color=surface, edgecolor=project_colour,
                    linewidth=1.4)
            ax.text(raised[column] + 1.5, row + shift, f"{raised[column]:.1f}", ha="left", va="center", fontsize=9,
                    color=ink)
        ax.set_xlim(0, 112)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_ylim(len(keys) - 0.5, -0.5)
        ax.set_yticks(range(len(keys)))
        ax.set_yticklabels(labels, fontsize=10, color=ink)
        ax.set_xlabel("percent of time", fontsize=9, color=muted)
        ax.set_title(f"{title}\n", loc="left", fontsize=11.5, color=ink)
        ax.text(0, 1.012, subtitle, transform=ax.transAxes, ha="left", va="bottom", fontsize=9, color=muted)
        ax.grid(axis="x", color=grid, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(axis="both", which="both", length=0, labelsize=9, colors=muted)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#c3c2b7")
    for label in axes[0].get_yticklabels():
        label.set_color(ink)
        label.set_fontsize(10)

    handles = [
        Patch(facecolor=reference_colour, label="Reference map (black line: lowest to highest of the 3 x 3 pixels around the point)"),
        Patch(facecolor=project_colour, label="This project, observer at 0 m"),
        Patch(facecolor=surface, edgecolor=project_colour, linewidth=1.4, label="This project, observer at 2 m"),
    ]
    fig.suptitle("Share of time the Sun and the Earth are visible: published maps and this project's terrain horizon masks",
                 x=0.012, y=0.975, ha="left", fontsize=13, color=ink)
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.008, 0.945), ncol=3, frameon=False, fontsize=9.5,
               labelcolor=ink, handlelength=1.6, columnspacing=2.2)
    fig.tight_layout(rect=(0, 0, 1, 0.905))
    fig.savefig(path, dpi=160, facecolor=surface)
    plt.close(fig)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
PERCENT_COLUMNS = ["reference_pct", "reference_min_3x3", "reference_max_3x3", "diff_centre_pp", "diff_disc_pp",
                   "diff_any_pp", "stored_mask_horizon_within_20m_pct_of_azimuths"]
PERCENT_COLUMNS += [f"{label}_{kind}_pct" for label in ("ours", "indep", "coarse") for kind in ("centre", "disc", "any")]
ANGLE_COLUMNS = ["stored_mask_min_deg", "stored_mask_mean_deg", "stored_mask_max_deg", "stored_vs_indep_mask_max_abs_deg",
                 "stored_vs_indep_mask_mean_abs_deg", "stored_vs_indep_single_precision_max_abs_deg"]


def print_table(rows: list) -> None:
    def cell(value) -> str:
        return "   n/a" if value is None else f"{value:6.1f}"

    print("\nSite                          PGDA   ours disc 0 m / 2 m   diff 0 m |  LROC   ours centre 0 m / 2 m   diff 0 m |"
          "  Earth map   ours    diff")
    for row in rows:
        print(f"{row['name'][:28]:<28} {cell(row['pgda_pct'])}   {cell(row['ours_disc_pct_18y'])} / "
              f"{cell(row['ours_disc_pct_18y_h2m'])}      {cell(row['diff_disc_vs_pgda_pp'])} | {cell(row['lroc_pct'])}   "
              f"{cell(row['ours_centre_pct_2010'])} / {cell(row['ours_centre_pct_2010_h2m'])}        "
              f"{cell(row['diff_vs_lroc_pp'])} |     {cell(row['earth_pgda_pct'])} {cell(row['earth_ours_pct_18y'])}  "
              f"{cell(row['diff_earth_pp'])}")


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)

    if "--replot" in sys.argv:
        # Redraw the chart from the saved samples without recomputing anything.
        plot(pd.read_csv(RESULTS / "illumination_samples.csv"), RESULTS / "illumination_check.png")
        print("Chart redrawn from saved samples.")
        return 0

    lroc = read_lroc()
    print(f"Illumination check: {len(SITE_KEYS)} sites x {len(HEIGHTS_M)} observer heights, "
          f"{LONG_DAYS * 24} hourly instants per site", flush=True)
    records, spot_terrain = [], None
    for key in SITE_KEYS:
        got, terrain = check_site(key, lroc)
        records.extend(got)
        if key == SPOT_SITE:
            spot_terrain = terrain
        del terrain
        print(f"  {SITES_BY_KEY[key].name}: done", flush=True)
    samples = pd.DataFrame(records)

    spot = geometry_spot_check(spot_terrain, samples)
    rows = summary_rows(samples)
    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "rows": rows,
        "notes": write_notes(samples, spot),
        "geometry_spot_check": spot,
        "references": build_references(samples, lroc),
    }

    saved = samples.copy()
    saved[PERCENT_COLUMNS] = saved[PERCENT_COLUMNS].round(3)
    saved[ANGLE_COLUMNS] = saved[ANGLE_COLUMNS].round(4)
    saved[["map_x_m", "map_y_m", "site_offset_from_pixel_centre_m"]] = saved[
        ["map_x_m", "map_y_m", "site_offset_from_pixel_centre_m"]].round(2)
    saved.to_csv(RESULTS / "illumination_samples.csv", index=False)
    (RESULTS / "illumination_summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    plot(samples, RESULTS / "illumination_check.png")

    print_table(rows)
    print(f"\nGeometry spot check ({spot['site_name']}, {len(SPOT_AZIMUTHS)} azimuths): stored mask against the "
          f"independent recomputation, largest difference {spot['max_abs_diff_deg_h0m']:.4f} deg at 0 m and "
          f"{spot['max_abs_diff_deg_h2m']:.4f} deg at 2 m; with single-precision terrain radius "
          f"{spot['max_abs_diff_single_precision_deg']:.4f} deg.")
    print("\nNotes:")
    for note in summary["notes"]:
        print(f"- {note}")
    print("\nThere is no pass threshold: the differences are reported as they are.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
