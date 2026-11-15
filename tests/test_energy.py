"""Tests of the power and battery model."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lunarnav.energy import (
    SOLAR_CONSTANT_W_M2, Battery, PanelSet, battery_summary, horizontal_panel, panel_power,
    simulate_battery, sun_vectors, sun_visible_fraction, sunlit_days, tipped_over, upright_faces,
)


def table(alt, az, clearance):
    n = len(alt)
    return pd.DataFrame({
        "time_utc": pd.date_range("2025-03-06", periods=n, freq="10min", tz="UTC"),
        "sun_alt_deg": np.asarray(alt, float), "sun_az_deg": np.asarray(az, float),
        "sun_clearance_deg": np.asarray(clearance, float),
    })


def test_visible_fraction_of_the_disk():
    assert sun_visible_fraction(-1.0) == 0.0 and sun_visible_fraction(1.0) == 1.0
    assert sun_visible_fraction(0.0) == pytest.approx(0.5)
    assert sun_visible_fraction(0.265) == pytest.approx(1.0) and sun_visible_fraction(-0.265) == pytest.approx(0.0)
    assert 0.5 < sun_visible_fraction(0.1) < 1.0
    # Symmetric about the half-covered disk.
    assert sun_visible_fraction(0.1) + sun_visible_fraction(-0.1) == pytest.approx(1.0)


def test_sun_vectors_and_panel_geometry():
    s = sun_vectors([0.0, 90.0, 0.0], [0.0, 0.0, 90.0])
    assert s[0] == pytest.approx([0, 1, 0]) and s[1] == pytest.approx([0, 0, 1], abs=1e-12)
    assert s[2] == pytest.approx([1, 0, 0], abs=1e-12)
    faces = upright_faces()
    assert faces.shape == (6, 3) and np.allclose(np.linalg.norm(faces, axis=1), 1) and np.allclose(faces[:, 2], 0)
    # Falling north: the top deck points north, the north face points down, the south face up.
    assert tipped_over(horizontal_panel(), 0.0)[0] == pytest.approx([0, 1, 0], abs=1e-12)
    fallen = tipped_over(faces, 0.0)
    assert fallen[0] == pytest.approx([0, 0, -1], abs=1e-12) and fallen[3] == pytest.approx([0, 0, 1], abs=1e-12)
    assert np.allclose(np.linalg.norm(fallen, axis=1), 1)


def test_panel_power_formula():
    t = table([0.0, 0.0, 30.0, 0.0], [0.0, 30.0, 0.0, 0.0], [5.0, 5.0, 5.0, 0.0])
    eta, area = 0.3, 2.0
    full = SOLAR_CONSTANT_W_M2 * area * eta
    tracking = panel_power(t, PanelSet("tracking", None, area), eta)
    assert tracking[:3] == pytest.approx([full] * 3) and tracking[3] == pytest.approx(full / 2)  # half the disk
    north_wall = panel_power(t, PanelSet("wall", np.array([[0.0, 1.0, 0.0]]), area), eta)
    assert north_wall[0] == pytest.approx(full)
    assert north_wall[1] == pytest.approx(full * np.cos(np.radians(30)))
    assert north_wall[2] == pytest.approx(full * np.cos(np.radians(30)))
    flat = panel_power(t, PanelSet("flat", horizontal_panel(), area), eta)
    assert flat[0] == pytest.approx(0.0, abs=1e-9) and flat[2] == pytest.approx(full * 0.5)
    # A hexagonal body with the Sun on the horizon collects between 1.73 and 2.0 face areas.
    hexagon = panel_power(t, PanelSet("hex", upright_faces(), area), eta)
    assert hexagon[0] == pytest.approx(full * 2.0) and hexagon[1] == pytest.approx(full * 2 * np.cos(np.radians(30)))
    back_wall = panel_power(t, PanelSet("back", np.array([[0.0, -1.0, 0.0]]), area), eta)
    assert back_wall[0] == 0.0


def test_battery_discharge_shed_and_recharge():
    times = pd.date_range("2025-03-06", periods=13, freq="1h", tz="UTC")
    battery = Battery(capacity_wh=1000.0, load_w=100.0, max_depth_of_discharge=0.8, charge_efficiency=1.0)
    dark = simulate_battery(times, np.zeros(13), battery)
    assert dark["soc"].iloc[1] == pytest.approx(0.9)
    assert dark["soc"].min() == pytest.approx(0.2)  # never below the depth-of-discharge limit
    assert battery_summary(dark)["hours_to_first_load_off"] == pytest.approx(8.0)  # 800 Wh at 100 W
    assert battery_summary(dark)["load_off_hours"] == pytest.approx(4.0)

    balanced = simulate_battery(times, np.full(13, 100.0), battery)
    assert balanced["soc"].to_numpy() == pytest.approx(1.0) and balanced["load_served"].all()

    # Charging: full rate below the taper start, slower above it, never over 100 %.
    low = Battery(capacity_wh=1000.0, load_w=0.0, charge_efficiency=1.0, initial_soc=0.5, max_charge_w=200.0)
    charging = simulate_battery(times, np.full(13, 400.0), low)
    steps = np.diff(charging["soc"].to_numpy())
    assert steps[0] == pytest.approx(0.2) and steps[2] < steps[0] and charging["soc"].max() <= 1.0
    assert (steps >= -1e-12).all()

    # After a blackout the load returns only once the restart margin is reached.
    power = np.array([0.0] * 9 + [150.0] * 4)
    back = simulate_battery(times, power, battery)
    assert not back["load_served"].iloc[9] and back["load_served"].iloc[-1]


def test_sunlit_days():
    t = table([1] * 145, [0] * 145, [1.0] * 72 + [-1.0] * 73)  # 24 h in 10-minute steps, lit for 12 h
    assert sunlit_days(t) == pytest.approx(0.5, abs=0.01)
    assert sunlit_days(t, weighted=True) == pytest.approx(0.5, abs=0.01)


def test_battery_independent_of_time_resolution():
    """pandas 3 stores times in microseconds; the battery must not depend on the stored resolution."""
    battery = Battery(capacity_wh=1000.0, load_w=100.0, max_depth_of_discharge=0.8, charge_efficiency=1.0)
    for unit in ("ns", "us", "s"):
        times = pd.date_range("2025-03-06", periods=13, freq="1h", tz="UTC").as_unit(unit)
        sim = simulate_battery(times, np.zeros(13), battery)
        assert sim["soc"].iloc[1] == pytest.approx(0.9), unit
        assert battery_summary(sim)["load_off_hours"] == pytest.approx(4.0), unit
