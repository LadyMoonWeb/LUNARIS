"""Lunar Landing Site Navigator - calculation package."""

from .compute import (
    apply_visibility,
    compute,
    flat_horizon,
    horizon_dip_deg,
    horizon_elevation_deg,
    positions,
    with_earth_definition,
)
from .metrics import (
    REQUIRED_DAYS_FULL,
    REQUIRED_DAYS_MIN,
    landing_scan,
    longest_stretch,
    next_event,
    stretches,
    summary,
    verdict,
)
from .series import get_series, yearly_positions

__all__ = [
    "apply_visibility",
    "compute",
    "flat_horizon",
    "horizon_dip_deg",
    "horizon_elevation_deg",
    "positions",
    "with_earth_definition",
    "REQUIRED_DAYS_FULL",
    "REQUIRED_DAYS_MIN",
    "landing_scan",
    "longest_stretch",
    "next_event",
    "stretches",
    "summary",
    "verdict",
    "get_series",
    "yearly_positions",
]
