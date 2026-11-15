"""Landing-date shift: battery charge curves side by side (MODEL).

The same generic 200 W / 700 Wh / 100 W lander as in scripts/athena_energy.py,
upright on the plateau at the Athena site, landing on the planned date and 7
and 14 days later. The window is the planned 10 days of surface operations.

    python scripts/landing_shift.py   ->  data/analysis/landing_shift.json, .png
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
sys.path.insert(0, str(ROOT / "scripts"))

from athena_energy import (  # noqa: E402  (same hardware assumptions, kept in one place)
    BATTERY, EFFICIENCY, FACE_AREA_M2, FACE_SLICES_M, HEIGHT_UPRIGHT_TOP, PARAMETERS, PLANNED_DAYS, TRACKING_AREA_M2,
)
from lunarnav import apply_visibility, positions  # noqa: E402
from lunarnav.energy import (  # noqa: E402
    PanelSet, battery_summary, horizontal_panel, panel_power, simulate_battery, sunlit_days, upright_faces,
)
from lunarnav.sites import SITES_BY_KEY  # noqa: E402
from lunarnav.terrain import load_site_grids, mask_from_grids  # noqa: E402

SITE = SITES_BY_KEY["im2"]
PLANNED_LANDING = pd.Timestamp("2025-03-06 17:30", tz="UTC")
SHIFTS_DAYS = [0, 7, 14]
STEP = "10min"
ARRANGEMENTS = ["six vertical faces", "horizontal panel", "Sun tracking"]
COLOURS = {"six vertical faces": "#2a78d6", "horizontal panel": "#eb6834", "Sun tracking": "#1baf7a"}


def main() -> int:
    near, far = load_site_grids(SITE.lat, SITE.lon)
    heights = sorted({*FACE_SLICES_M, HEIGHT_UPRIGHT_TOP})
    masks = {h: mask_from_grids(SITE.lat, SITE.lon, h, near, far) for h in heights}
    faces, slice_area = upright_faces(), FACE_AREA_M2 / len(FACE_SLICES_M)

    rows, curves = [], {}
    print(f"{'landing (UTC)':<18} {'panels':<20} {'Sun days':>8} {'mean W':>7} {'min SoC':>8} {'load off h':>10} "
          f"{'first off h':>11} {'end SoC':>8}")
    for shift in SHIFTS_DAYS:
        landing = PLANNED_LANDING + pd.Timedelta(days=shift)
        times = pd.date_range(landing, landing + pd.Timedelta(days=PLANNED_DAYS), freq=STEP)
        base = positions(SITE.lat, SITE.lon, times)
        tables = {h: apply_visibility(base, h, masks[h]) for h in heights}
        top = tables[HEIGHT_UPRIGHT_TOP]
        power = {
            "six vertical faces": sum(panel_power(tables[h], PanelSet("faces", faces, slice_area), EFFICIENCY)
                                      for h in FACE_SLICES_M),
            "horizontal panel": panel_power(top, PanelSet("top", horizontal_panel(), TRACKING_AREA_M2), EFFICIENCY),
            "Sun tracking": panel_power(top, PanelSet("tracking", None, TRACKING_AREA_M2), EFFICIENCY),
        }
        sun_days = sunlit_days(top)
        for name in ARRANGEMENTS:
            sim = simulate_battery(times, power[name], BATTERY)
            summary = battery_summary(sim)
            curves[(shift, name)] = sim
            rows.append({"shift_days": shift, "landing_utc": landing.strftime("%Y-%m-%d %H:%M"), "panels": name,
                         "sun_days_in_window": round(sun_days, 2), **summary})
            first = "never" if summary["hours_to_first_load_off"] is None else f"{summary['hours_to_first_load_off']:.1f}"
            print(f"{landing.strftime('%Y-%m-%d %H:%M'):<18} {name:<20} {sun_days:>8.2f} {summary['mean_power_w']:>7.1f} "
                  f"{summary['min_soc_pct']:>7.1f}% {summary['load_off_hours']:>10.1f} {first:>11} {summary['end_soc_pct']:>7.1f}%")

    out_dir = ROOT / "data" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "landing_shift.json").write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "warning": "MODEL with generic hardware parameters (see 'parameters').",
        "site": {"name": SITE.name, "lat": SITE.lat, "lon": SITE.lon}, "posture": "upright on the plateau",
        "window_days": PLANNED_DAYS, "step": STEP, "planned_landing_utc": PLANNED_LANDING.isoformat(),
        "battery": {"capacity_wh": BATTERY.capacity_wh, "load_w": BATTERY.load_w,
                    "max_depth_of_discharge": BATTERY.max_depth_of_discharge},
        "parameters": PARAMETERS, "rows": rows,
        # Hourly charge curves for the Research tab of the app.
        "curves": [{"shift_days": shift, "panels": name,
                    "hours": [round(float(h), 2) for h in
                              ((sim["time_utc"] - sim["time_utc"].iloc[0]) / pd.Timedelta(hours=1)).to_numpy()[::6]],
                    "soc_pct": [round(float(v) * 100, 1) for v in sim["soc"].to_numpy()[::6]]}
                   for (shift, name), sim in curves.items()],
    }, indent=1), encoding="utf-8")
    plot(curves, out_dir / "landing_shift.png")
    print(f"Written {out_dir.relative_to(ROOT)}\\landing_shift.json and landing_shift.png")
    return 0


def plot(curves: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, grid, surface = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
    fig, axes = plt.subplots(1, len(SHIFTS_DAYS), figsize=(12.5, 4.2), sharey=True, facecolor=surface)
    for ax, shift in zip(axes, SHIFTS_DAYS):
        ax.set_facecolor(surface)
        for name in ARRANGEMENTS:
            sim = curves[(shift, name)]
            days = (sim["time_utc"] - sim["time_utc"].iloc[0]) / pd.Timedelta(days=1)
            ax.plot(days, sim["soc"] * 100, color=COLOURS[name], linewidth=2, label=name)
        landing = PLANNED_LANDING + pd.Timedelta(days=shift)
        title = "planned date" if shift == 0 else f"{shift} days later"
        ax.set_title(f"Landing {landing.strftime('%d %b %Y')} ({title})", loc="left", fontsize=10, color=ink)
        ax.axhline(100 * (1 - BATTERY.max_depth_of_discharge), color=muted, linewidth=0.8)
        ax.set_ylim(0, 105)
        ax.set_xlim(0, PLANNED_DAYS)
        ax.set_xlabel("days since touchdown", fontsize=9, color=muted)
        ax.grid(axis="y", color=grid, linewidth=0.6)
        ax.tick_params(length=0, labelsize=9, colors=muted)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#c3c2b7")
    axes[0].set_ylabel("battery charge, %", fontsize=9, color=muted)
    axes[0].text(0.15, 100 * (1 - BATTERY.max_depth_of_discharge) - 2, "load is shed at this level", fontsize=8,
                 color=muted, va="top")
    axes[-1].legend(loc="center right", frameon=False, fontsize=9)
    fig.suptitle("MODEL: battery charge after landing on three dates, generic 200 W / 700 Wh / 100 W lander, "
                 "upright on the plateau at the Athena site", x=0.01, ha="left", fontsize=11, color=ink)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=150, facecolor=surface)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
