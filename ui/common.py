"""Shared interface pieces: sidebar, cached data access, formatting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import json
from typing import Optional

import pandas as pd
import streamlit as st

from lunarnav import get_series
from lunarnav import landing_scan as _landing_scan
from lunarnav import terrain, with_earth_definition
from lunarnav.metrics import Verdict
from lunarnav.sites import ARTEMIS_III_REGIONS_URL, PENDING, SITES, Site

from . import theme

CUSTOM_LABEL = "Custom coordinates"
DEFAULT_SITE_KEY = "im2"  # IM-2 Athena: the first thing shown is a real terrain horizon
EARTH_CHOICES = {"Centre of the disk is up": "centre", "Any part of the disk is up": "any"}
EARTH_TEXT = {"centre": "centre of the Earth's disk above the horizon",
              "any": "any part of the Earth's disk above the horizon"}
MIN_DATE = date(1950, 1, 1)
MAX_DATE = date(2048, 11, 30)  # DE421 ends in 2050; one year of look-ahead is kept free
KIND_TEXT = {
    "measured": "measured position",
    "reported": "position as listed by NSSDC",
    "planned": "planned landing site",
    "region": "approximate region reference point",
    "check": "validation check point, not a landing site",
}


@dataclass(frozen=True)
class Selection:
    """What the sidebar currently describes."""

    name: str
    lat: float
    lon: float
    panel_height_m: float  # the Sun is judged at this height
    antenna_height_m: float  # the Earth is judged at this height
    landing: pd.Timestamp  # UTC
    period_days: int
    site: Optional[Site]
    mask_key: Optional[str] = None  # key of the terrain masks in use, None = smooth sphere
    earth_definition: str = "centre"  # "centre" (strict) or "any" part of the Earth's disk
    horizon_note: str = ""  # one sentence saying which horizon is in use and why

    @property
    def end(self) -> pd.Timestamp:
        return self.landing + pd.Timedelta(days=self.period_days)

    @property
    def panel_mask(self):
        """Terrain mask at the panel height, or None for the smooth sphere."""
        return load_terrain_mask(self.mask_key, self.panel_height_m) if self.mask_key else None

    @property
    def antenna_mask(self):
        return load_terrain_mask(self.mask_key, self.antenna_height_m) if self.mask_key else None


# --------------------------------------------------------------------------
# Data access (cached: moving a slider never recomputes the ephemeris)
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner=False, max_entries=96)
def load_terrain_mask(key: str, height_m: float):
    """Stored terrain mask of a site for one height (None if absent)."""
    return terrain.load_mask(key, height_m)


def resolve_mask_key(key: str, lat: float, lon: float, heights) -> Optional[str]:
    """The key if terrain masks exist for these heights, computing them when the elevation data is on disk."""
    stored = set(terrain.stored_heights(key))
    missing = [h for h in heights if float(h) not in stored]
    if not missing:
        return key
    if lat <= -80.0 and terrain.terrain_available(lat, lon):
        with st.spinner("Computing the terrain horizon (720 directions, rays to 150 km)..."):
            grids = terrain.load_site_grids(lat, lon)
            for height in missing:
                mask = terrain.compute_mask(lat, lon, float(height), grids)
                mask.meta["site_key"] = key
                mask.save(terrain.mask_path(key, float(height)))
        load_terrain_mask.clear()
        return key
    return None


def nearest_terrain_site(lat: float, lon: float) -> Optional[Site]:
    """The closest preset that has terrain masks (for sites where terrain views cannot be shown)."""
    import numpy as np

    def distance(site: Site) -> float:
        a, b = np.radians([lat, lon]), np.radians([site.lat, site.lon])
        cos = np.sin(a[0]) * np.sin(b[0]) + np.cos(a[0]) * np.cos(b[0]) * np.cos(a[1] - b[1])
        return float(np.arccos(np.clip(cos, -1, 1)))

    candidates = [s for s in SITES if s.kind != "check" and terrain.has_all_heights(s.key)]
    return min(candidates, key=distance) if candidates else None


@st.cache_data(show_spinner="Computing the ephemeris for this site (first time only)...", max_entries=64)
def load_series(lat: float, lon: float, start_iso: str, end_iso: str, panel_height_m: float,
                antenna_height_m: float, mask_key: Optional[str] = None,
                earth_definition: str = "centre") -> pd.DataFrame:
    """Series for the interface: Sun at the panel height, Earth at the antenna height."""
    panel_mask = load_terrain_mask(mask_key, panel_height_m) if mask_key else None
    antenna_mask = load_terrain_mask(mask_key, antenna_height_m) if mask_key else None
    table = get_series(lat, lon, start_iso, end_iso, observer_height_m=panel_height_m, horizon_mask=panel_mask,
                       antenna_height_m=antenna_height_m, antenna_horizon_mask=antenna_mask)
    return with_earth_definition(table, earth_definition)


@st.cache_data(show_spinner="Scanning landing dates...", max_entries=48)
def load_landing_scan(lat: float, lon: float, panel_height_m: float, antenna_height_m: float,
                      mask_key: Optional[str], year: int, time_of_day: str, window_days: int,
                      from_touchdown: bool, earth_definition: str = "centre") -> pd.DataFrame:
    first = pd.Timestamp(f"{year}-01-01 {time_of_day}", tz="UTC")
    landings = pd.date_range(first, pd.Timestamp(f"{year}-12-31 {time_of_day}", tz="UTC"), freq="D")
    start = pd.Timestamp(f"{year}-01-01", tz="UTC")
    end = landings[-1] + pd.Timedelta(days=window_days + 1)
    panel_mask = load_terrain_mask(mask_key, panel_height_m) if mask_key else None
    antenna_mask = load_terrain_mask(mask_key, antenna_height_m) if mask_key else None
    table = get_series(lat, lon, start, end, observer_height_m=panel_height_m, horizon_mask=panel_mask,
                       antenna_height_m=antenna_height_m, antenna_horizon_mask=antenna_mask)
    return _landing_scan(with_earth_definition(table, earth_definition), landings, window_days,
                         from_touchdown=from_touchdown)


def iso(stamp: pd.Timestamp) -> str:
    return stamp.strftime("%Y-%m-%dT%H:%M:%S%z")


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def fmt_duration(delta: pd.Timedelta) -> str:
    minutes = int(round(delta.total_seconds() / 60))
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    if days:
        return f"{days} d {hours:02d} h {mins:02d} min"
    if hours:
        return f"{hours} h {mins:02d} min"
    return f"{mins} min"


def fmt_utc(stamp: pd.Timestamp) -> str:
    return stamp.strftime("%Y-%m-%d %H:%M UTC")


def fmt_lat_lon(lat: float, lon: float) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{abs(lat):.4f}° {ns}, {abs(lon):.4f}° {ew}"


def site_label(site: Site) -> str:
    return f"{site.group} · {site.name}"


def verdict_chip(verdict: Verdict) -> str:
    """Status as icon + label + colour (never colour alone)."""
    colour, icon = theme.STATUS[verdict.level]
    return (
        f'<span class="verdict-chip" style="border-color:{colour}">'
        f'<span style="color:{colour}">{icon}</span> {verdict.label}</span>'
    )


CSS = f"""
<style>
.big-card {{ background:{theme.SURFACE}; border:1px solid rgba(255,255,255,0.10); border-radius:10px;
            padding:18px 22px; height:100%; }}
