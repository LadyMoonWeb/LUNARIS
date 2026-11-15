"""Colours and chart defaults shared by all tabs (dark theme)."""

from __future__ import annotations

# Chart chrome
SURFACE = "#1a1a19"
PAGE = "#0d0d0d"
INK = "#f0efec"
INK_SECONDARY = "#c3c2b7"
MUTED = "#898781"
GRID = "#2c2c2a"
AXIS = "#383835"

# One colour per entity, the same in every chart.
SUN = "#d95926"
EARTH = "#3987e5"
BOTH = "#199e70"

# Status colours: always shown together with an icon and a label.
STATUS = {
    "meets": ("#0ca30c", "✔"),
    "marginal": ("#fab219", "▲"),
    "short": ("#d03b3b", "✖"),
    "na": ("#898781", "—"),  # the period is shorter than the requirement: no verdict
}

# Sequential blue ramp for magnitude, dark (near zero) to light (large).
SEQUENTIAL = ["#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"]

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def base_layout(**overrides) -> dict:
    """Plotly layout shared by the charts."""
    layout = dict(
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK_SECONDARY, size=13),
        margin=dict(l=60, r=24, t=48, b=52),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(color=INK_SECONDARY), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#262624", bordercolor=AXIS, font=dict(family=FONT, color=INK, size=13)),
    )
    layout.update(overrides)
    return layout


def axis(**overrides) -> dict:
    """Recessive axis: hairline grid, muted tick labels."""
    style = dict(
        gridcolor=GRID,
        gridwidth=1,
        linecolor=AXIS,
        zeroline=False,
        tickfont=dict(color=MUTED, size=12),
        title_font=dict(color=MUTED, size=12),
    )
    style.update(overrides)
    return style


PLOTLY_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]}
