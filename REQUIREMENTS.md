# Requirements checklist

Challenge: NASA Space Apps 2026, "Lunar Landing Site Navigator".
Source of the items: the Objectives and Potential Considerations of the official
challenge page, as pasted by the project owner on 2026-11-15 (the page itself
could not be opened from the development machine because of a certificate
error). Official page: https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/

Status values: **done**, **partial**, **no**. "Where" names the tab of the app or
the file.

## Objectives

| # | Objective | Status | Where in the app / what is missing |
| --- | --- | --- | --- |
| O1a | Curated list of notable landing sites: past Apollo missions | done | Sidebar "Landing site": Apollo 11, 12, 14, 15, 16, 17 (NSSDC coordinates). |
| O1b | ... future CLPS mission targets | partial | Flown CLPS missions (IM-1, IM-2, Blue Ghost 1) and the planned IM-2 target are listed. Targets of CLPS missions that have not flown are missing: no official coordinates were found for them. |
| O1c | ... targets of other commercial lunar missions | partial | Intuitive Machines and Firefly landers are listed; no other commercial targets with official coordinates were found. |
| O1d | ... landing sites from other countries' lunar programs | done | Chandrayaan-3, SLIM, Chang'e 3-6, Luna 9-24 (see "Sites" in the README). |
| O1e | Custom lunar coordinates | done | Sidebar, "Custom coordinates". |
| O1f | Side-by-side or sequential comparison of multiple sites to assess trade-offs | done | Compare tab: 2 to 4 site + date scenarios, table, time bands, map. |
| O2a | Select landing dates and times | done | Sidebar: landing date and time (UTC), analysis period. |
| O2b | Explore how conditions change across different lunar days or seasons | done | Launch slip tab: 12-month heat map for any year 1950-2048; Sky slider over the period. |
| O2c | Show how schedule adjustments affect feasibility | done | Launch slip tab; Research tab, figure 3 (landing 7 and 14 days later). |
| O3a | Positions of the Sun and Earth relative to the horizon at a selected site and date | done | Sky tab: panorama with the horizon (terrain south of 80 S), paths, markers; Plate view; Site tab: 3D view with a sky dome. All follow the sidebar scenario. |
| O3b | Time remaining before sunset or Earthset | done | Sky tab: two large cards, updated with the time slider. |
| O4a | Key metrics: solar elevation angle | done | Sky tab: first large card "Sun elevation now"; data table. |
| O4b | Key metrics: duration of sunlight | done | Sky tab: longest stretches; Compare table; Launch slip. |
| O4c | Key metrics: Earth visibility windows | done | Sky tab (two definitions of "visible", sidebar switch), Compare bands, radio-link section. |
| O4d | Quick assessment of whether a site-date combination is viable | done | Verdict against 6-6.5 days (Sky, Compare, Launch slip, the cell card of the Site tab), plain-language summary, energy and link-margin sections. A period shorter than 6 days gives "N/A: period shorter than requirement" instead of a false "short". |
| O5 | Multiple visualization approaches: 2D maps, 3D surface visualizations, or other creative representations | done | 2D: map of the sites (Compare) and the horizon panorama (Sky). 3D: Site tab for each of the 19 sites south of 80 S (shadows, landing ellipse, sky dome, lander, colour by illumination / elevation / slope). Creative: the ink-drawing "Plate" view (Sky). |
| O6 | Temporal dynamics: animations or timeline views over a lunar day or several days | done | Sky time slider with paths; Compare time bands; Site tab animation with a sun / communication time strip; Plate animation of the selected site and period with the computed tracks. |
| O7 | Accessibility across skill levels: mission planners, educators, general public | partial | Planners: numbers, tables, CSV, assumptions on every chart. Public: plain-language summary and "How to read this page". Not tested with real users. |

## Potential Considerations

| # | Consideration | Status | Where in the app / what is missing |
| --- | --- | --- | --- |
| C1 | Ephemeris data from JPL Horizons or pre-computed datasets | done | JPL DE421 through skyfield, cached per site and year; checked against JPL Horizons (Validation tab: maximum difference 0.0002 degrees). |
| C2 | LOLA topography for realistic surface visualizations and accurate horizon calculations | partial | Horizon masks from LOLA (10 m and 40 m) for all 19 preset sites south of 80 S, at heights 0, 1, 2, 5 and 10 m, used by every tab (Sky, Plate, Compare, Launch slip, Site). Missing: sites at other latitudes use the smooth sphere (said in the sidebar); IM-1 has partial terrain (41 % of ray samples outside the grid); hand-entered polar points need the elevation data on the machine. |
| C3 | No atmosphere: no refraction; horizon set by local terrain and the edge of the lunar sphere | done | No refraction anywhere; smooth-sphere horizon with the dip of the observer height, or the terrain mask. |
| C4 | Solar elevation angle as a key power metric, displayed prominently | done | Sky tab, first large card. |
| C5 | Prioritize rapid comparison of multiple site-date combinations | done | Compare tab; cached series make every change instant. |
| C6 | Clearly communicate time remaining before sunset or Earthset | done | Sky tab, large cards. |
| C7 | Make the extreme differences between lunar and terrestrial conditions apparent | done | Sky tab: "How to read this page, and why the Moon is not like Earth", with numbers for the selected site. |
| C8 | Help users understand why small location or date changes have large impacts on feasibility | done | Research tab: crater against plateau, crest against plateau, landing-date shift. |
| C9 | Account for actual lunar topography | partial | Same limit as C2: terrain for the polar presets only. |
| C10 | Account for Earth libration and the Moon's orbital variations | done | Included in the ephemeris: the Earth's sway is visible in the Sky panorama, the changing distance enters the link margin. |
| C11 | Represent steep slopes and deep craters that create extreme shadow conditions | partial | Terrain masks and the 3D shadows show them at 10 m scale; the Site tab has a slope colour mode and a landing ellipse with the share of area that gets 6 days of light. The 20 m crater of Athena is below the resolution of the data and is a labelled model (Research tab). |
| C12 | Support coordination between science and engineering teams | partial | One shared scenario (site, date, period, panel height, antenna height, definitions) drives every tab; CSV and JSON exports. No saved or shareable scenarios. |
| C13 | Help teams respond quickly to schedule changes or hardware-driven date/location adjustments | done | Launch slip; Research figures 2 and 3; panel type, battery, load and antenna inputs in the Sky tab. |
| C14 | Serve as an educational tool on why lunar mission planning is complex | partial | Research case study, reading guide, Plate. No lesson mode or guided tour. |

## Summary

Objectives: 15 done, 3 partial, 0 no. Considerations: 9 done, 5 partial, 0 no.
The partial items share three causes: terrain is used for the 19 polar presets
only (other latitudes use the smooth sphere, and nothing finer than 10 m is
resolved), official coordinates are missing for future mission targets, and the
tool has not been tested with users.
