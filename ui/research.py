"""Research tab: the Athena case study (question, method, verification, result)."""

from __future__ import annotations

import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from . import theme

ANALYSIS = Path(__file__).resolve().parent.parent / "data" / "analysis"
BLUE, ORANGE, AQUA = theme.EARTH, theme.SUN, theme.BOTH  # three validated categorical colours


def _load(name: str):
    path = ANALYSIS / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _note(fig: go.Figure, text: str, x: float = 0.01, y: float = 0.02, anchor: str = "bottom") -> None:
    """Assumptions written directly on the chart."""
    fig.add_annotation(xref="paper", yref="paper", x=x, y=y, xanchor="left", yanchor=anchor, align="left",
                       showarrow=False, text=text, font=dict(color=theme.INK_SECONDARY, size=11),
                       bgcolor="rgba(13,13,13,0.78)", bordercolor=theme.AXIS, borderwidth=1, borderpad=6)


def crater_figure(data: dict) -> go.Figure:
    window = "planned (10 d)"
    cases = [("plateau, no crater", "Plateau (LOLA terrain)", BLUE)]
    for row in data["rows"]:
        if row["model"] and row["case"] not in [c[0] for c in cases]:
            depth = row["depth_m"]
            cases.append((row["case"], f"MODEL crater, {depth:g} m deep", ORANGE if depth < 3 else AQUA))
    fig = go.Figure()
    for case, label, colour in cases:
        rows = [r for r in data["rows"] if r["case"] == case]
        fig.add_trace(go.Bar(
            x=[f"{r['observer_height_m']:g} m" for r in rows], y=[r["sun_days"][window]["centre_days"] for r in rows],
            name=label, marker=dict(color=colour, line=dict(color=theme.SURFACE, width=2)),
            text=[f"{r['sun_days'][window]['centre_days']:.1f}" for r in rows], textposition="outside",
            textfont=dict(color=theme.INK, size=12),
            customdata=[[r["horizon_min_deg"], r["horizon_max_deg"], r["height_meaning"]] for r in rows],
            hovertemplate=f"<b>{label}</b><br>%{{x}} above the floor: %{{customdata[2]}}<br>%{{y:.2f}} days of Sun"
                          "<br>horizon %{customdata[0]:.1f}° to %{customdata[1]:.1f}°<extra></extra>",
        ))
    fig.update_layout(**theme.base_layout(
        barmode="group", barcornerradius=4, height=470, bargap=0.28,
        xaxis=theme.axis(title_text="Height of the panels above the ground or the crater floor", showgrid=False,
                         type="category"),
        yaxis=theme.axis(title_text="Days of Sun in the planned 10 days", range=[0, 13.5]),
    ))
    _note(fig, "<b>MODEL, not measured terrain.</b> Crater: parabolic bowl without a raised rim, 20 m across "
               "(diameter from LROC), depth ASSUMED 2 m and 4 m<br>(depth / diameter 0.1 and 0.2), lander at its "
               "centre. Sun = centre of the disk above the horizon. Window: 6-16 Mar 2025.<br>Heights: 0.8 m and "
               "1.6 m = lander on its side, 4 m = top of an upright lander.", y=0.985, anchor="top")
    return fig


def height_figure(data: dict) -> go.Figure:
    heights = data["heights_m"]
    fig = go.Figure()
    for site, colour, label in zip(data["sites"], (BLUE, ORANGE), ("Plateau (Athena point)", "Nearby crest")):
        diagonal = [site["both_pct_rows_panel_cols_antenna"][i][i] for i in range(len(heights))]
        gaps = [site["longest_gap_days_rows_panel_cols_antenna"][i][i] for i in range(len(heights))]
        fig.add_trace(go.Scatter(
            x=heights, y=diagonal, mode="lines+markers+text", name=label, customdata=gaps,
            line=dict(color=colour, width=2), marker=dict(size=9, color=colour, line=dict(color=theme.SURFACE, width=2)),
            text=[f"{diagonal[0]:.1f}%"] + [""] * (len(heights) - 2) + [f"{diagonal[-1]:.1f}%"],
            textposition=["middle left"] + ["top center"] * (len(heights) - 2) + ["middle right"],
            textfont=dict(color=theme.INK, size=12),
            hovertemplate=f"<b>{label}</b><br>panels and antenna at %{{x:g}} m<br>Sun and Earth together %{{y:.1f}} %"
                          "<br>longest gap %{customdata:.1f} days<extra></extra>",
        ))
    crest = data["crest"]
    fig.update_layout(**theme.base_layout(
        height=470, margin=dict(l=70, r=70, t=48, b=52),
        xaxis=theme.axis(title_text="Height of panels and antenna above the ground, m", tickvals=heights,
                         range=[-1.1, 11.1]),
        yaxis=theme.axis(title_text="Sun and Earth together, % of the year", ticksuffix="%"),
    ))
    _note(fig, f"Assumptions: one year from the Athena touchdown (6 Mar 2025), 30-minute step. Sun and Earth = centre "
               f"of the disk above the terrain horizon<br>(LOLA 10 m near, 40 m to 150 km). Crest = highest 10 m cell "
               f"within 5 km: {crest['distance_from_athena_m']:.0f} m away, {crest['height_above_athena_m']:+.0f} m. "
               "Panels and antenna at the same height.<br>No spread band: the 100 PGDA terrain variants do not cover "
               "this area.", x=0.99, y=0.03)
    fig.layout.annotations[-1].update(xanchor="right")
    return fig


