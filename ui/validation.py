"""Validation tab: results of the comparison with JPL Horizons."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from . import theme
from .common import stat_card

RESULTS = Path(__file__).resolve().parent.parent / "validation" / "results"
FLOOR = 1e-7  # Horizons prints 1e-6 deg; smaller differences are drawn at this floor


@st.cache_data(show_spinner=False)
def _load(modified: float):
    summary = json.loads((RESULTS / "horizons_summary.json").read_text(encoding="utf-8"))
    samples = pd.read_csv(RESULTS / "horizons_samples.csv")
    return summary, samples


def _figure(samples: pd.DataFrame, tolerance: float) -> go.Figure:
    sites = list(samples["site"].unique())
    rng = np.random.default_rng(0)
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.04,
                        subplot_titles=("Altitude", "Azimuth"))
    for col, column in enumerate(("d_alt_deg", "d_az_deg"), start=1):
        for body, name, colour, offset in (("sun", "Sun", theme.SUN, -0.17), ("earth", "Earth", theme.EARTH, 0.17)):
            chosen = samples[samples["body"] == body]
            y = chosen["site"].map(sites.index).values + offset + rng.uniform(-0.12, 0.12, len(chosen))
            fig.add_trace(go.Scatter(
                x=np.maximum(chosen[column].abs().values, FLOOR), y=y, mode="markers", name=name,
                legendgroup=name, showlegend=(col == 1), marker=dict(size=5, color=colour, opacity=0.6),
                customdata=np.stack([chosen["site"], chosen["time_utc"].str.slice(0, 16), chosen[column]], axis=1),
                hovertemplate=f"<b>{name}</b> at %{{customdata[0]}}<br>%{{customdata[1]}} UTC"
                              "<br>difference %{customdata[2]:.6f}°<extra></extra>",
            ), row=1, col=col)
        fig.add_vline(x=tolerance, line=dict(color=theme.INK, width=1.5), row=1, col=col)
        fig.add_annotation(x=np.log10(tolerance), y=1.0, xref=f"x{col if col > 1 else ''}", yref="paper",
                           yanchor="bottom", text=f"tolerance {tolerance:g}°", showarrow=False,
                           font=dict(color=theme.INK, size=12))
        fig.update_xaxes(theme.axis(type="log", range=[np.log10(FLOOR * 0.6), np.log10(0.05)], dtick=1,
                                    exponentformat="power", title_text="absolute difference, degrees (log scale)"),
                         row=1, col=col)
    fig.update_yaxes(theme.axis(tickvals=list(range(len(sites))), ticktext=sites, showgrid=False,
                                range=[len(sites) - 0.5, -0.5], tickfont=dict(color=theme.INK_SECONDARY, size=12)))
    fig.update_layout(**theme.base_layout(height=440, margin=dict(l=120, r=24, t=70, b=56)))
    for annotation in fig.layout.annotations[:2]:  # subplot titles
        annotation.update(x=annotation.x - 0.2, font=dict(color=theme.INK, size=14))
    return fig


def _illumination_figure(rows: list) -> go.Figure:
    """Reference map value against this project's value, one row per comparison."""
    labels, reference, ours, ours_2m, spans = [], [], [], [], []
    for row in rows:
        for ref_key, our_key, our_2m_key, lo_key, hi_key, tag in (
            ("pgda_pct", "ours_disc_pct_18y", "ours_disc_pct_18y_h2m", "pgda_min_3x3", "pgda_max_3x3", "PGDA, 18.6 yr"),
            ("lroc_pct", "ours_centre_pct_2010", "ours_centre_pct_2010_h2m", "lroc_min_3x3", "lroc_max_3x3",
             "LROC WAC, 2010"),
        ):
            if row.get(ref_key) is None or row.get(our_key) is None:
                continue
            labels.append(f"{row['name'].replace('Check point: ', '')} · {tag}")
            reference.append(row[ref_key])
            ours.append(row[our_key])
            ours_2m.append(row.get(our_2m_key))
            spans.append((row.get(lo_key), row.get(hi_key)))

    fig = go.Figure()
    for label, ref, mine, mine_2m, (lo, hi) in zip(labels, reference, ours, ours_2m, spans):
        if lo is not None and hi is not None:  # spread of the map in the neighbouring pixels
            fig.add_trace(go.Scatter(x=[lo, hi], y=[label, label], mode="lines", showlegend=False, hoverinfo="skip",
                                     line=dict(color=theme.AXIS, width=7)))
        ends = [v for v in (ref, mine, mine_2m) if v is not None]
        fig.add_trace(go.Scatter(x=[min(ends), max(ends)], y=[label, label], mode="lines", showlegend=False,
                                 hoverinfo="skip", line=dict(color=theme.MUTED, width=1.5)))
    ring = dict(color=theme.SURFACE, width=2)
    fig.add_trace(go.Scatter(x=reference, y=labels, mode="markers", name="Reference map",
                             marker=dict(size=12, color=theme.INK_SECONDARY, symbol="diamond", line=ring),
                             hovertemplate="%{y}<br>reference map %{x:.1f}%<extra></extra>"))
    fig.add_trace(go.Scatter(x=ours, y=labels, mode="markers", name="This project, observer on the ground (0 m)",
                             marker=dict(size=11, color=theme.EARTH, line=ring),
                             hovertemplate="%{y}<br>this project, 0 m: %{x:.1f}%<extra></extra>"))
    fig.add_trace(go.Scatter(x=ours_2m, y=labels, mode="markers", name="This project, observer at 2 m",
                             marker=dict(size=11, color=theme.BOTH, symbol="square", line=ring),
                             hovertemplate="%{y}<br>this project, 2 m: %{x:.1f}%<extra></extra>"))
    fig.update_layout(**theme.base_layout(
        height=150 + 36 * len(labels), margin=dict(l=250, r=24, t=84, b=52),
        legend=dict(orientation="h", yanchor="bottom", y=1.06, xanchor="left", x=-0.3,
                    font=dict(color=theme.INK_SECONDARY), bgcolor="rgba(0,0,0,0)"),
        xaxis=theme.axis(range=[0, 100], ticksuffix="%", title_text="Share of time the Sun is visible"),
        yaxis=theme.axis(autorange="reversed", showgrid=False, tickfont=dict(color=theme.INK_SECONDARY, size=12)),
    ))
    return fig


