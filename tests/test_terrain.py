"""Tests of the horizon-mask geometry on synthetic terrain (no downloads needed)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lunarnav import compute, horizon_dip_deg
from lunarnav.compute import horizon_elevation_deg
from lunarnav.ephemeris import MOON_RADIUS_M, kernels
from lunarnav.terrain import (
    N_AZIMUTHS,
    Grid,
    HorizonMask,
    destination,
    elevation_angle_deg,
    latlon_to_xy,
    mask_from_grids,
    xy_to_latlon,
)

SITE = (-89.0, 0.0)  # on the lon 0 meridian: north (azimuth 0) points toward +y


def flat_grid(half_width_m: float, pixel_m: float, centre=(0.0, 0.0)) -> Grid:
    n = int(2 * half_width_m / pixel_m)
    return Grid(np.zeros((n, n), dtype=np.float32), centre[0] - half_width_m, centre[1] + half_width_m, pixel_m, "flat")


def small_mask(near, far, height=0.0):
    return mask_from_grids(*SITE, height, near, far, near_range_m=4000, max_range_m=40_000,
                           near_step_m=10, far_step_m=40)


def test_projection_round_trip():
    lat, lon = xy_to_latlon(*latlon_to_xy(-84.7906, 29.1957))
    assert lat == pytest.approx(-84.7906, abs=1e-9)
    assert lon == pytest.approx(29.1957, abs=1e-9)
    x, y = latlon_to_xy(-84.7906, 29.1957)
    assert x / 1000 == pytest.approx(77.1, abs=0.1) and y / 1000 == pytest.approx(138.0, abs=0.1)
    # At the south pole east longitude 90 is +x, longitude 0 is +y.
    x, y = latlon_to_xy(-89.0, 90.0)
    assert x > 0 and abs(y) < 1e-6


def test_destination_follows_meridian_and_distance():
    lat, lon = destination(-89.0, 0.0, 0.0, MOON_RADIUS_M * np.radians(1.0))
    assert lat == pytest.approx(-88.0, abs=1e-9) and lon == pytest.approx(0.0, abs=1e-9)
    lat, lon = destination(0.0, 10.0, 90.0, MOON_RADIUS_M * np.radians(5.0))
    assert lat == pytest.approx(0.0, abs=1e-9) and lon == pytest.approx(15.0, abs=1e-9)


def test_flat_sphere_gives_the_analytic_dip():
    x0, y0 = latlon_to_xy(*SITE)
    near = flat_grid(6000, 10, (x0, y0))
    far = flat_grid(60_000, 40, (x0, y0))
    on_ground = small_mask(near, far, 0.0)
    assert np.abs(on_ground.mask_deg).max() < 1e-3  # horizon at 0 for an eye on the surface
    for height in (2.0, 30.0):
        raised = small_mask(near, far, height)
        assert raised.mask_deg == pytest.approx(-horizon_dip_deg(height), abs=2e-3)


def test_no_single_precision_rounding_on_a_raised_plateau():
    """A level surface at a non-round height must still give a flat horizon.

    Regression test: adding the lunar radius to float32 heights rounds to
    0.125 m, which showed up as errors of up to 0.36 degrees for terrain 10 m away
    (found by the independent illumination check).
    """
    x0, y0 = latlon_to_xy(*SITE)
    near = flat_grid(6000, 10, (x0, y0))
    far = flat_grid(60_000, 40, (x0, y0))
    near.heights[:] = 5321.77
    far.heights[:] = 5321.77
    mask = small_mask(near, far, 0.0)
    assert np.abs(mask.mask_deg).max() < 2e-3
    assert mask.meta["site_height_m"] == pytest.approx(5321.77, abs=0.01)


def test_modelled_crater_gives_the_analytic_rim_angle():
    """From the floor of a parabolic bowl the horizon is the rim: atan(depth / radius)."""
    from lunarnav.crater import mask_with_crater

    x0, y0 = latlon_to_xy(*SITE)
    near = flat_grid(16_000, 10, (x0, y0))
    far = flat_grid(160_000, 40, (x0, y0))
    for ratio, depth in ((0.1, 2.0), (0.2, 4.0)):
        floor = mask_with_crater(*SITE, 0.0, near, far, diameter_m=20.0, depth_ratio=ratio)
        # The 0.5 m grid rounds the sharp rim slightly, hence the tolerance.
        assert floor.mask_deg == pytest.approx(np.degrees(np.arctan(depth / 10.0)), abs=0.6)
        assert floor.mask_deg.max() <= np.degrees(np.arctan(depth / 10.0)) + 0.01
        assert floor.meta["model"] is True and floor.meta["site_height_m"] == pytest.approx(-depth, abs=0.02)
        # An eye level with the surrounding ground sees the flat horizon again.
        level = mask_with_crater(*SITE, depth, near, far, diameter_m=20.0, depth_ratio=ratio)
        assert np.abs(level.mask_deg).max() < 0.02
    plain = mask_with_crater(*SITE, 0.0, near, far)
    assert plain.meta["model"] is False and np.abs(plain.mask_deg).max() < 2e-3


def test_wall_of_known_height_at_known_distance():
    x0, y0 = latlon_to_xy(*SITE)
    near = flat_grid(6000, 10, (x0, y0))
    far = flat_grid(60_000, 40, (x0, y0))
    rows = far.heights.shape[0]
    wall_rows = int((far.y_top - (y0 + 20_000)) / far.pixel_m)  # every cell north of y0 + 20 km
    far.heights[:wall_rows, :] = 1000.0
    mask = small_mask(near, far, 0.0)

    expected = float(elevation_angle_deg(MOON_RADIUS_M, MOON_RADIUS_M + 1000.0, 20_000.0))
    assert expected == pytest.approx(2.53, abs=0.01)  # 1000 m minus 115 m of curvature drop over 20 km
    assert mask(0.0) == pytest.approx(expected, abs=0.02)  # looking north, straight at the wall
    assert mask.distance_km[0] == pytest.approx(20.0, abs=0.1)
    assert abs(float(mask(180.0))) < 1e-3  # looking south: flat ground
    # At 45 degrees from north the ray meets the wall after 20 km * sqrt(2).
    far_away = float(elevation_angle_deg(MOON_RADIUS_M, MOON_RADIUS_M + 1000.0, 20_000.0 * np.sqrt(2)))
    assert mask(45.0) == pytest.approx(far_away, abs=0.03)
    assert mask.distance_km[90] == pytest.approx(28.28, abs=0.15)
    assert rows > wall_rows > 0


def test_azimuth_convention_matches_skyfield():
    """The great-circle bearing to the sub-Earth point equals skyfield's azimuth of the Earth."""
    k = kernels()
    t = k.ts.utc(2025, 3, 6, 17, 30)
    lat_e, lon_e, _ = k.moon.at(t).observe(k.earth).frame_latlon(k.frame)
    lat, lon = -84.7906, 29.1957
    row = compute(lat, lon, "2025-03-06 17:30", "2025-03-06 17:30", 1).iloc[0]

    # Bearing whose destination passes through the sub-Earth point.
    az = np.arange(0, 360, 0.01)
    angle = np.radians(90.0)  # any distance along the great circle works; use a quarter turn
    lat2, lon2 = destination(lat, lon, az, MOON_RADIUS_M * angle)
    # Unit vectors; the right bearing maximises the dot product with the sub-Earth direction.
    def unit(la, lo):
        la, lo = np.radians(la), np.radians(lo)
        return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], axis=-1)
    best = az[np.argmax(unit(lat2, lon2) @ unit(lat_e.degrees, lon_e.degrees))]
    difference = (best - row["earth_az_deg"] + 180) % 360 - 180
    assert abs(difference) < 0.03