def shift_figure(data: dict) -> go.Figure:
    shifts = sorted({c["shift_days"] for c in data["curves"]})
    titles = ["Planned date (6 Mar 2025)"] + [f"{s} days later" for s in shifts[1:]]
    fig = make_subplots(rows=1, cols=len(shifts), shared_yaxes=True, horizontal_spacing=0.03, subplot_titles=titles)
    colours = {"six vertical faces": BLUE, "horizontal panel": ORANGE, "Sun tracking": AQUA}
    dashes = {"six vertical faces": "solid", "horizontal panel": "solid", "Sun tracking": "dot"}
    for col, shift in enumerate(shifts, start=1):
        for curve in [c for c in data["curves"] if c["shift_days"] == shift]:
            name = curve["panels"]
            fig.add_trace(go.Scatter(
                x=[h / 24 for h in curve["hours"]], y=curve["soc_pct"], mode="lines", name=name.capitalize(),
                legendgroup=name, showlegend=(col == 1), line=dict(color=colours[name], width=2, dash=dashes[name]),
                hovertemplate=f"<b>{name}</b><br>day %{{x:.1f}}<br>charge %{{y:.0f}} %<extra></extra>",
            ), row=1, col=col)
        fig.update_xaxes(theme.axis(title_text="Days since touchdown", range=[0, data["window_days"]], dtick=2),
                         row=1, col=col)
    floor = 100 * (1 - data["battery"]["max_depth_of_discharge"])
    fig.add_hline(y=floor, line=dict(color=theme.MUTED, width=1))
    fig.update_yaxes(theme.axis(range=[0, 108], ticksuffix="%"))
    fig.update_yaxes(title_text="Battery charge", row=1, col=1)
    fig.update_layout(**theme.base_layout(
        height=560, margin=dict(l=70, r=24, t=96, b=150),
        legend=dict(orientation="h", yanchor="bottom", y=1.12, xanchor="left", x=0,
                    font=dict(color=theme.INK_SECONDARY), bgcolor="rgba(0,0,0,0)")))
    for annotation in fig.layout.annotations[:len(shifts)]:
        annotation.update(font=dict(color=theme.INK, size=13), y=1.01)
    battery = data["battery"]
    _note(fig, f"<b>MODEL, generic lander.</b> Official: 200 W on the surface (NSSDC). ASSUMED: panel placement "
               f"(not published), efficiency 0.28, battery {battery['capacity_wh']:g} Wh, load {battery['load_w']:g} W,<br>"
               f"load shed at {floor:.0f} % charge (grey line), charge taper above 80 %. Lander upright on the plateau, "
               "terrain horizon from LOLA.<br>P = S A η max(0, n·s) V, with V the visible fraction of the 0.53° "
               "solar disk.", x=0.0, y=-0.2, anchor="top")
    return fig


