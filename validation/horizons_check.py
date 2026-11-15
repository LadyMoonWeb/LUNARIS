"""Validation of the calculations against JPL Horizons.

For each of 5 sites, 300 random instants are drawn and the apparent altitude
and azimuth of the Sun and the Earth computed by ``lunarnav`` are compared
with JPL Horizons (queried through astroquery, observer on the Moon, body 301).
Epochs are sent in batches.

Outputs, in ``validation/results/``:
    horizons_samples.csv      every compared sample
    horizons_summary.json     maximum and mean discrepancy, per site and overall
    horizons_discrepancy.png  plot of the discrepancies against the tolerance

Run from the project root:  python validation/horizons_check.py
Exit code 1 means the tolerance was exceeded.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from astroquery.jplhorizons import Horizons  # noqa: E402

from lunarnav import positions  # noqa: E402
from lunarnav.sites import SITES_BY_KEY  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

# Five places chosen to cover the geometry: near-side equator, northern
# mid-latitude, far side, high southern latitude and the south polar region.
SITE_KEYS = ["apollo11", "apollo15", "change4", "chandrayaan3", "im2"]

SAMPLES_PER_SITE = 300
BATCH_SIZE = 50  # epochs per Horizons request (keeps the request URL short)
SEED = 2026
RANGE_START = pd.Timestamp("2026-01-01", tz="UTC")
RANGE_END = pd.Timestamp("2031-01-01", tz="UTC")
TOLERANCE_DEG = 0.01

BODIES = {"sun": "10", "earth": "399"}  # Horizons ids
MOON_ID = 301
PAUSE_S = 0.4  # politeness delay between requests


def random_instants(rng: np.random.Generator, count: int) -> pd.DatetimeIndex:
    """Random whole minutes inside the validation range, sorted."""
    total_minutes = int((RANGE_END - RANGE_START) / pd.Timedelta(minutes=1))
    minutes = np.sort(rng.choice(total_minutes, size=count, replace=False))
    return RANGE_START + pd.to_timedelta(minutes, unit="min")


def query_horizons(lat: float, lon: float, body_id: str, jd_utc: np.ndarray) -> pd.DataFrame:
    """Apparent azimuth / elevation from Horizons for a list of UTC Julian dates."""
    location = {"lon": lon, "lat": lat, "elevation": 0.0, "body": MOON_ID}
    last_error = None
    for attempt in range(4):
        try:
            table = Horizons(id=body_id, location=location, epochs=list(jd_utc)).ephemerides(quantities="4")
            return pd.DataFrame(
                {
                    "jd": np.asarray(table["datetime_jd"], dtype=float),
                    "az": np.asarray(table["AZ"], dtype=float),
                    "alt": np.asarray(table["EL"], dtype=float),
                }
            )
        except Exception as error:  # network hiccup: wait and retry
            last_error = error
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Horizons query failed after retries: {last_error}")


def wrap180(angle):
    return (np.asarray(angle) + 180.0) % 360.0 - 180.0


def check_site(site, rng: np.random.Generator) -> pd.DataFrame:
    times = random_instants(rng, SAMPLES_PER_SITE)
    jd = times.tz_localize(None).to_julian_date().values
    ours = positions(site.lat, site.lon, times)

    frames = []
    for body, body_id in BODIES.items():
        parts = []
        for first in range(0, len(jd), BATCH_SIZE):
            chunk = jd[first:first + BATCH_SIZE]
            got = query_horizons(site.lat, site.lon, body_id, chunk)
            if len(got) != len(chunk) or np.max(np.abs(got["jd"].values - chunk)) > 1e-7:
                raise RuntimeError("Horizons returned different epochs than requested")
            parts.append(got)
            time.sleep(PAUSE_S)
        ref = pd.concat(parts, ignore_index=True)

        alt = ours[f"{body}_alt_deg"].values
        az = ours[f"{body}_az_deg"].values
        d_alt = alt - ref["alt"].values
        d_az = wrap180(az - ref["az"].values)
        frames.append(
            pd.DataFrame(
                {
                    "site": site.name,
                    "site_key": site.key,
                    "lat": site.lat,
                    "lon": site.lon,
                    "time_utc": times,
                    "jd_utc": jd,
                    "body": body,
                    "alt_ours_deg": alt,
                    "az_ours_deg": az,
                    "alt_horizons_deg": ref["alt"].values,
                    "az_horizons_deg": ref["az"].values,
                    "d_alt_deg": d_alt,
                    "d_az_deg": d_az,
                    # Azimuth difference as an arc on the sky (az lines converge at the zenith).
                    "d_az_on_sky_deg": d_az * np.cos(np.radians(alt)),
                }
            )
        )
        print(f"  {site.name:<28} {body:<5} max |d alt| {np.abs(d_alt).max():.6f} deg   max |d az| {np.abs(d_az).max():.6f} deg")
    return pd.concat(frames, ignore_index=True)


def summarise(samples: pd.DataFrame) -> dict:
    def block(frame: pd.DataFrame) -> dict:
        a, z = frame["d_alt_deg"].abs(), frame["d_az_deg"].abs()
        return {
            "samples": int(len(frame)),
            "max_abs_alt_deg": float(a.max()),
            "mean_abs_alt_deg": float(a.mean()),
            "max_abs_az_deg": float(z.max()),
            "mean_abs_az_deg": float(z.mean()),
            "max_abs_deg": float(max(a.max(), z.max())),
            "mean_abs_deg": float(np.concatenate([a.values, z.values]).mean()),
        }

    worst = samples.loc[samples[["d_alt_deg", "d_az_deg"]].abs().max(axis=1).idxmax()]
    overall = block(samples)
    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "reference": "JPL Horizons via astroquery, observer on the Moon (body 301), quantity 4 (apparent AZ/EL)",
        "ours": "skyfield, DE421, MOON_ME_DE421, apparent positions",
        "sites": int(samples["site"].nunique()),
        "samples_per_site": SAMPLES_PER_SITE,
        "time_range_utc": [RANGE_START.strftime("%Y-%m-%d"), RANGE_END.strftime("%Y-%m-%d")],
        "seed": SEED,
        "tolerance_deg": TOLERANCE_DEG,
        "passed": bool(overall["max_abs_deg"] <= TOLERANCE_DEG),
        "overall": overall,
        "worst_sample": {
            "site": worst["site"],
            "body": worst["body"],
            "time_utc": pd.Timestamp(worst["time_utc"]).strftime("%Y-%m-%d %H:%M"),
            "d_alt_deg": float(worst["d_alt_deg"]),
            "d_az_deg": float(worst["d_az_deg"]),
        },
        "by_body": {body: block(frame) for body, frame in samples.groupby("body")},
        "by_site": {
            site: {"lat": float(frame["lat"].iloc[0]), "lon": float(frame["lon"].iloc[0]), **block(frame)}
            for site, frame in samples.groupby("site", sort=False)
        },
    }


def plot(samples: pd.DataFrame, summary: dict, path: Path) -> None:
    """Every sample's discrepancy per site on a log scale, with the tolerance."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, grid, surface = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
    colors = {"sun": "#eb6834", "earth": "#2a78d6"}  # fixed per body
    labels = {"sun": "Sun", "earth": "Earth"}
    floor = 1e-7  # Horizons prints 1e-6 deg; smaller differences are drawn here

    sites = list(samples["site"].unique())
    rng = np.random.default_rng(0)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True, facecolor=surface)
    for ax, column, title in zip(axes, ("d_alt_deg", "d_az_deg"), ("Altitude", "Azimuth")):
        ax.set_facecolor(surface)
        for row, site in enumerate(sites):
            for offset, body in ((-0.17, "sun"), (0.17, "earth")):
                chosen = samples[(samples["site"] == site) & (samples["body"] == body)]
                x = np.maximum(chosen[column].abs().values, floor)
                y = row + offset + rng.uniform(-0.12, 0.12, len(x))
                ax.scatter(x, y, s=7, color=colors[body], alpha=0.55, linewidths=0,
                           label=labels[body] if row == 0 else None)
        ax.axvline(TOLERANCE_DEG, color=ink, linewidth=1.2)
        ax.text(TOLERANCE_DEG, 1.01, "tolerance 0.01°", transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=9, color=ink)
        ax.set_xscale("log")
        ax.set_xlim(floor * 0.6, 0.05)
        ax.set_ylim(len(sites) - 0.5, -0.5)
        ax.set_yticks(range(len(sites)))
        ax.set_yticklabels(sites, fontsize=9, color=ink)
        ax.set_xlabel("absolute difference, degrees (log scale)", fontsize=9, color=muted)
        ax.set_title(title, loc="left", fontsize=11, color=ink)
        ax.grid(axis="x", color=grid, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(axis="both", which="both", length=0, labelsize=9, colors=muted)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#c3c2b7")
    for label in axes[0].get_yticklabels():
        label.set_color(ink)
    axes[1].legend(loc="lower right", frameon=False, fontsize=9, markerscale=2.2, handletextpad=0.2)

    overall = summary["overall"]
    fig.suptitle(
        "lunarnav vs JPL Horizons: {n} samples, max difference {mx:.5f}°, mean {mean:.6f}°".format(
            n=overall["samples"], mx=overall["max_abs_deg"], mean=overall["mean_abs_deg"]),
        x=0.01, ha="left", fontsize=12, color=ink)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=160, facecolor=surface)
    plt.close(fig)


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)

    if "--replot" in sys.argv:
        # Redraw the plot from the saved samples without querying Horizons again.
        samples = pd.read_csv(RESULTS / "horizons_samples.csv", parse_dates=["time_utc"])
        summary = json.loads((RESULTS / "horizons_summary.json").read_text(encoding="utf-8"))
        plot(samples, summary, RESULTS / "horizons_discrepancy.png")
        print("Plot redrawn from saved samples.")
        return 0 if summary["passed"] else 1

    rng = np.random.default_rng(SEED)
    print(f"Comparing with JPL Horizons: {len(SITE_KEYS)} sites x {SAMPLES_PER_SITE} instants, "
          f"batches of {BATCH_SIZE} epochs", flush=True)
    samples = pd.concat([check_site(SITES_BY_KEY[key], rng) for key in SITE_KEYS], ignore_index=True)
    summary = summarise(samples)

    samples.to_csv(RESULTS / "horizons_samples.csv", index=False)
    (RESULTS / "horizons_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    plot(samples, summary, RESULTS / "horizons_discrepancy.png")

    overall = summary["overall"]
    print(f"\nMaximum discrepancy: {overall['max_abs_deg']:.6f} deg "
          f"(altitude {overall['max_abs_alt_deg']:.6f}, azimuth {overall['max_abs_az_deg']:.6f})")
    print(f"Mean discrepancy:    {overall['mean_abs_deg']:.6f} deg")
    print(f"Tolerance:           {TOLERANCE_DEG} deg")
    if not summary["passed"]:
        worst = summary["worst_sample"]
        print(f"\nTOLERANCE EXCEEDED - worst sample: {worst['site']}, {worst['body']}, {worst['time_utc']} UTC, "
              f"d alt {worst['d_alt_deg']:+.6f} deg, d az {worst['d_az_deg']:+.6f} deg")
        return 1
    print("\nPASSED - all samples are within the tolerance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
