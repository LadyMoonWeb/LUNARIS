"""Sky tab: panorama of the horizon with the Sun and the Earth."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from lunarnav import energy, horizon_elevation_deg, link, next_event, summary

from . import panorama, theme
from .common import (
    EARTH_TEXT, Selection, big_card, embed_html, fmt_duration, fmt_utc, iso, load_series, nearest_terrain_site,
    stat_card, verdict_chip,
)

ROOT = Path(__file__).resolve().parent.parent
PLATE_EMBED = ROOT / "assets" / "plate-embed.html"  # the owner's plate without header and notes
LOOKAHEAD_DAYS = 366  # how far ahead the next sunset / Earthset is searched
STRETCH_NOTE = "Altitude axis is stretched about 8× relative to azimuth"


@st.cache_data(show_spinner=False)
def _background(path_text: str, modified: float) -> str:
    return panorama.as_data_uri(panorama.Path(path_text) if path_text else None)


def _broken_at_wrap(az, alt, labels):
    """Insert gaps where the azimuth jumps across north, so lines do not cross the chart."""
    az, alt = np.asarray(az, float), np.asarray(alt, float)
    cut = np.nonzero(np.abs(np.diff(az)) > 180)[0] + 1
    return np.insert(az, cut, np.nan), np.insert(alt, cut, np.nan), np.insert(np.asarray(labels, object), cut, "")


def _now_marker(fig, name, colour, az, alt, visible=True):
    """Body at the chosen moment; pinned to the frame edge when outside the panorama."""
    if alt > panorama.ALT_MAX:
        y, symbol, text, position = panorama.ALT_MAX - 0.45, "triangle-up", f"{name} is {alt:.1f}° up", "bottom center"
    elif alt < panorama.ALT_MIN:
        y, symbol, text, position = panorama.ALT_MIN + 0.45, "triangle-down", f"{name} is {abs(alt):.1f}° below", "top center"
    else:
        # A body behind the horizon is drawn as a ring and labelled, not hidden.
        y, position = alt, "top center"
        symbol, text = ("circle", name) if visible else ("circle-open", f"{name} (behind horizon)")
    fig.add_trace(go.Scatter(
        x=[az], y=[y], mode="markers+text", name=f"{name} now",
        marker=dict(size=22, color=colour, symbol=symbol,
                    line=dict(color=theme.PAGE if visible or symbol != "circle-open" else colour, width=2)),
        text=[text], textposition=position, textfont=dict(color=theme.INK, size=13),
        hovertemplate=f"<b>{name}</b><br>altitude {alt:.2f}°<br>azimuth {az:.1f}°<extra></extra>",
    ))


def panorama_figure(period: pd.DataFrame, now: pd.Series, sel: Selection, background_uri: str,
                    draw_silhouette: bool = True) -> go.Figure:
    fig = go.Figure()
    fig.add_layout_image(dict(
        source=background_uri, xref="x", yref="y", x=panorama.AZ_MIN, y=panorama.ALT_MAX,
        sizex=panorama.AZ_MAX - panorama.AZ_MIN, sizey=panorama.ALT_MAX - panorama.ALT_MIN,
        sizing="stretch", layer="below",
    ))

    # Local horizon: smooth sphere minus the dip, or the terrain mask from LOLA.
    mask = sel.panel_mask
    az_grid = np.linspace(0, 360, 721)
    horizon = horizon_elevation_deg(az_grid, sel.panel_height_m, mask)
    if sel.antenna_height_m != sel.panel_height_m:
        # The Earth is judged from the antenna height: its horizon is drawn as a second line.
        fig.add_trace(go.Scatter(
            x=az_grid, y=horizon_elevation_deg(az_grid, sel.antenna_height_m, sel.antenna_mask), mode="lines",
            name=f"Horizon at antenna height ({sel.antenna_height_m:g} m)", hoverinfo="skip",
            line=dict(color=theme.EARTH, width=1),
        ))
    if mask is not None and draw_silhouette:
        # Terrain silhouette: filled from the bottom of the frame up to the mask.
        fig.add_trace(go.Scatter(
            x=np.concatenate([az_grid, [360.0, 0.0]]),
            y=np.concatenate([np.maximum(horizon, panorama.ALT_MIN), [panorama.ALT_MIN, panorama.ALT_MIN]]),
            mode="lines", fill="toself", fillcolor="#4d4d4a", line=dict(width=0),
            hoverinfo="skip", showlegend=False,
        ))
    if mask is not None and mask.distance_km is not None:
        distance = np.interp(az_grid, mask.azimuth_deg, mask.distance_km, period=360.0)
        fig.add_trace(go.Scatter(
            x=az_grid, y=horizon, mode="lines", customdata=distance,
            name=f"Terrain horizon at panel height ({sel.panel_height_m:g} m)",
            line=dict(color="rgba(240,239,236,0.85)", width=1.5),
            hovertemplate="<b>Horizon</b><br>azimuth %{x:.1f}°<br>elevation %{y:.2f}°"
                          "<br>terrain %{customdata:.1f} km away<extra></extra>",
        ))
    else:
        fig.add_trace(go.Scatter(
            x=az_grid, y=horizon, mode="lines", name="Local horizon",
            line=dict(color="rgba(240,239,236,0.6)", width=1), hoverinfo="skip",
        ))

    stamps = period["time_utc"].dt.strftime("%Y-%m-%d %H:%M")
    for body, name, colour in (("sun", "Sun", theme.SUN), ("earth", "Earth", theme.EARTH)):
        az, alt, labels = _broken_at_wrap(period[f"{body}_az_deg"], period[f"{body}_alt_deg"], stamps)
        fig.add_trace(go.Scatter(
            x=az, y=alt, mode="lines", name=f"{name} path", customdata=labels,
            line=dict(color=colour, width=2), opacity=0.9,
            hovertemplate=f"<b>{name}</b> %{{customdata}} UTC<br>altitude %{{y:.2f}}°<br>azimuth %{{x:.1f}}°<extra></extra>",
        ))
        # One dot per day gives a sense of how fast the body moves.
        daily = period[period["time_utc"].dt.hour.eq(period["time_utc"].iloc[0].hour)
                       & period["time_utc"].dt.minute.eq(period["time_utc"].iloc[0].minute)]
        fig.add_trace(go.Scatter(
            x=daily[f"{body}_az_deg"], y=daily[f"{body}_alt_deg"], mode="markers", showlegend=False,
            marker=dict(size=7, color=colour, line=dict(color=theme.PAGE, width=1.5)),
            customdata=daily["time_utc"].dt.strftime("%Y-%m-%d %H:%M"),
            hovertemplate=f"<b>{name}</b> %{{customdata}} UTC<br>altitude %{{y:.2f}}°<br>azimuth %{{x:.1f}}°<extra></extra>",
        ))

    _now_marker(fig, "Sun", theme.SUN, float(now["sun_az_deg"]), float(now["sun_alt_deg"]), bool(now["sunlit"]))
    _now_marker(fig, "Earth", theme.EARTH, float(now["earth_az_deg"]), float(now["earth_alt_deg"]),
                bool(now["earth_visible"]))

    compass = {0: "N 0°", 90: "E 90°", 180: "S 180°", 270: "W 270°", 360: "N 360°"}
    ticks = list(range(0, 361, 30))
    fig.update_layout(**theme.base_layout(
        height=470,
        margin=dict(l=60, r=24, t=56, b=52),
        xaxis=theme.axis(range=[panorama.AZ_MIN, panorama.AZ_MAX], tickvals=ticks,
                         ticktext=[compass.get(t, f"{t}°") for t in ticks],
                         title_text="Azimuth (from north through east)", showgrid=False),
        yaxis=theme.axis(range=[panorama.ALT_MIN, panorama.ALT_MAX], tickvals=[-5, -2.5, 0, 2.5, 5, 7.5, 10],
                         ticksuffix="°", title_text="Altitude (stretched)", showgrid=False),
    ))
    fig.add_annotation(
        xref="paper", yref="paper", x=1.0, y=1.03, xanchor="right", yanchor="bottom", showarrow=False,
        text=STRETCH_NOTE, font=dict(color=theme.INK_SECONDARY, size=12),
    )
    return fig


def _event_card(event, body: str, colour: str, set_word: str, rise_word: str) -> str:
    label = f"Time to {set_word}"
    days_searched = LOOKAHEAD_DAYS
    if event.visible_now and event.time_to_set is not None:
        return big_card(label, fmt_duration(event.time_to_set),
                        f"{set_word.capitalize()} at {fmt_utc(event.next_set)}", colour)
    if event.visible_now:
        return big_card(label, f"No {set_word}",
                        f"The {body} stays above the horizon for at least the next {days_searched} days", colour)
    if event.time_to_rise is not None:
        return big_card(label, f"{body} is down",
                        f"{rise_word.capitalize()} in {fmt_duration(event.time_to_rise)} ({fmt_utc(event.next_rise)})", colour)
    return big_card(label, f"{body} is down", f"No {rise_word} in the next {days_searched} days", colour)


def _plain_summary(sel: Selection, now, sun_event, earth_event, stats) -> str:
    """One paragraph a non-specialist can read."""
    light = "in sunlight" if now["sunlit"] else "in shadow"
    contact = "can see the Earth" if now["earth_visible"] else "cannot see the Earth"
    if now["sunlit"] and sun_event.time_to_set is not None:
        sun_text = f"The Sun stays up for another {fmt_duration(sun_event.time_to_set)}."
    elif now["sunlit"]:
        sun_text = "The Sun does not set within the next year."
    elif sun_event.time_to_rise is not None:
        sun_text = f"The Sun comes back in {fmt_duration(sun_event.time_to_rise)}."
    else:
        sun_text = "The Sun does not come back within the next year."
    both = stats["longest_both_days"]
    level = stats["verdict"].level
    if level == "na":
        closing = (f"{both:.1f} days; the period is shorter than the 6 to 6.5 day requirement, so no verdict is "
                   "given. Lengthen the analysis period to judge it.")
    else:
        verdict = {"meets": "long enough for", "marginal": "barely enough for", "short": "too short for"}[level]
        closing = f"{both:.1f} days, {verdict} a 6 to 6.5 day surface mission."
    return (f"**In plain words:** at this moment the site is {light} and {contact}. {sun_text} Within the "
            f"{sel.period_days}-day period the longest unbroken time with both sunlight and Earth contact is "
            + closing)


def _plate_view(period: pd.DataFrame, sel: Selection) -> None:
    """The ink plate for the selected site, date and period.

    The plate gets the site name (``setTitle``), the terrain mask at the panel
    height (``setHorizonMask``, 720 values) and the computed Sun and Earth paths
    of the analysis period (``setTracks``, points ``{t, az, alt}`` with ISO times).
    Without a terrain mask nothing is drawn: another site's horizon is never shown.
    """
    if not PLATE_EMBED.exists():
        st.info("The plate needs assets/plate-embed.html.")
        return
    mask = sel.panel_mask
    if mask is None:
        near = nearest_terrain_site(sel.lat, sel.lon)
        hint = f" The nearest site with terrain is {near.name}." if near is not None else ""
        st.info(f"The plate draws a real terrain horizon, and there is no terrain mask for {sel.name}.{hint} "
                "Use the Panorama view for this site.")
        return
    tracks = {body: [{"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "az": round(float(az), 3), "alt": round(float(alt), 3)}
                     for t, az, alt in zip(period["time_utc"], period[f"{body}_az_deg"], period[f"{body}_alt_deg"])]
              for body in ("sun", "earth")}
    page = (PLATE_EMBED.read_text(encoding="utf-8")
            + "\n<script>window.setTitle(" + json.dumps(sel.name) + ");"
            + "window.setHorizonMask(" + json.dumps([round(float(v), 4) for v in mask.mask_deg]) + ");"
            + "window.setTracks(" + json.dumps(tracks, separators=(",", ":")) + ");</script>\n")
    embed_html(page, height=540)
    st.caption(f"Plate: the terrain horizon of {sel.name} at the panel height ({sel.panel_height_m:g} m) with the "
               f"computed tracks of the Sun and the Earth for the {sel.period_days}-day period from "
               f"{fmt_utc(sel.landing)}. The plate has its own time slider.")


def _energy_section(period: pd.DataFrame, moment: pd.Timestamp, sel: Selection) -> None:
    st.markdown("##### Energy over the analysis period (generic lander model)")
    c1, c2, c3 = st.columns(3)
    kind = c1.selectbox("Panel type", list(energy.PANEL_KINDS), format_func=energy.PANEL_KINDS.get, key="energy_kind")
    capacity = c2.number_input("Battery capacity (Wh)", 50.0, 50000.0, energy.GENERIC_BATTERY_WH, step=50.0,
                               key="energy_capacity")
    load = c3.number_input("Load (W)", 0.0, 5000.0, energy.GENERIC_LOAD_W, step=10.0, key="energy_load")

    power = energy.panel_power(period, energy.generic_panel_set(kind), energy.GENERIC_EFFICIENCY)
    sim = energy.simulate_battery(period["time_utc"], power, energy.Battery(capacity_wh=capacity, load_w=load))
    numbers = energy.battery_summary(sim)
    hours = (sim["time_utc"] - sim["time_utc"].iloc[0]) / pd.Timedelta(hours=1)
    days = hours / 24.0

    cols = st.columns(4)
    cols[0].markdown(stat_card("Mean power", f"{numbers['mean_power_w']:.0f} W",
                               f"{numbers['energy_wh_per_day']:.0f} Wh per day"), unsafe_allow_html=True)
    cols[1].markdown(stat_card("Lowest battery charge", f"{numbers['min_soc_pct']:.0f} %",
                               f"{numbers['end_soc_pct']:.0f} % at the end of the period"), unsafe_allow_html=True)
    first_off = numbers["hours_to_first_load_off"]
    cols[2].markdown(stat_card("Load switched off", f"{numbers['load_off_hours']:.0f} hours",
                               "never during the period" if first_off is None else
                               f"first time {first_off:.0f} h after the start"), unsafe_allow_html=True)
    now_index = int(round((moment - sim["time_utc"].iloc[0]) / pd.Timedelta(minutes=30)))
    cols[3].markdown(stat_card("At the chosen moment", f"{power[now_index]:.0f} W",
                               f"battery {sim['soc'].iloc[now_index] * 100:.0f} %"), unsafe_allow_html=True)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.09, row_heights=[0.42, 0.58])
    fig.add_trace(go.Scatter(x=days, y=power, mode="lines", name="Generated power", line=dict(color=theme.SUN, width=2),
                             hovertemplate="day %{x:.2f}<br>%{y:.0f} W<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=[days.iloc[0], days.iloc[-1]], y=[load, load], mode="lines", name="Load",
                             line=dict(color=theme.MUTED, width=1.5), hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Scatter(x=days, y=sim["soc"] * 100, mode="lines", name="Battery charge",
                             line=dict(color=theme.EARTH, width=2),
                             hovertemplate="day %{x:.2f}<br>charge %{y:.0f} %<extra></extra>"), row=2, col=1)
    floor = 20.0
    fig.add_hline(y=floor, line=dict(color=theme.MUTED, width=1), row=2, col=1)
    fig.add_annotation(x=float(days.iloc[-1]), y=floor, xref="x2", yref="y2", xanchor="right", yanchor="bottom",
                       text="load is shed at 20 %", showarrow=False, font=dict(color=theme.MUTED, size=11))
    fig.add_vline(x=float(days.iloc[now_index]), line=dict(color=theme.INK_SECONDARY, width=1))
    fig.update_yaxes(theme.axis(title_text="Power, W", rangemode="tozero"), row=1, col=1)
    fig.update_yaxes(theme.axis(title_text="Charge, %", range=[0, 105]), row=2, col=1)
    fig.update_xaxes(theme.axis(), row=1, col=1)
    fig.update_xaxes(theme.axis(title_text="Days since the start of the period"), row=2, col=1)
    fig.update_layout(**theme.base_layout(height=430))
    st.plotly_chart(fig, width="stretch", theme=None, config=theme.PLOTLY_CONFIG, key="sky_energy")
    st.caption(
        "Model: P = S·A·η·max(0, n·s)·V, V = visible fraction of the 0.53° solar disk above the horizon in use. "
        f"Generic lander: {energy.GENERIC_RATED_POWER_W:g} W rated (the only official figure, NASA NSSDC), efficiency "
        f"{energy.GENERIC_EFFICIENCY:g}, panel areas scaled to give the rated power in each arrangement's best case; "
        "panel placement is not published, so the three arrangements are generic. The load is shed at 80 % depth of "
        "discharge; charging tapers above 80 % charge. Panels are taken at the observer height from the sidebar "
        f"({sel.panel_height_m:g} m). The vertical line marks the chosen moment."
    )


def _link_section(period: pd.DataFrame, now, sel: Selection) -> None:
    st.markdown("##### Radio link to a DSN 34 m antenna (generic parameters)")
    with st.expander("Link assumptions"):
        c1, c2, c3 = st.columns(3)
        tx_power = c1.number_input("Transmitter power (W)", 0.1, 1000.0, 10.0, step=1.0, key="link_power")
        tx_gain = c2.number_input("Lander antenna gain (dBi)", -5.0, 40.0, 6.0, step=1.0, key="link_gain")
        rate = c3.number_input("Data rate (kbit/s)", 0.1, 100000.0, 100.0, step=10.0, key="link_rate")
        st.caption("Other terms: S-band 2.2 GHz, transmit losses 2 dB, other losses 2 dB, 34 m dish at 60 % "
                   "efficiency, system noise 40 K, required Eb/N0 3 dB. All generic, not a real lander.")
    budget = link.LinkBudget(tx_power_w=tx_power, tx_gain_dbi=tx_gain, data_rate_bps=rate * 1000.0)
    table = link.link_table(period, budget)
    row = table.iloc[int(now.name)]
    visible, low = bool(row["line_of_sight"]), bool(row["low_elevation"])

    cols = st.columns(4)
    cols[0].markdown(stat_card("Earth above the local horizon", f"{row['earth_elevation_deg']:+.2f}°",
                               "centre of the Earth's disk"), unsafe_allow_html=True)
    cols[1].markdown(stat_card("Free-space loss", f"{row['fspl_db']:.1f} dB",
                               f"range {row['earth_distance_km']:,.0f} km"), unsafe_allow_html=True)
    cols[2].markdown(stat_card("Link margin", f"{row['margin_db']:+.1f} dB" if visible else "no line of sight",
                               f"{rate:g} kbit/s to a 34 m antenna"), unsafe_allow_html=True)
    if not visible:
        flag, detail = "✖ Earth below the horizon", "no direct link"
    elif low:
        flag, detail = "▲ Earth below 6°", "low over the terrain: reflections likely"
    else:
        flag, detail = "✔ Earth above 6°", "clear of the low-elevation zone"
    cols[3].markdown(stat_card("Low-elevation flag", flag, detail), unsafe_allow_html=True)

    up = float(table["line_of_sight"].mean()) * 100
    low_share = float(table["low_elevation"].sum() / max(int(table["line_of_sight"].sum()), 1)) * 100
    margins = table["margin_db"].dropna()
    spread = f"{margins.min():+.1f} to {margins.max():+.1f} dB" if len(margins) else "n/a"
    st.caption(
        f"Over the period the Earth is above the horizon {up:.0f} % of the time, and {low_share:.0f} % of that time it "
        f"is below {link.LOW_ELEVATION_DEG:g}°. Margin while in view: {spread} (it changes only with the Earth-Moon "
        "distance). **Reflections from the terrain (multipath) are not modelled**, nor are antenna pointing and "
        "ground-station schedules; the flag only marks when the Earth is low enough for them to matter."
    )


def _reading_guide(period: pd.DataFrame, sel: Selection) -> None:
    with st.expander("How to read this page, and why the Moon is not like Earth"):
        top = float(period["sun_alt_deg"].max())
        swing = float(period["earth_az_deg"].max() - period["earth_az_deg"].min())
        st.markdown(
            f"""