def test_mask_object_and_compute_integration():
    values = np.zeros(N_AZIMUTHS)
    values[:360] = 4.0  # a 4 degree ridge over the eastern half of the horizon
    mask = HorizonMask(values, {"lat": -84.8, "lon": 29.2})
    assert mask(10.0) == 4.0 and mask(270.0) == 0.0
    assert mask(-10.0) == mask(350.0)
    assert float(mask(359.75)) == pytest.approx(2.0)  # wraps around between the last and first sample

    # A terrain mask already contains the observer height: no second dip.
    assert horizon_elevation_deg(np.array([10.0]), 50.0, mask)[0] == 4.0
    # A plain function keeps the stage 1 behaviour: mask minus dip.
    assert horizon_elevation_deg(np.array([10.0]), 50.0, lambda az: 4.0)[0] == pytest.approx(4.0 - horizon_dip_deg(50.0))

    plain = compute(-84.7906, 29.1957, "2026-01-01", "2026-02-01", 60)
    masked = compute(-84.7906, 29.1957, "2026-01-01", "2026-02-01", 60, horizon_mask=mask)
    assert masked["sunlit"].sum() < plain["sunlit"].sum()
    assert (masked["sun_alt_deg"] == plain["sun_alt_deg"]).all()  # positions are untouched


def test_stored_masks_cover_every_polar_site():
    """The app must run without elevation data: masks for all sites south of 80 S are in the repository."""
    from lunarnav.sites import SITES
    from lunarnav.terrain import MASK_HEIGHTS_M, custom_key, has_all_heights, load_mask

    polar = [site for site in SITES if site.lat <= -80.0]
    assert len(polar) >= 19
    for site in polar:
        assert has_all_heights(site.key), f"masks missing for {site.key}"
    mask = load_mask("im2", 2.0)
    assert mask is not None and mask.mask_deg.shape == (N_AZIMUTHS,) and mask.includes_observer_height
    assert len(MASK_HEIGHTS_M) == 5
    # Higher eye, lower (or equal) horizon on average.
    assert load_mask("im2", 10.0).mask_deg.mean() <= load_mask("im2", 0.0).mask_deg.mean()
    assert custom_key(-89.5, 0.0) != custom_key(-89.5, 0.1) and " " not in custom_key(-84.79, 29.2)


def test_mask_round_trip(tmp_path):
    mask = HorizonMask(np.linspace(-1, 3, N_AZIMUTHS), {"lat": 1.0, "lon": 2.0}, np.full(N_AZIMUTHS, 12.5))
    again = HorizonMask.load(mask.save(tmp_path / "m.json"))
    assert again.mask_deg == pytest.approx(mask.mask_deg, abs=1e-4)
    assert again.meta["lat"] == 1.0 and again.distance_km[0] == 12.5
    assert again.includes_observer_height