def render_illumination() -> None:
    """Stage 2: sunlit share with terrain masks against published illumination maps."""
    st.subheader("Terrain: illumination against published maps")
    path = RESULTS / "illumination_summary.json"
    if not path.exists():
        st.info("No illumination check yet. Run `python validation/illumination_check.py` from the project root.")
        return
    summary = json.loads(path.read_text(encoding="utf-8"))
    rows = summary.get("rows", [])
    st.caption(
        "Long-term share of time with the Sun visible, computed with the LOLA terrain horizon masks, compared "
        "with PGDA product 69 (Mazarico et al. 2011, 18.6 years) and with the LROC WAC percentage-based "
        f"illumination map (Speyerer and Robinson 2013, 88-90 S, one lunar year). Generated {summary.get('generated_utc', '')}."
    )
    athena = next((r for r in rows if r.get("key") == "im2"), None)
    if athena:
        cols = st.columns(4)
        cols[0].markdown(stat_card("IM-2 Athena site: sunlit share, this project",
                                   f"{athena['ours_disc_pct_18y']:.1f} %", "terrain mask, observer on the ground, 18.6 years"),
                         unsafe_allow_html=True)
        cols[1].markdown(stat_card("Same point in the PGDA map", f"{athena['pgda_pct']:.1f} %",
                                   "Mazarico et al. 2011, 120 m pixel"), unsafe_allow_html=True)
        cols[2].markdown(stat_card("Difference", f"{athena['diff_disc_vs_pgda_pp']:+.1f} points",
                                   f"{athena['ours_disc_pct_18y_h2m']:.1f} % with the observer at 2 m"),
                         unsafe_allow_html=True)
        cols[3].markdown(stat_card("Independent check of the horizon", "< 0.001°",
                                   "stored masks against the verifier's own computation"), unsafe_allow_html=True)
    if rows:
        st.plotly_chart(_illumination_figure(rows), width="stretch", theme=None, config=theme.PLOTLY_CONFIG,
                        key="illumination_plot")
        st.caption("The grey bar is the spread of the reference map in the neighbouring 3 x 3 pixels: "
                   "near sharp ridges the map itself changes strongly from pixel to pixel. The three check points "
                   "are sharp summits, where two metres of observer height change the result by 27 to 39 points; "
                   "at the IM-2 site the height matters by less than one point.")
        table = pd.DataFrame(rows).drop(columns=[c for c in ("key",) if c in pd.DataFrame(rows).columns])
        st.dataframe(table, width="stretch", hide_index=True)
    samples_path = RESULTS / "illumination_samples.csv"
    if samples_path.exists():
        samples = pd.read_csv(samples_path)
        earth = samples[(samples["reference"] == "pgda_earth") & (samples["observer_height_m"] == 0)]
        if len(earth):
            st.markdown("##### Earth visibility: both definitions against the PGDA Earth map")
            st.dataframe(pd.DataFrame({
                "Point": earth["name"].str.replace("Check point: ", ""),
                "PGDA Earth map (%)": earth["reference_pct"].round(1),
                "Centre of the disk above the horizon (%)": earth["ours_centre_pct"].round(1),
                "Difference, centre (points)": (earth["ours_centre_pct"] - earth["reference_pct"]).round(1),
                "Any part of the disk above the horizon (%)": earth["ours_any_pct"].round(1),
                "Difference, any part (points)": (earth["ours_any_pct"] - earth["reference_pct"]).round(1),
            }), width="stretch", hide_index=True)
            st.caption("Observer on the ground, 18.6 years, hourly. The strict definition (centre of the disk) is the "
                       "project default; the sidebar switches every tab to \"any part of the disk\". The definition "
                       "used by the published map could not be confirmed; \"any part\" is the one that matches it.")
    for note in summary.get("notes", []):
        st.markdown(f"- {note}")
    st.caption("Reproduce with `python validation/illumination_check.py`. There is no pass threshold: "
               "the differences are reported as they are.")