- **One day lasts a month.** The Sun takes 29.5 Earth days to go around the sky once, so "daylight" and "night"
  each last about two weeks at most sites.
- **The Sun stays low near the poles.** In this period it never rises above **{top:.1f}°** at this site
  (on Earth's equator it reaches 90°). A hill a few metres high can hide it, which is why the horizon line matters
  more than anything else.
- **No air.** There is no twilight and no bending of light: the moment the Sun's disk goes behind the terrain it
  is dark and cold, and shadows are black.
- **The Earth hardly moves.** It does not rise and set daily; it sways slowly (here by about {min(swing, 360):.0f}° in
  azimuth) as the Moon wobbles. Where it sits low, small terrain features decide whether there is radio contact.
- **Reading the numbers.** *Elevation* (altitude) is the angle above the level horizon; *azimuth* is the compass
  direction, 0° north, 90° east. *Sunlit* means the centre of the Sun is above the horizon in use.
  *Communication* means the Earth is above it; the sidebar chooses whether the centre or any part of the disk counts.
            """
        )

    with st.expander("Data table for the analysis period"):
        table = period[["time_utc", "sun_alt_deg", "sun_az_deg", "earth_alt_deg", "earth_az_deg",
                        "sunlit", "earth_visible", "both"]].copy()
        table["time_utc"] = table["time_utc"].dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(table, width="stretch", hide_index=True)
        st.download_button("Download CSV", table.to_csv(index=False), file_name="sky_series.csv", mime="text/csv")


def render(sel: Selection) -> None:
    ahead = load_series(sel.lat, sel.lon, iso(sel.landing),
                        iso(sel.end + pd.Timedelta(days=LOOKAHEAD_DAYS)), sel.panel_height_m,
                        sel.antenna_height_m, sel.mask_key, sel.earth_definition)
    period = ahead[ahead["time_utc"] <= sel.end].reset_index(drop=True)

    st.subheader(f"{sel.name}: sky from {fmt_utc(sel.landing)}, {sel.period_days} days")
    st.caption(f"{sel.horizon_note} Earth visible = {EARTH_TEXT[sel.earth_definition]}.")

    start = sel.landing.tz_localize(None).to_pydatetime()
    moment_naive = st.slider(
        "Moment (UTC)", min_value=start, max_value=sel.end.tz_localize(None).to_pydatetime(), value=start,
        step=timedelta(minutes=30), format="YYYY-MM-DD HH:mm",
        key=f"moment_{sel.landing.isoformat()}_{sel.period_days}",
    )
    moment = pd.Timestamp(moment_naive, tz="UTC")
    now = period.iloc[int(round((moment - sel.landing) / pd.Timedelta(minutes=30)))]

    sun_event = next_event(ahead, moment, "sun")
    earth_event = next_event(ahead, moment, "earth")
    stats = summary(period)

    # Solar elevation is the key power metric at the poles: shown first and large.
    first, left, right = st.columns(3)
    first.markdown(big_card(
        "Sun elevation now", f"{now['sun_alt_deg']:.2f}°",
        f"{now['sun_clearance_deg']:+.2f}° against the local horizon · azimuth {now['sun_az_deg']:.0f}° · "
        + ("sunlit" if now["sunlit"] else "in shadow"), theme.SUN), unsafe_allow_html=True)
    left.markdown(_event_card(sun_event, "Sun", theme.SUN, "sunset", "sunrise"), unsafe_allow_html=True)
    right.markdown(_event_card(earth_event, "Earth", theme.EARTH, "Earthset", "Earthrise"), unsafe_allow_html=True)
    st.markdown(_plain_summary(sel, now, sun_event, earth_event, stats))

    view = st.radio("View", ["Plate (ink drawing)", "Panorama"], horizontal=True, key="sky_view",
                    label_visibility="collapsed")
    if view == "Panorama":
        path, is_custom = panorama.background_path()
        uri = _background(str(path) if path else "", path.stat().st_mtime if path else 0.0)
        # With the owner's own picture only the horizon line is drawn over it.
        st.plotly_chart(panorama_figure(period, now, sel, uri, draw_silhouette=not is_custom), width="stretch",
                        theme=None, config=theme.PLOTLY_CONFIG, key="sky_panorama")
        st.caption(
            f"{STRETCH_NOTE}: the panorama spans 360° of azimuth but only 15° of altitude "
            "(−5° to +10°). A body outside this band is pinned to the frame edge with its altitude. "
            "Lines show the paths over the analysis period, dots mark every 24 hours. "
            + ("Background: your picture." if is_custom else
               "Background: placeholder" + (" with the terrain silhouette drawn from the mask" if sel.mask_key else
                                            " with a flat horizon")
               + ". Put your own picture at assets/panorama_background.png to replace it.")
        )
    else:
        _plate_view(period, sel)

    st.markdown(
        f"At {fmt_utc(moment)}: **Sun** altitude {now['sun_alt_deg']:.2f}°, azimuth {now['sun_az_deg']:.1f}° "
        f"({'sunlit' if now['sunlit'] else 'dark'}) · **Earth** altitude {now['earth_alt_deg']:.2f}°, "
        f"azimuth {now['earth_az_deg']:.1f}° ({'in view' if now['earth_visible'] else 'not in view'})"
    )

    st.markdown("##### Longest continuous stretch within the analysis period")
    cols = st.columns(4)
    for col, what, title in zip(cols, ("sun", "earth", "both"),
                                ("Sunlight", "Communication (Earth in view)", "Sunlight and communication together")):
        best = stats[f"longest_{what}"]
        running = best is not None and best.open_end
        col.markdown(stat_card(title, f"{stats[f'longest_{what}_days']:.2f} days",
                               "still running when the period ends" if running else ""), unsafe_allow_html=True)
    with cols[3]:
        chip = f'<span style="font-size:0.92rem">{verdict_chip(stats["verdict"])}</span>'
        st.markdown(stat_card("Requirement: 6 to 6.5 days", chip, stats["verdict"].detail), unsafe_allow_html=True)

    _energy_section(period, moment, sel)
    _link_section(period, now, sel)
    _reading_guide(period, sel)
