"""Site tab: 3D view of the terrain around the selected site.

The page follows the sidebar: site, landing date, analysis period, panel and
antenna heights. The terrain patch and the per-cell horizons are static files
(``data/site3d/<site>.json``); the Sun and Earth positions of the period and
the mask-based visibility of the site are computed here and passed in.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from lunarnav import REQUIRED_DAYS_FULL, REQUIRED_DAYS_MIN

from .common import Selection, embed_html, iso, load_series, nearest_terrain_site

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "assets" / "site3d.html"
DATA_DIR = ROOT / "data" / "site3d"


@st.cache_data(show_spinner=False)
def _static(key: str, modified: float) -> str:
    return (DATA_DIR / f"{key}.json").read_text(encoding="utf-8")


def run_payload(period: pd.DataFrame, sel: Selection) -> dict:
    """Hourly Sun / Earth positions of the period and the site's visibility from the 720-direction masks."""
    hourly = period.iloc[::2]
    return {
        "site_name": sel.name,
        "start_utc": sel.landing.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "step_hours": 1,
        "period_days": sel.period_days,
        "panel_height_m": sel.panel_height_m,
        "antenna_height_m": sel.antenna_height_m,
        "req_min": REQUIRED_DAYS_MIN,
        "req_full": REQUIRED_DAYS_FULL,
        "sun": [[round(float(a), 2), round(float(b), 2)] for a, b in zip(hourly["sun_az_deg"], hourly["sun_alt_deg"])],
        "earth": [[round(float(a), 2), round(float(b), 2)] for a, b in zip(hourly["earth_az_deg"], hourly["earth_alt_deg"])],
        "sun_up": [int(v) for v in hourly["sunlit"]],
        "earth_up": [int(v) for v in hourly["earth_visible"]],
    }


def render(sel: Selection) -> None:
    st.subheader(f"Site: the ground around {sel.name} in 3D")
    key = sel.site.key if sel.site is not None else None
    path = DATA_DIR / f"{key}.json" if key else None
    if not TEMPLATE.exists() or path is None or not path.exists() or sel.mask_key is None:
        near = nearest_terrain_site(sel.lat, sel.lon)
        hint = f" The nearest site with terrain is **{near.name}**." if near is not None else ""
        reason = ("terrain is switched off in the sidebar" if path is not None and path.exists() and sel.mask_key is None
                  else "there is no terrain data for this point (3D patches exist for the preset sites south of 80° S)")
        st.info(f"No 3D view for {sel.name}: {reason}.{hint} Another site's terrain is never shown in its place.")
        return

    period = load_series(sel.lat, sel.lon, iso(sel.landing), iso(sel.end), sel.panel_height_m,
                         sel.antenna_height_m, sel.mask_key, sel.earth_definition)
    static = _static(key, path.stat().st_mtime)
    meta = json.loads(static)
    page = (TEMPLATE.read_text(encoding="utf-8")
            .replace("/*__DATA__*/null", static)
            .replace("/*__RUN__*/null", json.dumps(run_payload(period, sel), separators=(",", ":"))))
    st.caption("Drag to turn, + and − to zoom, click the terrain to move the selected point. Play runs through the "
               "analysis period from the sidebar.")
    embed_html(page, height=860)
    check = meta.get("centre_check")
    st.caption(
        f"3 × 3 km around {sel.name}. Terrain: {meta['terrain']}. Sun and Earth positions: the same calculation as "
        f"the Sky tab, hourly, for the {sel.period_days} days from the sidebar. **Two kinds of numbers:** the time "
        f"strip and the status line of the site use the 720-direction masks at the sidebar heights (panels "
        f"{sel.panel_height_m:g} m, antenna {sel.antenna_height_m:g} m). The shadows, the card of a clicked cell, the "
        f"landing ellipse and the ray to the Earth are a visualisation from per-cell horizons: 36 directions, terrain "
        f"out to {meta['horizon']['ray_km']:g} km, eye {meta['horizon']['eye_m']:g} m above the ground, "
        f"{meta['horizon']['step_m']:g} m cells."
        + (f" Check: at the site the cell horizon differs from the 720-direction mask by "
           f"{abs(check['mean_diff_deg']):.2f}° on average ({check['max_abs_diff_deg']:.2f}° at most)." if check else "")
        + " The lander is a generic hexagonal body drawn 30 times larger than life; a 20 m crater is smaller than the "
          "grid and cannot appear. The 3D library is loaded from cdnjs and needs an internet connection."
    )
