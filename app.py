"""Lunar Landing Site Navigator - Streamlit entry point.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from ui import compare, launch_slip, research, site3d, sky, validation
from ui.common import CSS, sidebar

st.set_page_config(page_title="LUNARIS — Lunar Landing Site Navigator", page_icon="\U0001F319", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

st.title("LUNARIS — Lunar Landing Site Navigator")
st.caption("Sunlight and direct-to-Earth communication windows for lunar landing sites. "
           "Terrain horizon from LOLA elevation data where a mask is available; smooth sphere elsewhere.")

selection = sidebar()

tab_sky, tab_compare, tab_slip, tab_site, tab_research, tab_validation = st.tabs(
    ["Sky", "Compare", "Launch slip", "Site", "Research", "Validation"]
)
with tab_sky:
    sky.render(selection)
with tab_compare:
    compare.render(selection)
with tab_slip:
    launch_slip.render(selection)
with tab_site:
    site3d.render(selection)
with tab_research:
    research.render()
with tab_validation:
    validation.render()
