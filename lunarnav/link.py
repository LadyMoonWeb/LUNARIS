"""Direct-to-Earth radio link margin (generic parameters).

Margin of a lander downlink received by a 34 m Deep Space Network antenna:

    margin = EIRP - free-space loss - other losses + G/T - k - 10 log10(rate) - required Eb/N0

Only geometry and free-space loss are modelled. NOT modelled: reflections
from the terrain (multipath), which matter when the Earth is low above the
horizon; antenna pattern and pointing; ground-station schedule and weather.
A flag marks the times when the Earth is less than 6 degrees above the local
horizon, where multipath is most likely.

All hardware numbers are generic placeholders, not the parameters of any
real lander; they are fields of ``LinkBudget`` so that they can be replaced.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .compute import EARTH_RADIUS_KM

SPEED_OF_LIGHT_M_S = 299_792_458.0
BOLTZMANN_DBW_PER_K_HZ = -228.6
MEAN_EARTH_DISTANCE_KM = 384_400.0
LOW_ELEVATION_DEG = 6.0  # below this the link is flagged


@dataclass(frozen=True)
class LinkBudget:
    """Generic S-band downlink to a DSN 34 m antenna."""

    frequency_hz: float = 2.2e9
    tx_power_w: float = 10.0
    tx_gain_dbi: float = 6.0  # generic medium-gain antenna
    tx_losses_db: float = 2.0  # cables and pointing
    rx_dish_m: float = 34.0  # Deep Space Network 34 m antenna
    rx_efficiency: float = 0.6
    system_noise_k: float = 40.0
    other_losses_db: float = 2.0  # polarisation, Earth atmosphere
    data_rate_bps: float = 100_000.0
    required_ebn0_db: float = 3.0  # with coding


def fspl_db(distance_km, frequency_hz: float) -> np.ndarray:
    """Free-space path loss in dB."""
    wavelength = SPEED_OF_LIGHT_M_S / frequency_hz
    return 20.0 * np.log10(4.0 * np.pi * np.asarray(distance_km, dtype=float) * 1000.0 / wavelength)


def dish_gain_dbi(diameter_m: float, frequency_hz: float, efficiency: float) -> float:
    wavelength = SPEED_OF_LIGHT_M_S / frequency_hz
    return float(10.0 * np.log10(efficiency * (np.pi * diameter_m / wavelength) ** 2))


def earth_distance_km(earth_radius_deg) -> np.ndarray:
    """Distance to the Earth's centre from the angular radius of its disk."""
    return EARTH_RADIUS_KM / np.sin(np.radians(np.asarray(earth_radius_deg, dtype=float)))


def link_margin(distance_km, budget: LinkBudget = LinkBudget()) -> dict:
    """Terms of the link budget and the margin in dB (arrays if the distance is an array)."""
    eirp = 10.0 * np.log10(budget.tx_power_w) + budget.tx_gain_dbi - budget.tx_losses_db
    loss = fspl_db(distance_km, budget.frequency_hz)
    g_over_t = dish_gain_dbi(budget.rx_dish_m, budget.frequency_hz, budget.rx_efficiency) \
        - 10.0 * np.log10(budget.system_noise_k)
    cn0 = eirp - loss - budget.other_losses_db + g_over_t - BOLTZMANN_DBW_PER_K_HZ
    ebn0 = cn0 - 10.0 * np.log10(budget.data_rate_bps)
    return {"eirp_dbw": float(eirp), "fspl_db": loss, "g_over_t_db_k": float(g_over_t), "cn0_dbhz": cn0,
            "ebn0_db": ebn0, "margin_db": ebn0 - budget.required_ebn0_db}


def link_table(table, budget: LinkBudget = LinkBudget()):
    """Link state for every row of a ``compute()`` table.

    Adds ``earth_elevation_deg`` (centre of the Earth above the local horizon),
    ``earth_distance_km``, ``fspl_db``, ``margin_db`` (NaN without line of
    sight), ``line_of_sight`` and ``low_elevation`` (Earth up but below 6 deg).
    """
    out = table[["time_utc"]].copy()
    centre = table["earth_any_clearance_deg"] - table["earth_radius_deg"] if "earth_any_clearance_deg" in table \
        else table["earth_clearance_deg"]
    distance = earth_distance_km(table["earth_radius_deg"]) if "earth_radius_deg" in table \
        else np.full(len(table), MEAN_EARTH_DISTANCE_KM)
    terms = link_margin(distance, budget)
    visible = centre.to_numpy() > 0
    out["earth_elevation_deg"] = centre.to_numpy()
    out["earth_distance_km"] = distance
    out["fspl_db"] = terms["fspl_db"]
    out["line_of_sight"] = visible
    out["margin_db"] = np.where(visible, terms["margin_db"], np.nan)
    out["low_elevation"] = visible & (centre.to_numpy() < LOW_ELEVATION_DEG)
    return out
