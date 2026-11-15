"""Compare tab: 2-4 "site + date" scenarios side by side."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lunarnav import stretches, summary, terrain
from lunarnav.sites import SITES

from . import theme
from .common import MAX_DATE, MIN_DATE, Selection, fmt_lat_lon, iso, load_series, site_label

LETTERS = "ABCD"
SIDEBAR_LABEL = "Sidebar selection"
DEFAULT_KEYS = ["apollo11", "im2", "change4", "artemis_malapert"]
BANDS = (("sun", "Sun", theme.SUN), ("earth", "Comm", theme.EARTH), ("both", "Sun + comm", theme.BOTH))


def _bands_figure(scenarios, period_days: int) -> go.Figure:
    fig = go.Figure()
    rows = []
    for letter, _, landing, table, stats in scenarios:
        for what, band_name, colour in BANDS:
            row = f"{letter} · {band_name}"
            rows.append(row)
            found = stretches(table, what)
            if not found:
                continue
            base = [(s.start - landing) / pd.Timedelta(days=1) for s in found]
            fig.add_trace(go.Bar(
                orientation="h", y=[row] * len(found), base=base, x=[s.days for s in found],
                marker=dict(color=colour, line=dict(color=theme.SURFACE, width=2)), width=0.5,
                name=band_name, legendgroup=band_name, showlegend=(letter == scenarios[0][0]),
                customdata=[[s.start.strftime("%Y-%m-%d %H:%M"), s.end.strftime("%Y-%m-%d %H:%M")] for s in found],
                hovertemplate=f"<b>{letter} · {band_name}</b><br>%{{customdata[0]}} → %{{customdata[1]}} UTC"
                              "<br>%{x:.2f} d<extra></extra>",
            ))
        # Direct label on the one stretch that decides the verdict.
        best = stats["longest_both"]
        if best is not None:
            fig.add_annotation(
                x=(best.start - landing) / pd.Timedelta(days=1) + best.days / 2, y=f"{letter} · Sun + comm",
                text=f"{best.days:.1f} d", showarrow=False, font=dict(color="#ffffff", size=12),
            )

    fig.update_layout(**theme.base_layout(
        barmode="overlay", barcornerradius=4, height=110 + 34 * len(rows),
        margin=dict(l=130, r=24, t=48, b=52),
        xaxis=theme.axis(range=[0, period_days], title_text="Days since landing", dtick=1),
        yaxis=theme.axis(categoryorder="array", categoryarray=rows[::-1], showgrid=False,
                         tickfont=dict(color=theme.INK_SECONDARY, size=12)),
    ))
    return fig


def _sites_map(scenarios) -> go.Figure:
    """2D map of all preset sites: whole Moon (lon / lat) and the south polar cap."""
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=1, cols=2, column_widths=[0.66, 0.34], specs=[[{"type": "xy"}, {"type": "polar"}]],
                        subplot_titles=("Whole Moon (near side in the middle)", "South polar cap, 80° S to the pole"))
    ring = dict(color=theme.SURFACE, width=1.5)
    fig.add_trace(go.Scatter(
        x=[s.lon for s in SITES], y=[s.lat for s in SITES], mode="markers", name="Preset sites",
        marker=dict(size=8, color=theme.MUTED, line=ring), text=[s.name for s in SITES],
        hovertemplate="<b>%{text}</b><br>lat %{y:.2f}°, lon %{x:.2f}°<extra></extra>"), row=1, col=1)
    polar = [s for s in SITES if s.lat <= -80]
    fig.add_trace(go.Scatterpolar(
        r=[90 + s.lat for s in polar], theta=[s.lon for s in polar], mode="markers", showlegend=False,
        marker=dict(size=8, color=theme.MUTED, line=ring), text=[s.name for s in polar],
        hovertemplate="<b>%{text}</b><br>%{r:.2f}° from the pole, lon %{theta:.1f}°<extra></extra>"), row=1, col=2)
    for letter, (name, lat, lon), _, _, stats in scenarios:
        colour = theme.STATUS[stats["verdict"].level][0]
        fig.add_trace(go.Scatter(
            x=[lon], y=[lat], mode="markers+text", text=[letter], textposition="top center", showlegend=False,
            textfont=dict(color=theme.INK, size=14), marker=dict(size=13, color=theme.EARTH, line=ring),
            hovertemplate=f"<b>{letter}: {name}</b><br>{stats['verdict'].label}<extra></extra>"), row=1, col=1)
        if lat <= -80:
            fig.add_trace(go.Scatterpolar(
                r=[90 + lat], theta=[lon], mode="markers+text", text=[letter], textposition="top center",
                showlegend=False, textfont=dict(color=theme.INK, size=14),
                marker=dict(size=13, color=theme.EARTH, line=ring), hoverinfo="skip"), row=1, col=2)
    fig.update_xaxes(theme.axis(range=[-180, 180], dtick=60, ticksuffix="°", title_text="East longitude"), row=1, col=1)
    fig.update_yaxes(theme.axis(range=[-90, 90], dtick=30, ticksuffix="°", title_text="Latitude"), row=1, col=1)
    fig.update_layout(**theme.base_layout(
        height=420, showlegend=False,
        polar=dict(bgcolor=theme.SURFACE,
                   radialaxis=dict(range=[0, 10], tickvals=[2, 4, 6, 8, 10], ticktext=["88°", "86°", "84°", "82°", "80° S"],
                                   gridcolor=theme.GRID, linecolor=theme.AXIS, tickfont=dict(color=theme.MUTED, size=10)),
                   angularaxis=dict(direction="clockwise", rotation=90, gridcolor=theme.GRID, linecolor=theme.AXIS,
                                    tickfont=dict(color=theme.MUTED, size=10), dtick=45))))
    for annotation in fig.layout.annotations:
        annotation.update(font=dict(color=theme.INK_SECONDARY, size=12))
    return fig


def render(sel: Selection) -> None:
    st.subheader("Compare scenarios")
    st.caption(f"Each scenario runs for the analysis period from the sidebar ({sel.period_days} days), "
               f"starting at {sel.landing.strftime('%H:%M')} UTC on its landing date. "
               f"Sun at the panel height ({sel.panel_height_m:g} m), Earth at the antenna height "
               f"({sel.antenna_height_m:g} m). Sites south of 80° S use the LOLA terrain horizon, the others the "
               "smooth sphere; the Horizon column says which.")

    count = st.radio("Number of scenarios", [2, 3, 4], horizontal=True, key="cmp_count")
    labels = [SIDEBAR_LABEL] + [site_label(site) for site in SITES]
    keys = [site.key for site in SITES]

    scenarios, horizon_used = [], {}
    for i, col in enumerate(st.columns(count)):
        with col:
            default = 0 if i == 0 else 1 + keys.index(DEFAULT_KEYS[i])
            choice = st.selectbox(f"Scenario {LETTERS[i]}: site", labels, index=default, key=f"cmp_site_{i}")
            landing_date = st.date_input("Landing date (UTC)", value=sel.landing.date(), min_value=MIN_DATE,
                                         max_value=MAX_DATE, key=f"cmp_date_{i}")
        if choice == SIDEBAR_LABEL:
            name, lat, lon = sel.name, sel.lat, sel.lon
        else:
            site = SITES[labels.index(choice) - 1]
            name, lat, lon = site.name, site.lat, site.lon
        landing = pd.Timestamp(datetime.combine(landing_date, sel.landing.time()), tz="UTC")
        # Same horizon rule as the Sky tab: terrain masks where they exist, unless switched off in the sidebar.
        if choice == SIDEBAR_LABEL:
            mask_key = sel.mask_key
        else:
            wanted = {sel.panel_height_m, sel.antenna_height_m}
            terrain_on = sel.mask_key is not None or sel.lat > -80.0
            mask_key = site.key if terrain_on and wanted <= set(terrain.stored_heights(site.key)) else None
        horizon_used[LETTERS[i]] = "LOLA terrain" if mask_key else "smooth sphere"
        table = load_series(lat, lon, iso(landing), iso(landing + pd.Timedelta(days=sel.period_days)),
                            sel.panel_height_m, sel.antenna_height_m, mask_key, sel.earth_definition)
        scenarios.append((LETTERS[i], (name, lat, lon), landing, table, summary(table)))

    # Summary table: the verdict and the deciding number come first.
    rows = []
    for letter, (name, lat, lon), landing, table, stats in scenarios:
        rows.append({
            "Scenario": letter,
            "Site": name,
            "Landing (UTC)": landing.strftime("%Y-%m-%d %H:%M"),
            "Verdict (6–6.5 d)": f"{theme.STATUS[stats['verdict'].level][1]} {stats['verdict'].label}",
            "Horizon": horizon_used[letter],
            "Longest sun + comm (d)": round(stats["longest_both_days"], 2),
            "Longest sun (d)": round(stats["longest_sun_days"], 2),
            "Longest comm (d)": round(stats["longest_earth_days"], 2),
            "Sunlit (%)": round(100 * stats["sun_fraction"], 1),
            "Comm (%)": round(100 * stats["earth_fraction"], 1),
            "Coordinates": fmt_lat_lon(lat, lon),
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.markdown("##### Sunlight and communication over time")
    st.plotly_chart(_bands_figure(scenarios, sel.period_days), width="stretch", theme=None,
                    config=theme.PLOTLY_CONFIG, key="cmp_bands")
    with st.expander("Map of the sites", expanded=False):
        st.plotly_chart(_sites_map(scenarios), width="stretch", theme=None, config=theme.PLOTLY_CONFIG, key="cmp_map")
        st.caption("Grey dots: all preset sites. Blue letters: the scenarios compared above. The right panel "
                   "enlarges the south polar cap, where a few kilometres change the lighting completely.")
    st.caption("A bar means the condition holds: Sun = centre of the solar disk above the horizon, "
               "Comm = Earth above the horizon, Sun + comm = both at once. The number is the longest "
               "Sun + comm stretch, which is compared with the 6–6.5 day requirement.")
