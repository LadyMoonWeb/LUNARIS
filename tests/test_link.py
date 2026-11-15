"""Tests of the radio link budget."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lunarnav import compute
from lunarnav.link import LinkBudget, dish_gain_dbi, earth_distance_km, fspl_db, link_margin, link_table


def test_free_space_loss_and_dish_gain():
    # Textbook value: 384 400 km at 2.2 GHz is about 211 dB.
    assert fspl_db(384_400.0, 2.2e9) == pytest.approx(211.0, abs=0.1)
    assert fspl_db(768_800.0, 2.2e9) - fspl_db(384_400.0, 2.2e9) == pytest.approx(6.02, abs=0.01)  # twice as far
    assert dish_gain_dbi(34.0, 2.2e9, 0.6) == pytest.approx(55.7, abs=0.2)
    assert earth_distance_km(0.95) == pytest.approx(384_700, rel=0.01)


def test_margin_follows_the_budget_terms():
    base = link_margin(384_400.0)
    assert base["margin_db"] == pytest.approx(base["ebn0_db"] - 3.0)
    # Ten times the data rate costs 10 dB; ten times the power gains 10 dB.
    assert link_margin(384_400.0, LinkBudget(data_rate_bps=1e6))["margin_db"] == pytest.approx(base["margin_db"] - 10.0)
    assert link_margin(384_400.0, LinkBudget(tx_power_w=100.0))["margin_db"] == pytest.approx(base["margin_db"] + 10.0)
    assert 5.0 < base["margin_db"] < 30.0


def test_link_table_flags():
    table = compute(-84.7906, 29.1957, "2025-03-06 17:30", "2025-04-05", 60, horizon_mask=lambda az: 1.0)
    out = link_table(table)
    up = out["line_of_sight"].to_numpy()
    assert up.any() and (~up).any()
    assert out.loc[~out["line_of_sight"], "margin_db"].isna().all()
    assert out.loc[out["line_of_sight"], "margin_db"].notna().all()
    low = out["low_elevation"].to_numpy()
    assert (out.loc[low, "earth_elevation_deg"] < 6.0).all() and (out.loc[low, "earth_elevation_deg"] > 0).all()
    assert not (low & ~up).any()
    assert out["earth_distance_km"].between(356_000, 407_000).all()
    # Same answer whichever Earth definition the table was switched to.
    from lunarnav import with_earth_definition

    other = link_table(with_earth_definition(table, "any"))
    assert np.allclose(other["earth_elevation_deg"], out["earth_elevation_deg"])
