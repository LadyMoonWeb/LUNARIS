"""Metrics derived from a ``compute()`` table.

* longest continuous stretch of sunlight, of Earth visibility (communication)
  and of both together, in days;
* time from a chosen instant to the next sunset and the next Earthset;
* verdict against the required 6 - 6.5 days of surface operations;
* landing-date scan for the launch-slip view.

Rise and set instants are interpolated linearly between samples using the
``*_clearance_deg`` columns (altitude above the local horizon). With a
30-minute step the altitude changes by at most about 0.25 degrees per sample
and almost linearly, so the interpolated instants are good to about a minute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from .compute import to_utc

# Required duration of continuous sunlight + communication, in days.
REQUIRED_DAYS_MIN = 6.0
REQUIRED_DAYS_FULL = 6.5

CLEARANCE_COLUMN = {
    "sun": "sun_clearance_deg",
    "earth": "earth_clearance_deg",
    "both": "both_clearance_deg",
}

_NS_PER_DAY = 86_400e9


@dataclass(frozen=True)
class Stretch:
    """A continuous interval during which a condition holds."""

    start: pd.Timestamp
    end: pd.Timestamp
    open_start: bool  # already true at the first sample (real start is earlier)
    open_end: bool  # still true at the last sample (real end is later)

    @property
    def days(self) -> float:
        return (self.end - self.start) / pd.Timedelta(days=1)


@dataclass(frozen=True)
class NextEvent:
    """State of a body at an instant and its next horizon crossings."""

    visible_now: bool
    next_set: Optional[pd.Timestamp]
    next_rise: Optional[pd.Timestamp]
    time_to_set: Optional[pd.Timedelta]
    time_to_rise: Optional[pd.Timedelta]
    searched_until: pd.Timestamp


@dataclass(frozen=True)
class Verdict:
    level: str  # "meets", "marginal", "short" or "na" (period shorter than the requirement)
    label: str
    detail: str


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _time_ns(table: pd.DataFrame) -> np.ndarray:
    return table["time_utc"].dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ns]").astype("int64")


def _stamp(ns: float) -> pd.Timestamp:
    return pd.Timestamp(int(round(ns)), tz="UTC")


def _crossings(t_ns: np.ndarray, clearance: np.ndarray):
    """Interpolated instants (ns) where the clearance changes sign.

    Returns ``(rises, sets)``.
    """
    up = clearance > 0
    change = np.diff(up.astype(np.int8))
    idx = np.nonzero(change)[0]
    if idx.size == 0:
        return np.array([]), np.array([])
    c0, c1 = clearance[idx], clearance[idx + 1]
    frac = (0.0 - c0) / (c1 - c0)
    when = t_ns[idx] + frac * (t_ns[idx + 1] - t_ns[idx])
    return when[change[idx] > 0], when[change[idx] < 0]


# --------------------------------------------------------------------------
# Stretches
# --------------------------------------------------------------------------
def stretches(table: pd.DataFrame, what: str = "both") -> List[Stretch]:
    """All continuous intervals of ``what`` ("sun", "earth" or "both")."""
    if len(table) == 0:
        return []
    t_ns = _time_ns(table)
    clearance = table[CLEARANCE_COLUMN[what]].values.astype(float)
    rises, sets = _crossings(t_ns, clearance)

    starts = list(rises)
    ends = list(sets)
    open_start = bool(clearance[0] > 0)
    open_end = bool(clearance[-1] > 0)
    if open_start:
        starts.insert(0, float(t_ns[0]))
    if open_end:
        ends.append(float(t_ns[-1]))

    out = []
    for i, (a, b) in enumerate(zip(starts, ends)):
        out.append(
            Stretch(
                start=_stamp(a),
                end=_stamp(b),
                open_start=open_start and i == 0,
                open_end=open_end and i == len(starts) - 1,
            )
        )
    return out


def longest_stretch(table: pd.DataFrame, what: str = "both") -> Optional[Stretch]:
    """The longest continuous interval of ``what``, or None if it never holds."""
    found = stretches(table, what)
    return max(found, key=lambda s: s.days) if found else None


def fraction(table: pd.DataFrame, what: str = "both") -> float:
    """Share of the samples for which ``what`` holds (0..1)."""
    column = {"sun": "sunlit", "earth": "earth_visible", "both": "both"}[what]
    return float(table[column].mean()) if len(table) else 0.0


# --------------------------------------------------------------------------
# Next set / rise
# --------------------------------------------------------------------------
def next_event(table: pd.DataFrame, moment, what: str = "sun") -> NextEvent:
    """Next set and next rise of ``what`` after ``moment``.

    ``table`` has to start at or before ``moment`` and should extend far
    enough ahead; ``searched_until`` tells how far the search went.
    """
    moment = to_utc(moment)
    t_ns = _time_ns(table)
    clearance = table[CLEARANCE_COLUMN[what]].values.astype(float)
    now_ns = float(moment.value)
    if not t_ns[0] <= now_ns <= t_ns[-1]:
        raise ValueError("moment is outside the time range of the table")

    visible_now = bool(np.interp(now_ns, t_ns, clearance) > 0)
    rises, sets = _crossings(t_ns, clearance)
    later_sets = sets[sets > now_ns]
    later_rises = rises[rises > now_ns]

    next_set = _stamp(later_sets[0]) if later_sets.size else None
    next_rise = _stamp(later_rises[0]) if later_rises.size else None
    return NextEvent(
        visible_now=visible_now,
        next_set=next_set,
        next_rise=next_rise,
        time_to_set=(next_set - moment) if next_set is not None else None,
        time_to_rise=(next_rise - moment) if next_rise is not None else None,
        searched_until=_stamp(t_ns[-1]),
    )


# --------------------------------------------------------------------------
# Verdict
# --------------------------------------------------------------------------
def verdict(days: float, period_days: Optional[float] = None) -> Verdict:
    """Compare a continuous sunlight + communication window with 6 - 6.5 days.

    When the analysed period itself is shorter than the requirement the
    question cannot be answered, and the verdict is "N/A" instead of "short".
    """
    if period_days is not None and period_days < REQUIRED_DAYS_MIN - 1e-9 and days < REQUIRED_DAYS_MIN:
        return Verdict(
            "na",
            "N/A: period shorter than requirement",
            f"The analysed period is {period_days:.1f} d; at least {REQUIRED_DAYS_MIN:g} d are needed to judge "
            f"the {REQUIRED_DAYS_MIN:g}-{REQUIRED_DAYS_FULL:g} d requirement.",
        )
    if days >= REQUIRED_DAYS_FULL:
        return Verdict(
            "meets",
            "Meets requirement",
            f"{days:.2f} d of continuous sunlight and communication "
            f"(required {REQUIRED_DAYS_MIN:g}-{REQUIRED_DAYS_FULL:g} d).",
        )
    if days >= REQUIRED_DAYS_MIN:
        return Verdict(
            "marginal",
            "Marginal",
            f"{days:.2f} d covers the {REQUIRED_DAYS_MIN:g} d minimum but not "
            f"the full {REQUIRED_DAYS_FULL:g} d.",
        )
    return Verdict(
        "short",
        "Does not meet requirement",
        f"{days:.2f} d is shorter than the {REQUIRED_DAYS_MIN:g} d minimum.",
    )


def summary(table: pd.DataFrame) -> dict:
    """Longest stretches, coverage shares and the verdict for one table."""
    result = {}
    for what in ("sun", "earth", "both"):
        best = longest_stretch(table, what)
        result[f"longest_{what}_days"] = best.days if best else 0.0
        result[f"longest_{what}"] = best
        result[f"{what}_fraction"] = fraction(table, what)
    period = None
    if len(table) > 1:
        period = (table["time_utc"].iloc[-1] - table["time_utc"].iloc[0]) / pd.Timedelta(days=1)
    result["period_days"] = period
    result["verdict"] = verdict(result["longest_both_days"], period)
    return result


# --------------------------------------------------------------------------
# Landing-date scan (launch slip)
# --------------------------------------------------------------------------
def landing_scan(
    table: pd.DataFrame,
    landings,
    window_days: float,
    from_touchdown: bool = False,
    what: str = "both",
) -> pd.DataFrame:
    """Continuous window of ``what`` available for each landing instant.

    ``from_touchdown=False`` - the longest continuous stretch inside the
    mission window ``[landing, landing + window_days]``.
    ``from_touchdown=True``  - only the stretch that is already running at
    touchdown (0 if the condition does not hold at landing).

    ``table`` must cover every mission window.
    """
    landings = pd.DatetimeIndex([to_utc(x) for x in landings])
    land_ns = landings.tz_localize(None).values.astype("datetime64[ns]").astype("int64").astype(float)
    end_ns = land_ns + window_days * _NS_PER_DAY

    t_ns = _time_ns(table)
    if len(landings) and (land_ns.min() < t_ns[0] or end_ns.max() > t_ns[-1]):
        raise ValueError("table does not cover all mission windows")

    found = stretches(table, what)
    if not found or not len(landings):
        return pd.DataFrame({"landing_utc": landings, "days": np.zeros(len(landings))})

    starts = np.array([s.start.value for s in found], dtype=float)[None, :]
    ends = np.array([s.end.value for s in found], dtype=float)[None, :]
    lo = np.maximum(starts, land_ns[:, None])
    hi = np.minimum(ends, end_ns[:, None])
    overlap = np.clip(hi - lo, 0.0, None)
    if from_touchdown:
        running = (starts <= land_ns[:, None]) & (ends > land_ns[:, None])
        overlap = np.where(running, overlap, 0.0)

    return pd.DataFrame({"landing_utc": landings, "days": overlap.max(axis=1) / _NS_PER_DAY})