def render() -> None:
    render_illumination()
    st.divider()
    st.subheader("Validation against JPL Horizons")
    summary_path = RESULTS / "horizons_summary.json"
    if not summary_path.exists():
        st.warning("No validation results yet. Run `python validation/horizons_check.py` from the project root.")
        return

    summary, samples = _load(summary_path.stat().st_mtime)
    overall = summary["overall"]
    tolerance = summary["tolerance_deg"]

    colour, icon = theme.STATUS["meets" if summary["passed"] else "short"]
    state = "Passed: every sample is within the tolerance" if summary["passed"] else "Failed: tolerance exceeded"
    st.markdown(f'<span class="verdict-chip" style="border-color:{colour}"><span style="color:{colour}">{icon}</span> '
                f"{state}</span>", unsafe_allow_html=True)
    st.caption(f"{summary['ours']} compared with {summary['reference']}. Generated {summary['generated_utc']}.")

    cols = st.columns(4)
    cols[0].metric("Maximum difference", f"{overall['max_abs_deg']:.6f}°")
    cols[1].metric("Mean difference", f"{overall['mean_abs_deg']:.6f}°")
    cols[2].metric("Tolerance", f"{tolerance:g}°", help=f"Margin: {tolerance / overall['max_abs_deg']:.0f}×")
    cols[3].metric("Comparisons", f"{overall['samples']:,}",
                   help=f"{summary['sites']} sites × {summary['samples_per_site']} random instants × 2 bodies")

    st.plotly_chart(_figure(samples, tolerance), width="stretch", theme=None, config=theme.PLOTLY_CONFIG,
                    key="validation_plot")
    worst = summary["worst_sample"]
    st.caption(
        f"Each dot is one comparison. Random instants between {summary['time_range_utc'][0]} and "
        f"{summary['time_range_utc'][1]} (seed {summary['seed']}). Largest difference: {worst['body'].capitalize()} "
        f"at {worst['site']}, {worst['time_utc']} UTC (azimuth differences grow when a body is close to the zenith)."
    )

    rows = [{
        "Site": site,
        "Latitude": block["lat"],
        "Longitude": block["lon"],
        "Comparisons": block["samples"],
        "Max altitude diff (°)": f"{block['max_abs_alt_deg']:.6f}",
        "Max azimuth diff (°)": f"{block['max_abs_az_deg']:.6f}",
        "Mean diff (°)": f"{block['mean_abs_deg']:.6f}",
    } for site, block in summary["by_site"].items()]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.caption("Reproduce with `python validation/horizons_check.py`. Raw samples: "
               "`validation/results/horizons_samples.csv`.")
