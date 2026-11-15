"""Energy balance of a Nova-C class lander at the Athena site (MODEL).

    P = S * A * eta * max(0, n . s) * V

for three panel arrangements (vertical panels on the six faces, one horizontal
panel, one Sun-tracking panel), with V the visible fraction of the 0.53 degree
solar disk given the terrain horizon, and a battery with a load, a
depth-of-discharge limit and a tapering charge curve.

Cases: lander upright or lying on its side; on the plateau or inside the
modelled 20 m crater (depth 2 m and 4 m).

What is official and what is generic is listed in PARAMETERS below and written
into the output. Nothing here is a statement about the real Athena hardware.

    python scripts/athena_energy.py   ->  data/analysis/athena_energy.json, .png
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lunarnav import apply_visibility, positions  # noqa: E402
from lunarnav.crater import mask_with_crater  # noqa: E402
from lunarnav.energy import (  # noqa: E402
    SOLAR_CONSTANT_W_M2, Battery, PanelSet, battery_summary, horizontal_panel, panel_power,
    simulate_battery, tipped_over, upright_faces,
)
from lunarnav.sites import SITES_BY_KEY  # noqa: E402
from lunarnav.terrain import load_site_grids  # noqa: E402

SITE = SITES_BY_KEY["im2"]
LANDING = pd.Timestamp("2025-03-06 17:30", tz="UTC")
ACTUAL_END = pd.Timestamp("2025-03-07 06:15", tz="UTC")
PLANNED_DAYS = 10
STEP = "10min"
CRATER_DIAMETER_M = 20.0

# ---------------------------------------------------------------- parameters
EFFICIENCY = 0.28
RATED_POWER_W = 200.0
TRACKING_AREA_M2 = RATED_POWER_W / (SOLAR_CONSTANT_W_M2 * EFFICIENCY)  # 200 W at normal incidence
HEX_MEAN_PROJECTION = 1.91  # mean of sum max(0, cos) over six faces with the Sun on the horizon
FACE_AREA_M2 = RATED_POWER_W / (SOLAR_CONSTANT_W_M2 * EFFICIENCY * HEX_MEAN_PROJECTION)
BATTERY = Battery(capacity_wh=700.0, load_w=100.0, max_depth_of_discharge=0.8, charge_efficiency=0.95)

PARAMETERS = {
    "official": {
        "rated_power_w": "200 W 'on the surface' - NASA NSSDC, Intuitive Machines 3 (Nova-C lander): "
                         "'It uses solar panels to generate 200 W of power on the surface.'",
        "shape": "'a tall hexagonal cylinder on 6 landing legs' - same NSSDC entry",
        "planned_surface_operations": "'Approximately 10 days' - NASA CLPS IM-2 press kit",
    },
    "seen_only_through_web_search": {
        "size": "4.0 m tall, 1.57 m wide (NSSDC entry for IM-1; the page returned an error when read directly)",
        "battery": "25 Ah at 28 V = 700 Wh (same NSSDC IM-1 entry, same caveat)",
    },
    "generic_assumptions": {
        "panel_placement": "NOT published by NASA or Intuitive Machines in any page we could read. Three generic "
                           "arrangements are modelled instead: six vertical panels on the faces, one horizontal "
                           "panel, one Sun-tracking panel.",
        "efficiency": EFFICIENCY,
        "areas_m2": {"tracking": round(TRACKING_AREA_M2, 3), "horizontal": round(TRACKING_AREA_M2, 3),
                     "each_of_six_faces": round(FACE_AREA_M2, 3)},
        "area_rule": "Areas are scaled so that each arrangement gives the official 200 W in its best case: the "
                     "tracking and horizontal panels at normal incidence, the six faces with the Sun on the horizon.",
        "load_w": BATTERY.load_w,
        "max_depth_of_discharge": BATTERY.max_depth_of_discharge,
        "charge_curve": "full acceptance (0.5 C) up to 80 % charge, linear taper to zero at 100 %; efficiency 0.95",
        "yaw": "upright lander: one face toward north; on its side: averaged over 12 fall directions",
        "shading": "only the horizon mask (visible fraction of the solar disk); panels shading each other, "
                   "the ground under a fallen lander and dust are not modelled",
    },
}

# Height of the panels above the ground (or above the crater floor) for each posture.
FACE_SLICES_M = (0.5, 1.5, 2.5, 3.5)  # the side panels of a 4.0 m body, in four equal bands
HEIGHT_UPRIGHT_TOP = 4.0
HEIGHT_ON_SIDE = 0.8  # mid-height of a 1.57 m wide body lying down

LOCATIONS = [("plateau", 0.0), ("MODEL crater 2 m deep", 0.1), ("MODEL crater 4 m deep", 0.2)]
FALL_DIRECTIONS = np.arange(0, 360, 30)


def main() -> int:
    near, far = load_site_grids(SITE.lat, SITE.lon)
    times = pd.date_range(LANDING, LANDING + pd.Timedelta(days=PLANNED_DAYS), freq=STEP)
    base = positions(SITE.lat, SITE.lon, times)
    actual = times <= ACTUAL_END

    tables = {}
    for location, ratio in LOCATIONS:
        for height in sorted({HEIGHT_ON_SIDE, HEIGHT_UPRIGHT_TOP, *FACE_SLICES_M}):
            mask = mask_with_crater(SITE.lat, SITE.lon, height, near, far, CRATER_DIAMETER_M if ratio else 0.0, ratio)
            tables[(location, height)] = apply_visibility(base, height, mask)

    faces, top = upright_faces(), horizontal_panel()
    slice_area = FACE_AREA_M2 / len(FACE_SLICES_M)
    rows, curves = [], {}
    header = (f"{'location':<22} {'posture':<9} {'panels':<22} {'mean W':>7} {'Wh/day':>7} {'min SoC':>8} "
              f"{'load off h':>10} {'first off h':>11} | {'12.75 h: mean W':>15} {'end SoC':>8}")
    print(header)
    for location, _ in LOCATIONS:
        for posture in ("upright", "on side"):
            # Each variant is a list of alternatives (fall directions); an alternative is a list of
            # (panels, height above the ground or crater floor) parts whose power is added up.
            if posture == "upright":
                variants = [("six vertical faces", [[(PanelSet("faces", faces, slice_area), h) for h in FACE_SLICES_M]]),
                            ("horizontal top", [[(PanelSet("top", top, TRACKING_AREA_M2), HEIGHT_UPRIGHT_TOP)]]),
                            ("Sun tracking", [[(PanelSet("tracking", None, TRACKING_AREA_M2), HEIGHT_UPRIGHT_TOP)]])]
            else:
                variants = [("six faces, fallen", [[(PanelSet("faces", tipped_over(faces, d), FACE_AREA_M2), HEIGHT_ON_SIDE)]
                                                    for d in FALL_DIRECTIONS]),
                            ("top panel, fallen", [[(PanelSet("top", tipped_over(top, d), TRACKING_AREA_M2), HEIGHT_ON_SIDE)]
                                                   for d in FALL_DIRECTIONS])]
            for label, alternatives in variants:
                height = "0.5-3.5" if label == "six vertical faces" else alternatives[0][0][1]
                stamps = base["time_utc"]
                results = []
                for parts in alternatives:
                    power = sum(panel_power(tables[(location, h)], panels, EFFICIENCY) for panels, h in parts)
                    sim = simulate_battery(stamps, power, BATTERY)
                    first = simulate_battery(stamps[actual], power[actual], BATTERY)
                    results.append((battery_summary(sim), battery_summary(first), sim))
                # A fallen lander: report the average over fall directions and the range.
                keys = ("mean_power_w", "energy_wh_per_day", "min_soc_pct", "load_off_hours")
                mean = {k: round(float(np.mean([r[0][k] for r in results])), 1) for k in keys}
                spread = {k: [round(float(min(r[0][k] for r in results)), 1), round(float(max(r[0][k] for r in results)), 1)]
                          for k in keys}
                first_off = [r[0]["hours_to_first_load_off"] for r in results]
                first_off_text = "never" if all(v is None for v in first_off) else \
                    f"{min(v for v in first_off if v is not None):.1f}" + ("" if all(v is not None for v in first_off) else "+")
                short_mean = round(float(np.mean([r[1]["mean_power_w"] for r in results])), 1)
                short_end = round(float(np.mean([r[1]["end_soc_pct"] for r in results])), 1)
                rows.append({"location": location, "posture": posture, "panels": label, "panel_height_m": height,
                             "directions_averaged": len(results), "planned_10_days": mean, "range_over_directions": spread,
                             "hours_to_first_load_off": first_off_text,
                             "actual_12_75_h": {"mean_power_w": short_mean, "end_soc_pct": short_end},
                             "model": location != "plateau"})
                best = max(results, key=lambda r: r[0]["mean_power_w"])
                curves[f"{location} | {posture} | {label}"] = best[2]
                print(f"{location:<22} {posture:<9} {label:<22} {mean['mean_power_w']:>7.1f} {mean['energy_wh_per_day']:>7.0f} "
                      f"{mean['min_soc_pct']:>7.1f}% {mean['load_off_hours']:>10.1f} {first_off_text:>11} | "
                      f"{short_mean:>15.1f} {short_end:>7.1f}%")

    print(f"\nBattery {BATTERY.capacity_wh:g} Wh, load {BATTERY.load_w:g} W, depth-of-discharge limit "
          f"{BATTERY.max_depth_of_discharge:.0%}: without any Sun the load is shed after "
          f"{BATTERY.capacity_wh * BATTERY.max_depth_of_discharge / BATTERY.load_w:.1f} h.")

    out_dir = ROOT / "data" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "athena_energy.json").write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "warning": "MODEL with generic hardware parameters; the crater rows use an assumed crater depth.",
        "formula": "P = S * A * eta * max(0, n.s) * V", "solar_constant_w_m2": SOLAR_CONSTANT_W_M2,
        "site": {"name": SITE.name, "lat": SITE.lat, "lon": SITE.lon},
        "window": {"start_utc": LANDING.isoformat(), "planned_days": PLANNED_DAYS, "actual_end_utc": ACTUAL_END.isoformat(),
                   "step": STEP},
        "battery": {"capacity_wh": BATTERY.capacity_wh, "load_w": BATTERY.load_w,
                    "max_depth_of_discharge": BATTERY.max_depth_of_discharge},
        "parameters": PARAMETERS, "rows": rows,
    }, indent=1), encoding="utf-8")
    plot(curves, out_dir / "athena_energy.png")
    print(f"Written {out_dir.relative_to(ROOT)}\\athena_energy.json and athena_energy.png")
    return 0


def plot(curves: dict, path: Path) -> None:
    """State of charge for the six location x posture cases (body panels), small multiples."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, grid, surface, blue, red = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb", "#2a78d6", "#d03b3b"
    wanted = [k for k in curves if "faces" in k]
    fig, axes = plt.subplots(2, 3, figsize=(12, 5.6), sharex=True, sharey=True, facecolor=surface)
    for ax, key in zip(axes.T.ravel(), wanted):
        sim = curves[key]
        days = (sim["time_utc"] - sim["time_utc"].iloc[0]) / pd.Timedelta(days=1)
        ax.set_facecolor(surface)
        ax.plot(days, sim["soc"] * 100, color=blue, linewidth=2)
        off = ~sim["load_served"].to_numpy()
        if off.any():
            ax.fill_between(days, 0, 100, where=off, color=red, alpha=0.12, linewidth=0)
            ax.text(float(days[off].iloc[0]) + 0.15, 92, "load off", color=red, fontsize=8, va="top")
        location, posture, _ = [part.strip() for part in key.split("|")]
        ax.set_title(f"{location}, {posture}", loc="left", fontsize=10, color=ink)
        ax.set_ylim(0, 105)
        ax.set_xlim(0, float(days.iloc[-1]))
        ax.grid(axis="y", color=grid, linewidth=0.6)
        ax.tick_params(length=0, labelsize=9, colors=muted)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#c3c2b7")
    for ax in axes[-1]:
        ax.set_xlabel("days since touchdown", fontsize=9, color=muted)
    for ax in axes[:, 0]:
        ax.set_ylabel("battery charge, %", fontsize=9, color=muted)
    fig.suptitle("MODEL: battery charge with body-mounted panels, generic 200 W / 700 Wh / 100 W lander at the Athena site",
                 x=0.01, ha="left", fontsize=11, color=ink)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=150, facecolor=surface)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
