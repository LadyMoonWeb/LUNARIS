"""Tests for the calculation package (run with ``python -m pytest tests``)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lunarnav import compute, horizon_dip_deg, landing_scan, longest_stretch, next_event, summary, verdict
from lunarnav.compute import apply_visibility
from lunarnav.ephemeris import MOON_RADIUS_M


def test_skyfield_documentation_example():
    """Earth from Aristarchus, 2019-12-20 11:05 UTC: 32.453 deg / 118.216 deg."""
    row = compute(26.3, -46.8, "2019-12-20 11:05", "2019-12-20 11:05", 1).iloc[0]
    assert row["earth_alt_deg"] == pytest.approx(32.453, abs=5e-4)
    assert row["earth_az_deg"] == pytest.approx(118.216, abs=5e-4)


def test_columns_and_grid():
    table = compute(0.0, 0.0, "2026-01-01", "2026-01-02", 30)
    for name in ("time_utc", "sun_alt_deg", "sun_az_deg", "earth_alt_deg", "earth_az_deg",
                 "sunlit", "earth_visible", "both"):
        assert name in table.columns
    assert len(table) == 49  # both ends included
    assert (table["both"] == (table["sunlit"] & table["earth_visible"])).all()
    # Sub-Earth point: the Earth stays near the zenith.
    assert table["earth_alt_deg"].min() > 75


def test_far_side_never_sees_earth():
    table = compute(0.0, 180.0, "2026-01-01", "2026-03-01", 120)
    assert not table["earth_visible"].any()
    assert not table["both"].any()


def test_horizon_dip():
    assert horizon_dip_deg(0) == 0
    # Small-angle formula sqrt(2h/R).
    assert horizon_dip_deg(2.0) == pytest.approx(np.degrees(np.sqrt(2 * 2.0 / MOON_RADIUS_M)), rel=1e-4)
    assert horizon_dip_deg(100.0) > horizon_dip_deg(2.0)
    with pytest.raises(ValueError):
        horizon_dip_deg(-1)


def test_observer_height_and_mask_change_visibility():
    base = compute(-89.5, 0.0, "2026-01-01", "2026-03-01", 60)
    tall = compute(-89.5, 0.0, "2026-01-01", "2026-03-01", 60, observer_height_m=1000)
    walled = compute(-89.5, 0.0, "2026-01-01", "2026-03-01", 60, horizon_mask=lambda az: 5.0)
    assert tall["sunlit"].sum() >= base["sunlit"].sum()
    assert walled["sunlit"].sum() < base["sunlit"].sum()
    # A mask may depend on azimuth and may be scalar-only.
    lumpy = compute(-89.5, 0.0, "2026-01-01", "2026-01-05", 60,
                    horizon_mask=lambda az: 3.0 if float(az) < 180 else 0.0)
    assert len(lumpy) == len(compute(-89.5, 0.0, "2026-01-01", "2026-01-05", 60))


def _synthetic(sun, earth, step_min=30):
    times = pd.date_range("2026-01-01", periods=len(sun), freq=f"{step_min}min", tz="UTC")
    table = pd.DataFrame({
        "time_utc": times,
        "sun_alt_deg": np.asarray(sun, float), "sun_az_deg": 90.0,
        "earth_alt_deg": np.asarray(earth, float), "earth_az_deg": 180.0,
    })
    return apply_visibility(table)


def test_stretch_edges_are_interpolated():
    # Sun rises exactly half-way between samples 1 and 2, sets half-way between 5 and 6.
    table = _synthetic([-3, -1, 1, 3, 3, 1, -1, -3], [5] * 8)
    best = longest_stretch(table, "sun")
    assert best.days * 24 == pytest.approx(2.0)  # 4 samples up, 30 min grid
    assert not best.open_start and not best.open_end
    both = longest_stretch(table, "both")
    assert both.days == pytest.approx(best.days)
    earth = longest_stretch(table, "earth")
    assert earth.open_start and earth.open_end


def test_next_event():
    table = _synthetic([3, 1, -1, -3, -1, 1, 3], [5] * 7)
    start = table["time_utc"].iloc[0]
    event = next_event(table, start, "sun")
    assert event.visible_now
    assert event.time_to_set == pd.Timedelta(minutes=45)
    assert event.time_to_rise == pd.Timedelta(minutes=135)
    earth = next_event(table, start, "earth")
    assert earth.visible_now and earth.next_set is None


def test_earth_any_part_definition():
    """The looser Earth definition counts the disk as visible while its upper limb shows."""
    from lunarnav import with_earth_definition

    # Limb site: the Earth hovers around the horizon.
    table = compute(-84.7906, 29.1957, "2026-01-01", "2026-03-01", 60, horizon_mask=lambda az: 2.0)
    assert table["earth_radius_deg"].between(0.88, 1.03).all()
    assert (table["earth_any_clearance_deg"] - table["earth_clearance_deg"]
            ).to_numpy() == pytest.approx(table["earth_radius_deg"].to_numpy())
    assert table["earth_any_visible"].sum() > table["earth_visible"].sum()
    assert (table["earth_any_visible"] | ~table["earth_visible"]).all()  # centre up implies any part up
    assert (table["both_any"] == (table["sunlit"] & table["earth_any_visible"])).all()

    strict = summary(with_earth_definition(table, "centre"))
    loose = summary(with_earth_definition(table, "any"))
    assert loose["earth_fraction"] > strict["earth_fraction"]
    assert loose["longest_both_days"] >= strict["longest_both_days"]
    assert loose["sun_fraction"] == strict["sun_fraction"]  # the Sun is not affected
    assert with_earth_definition(table, "centre") is table
    with pytest.raises(ValueError):
        with_earth_definition(table, "half")


def test_verdict_thresholds():
    assert verdict(6.5).level == "meets"
    assert verdict(6.2).level == "marginal"
    assert verdict(5.99).level == "short"
    # A period shorter than the requirement gives no verdict instead of a failure.
    assert verdict(3.0, period_days=3.0).level == "na"
    assert "shorter than requirement" in verdict(3.0, period_days=3.0).label
    assert verdict(3.0, period_days=14.0).level == "short"
    assert verdict(7.0, period_days=14.0).level == "meets"
    short_table = compute(-84.7906, 29.1957, "2026-01-01", "2026-01-04", 60)
    assert summary(short_table)["verdict"].level == "na"
    assert summary(short_table)["period_days"] == pytest.approx(3.0)


def test_sun_at_panel_height_earth_at_antenna_height():
    """Two heights: the Sun uses the panel horizon, the Earth the antenna horizon."""
    wall, low = (lambda az: 30.0), (lambda az: -5.0)
    kwargs = dict(lat=-84.7906, lon=29.1957, start="2026-01-01", end="2026-02-01", step=120)
    both_low = compute(**kwargs, observer_height_m=2, horizon_mask=low)
    sun_blocked = compute(**kwargs, observer_height_m=2, horizon_mask=wall, antenna_height_m=10, antenna_horizon_mask=low)
    earth_blocked = compute(**kwargs, observer_height_m=2, horizon_mask=low, antenna_height_m=10, antenna_horizon_mask=wall)
    assert not sun_blocked["sunlit"].any() and (sun_blocked["earth_visible"] == both_low["earth_visible"]).all()
    assert not earth_blocked["earth_visible"].any() and (earth_blocked["sunlit"] == both_low["sunlit"]).all()
    # Without antenna arguments the Earth follows the panel values (unchanged behaviour).
    same = compute(**kwargs, observer_height_m=2, horizon_mask=wall)
    assert not same["sunlit"].any() and not same["earth_visible"].any()
    # Smooth sphere: a higher antenna lowers only the Earth's horizon.
    flat = compute(**kwargs, observer_height_m=0, antenna_height_m=10)
    plain = compute(**kwargs, observer_height_m=0)
    assert (flat["sun_clearance_deg"] == plain["sun_clearance_deg"]).all()
    assert (flat["earth_clearance_deg"] > plain["earth_clearance_deg"]).all()


def test_landing_scan_modes():
    # 2 days dark, 8 days of light, then dark again (hourly samples).
    sun = [-5] * 48 + [5] * 192 + [-5] * 240
    table = _synthetic(sun, [5] * len(sun), step_min=60)
    t0 = table["time_utc"].iloc[0]
    landings = [t0, t0 + pd.Timedelta(days=5)]
    longest = landing_scan(table, landings, window_days=10)
    touchdown = landing_scan(table, landings, window_days=10, from_touchdown=True)
    assert longest["days"].iloc[0] == pytest.approx(8.0, abs=0.05)  # waits 2 d, then 8 d
    assert touchdown["days"].iloc[0] == 0.0  # lands in the dark
    assert touchdown["days"].iloc[1] == pytest.approx(5.0, abs=0.05)
    assert summary(table)["longest_both_days"] == pytest.approx(8.0, abs=0.05)
