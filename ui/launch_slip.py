"""Launch slip tab: what a shifted landing date does to the sun + comm window."""

from __future__ import annotations

import calendar

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lunarnav import REQUIRED_DAYS_FULL, REQUIRED_DAYS_MIN

from . import theme
from .common import Selection, load_landing_scan, stat_card

MODES = {
    "Longest window within the mission period": False,
    "Window that starts at touchdown": True,
}


def _heatmap(scan: pd.DataFrame, year: int, window_days: int, selected: pd.Timestamp | None) -> go.Figure:
    months = [calendar.month_abbr[m] for m in range(1, 13)]
    z = np.full((12, 31), np.nan)
    dates = np.full((12, 31), "", dtype=object)
    for stamp, days in zip(scan["landing_utc"], scan["days"]):
        z[stamp.month - 1, stamp.day - 1] = days
        dates[stamp.month - 1, stamp.day - 1] = stamp.strftime("%Y-%m-%d")

    fig = go.Figure(go.Heatmap(
        z=z, x=list(range(1, 32)), y=months, customdata=dates, xgap=2, ygap=2,
        zmin=0, zmax=window_days, colorscale=[[i / 6, c] for i, c in enumerate(theme.SEQUENTIAL)],
        hoverongaps=False,
        hovertemplate="<b>Landing %{customdata}</b><br>%{z:.2f} d of sun + comm<extra></extra>",
        colorbar=dict(title=dict(text="days", font=dict(color=theme.MUTED, size=12)), thickness=12, len=0.9,
                      tickfont=dict(color=theme.MUTED, size=12), outlinewidth=0),
    ))

    # Second encoding besides colour: a dot on every date that meets the full requirement.
    ok = scan[scan["days"] >= REQUIRED_DAYS_FULL]["landing_utc"]
    fig.add_trace(go.Scatter(
        x=ok.dt.day, y=[months[m - 1] for m in ok.dt.month], mode="markers", hoverinfo="skip",
        marker=dict(size=7, color=theme.PAGE, line=dict(color=theme.INK, width=1)),
        name=f"meets {REQUIRED_DAYS_FULL:g} d",
    ))
    if selected is not None and selected.year == year:
        fig.add_trace(go.Scatter(
            x=[selected.day], y=[months[selected.month - 1]], mode="markers", hoverinfo="skip",
            marker=dict(size=19, symbol="square-open", color=theme.INK, line=dict(width=2)),
            name="landing date from the sidebar",
        ))

    fig.update_layout(**theme.base_layout(
        height=470,
        xaxis=theme.axis(title_text="Day of month", dtick=1, showgrid=False, range=[0.5, 31.5]),
        yaxis=theme.axis(autorange="reversed", showgrid=False, tickfont=dict(color=theme.INK_SECONDARY, size=12)),
    ))
    return fig


def render(sel: Selection) -> None:
    st.subheader(f"Launch slip: {sel.name}")
    left, right = st.columns([1, 3])
    years = list(range(max(sel.landing.year - 1, 1950), min(sel.landing.year + 4, 2048) + 1))
    year = left.selectbox("Year", years, index=years.index(sel.landing.year), key="slip_year")
    mode = right.radio("Window definition", list(MODES), horizontal=True, key="slip_mode")

    scan = load_landing_scan(sel.lat, sel.lon, sel.panel_height_m, sel.antenna_height_m, sel.mask_key, int(year),
                             sel.landing.strftime("%H:%M"),
                             sel.period_days, MODES[mode], sel.earth_definition)

    st.caption(sel.horizon_note)
    too_short = sel.period_days < REQUIRED_DAYS_MIN
    meets = int((scan["days"] >= REQUIRED_DAYS_FULL).sum())
    marginal = int(((scan["days"] >= REQUIRED_DAYS_MIN) & (scan["days"] < REQUIRED_DAYS_FULL)).sum())
    best = scan.loc[scan["days"].idxmax()]
    cols = st.columns(4)
    if too_short:
        # A period shorter than the requirement cannot show whether the requirement is met.
        cols[0].markdown(stat_card(f"Dates with at least {REQUIRED_DAYS_FULL:g} days",
                                   "N/A", "period shorter than requirement"), unsafe_allow_html=True)
        cols[1].markdown(stat_card(f"Dates with {REQUIRED_DAYS_MIN:g} to {REQUIRED_DAYS_FULL:g} days",
                                   "N/A", f"set the analysis period to {REQUIRED_DAYS_MIN:g} days or more"),
                         unsafe_allow_html=True)
    else:
        cols[0].markdown(stat_card(f"Dates with at least {REQUIRED_DAYS_FULL:g} days", f"{meets} of {len(scan)}"),
                         unsafe_allow_html=True)
        cols[1].markdown(stat_card(f"Dates with {REQUIRED_DAYS_MIN:g} to {REQUIRED_DAYS_FULL:g} days", f"{marginal}"),
                         unsafe_allow_html=True)
    cols[2].markdown(stat_card("Best landing date", best["landing_utc"].strftime("%b %d"),
                               f"{best['days']:.2f} days of Sun and communication"), unsafe_allow_html=True)
    cols[3].markdown(stat_card("Median window", f"{scan['days'].median():.2f} days"), unsafe_allow_html=True)

    st.plotly_chart(_heatmap(scan, int(year), sel.period_days, sel.landing), width="stretch", theme=None,
                    config=theme.PLOTLY_CONFIG, key="slip_heatmap")
    explanation = (
        "the continuous stretch that is already running at touchdown (0 if the site is dark or out of contact when landing)"
        if MODES[mode] else
        f"the longest continuous stretch inside the {sel.period_days}-day mission period that starts at landing"
    )
    st.caption(
        f"Each cell is one landing date at {sel.landing.strftime('%H:%M')} UTC. Colour is the duration of sunlight "
        f"and communication together: {explanation}. A launch slip of N days moves the landing N cells to the "
        f"right. Dots mark dates that meet the full {REQUIRED_DAYS_FULL:g}-day requirement"
        + (" (none can be marked: the period is shorter than the requirement)." if too_short else ".")
    )

    with st.expander("Data table"):
        table = pd.DataFrame({
            "Landing (UTC)": scan["landing_utc"].dt.strftime("%Y-%m-%d %H:%M"),
            "Sun + comm (d)": scan["days"].round(2),
        })
        st.dataframe(table, width="stretch", hide_index=True)
        st.download_button("Download CSV", table.to_csv(index=False), file_name="launch_slip.csv", mime="text/csv")