.big-label {{ color:{theme.MUTED}; font-size:0.8rem; letter-spacing:0.06em; text-transform:uppercase; }}
.big-value {{ color:{theme.INK}; font-size:clamp(1.7rem, 3.1vw, 2.7rem); font-weight:650; line-height:1.15;
             margin:4px 0 2px 0; }}
.big-detail {{ color:{theme.INK_SECONDARY}; font-size:0.95rem; }}
.big-dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:8px; }}
.stat-card {{ background:{theme.SURFACE}; border:1px solid rgba(255,255,255,0.10); border-radius:10px;
             padding:12px 16px; height:100%; }}
.stat-label {{ color:{theme.INK_SECONDARY}; font-size:0.86rem; line-height:1.25; white-space:normal;
              overflow-wrap:break-word; }}
.stat-value {{ color:{theme.INK}; font-size:clamp(1.2rem, 2.1vw, 1.85rem); font-weight:650; line-height:1.2;
              margin-top:4px; white-space:normal; }}
.stat-detail {{ color:{theme.MUTED}; font-size:0.8rem; line-height:1.3; margin-top:2px; }}
.verdict-chip {{ display:inline-block; border:1px solid; border-radius:999px; padding:3px 12px;
                color:{theme.INK}; font-weight:600; white-space:nowrap; }}