def render() -> None:
    st.subheader("Case study: why did Athena run out of power, and what would have helped?")
    crater, height, shift, energy = (_load(n) for n in ("athena_crater.json", "equipment_height.json",
                                                         "landing_shift.json", "athena_energy.json"))
    if not all((crater, height, shift, energy)):
        st.info("The analysis files are missing. Run scripts/athena_crater.py, athena_energy.py, "
                "equipment_height.py and landing_shift.py from the project root.")
        return

    st.markdown(
        """
**Question.** IM-2 Athena landed on Mons Mouton (84.79° S) on 6 March 2025 at about 17:30 UTC and the mission
ended 12.75 hours later with empty batteries; the lander lay on its side in a crater about 20 m across (LROC, NASA).
The plateau itself was sunlit. How much of the loss is explained by the crater, by the posture, and by the date,
and how sensitive is a polar site to a few metres of height or a few days of delay?

**Method.** Sun and Earth directions come from the JPL DE421 ephemeris; the horizon comes from LOLA elevation data
(10 m near the site, 40 m out to 150 km), as 720 horizon angles per point. The crater is too small for any
elevation grid, so it is **modelled** as a bowl carved into a fine copy of the terrain. Power follows
P = S·A·η·max(0, n·s)·V with a battery, a load and a depth-of-discharge limit.

**Verification.** Positions agree with JPL Horizons to 0.0002°. The horizon masks were recomputed by an
independent verifier to better than 0.001°. Long-term sunlight at the Athena point is 44.4 % against 46.8 % in the
published PGDA map. The crater model reproduces the analytic rim angle. What is *not* verified: the real depth
of the crater, the real panel layout, load and battery of the lander.
        """
    )

    st.markdown("##### 1. The crater, not the site, takes the Sun away")
    st.plotly_chart(crater_figure(crater), width="stretch", theme=None, config=theme.PLOTLY_CONFIG, key="research_crater")
    low, high = crater["sun_altitude_range_lunar_day_deg"]
    st.caption(f"On the plateau the Sun stays up for all 10 planned days at any height. During that lunar day the Sun "
               f"never climbs above {high:.1f}°, so a rim only 2 m high and 10 m away (11°) hides it from the floor. "
               "In the first 12.75 hours a lander on its side sees no Sun in either crater model.")

    st.markdown("##### 2. A few metres of height: almost nothing on the plateau, a lot on the crest")
    st.plotly_chart(height_figure(height), width="stretch", theme=None, config=theme.PLOTLY_CONFIG, key="research_height")
    st.caption("The lines cross: at ground level the crest is worse than the plateau (its own slope blocks the Earth), "
               "from 1 m up it is better. On the crest the first metre of antenna height raises Earth visibility "
               "from 72 % to 80 %.")

    st.markdown("##### 3. A slip of one or two weeks decides everything")
    st.plotly_chart(shift_figure(shift), width="stretch", theme=None, config=theme.PLOTLY_CONFIG, key="research_shift")
    rows = {(r["shift_days"], r["panels"]): r for r in shift["rows"]}
    st.caption(
        f"Landing on the planned date: {rows[(0, 'six vertical faces')]['sun_days_in_window']:.0f} days of Sun, the battery "
        f"never drops. Seven days later: {rows[(7, 'six vertical faces')]['sun_days_in_window']:.1f} days of Sun, the load "
        f"is shed {rows[(7, 'six vertical faces')]['hours_to_first_load_off']:.0f} hours after touchdown. Fourteen days "
        "later the lander arrives in the dark and lasts under 6 hours. A horizontal panel fails on every date: at the "
        "pole the Sun is on the horizon, so panels must be vertical or tracking. The vertical-face and tracking "
        "curves overlap."
    )

    st.markdown(
        """
**Result.** In this model the site was good and the date was good: an upright lander on the plateau has power for
the whole planned mission. Lying on its side inside a 20 m crater it gets no sunlight in the first hours in either
crater model, which is consistent with the reported outcome. The same tools show the general lesson of the lunar
south pole: metres of terrain and days of schedule change the answer from "full power" to "none".

**Limits.** The crater depth, the panel layout, the load and the battery are assumptions, labelled on each
chart. The 10 m grid does not show boulders or the real crater. Reflections of radio and light from terrain are
not modelled.
        """
    )
    with st.expander("Power table for every posture and location (model)"):
        import pandas as pd

        st.dataframe(pd.DataFrame([{
            "Location": r["location"], "Posture": r["posture"], "Panels": r["panels"],
            "Mean power, 10 days (W)": r["planned_10_days"]["mean_power_w"],
            "Lowest charge (%)": r["planned_10_days"]["min_soc_pct"],
            "Load off (h)": r["planned_10_days"]["load_off_hours"],
            "Mean power, first 12.75 h (W)": r["actual_12_75_h"]["mean_power_w"],
        } for r in energy["rows"]]), width="stretch", hide_index=True)
