"""Tests of the data handed to the 3D Site page (no browser needed)."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lunarnav import compute
from lunarnav.sites import SITES
from lunarnav.terrain import load_mask


def test_every_polar_site_has_a_3d_patch_with_the_expected_shape():
    for site in (s for s in SITES if s.lat <= -80.0):
        path = ROOT / "data" / "site3d" / f"{site.key}.json"
        assert path.exists(), f"3D patch missing for {site.key}"
        assert path.stat().st_size < 2_000_000
    data = json.loads((ROOT / "data" / "site3d" / "im2.json").read_text(encoding="utf-8"))
    assert data["horizon"]["eye_m"] == 2.0 and data["horizon"]["ray_km"] == 30
    assert abs(data["centre_check"]["mean_diff_deg"]) < 0.5


def test_run_payload_uses_the_masks_and_the_sidebar_heights():
    pytest.importorskip("streamlit")
    from ui.site3d import run_payload

    lat, lon = -84.7906, 29.1957
    table = compute(lat, lon, "2025-03-06 17:30", "2025-03-09 17:30", 30, observer_height_m=10.0,
                    horizon_mask=load_mask("im2", 10.0), antenna_height_m=0.0,
                    antenna_horizon_mask=load_mask("im2", 0.0))
    sel = SimpleNamespace(name="IM-2 Athena", landing=datetime(2025, 3, 6, 17, 30, tzinfo=timezone.utc),
                          period_days=3, panel_height_m=10.0, antenna_height_m=0.0)
    payload = run_payload(table, sel)
    hours = len(table.iloc[::2])
    assert payload["step_hours"] == 1 and payload["period_days"] == 3
    assert len(payload["sun"]) == len(payload["earth"]) == len(payload["sun_up"]) == len(payload["earth_up"]) == hours
    assert payload["sun_up"] == [int(v) for v in table["sunlit"].iloc[::2]]
    assert payload["earth_up"] == [int(v) for v in table["earth_visible"].iloc[::2]]
    assert (payload["panel_height_m"], payload["antenna_height_m"]) == (10.0, 0.0)
    assert payload["req_min"] == 6.0 and payload["req_full"] == 6.5
    json.dumps(payload)  # everything is plain JSON
