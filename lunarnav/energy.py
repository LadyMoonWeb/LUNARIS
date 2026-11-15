"""Solar power and battery model (stage 3).

Power from one flat panel:

    P = S * A * eta * max(0, n . s) * V

    S    solar constant at the Moon, W/m^2
    A    panel area, m^2
    eta  conversion efficiency
    n    unit normal of the panel, s unit vector toward the Sun
    V    visible fraction of the solar disk (0..1) given the horizon mask

The functions here are generic; the numbers used for a particular lander are
passed in by the caller together with their source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

SOLAR_CONSTANT_W_M2 = 1361.0  # at 1 au; the Moon stays within 0.3 % of the Earth's distance
SUN_DIAMETER_DEG = 0.53
SUN_RADIUS_DEG = SUN_DIAMETER_DEG / 2.0


# Generic lander used by the app and the analysis scripts. Only the 200 W figure is
# official ("solar panels to generate 200 W of power on the surface", NASA NSSDC entry
# for the Nova-C lander of IM-3). Panel placement is not published, so three generic
# arrangements are offered; areas are scaled so that each gives 200 W in its best case.
GENERIC_RATED_POWER_W = 200.0
GENERIC_EFFICIENCY = 0.28
GENERIC_TRACKING_AREA_M2 = GENERIC_RATED_POWER_W / (SOLAR_CONSTANT_W_M2 * GENERIC_EFFICIENCY)
GENERIC_FACE_AREA_M2 = GENERIC_TRACKING_AREA_M2 / 1.91  # six faces, Sun on the horizon
GENERIC_BATTERY_WH = 700.0
GENERIC_LOAD_W = 100.0
PANEL_KINDS = {"faces": "Six vertical faces", "horizontal": "Horizontal panel", "tracking": "Sun tracking"}


def generic_panel_set(kind: str) -> "PanelSet":
    """One of the three generic panel arrangements: "faces", "horizontal" or "tracking"."""
    if kind == "faces":
        return PanelSet("faces", upright_faces(), GENERIC_FACE_AREA_M2)
    if kind == "horizontal":
        return PanelSet("horizontal", horizontal_panel(), GENERIC_TRACKING_AREA_M2)
    if kind == "tracking":
        return PanelSet("tracking", None, GENERIC_TRACKING_AREA_M2)
    raise ValueError(f"panel kind must be one of {list(PANEL_KINDS)}")


def sun_visible_fraction(clearance_deg, radius_deg: float = SUN_RADIUS_DEG) -> np.ndarray:
    """Visible fraction of the solar disk for a given clearance of its centre.

    ``clearance_deg`` is the altitude of the disk centre above the local
    horizon (column ``sun_clearance_deg`` of ``compute()``). The horizon is
    treated as a straight horizontal line across the half-degree disk, so the
    visible part is a circular segment.
    """
    s = np.clip(np.asarray(clearance_deg, dtype=float) / radius_deg, -1.0, 1.0)
    return (np.arccos(-s) + s * np.sqrt(1.0 - s * s)) / np.pi


def sun_vectors(alt_deg, az_deg) -> np.ndarray:
    """Unit vectors toward the Sun in local east / north / up axes, shape (T, 3)."""
    alt, az = np.radians(np.asarray(alt_deg, dtype=float)), np.radians(np.asarray(az_deg, dtype=float))
    return np.stack([np.cos(alt) * np.sin(az), np.cos(alt) * np.cos(az), np.sin(alt)], axis=-1)


@dataclass(frozen=True)
class PanelSet:
    """A set of flat panels (or one Sun-tracking panel)."""

    name: str
    normals: Optional[np.ndarray]  # (N, 3) east / north / up unit normals; None = always faces the Sun
    area_m2: float  # area of each panel
    note: str = ""


def upright_faces(count: int = 6, yaw_deg: float = 0.0) -> np.ndarray:
    """Normals of vertical panels on the side faces of an upright prism."""
    az = np.radians(yaw_deg + np.arange(count) * 360.0 / count)
    return np.stack([np.sin(az), np.cos(az), np.zeros(count)], axis=-1)


def horizontal_panel() -> np.ndarray:
    return np.array([[0.0, 0.0, 1.0]])


def tipped_over(normals: np.ndarray, fall_azimuth_deg: float) -> np.ndarray:
    """Normals after the vehicle falls flat on its side toward the given azimuth.

    The body's "up" axis ends horizontal, pointing to ``fall_azimuth_deg``;
    this is a 90 degree rotation about the horizontal axis perpendicular to it.
    """
    a = np.radians(fall_azimuth_deg)
    fall = np.array([np.sin(a), np.cos(a), 0.0])  # where the top now points
    up = np.array([0.0, 0.0, 1.0])
    side = np.cross(up, fall)  # rotation axis, unchanged by the fall
    n = np.asarray(normals, dtype=float)
    along_up, along_fall, along_side = n @ up, n @ fall, n @ side
    # up -> fall, fall -> -up, side -> side
    return along_up[:, None] * fall + along_fall[:, None] * (-up) + along_side[:, None] * side


def panel_power(table, panels: PanelSet, efficiency: float, solar_constant: float = SOLAR_CONSTANT_W_M2) -> np.ndarray:
    """Electrical power in watts for every row of a ``compute()`` table.

    P = S * A * eta * max(0, n . s) * V, summed over the panels. V comes from
    the ``sun_clearance_deg`` column, so the table has to be computed with the
    horizon mask that applies at the height of the panels.
    """
    visible = sun_visible_fraction(table["sun_clearance_deg"].to_numpy())
    if panels.normals is None:
        projected = np.full(len(table), panels.area_m2)
    else:
        s = sun_vectors(table["sun_alt_deg"].to_numpy(), table["sun_az_deg"].to_numpy())
        projected = panels.area_m2 * np.clip(s @ np.asarray(panels.normals, dtype=float).T, 0.0, None).sum(axis=1)
    return solar_constant * efficiency * projected * visible


@dataclass(frozen=True)
class Battery:
    capacity_wh: float
    load_w: float
    max_depth_of_discharge: float = 0.8  # the load is shed when this much has been used
    charge_efficiency: float = 0.95
    taper_start_soc: float = 0.8  # above this state of charge the accepted power falls linearly to zero
    max_charge_w: Optional[float] = None  # default: half the capacity per hour (0.5 C)
    initial_soc: float = 1.0
    restart_margin: float = 0.05  # the load comes back once the charge is this far above the floor


def simulate_battery(times, power_w, battery: Battery) -> pd.DataFrame:
    """State of charge over time for a given generated power.

    Charge curve: constant acceptance up to ``taper_start_soc``, then a linear
    taper to zero at full charge (a simple constant-current / constant-voltage
    shape). When the depth-of-discharge limit is reached the load is shed and
    everything generated goes into the battery until the restart margin is met.
    """
    stamps = pd.DatetimeIndex(times)
    power = np.asarray(power_w, dtype=float)
    # Explicit ns resolution: pandas 3 stores times in microseconds by default.
    hours = np.diff(stamps.tz_localize(None).values.astype("datetime64[ns]").astype("int64")) / 3.6e12
    floor = 1.0 - battery.max_depth_of_discharge
    limit = battery.max_charge_w if battery.max_charge_w is not None else battery.capacity_wh / 2.0

    soc = np.empty(len(power))
    served = np.ones(len(power), dtype=bool)
    level, on = battery.initial_soc, True
    for i in range(len(power)):
        soc[i], served[i] = level, on
        if i == len(power) - 1:
            break
        acceptance = limit if level < battery.taper_start_soc else \
            limit * max(0.0, 1.0 - level) / (1.0 - battery.taper_start_soc)
        net = power[i] - (battery.load_w if on else 0.0)
        if net >= 0:
            level += min(net * battery.charge_efficiency, acceptance) * hours[i] / battery.capacity_wh
        else:
            level += net * hours[i] / battery.capacity_wh
        level = min(1.0, level)
        if on and level <= floor + 1e-9:
            level, on = max(level, floor), False
        elif not on and level >= floor + battery.restart_margin:
            on = True
    return pd.DataFrame({"time_utc": stamps, "power_w": power, "soc": soc, "load_served": served})


def battery_summary(sim: pd.DataFrame) -> dict:
    """Headline numbers of a battery simulation."""
    hours = np.diff(pd.DatetimeIndex(sim["time_utc"]).tz_localize(None).values.astype("datetime64[ns]")
                    .astype("int64")) / 3.6e12
    off = ~sim["load_served"].to_numpy()[:-1]
    first_off = sim.loc[~sim["load_served"], "time_utc"]
    start = sim["time_utc"].iloc[0]
    power = sim["power_w"].to_numpy()
    return {
        "mean_power_w": round(float(np.sum(0.5 * (power[1:] + power[:-1]) * hours) / hours.sum()), 1),
        "energy_wh_per_day": round(float(np.sum(0.5 * (power[1:] + power[:-1]) * hours) / hours.sum() * 24.0), 0),
        "min_soc_pct": round(float(sim["soc"].min() * 100.0), 1),
        "end_soc_pct": round(float(sim["soc"].iloc[-1] * 100.0), 1),
        "load_off_hours": round(float(hours[off].sum()), 1),
        "hours_to_first_load_off": None if first_off.empty else
        round(float((first_off.iloc[0] - start) / pd.Timedelta(hours=1)), 1),
    }


def sunlit_days(table, weighted: bool = False) -> float:
    """Days of sunlight in a ``compute()`` table.

    ``weighted=False`` counts the time with the disk centre above the horizon,
    ``weighted=True`` integrates the visible fraction of the disk.
    """
    if len(table) < 2:
        return 0.0
    hours = table["time_utc"].diff().dt.total_seconds().to_numpy()[1:] / 3600.0
    value = sun_visible_fraction(table["sun_clearance_deg"].to_numpy()) if weighted \
        else (table["sun_clearance_deg"].to_numpy() > 0).astype(float)
    return float(np.sum(0.5 * (value[1:] + value[:-1]) * hours) / 24.0)