</style>
"""


def embed_html(html: str, height: int) -> None:
    """Embed a self-contained HTML page (our own files only) as a Streamlit component."""
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:  # older Streamlit
        import streamlit.components.v1 as components

        components.html(html, height=height, scrolling=True)


def stat_card(label: str, value: str, detail: str = "") -> str:
    """A metric whose label and value wrap instead of being cut off."""
    return ('<div class="stat-card">'
            f'<div class="stat-label">{label}</div><div class="stat-value">{value}</div>'
            + (f'<div class="stat-detail">{detail}</div>' if detail else "") + "</div>")


def big_card(label: str, value: str, detail: str, colour: str) -> str:
    return (
        '<div class="big-card">'
        f'<div class="big-label"><span class="big-dot" style="background:{colour}"></span>{label}</div>'
        f'<div class="big-value">{value}</div>'
        f'<div class="big-detail">{detail}</div>'
        "</div>"
    )


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------
def sidebar() -> Selection:
    side = st.sidebar
    side.header("Scenario")

    qp = st.query_params
    first_load = "qp_loaded" not in st.session_state
    st.session_state["qp_loaded"] = True
    qp_site = qp.get("site") if first_load else None

    labels = [site_label(site) for site in SITES] + [CUSTOM_LABEL]
    default = next((i for i, site in enumerate(SITES) if site.key == (qp_site or DEFAULT_SITE_KEY)),
                   next((i for i, site in enumerate(SITES) if site.key == DEFAULT_SITE_KEY), 0))
    if qp_site == "custom":
        default = len(labels) - 1
    choice = side.selectbox("Landing site", labels, index=default)

    if choice == CUSTOM_LABEL:
        site = None
        try:
            def_lat = min(90.0, max(-90.0, float(qp.get("lat", -89.5)))) if first_load else -89.5
            def_lon = min(180.0, max(-180.0, float(qp.get("lon", 0.0)))) if first_load else 0.0
        except (TypeError, ValueError):
            def_lat, def_lon = -89.5, 0.0
        lat = side.number_input("Latitude (°, north positive)", -90.0, 90.0, def_lat, step=0.1, format="%.4f")
        lon = side.number_input("Longitude (°, east positive)", -180.0, 180.0, def_lon, step=0.1, format="%.4f")
        name = f"Custom ({fmt_lat_lon(lat, lon)})"
        side.caption("Coordinates entered by hand, Mean Earth / Polar Axis frame.")
    else:
        site = SITES[labels.index(choice)]
        lat, lon, name = site.lat, site.lon, site.name
        side.caption(f"{fmt_lat_lon(lat, lon)} · {KIND_TEXT[site.kind]}")
        with side.expander("Coordinate source", expanded=False):
            st.write(site.source)
            st.write(site.source_url)
            if site.note:
                st.caption(site.note)

    today = datetime.now(timezone.utc).date()
    def_date = min(max(today, MIN_DATE), MAX_DATE)
    def_time = time(0, 0)
    def_days = 14
    heights = [float(h) for h in terrain.MASK_HEIGHTS_M]
    def_hp, def_ha = 2.0, 2.0
    if first_load and qp:
        try:
            if "date" in qp:
                def_date = min(max(date.fromisoformat(str(qp["date"])), MIN_DATE), MAX_DATE)
        except ValueError:
            pass
        try:
            if "time" in qp:
                hh, mm = map(int, str(qp["time"]).split(":")[:2])
                def_time = time(hh, mm)
        except (ValueError, TypeError):
            pass
        try:
            if "days" in qp:
                def_days = min(30, max(1, int(qp["days"])))
        except (ValueError, TypeError):
            pass
        try:
            if "hp" in qp and float(qp["hp"]) in heights:
                def_hp = float(qp["hp"])
        except (ValueError, TypeError):
            pass
        try:
            if "ha" in qp and float(qp["ha"]) in heights:
                def_ha = float(qp["ha"])
        except (ValueError, TypeError):
            pass

    landing_date = side.date_input("Landing date (UTC)", value=def_date,
                                   min_value=MIN_DATE, max_value=MAX_DATE)
    landing_time = side.time_input("Landing time (UTC)", value=def_time, step=1800)
    period_days = side.slider("Analysis period (days)", 1, 30, def_days)
    panel_height = side.select_slider(
        "Panel height above the ground (m)", heights, value=def_hp, format_func=lambda h: f"{h:g}",
        help="Sunlight is judged with the horizon seen from this height.")
    antenna_height = side.select_slider(
        "Antenna height above the ground (m)", heights, value=def_ha, format_func=lambda h: f"{h:g}",
        help="Earth visibility and the radio link are judged with the horizon seen from this height.")

    with side.expander("Artemis III regions without coordinates"):
        st.caption(
            "NASA's 2024 list names nine candidate regions but gives no latitude and longitude. Five of "
            "them share a name with a region of the 2022 list, whose centres are among the presets. No "
            "official numeric source was found for the other four, so they are not offered. "
            "Use Custom coordinates."
        )
        for region in PENDING:
            st.write(f"- {region}")
        st.write(ARTEMIS_III_REGIONS_URL)

    # Horizon: terrain from LOLA for every point south of 80 S that has masks (or elevation data to
    # compute them); the smooth sphere everywhere else, always said in words.
    mask_key = None
    if lat <= -80.0:
        use_terrain = side.checkbox(
            "Terrain horizon (LOLA)", value=True,
            help="Use the horizon computed from LOLA elevation data (720 directions, rays to 150 km) in every tab. "
                 "Switch off to see the smooth-sphere answer.")
        if use_terrain:
            key = site.key if site is not None else terrain.custom_key(lat, lon)
            mask_key = resolve_mask_key(key, lat, lon, (panel_height, antenna_height))
            if mask_key:
                note = (f"Horizon: LOLA terrain, 720 directions, rays to 150 km; Sun at the panel height "
                        f"{panel_height:g} m, Earth at the antenna height {antenna_height:g} m.")
                share = (load_terrain_mask(mask_key, panel_height).meta or {}).get("share_of_samples_without_data", 0)
                if share and share > 0.02:
                    note += (f" PARTIAL TERRAIN: {share:.0%} of the ray samples fall outside the elevation grid "
                             "(north of 80° S), so the horizon toward the north is incomplete.")
            else:
                note = ("Horizon: SMOOTH SPHERE. No terrain mask is stored for this point and the elevation "
                        "data is not on this machine, so results near the pole are optimistic.")
        else:
            note = "Horizon: smooth sphere (terrain switched off)."
    else:
        note = ("Horizon: smooth sphere. Terrain masks exist only south of 80° S; away from the poles the "
                "Sun and the Earth stand high and the terrain matters little.")
    side.caption(note)

    # What "Earth visible" means: the disk is almost 2 degrees wide, so the choice matters near the limb.
    earth_choice = side.radio(
        "Earth counts as visible when",
        list(EARTH_CHOICES),
        index=0,
        help="Centre: the centre of the Earth's disk is above the horizon (strict, the default). "
             "Any part: the upper edge of the disk is above the horizon. Published Earth-visibility maps "
             "agree with 'any part'. Applies to every tab.",
    )

    landing = pd.Timestamp(datetime.combine(landing_date, landing_time), tz="UTC")
    with side.expander("Share or export scenario", expanded=False):
        key_or_custom = site.key if site is not None else "custom"
        params = {
            "site": key_or_custom,
            "lat": f"{lat:.4f}",
            "lon": f"{lon:.4f}",
            "date": landing_date.isoformat(),
            "time": landing_time.strftime("%H:%M"),
            "days": str(period_days),
            "hp": f"{panel_height:g}",
            "ha": f"{antenna_height:g}",
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        st.code(f"?{qs}", language=None)
        if st.button("Sync browser URL to scenario", key="sync_url_btn"):
            st.query_params.update(params)
        scenario_json = json.dumps({
            "site_key": key_or_custom,
            "site_name": name,
            "lat_deg": round(float(lat), 5),
            "lon_deg": round(float(lon), 5),
            "landing_utc": iso(landing),
            "period_days": int(period_days),
            "panel_height_m": float(panel_height),
            "antenna_height_m": float(antenna_height),
            "terrain_mask": mask_key,
            "earth_definition": EARTH_CHOICES[earth_choice],
        }, indent=2)
        st.download_button("Download scenario JSON", scenario_json, file_name="lunaris_scenario.json",
                           mime="application/json", key="dl_scenario_json")
    return Selection(name, float(lat), float(lon), float(panel_height), float(antenna_height), landing,
                     int(period_days), site, mask_key, EARTH_CHOICES[earth_choice], note)
