# Project log

One entry per stage: start and end time, what broke, where the owner's input was
needed. Times are local (UTC+06:00).

## Stage 1 - working foundation without terrain

- **Start:** 2026-11-14 about 13:00 (entry written afterwards; times taken from file timestamps, approximate)
- **End:** 2026-11-14 about 13:45
- **Result:** `lunarnav` calculation package, validation against JPL Horizons
  (3000 comparisons, maximum 0.000196 deg, mean 0.000007 deg, tolerance 0.01 deg),
  16 sites with sources, Streamlit app with five tabs.

**What broke**
- NSSDC Master Catalog pages returned server errors for 8 of 9 spacecraft, so
  the Chang'e coordinates were taken from LROC instead.
- The USGS data release with Artemis III region grids sits behind a bot check
  and could not be read. Eight of nine Artemis III regions have no official
  coordinates in the project.
- The Streamlit page hung in the "running" state after `.streamlit/config.toml`
  was edited while the server was running. A server restart fixed it.
- Stale Python bytecode: three edits to `ui/compare.py` within one second kept
  the same file size and timestamp, so the old `.pyc` was reused and the table
  showed the old column order. A later edit of the file fixed it.
- The validation plot had a label overlapping the axis; redrawn.

**Where the owner was needed**
- Nothing blocked the stage. Left for the owner to decide: what to do about the
  Artemis III regions without official coordinates.

## Stage 2 - terrain

- **Start:** 2026-11-14 17:55 (planning), plan approved 18:22
- **Paused:** 18:32, the assistant's usage limit was reached; resumed 18:33 on the owner's request
- **End:** 2026-11-14 19:15

**Result**
- `lunarnav/terrain.py`: horizon masks (720 azimuths, 150 km rays, curvature, observer height)
  from LOLA elevation data; masks stored in `data/horizon/` for 5 points and observer heights 0, 2 and 5 m.
- `compute()` and the Sky tab use the masks; Compare and Launch slip stay on the smooth sphere.
- Sites added: planned IM-2 point and 3 validation check points near the pole.
- Illumination check by the `verifier` agent (`validation/illumination_check.py`):
  IM-2 site 44.4 % against 46.8 % in the PGDA map; summit check points 81-85 % at 2 m against
  83-88 % (PGDA) and 44-54 % at 0 m against 47-48 % (LROC WAC).
- `data/athena_panorama.json`: mask and Sun / Earth paths for three windows.
- 17 tests pass; stage 1 results unchanged (Horizons comparison, documentation example).
- Downloads: 997 MB (limit 2 GB).

**What broke**
- **A real bug, found by the verifier:** terrain height was added to the lunar radius in single
  precision, which rounds to 0.125 m and shifted the horizon by up to 0.36 deg for terrain 10 m away.
  Fixed, a regression test added, masks rebuilt; they now match the verifier's independent computation
  to better than 0.001 deg.
- The PGDA server gives about 0.5 MB/s per connection and dropped the downloads once; the script now
  resumes and uses 4 connections. Pieces of the interrupted download (348 MB, `data/dem/*.part.seg*`)
  were left on disk because nothing is deleted without the owner's confirmation.
- The 5 m PGDA site tile does not reach the Athena site (7 km short); 10 m data is used instead.
- The LROC WAC illumination map covers only 88-90 S, so it cannot be compared at the Athena site.
- First estimate of the distance between the planned IM-2 point and Athena (1.6 km) was wrong; it is about 0.4 km.
- A stray copy of `WAC_POLE_ILL_PCT_SOUTH_README.TXT` appeared in the project root when the browser
  tried to open that file during planning; left in place.
- Masks for 0 m at sharp summits mostly measure the nearest 10 m of ground, so the 0 m and 2 m
  results there differ by 27-39 percentage points. Not a bug, but the 0 m masks are not like-for-like
  with the PGDA map.

**Where the owner was needed**
- Approval of the plan and of about 1.1 GB of downloads.
- Choice of the Athena export windows: actual, planned and a full lunar day.
- Choice of who runs the stage: main session plus the `verifier` subagent.
- A restart after the usage limit ("continue stage 2").

**Verifier result on the illumination check (recorded 2026-11-14 19:13)**
- Sun against the PGDA map (18.6 years): IM-2 Athena 44.4 % at 0 m and 45.0 % at 2 m against 46.8 %;
  planned IM-2 point 44.3 / 44.8 % against 46.5 %; Connecting ridge 46.5 / 84.9 % against 88.4 %;
  Shackleton rim 43.9 / 81.9 % against 87.1 %; de Gerlache rim 54.0 / 81.0 % against 82.7 %.
- Sun against the LROC WAC map (2010-2011, 0 m): 46.7 % against 48.2 %, 43.8 % against 48.2 %,
  53.8 % against 47.4 % at the three check points; the IM-2 points are outside that map.
- Earth against the PGDA Earth map (centre of the disk, 0 m): 4.6 to 14.7 points lower
  (IM-2 Athena 80.9 % against 93.1 %); with "any part of the disk" the difference is at most 0.2 points.
- Independent recomputation of the horizon: found the single-precision rounding error
  (up to 0.36 deg at 0 m); after the fix the stored masks agree to better than 0.001 deg.
- Not confirmed: the exact definition of "visible" used by the PGDA maps; the effect of the
  elevation-model version (map 2016, terrain 2023).

**After the stage, on the owner's instructions (2026-11-15)**
- Deleted, with the owner's confirmation: the four leftover download pieces
  `data/dem/LDEM_80S_40MPP_ADJ.TIF.part.seg*` (348 MB) and the stray
  `WAC_POLE_ILL_PCT_SOUTH_README.TXT` in the project root. Nothing else was removed.
- Both Earth-visibility definitions added: `earth_visible` (centre, default) and
  `earth_any_visible` (any part of the disk), a choice in the sidebar for all tabs, and both
  flags in `data/athena_panorama.json`. 18 unit tests pass.
- Postponed by the owner: README update for this change, the final test run and the browser
  check. The new sidebar choice was run headlessly only, not looked at in the browser.

**Left for the owner to decide**
- Whether Compare and Launch slip should also use the terrain masks.

## Stage 3 - crater, SFS terrain, energy, equipment height, date shift, requirements

- **Start:** 2026-11-15. Rules from the owner: nothing deleted or published, no browser
  (checks by numbers and tests), one line here after every item, strictly in order.

**Item 0 - Athena crater (MODEL).** Official sources give only the diameter: "20-meter diameter crater"
(LROC image post 1408). Depth, wall slope and the lander's position inside it are not printed anywhere
(LROC 1408 and 1409, NASA LRO article, NASA release 25-025). Model: parabolic bowl without a rim,
depth/diameter 0.1 and 0.2 (`lunarnav/crater.py`, `scripts/athena_crater.py`, `data/analysis/athena_crater.json`).
Days with the Sun's centre above the horizon in the planned 10-day window from touchdown:
plateau 10.0 at every height; crater 2 m deep: 0 on the floor, 6.1 at 0.8 m, 10.0 at 1.6 m and 4 m;
crater 4 m deep: 0 at 0, 0.8 and 1.6 m, 10.0 at 4 m. In the actual 12.75 h of the mission: 0 on the floor
and at 0.8 m in both craters. Broke: nothing. Owner needed: no. Lander size (4.0 m x 1.57 m) comes from an
NSSDC entry seen only through web search; the page itself returns an error.

**Item 1 - SFS terrain (PGDA product 104, Zenodo 10.5281/zenodo.17954508).** The Leibnitz Beta archive is
1.05 GB (under the 3 GB limit). Only the needed members were pulled out of the remote zip by range requests:
elevation, uncertainty, mask, readme = 46 MB (`scripts/fetch_sfs.py`, `data/dem/sfs_leibnitz_beta/`).
Result (`scripts/compare_sfs.py`, `data/analysis/sfs_comparison.json`): the 5 m tile covers map x 65-81 km,
y 110-126 km; Athena is at y 138 km, 12.0 km outside it, so **the crater cannot be seen in this grid**
(and at 5 m a 20 m crater would be 4 pixels). SFS minus LOLA 40 m over the tile: mean -0.02 m, std 0.74 m,
95 % within 1.5 m. Using the tile along the rays that cross it changes the Athena mask by at most 0.005 deg.
At the tile centre the mask from SFS differs from the mask from LOLA 40 m by 0.08 deg on average, 0.34 deg at most.
Broke: the crater unit test needed a wider tolerance (the 0.5 m grid rounds the rim by up to 0.5 deg).
Owner needed: no. Side finding: the Zenodo README prints centre coordinates of the 13 Artemis III regions of 2022.

**Item 2 - energy (MODEL).** `lunarnav/energy.py` (P = S A eta max(0, n.s) V, battery with load, depth-of-discharge
limit and tapering charge curve), `scripts/athena_energy.py`, `data/analysis/athena_energy.json` and `.png`,
5 new tests. Official: 200 W on the surface, hexagonal cylinder on 6 legs (NSSDC, IM-3 entry), 10 days of
surface operations (NASA press kit). **Panel placement is not published anywhere we could read**, so three
generic arrangements are modelled; efficiency 0.28, load 100 W and 80 % depth of discharge are generic; the
700 Wh battery and the 4.0 x 1.57 m size come from an NSSDC IM-1 entry seen only through web search.
Mean power over the planned 10 days: upright on the plateau, six vertical faces 199 W, horizontal panel 16 W,
tracking 200 W; on its side on the plateau 128 W (average over 12 fall directions); upright in a 2 m crater
153 W; on its side in a 2 m crater 78 W, and 0 W in the first 12.75 h; in a 4 m crater 58 W upright and 0 W
on its side. With 700 Wh and 100 W the load is shed 5.6 h after the Sun is lost.
Broke: the first version put all side panels at one height, which gave 0 W for an upright lander in the 4 m
crater; the panels are now split into four height bands. Owner needed: no.

**Item 3 - equipment height.** `scripts/equipment_height.py`, `data/analysis/equipment_height.json`. One year from
the Athena touchdown, 30-minute step, heights 0, 1, 2, 5, 10 m, panels and antenna separately.
"Nearest crest" = highest cell of the 10 m grid within 5 km of Athena: 716 m away, 36.7 m higher (-84.81409, 29.21445);
picked from the data, not a named site. Sun and Earth together: plateau 37.6 % (both at 0 m) to 39.0 % (both at 10 m),
longest gap 23.8 to 23.7 days; crest 35.0 % to 42.7 %, longest gap 25.1 to 21.3 days. On the crest the first metre of
antenna height matters most (Earth 71.9 % at 0 m, 80.1 % at 1 m). **No spread band:** the 100 PGDA terrain variants
exist only for the product 78 site tiles, and the nearest one ends 7 km short of Athena.
Broke: nothing. Owner needed: no.

**Item 4 - landing-date shift (MODEL).** `scripts/landing_shift.py`, `data/analysis/landing_shift.json` and `.png`
(three charge curves side by side). Same generic lander, upright on the plateau, 10-day window. Planned date
6 Mar 2025: 10.0 days of Sun, vertical faces 199 W, battery stays at 100 %. Seven days later: 6.1 days of Sun,
120 W on average, the load is shed 153 h after touchdown and stays off 87 h. Fourteen days later: no Sun in the
window, the load is shed after 5.7 h. A horizontal panel fails on every date (16 W at best).
Broke: nothing. Owner needed: no.

**Item 5 - REQUIREMENTS.md.** Written, but **not from the official text**: the official challenge page
(spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/) could not be read. Its TLS certificate
fails verification from this machine in Python and in curl (untrusted root); the check was not bypassed; the
page-fetching agent failed the same way; web search returns only the title; the browser was not used at the
owner's request. The file holds a provisional checklist built from the one-paragraph description on a secondary
page (8 items: 3 done, 5 partial) and empty tables for Objectives and Potential Considerations.
Broke: access to the official page. **Owner needed: yes** - paste the Objectives and Potential Considerations
text, or allow the page to be opened in the browser.

- **End of stage 3 work in this session:** 2026-11-15. 24 unit tests pass.

## Stage 4 - final stage (app, requirements, sites, 3D, radio link)

- **Start:** 2026-11-15. Rules from the owner: everything to the end without questions unless the decision is hers;
  the browser only once, at the very end; one line here after every item. The official Objectives and Potential
  Considerations were pasted by the owner. Order note: the single browser pass (item 8) is done after items 9-11,
  so that the new tabs are checked too and the browser is still opened only once.

**Item 1 - Research tab.** `ui/research.py` rewritten as the Athena case study (question, method, verification,
result) with three figures built from `data/analysis/*.json`: crater model against plateau (marked MODEL),
equipment height plateau against crest 0-10 m (the lines cross between 0 and 1 m), landing shifted by 7 and 14 days
with charge curves; assumptions are written on each chart. `scripts/landing_shift.py` now stores hourly charge curves.
Checked: figures build headlessly. Not yet looked at in the browser.

**Item 2 - energy in the Sky tab.** Panel type (six vertical faces / horizontal / Sun tracking), battery capacity
and load, power and charge curves over the selected period, four numbers (mean power, lowest charge, load-off hours,
state at the chosen moment). Generic-lander constants moved into `lunarnav/energy.py` so that app and scripts share them.
Checked: headless run for three sites, no exceptions. Broke: nothing.

**Item 3 - Plate.** `galileo-horizon.html` copied to `assets/` (the original in Downloads is untouched) and embedded
in the Sky tab as the second view "Plate"; the 720-value mask from `data/athena_panorama.json` is passed through
`setHorizonMask`. Broke: `st.components.v1.html` is announced for removal in this Streamlit version, so the page is
embedded with `st.iframe` (its successor) with a fallback to components. Note for the owner: the page's own texts are
in Russian and its Sun / Earth tracks are illustrative; the file was not edited.

**Item 4 - Validation.** Headline cards for the Athena point (44.4 % against 46.8 % in the PGDA map, 45.0 % at 2 m,
horizon check better than 0.001 deg) and a table with both Earth-visibility definitions against the PGDA Earth map
(centre: 4.6 to 14.7 points lower; any part: within 0.2 points).

**Item 5 - small fixes.** The stretch metrics no longer use `st.metric` (which cut "Communi..." and ">= 13..."):
labels and values are HTML cards that wrap; the open-ended mark is spelled out ("still running when the period ends").
Broke along the way: a duplicated download button made the Sky tab fail in the headless run; removed.

**Item 6 - REQUIREMENTS.md.** Rewritten from the official Objectives and Potential Considerations pasted by the
owner: 18 objective rows (15 done, 3 partial) and 14 consideration rows (9 done, 5 partial), each with the tab or file.
Quick gaps closed on the way: Sun elevation as the first large card (C4), plain-language summary and "why the Moon
is not like Earth" guide (O7, C7), a 2D map of the sites in Compare (O5). Rows that depend on items 9-11 (Luna sites,
3D tab, link margin) are written for the finished state and re-checked after those items.

**Item 7 - README.** Rewritten in English: what the tool does, NASA data, checks with numbers, assumptions and limits,
sites, rebuild commands, AI assistance.

**Item 9 - sites.** 44 presets now. Added: Surveyor 1, 3, 5, 6, 7 (NSSDC Master Catalog, positions from LRO images),
Luna 9, 13, 16, 17, 20, 21, 24 (NSSDC "Soviet Lunar Missions"; marked "reported" because the page does not say they
were measured in LRO images), 13 Artemis III regions of 2022 (centres from the README of the PGDA product 104 archive).
Chang'e 5 and 6 were already present. The old approximate Malapert entry (86 S, 0 E) was replaced by the README centre
under the same key. Broke: the NSSDC catalog pages for the Luna missions return errors and LROC site pages return 404,
so the Luna coordinates are the two-decimal values of the NSSDC overview page. Still without coordinates: four regions
of the 2024 list (Peak near Cabeus B, Mons Mouton Plateau, Mons Mouton, Slater Plain).

**Item 10 - 3D "Site" tab.** `scripts/build_site3d.py` -> `data/site3d_athena.json` (608 kB), `assets/site3d.html`
(Three.js r128 from cdnjs, ink-and-hatching shader, contours every 10 m, orbit, time slider, Play), `ui/site3d.py`.
3 x 3 km around Athena, marks: Athena, planned point on the plateau, crest; arrows to the Sun and the Earth.
Shadows are real: per-cell horizons in 36 directions out to 30 km, Sun positions hourly from `compute()` for one
lunar day; a cell is lit by the visible fraction of the solar disk. **Deviation from the request:** the terrain is
LOLA 10 m, not SFS: the 5 m SFS tile ends 12 km short of Athena (found in stage 3). Checked by numbers: the centre
cell horizon differs from the stored Athena mask by 0.02 deg on average, 0.38 deg at most. Broke: nothing yet;
the page itself can only be judged in the browser pass.

**Item 11 - radio link.** `lunarnav/link.py` (free-space loss, 34 m DSN dish gain, margin; `link_table()` with the
Earth's elevation above the local horizon and the "Earth below 6 deg" flag), 3 tests, a section in the Sky tab with
inputs for transmitter power, antenna gain and data rate. All hardware numbers are generic and labelled as such.
The interface and the README state that reflections from the terrain are not modelled. With the defaults (10 W,
6 dBi, 100 kbit/s, S-band) the margin is about 16 dB at 384 400 km and changes by about 1 dB with the distance.

**Item 8 - one browser pass (done last, after items 9-11).** All six tabs opened in the built-in browser with the
IM-2 Athena site: Sky (cards, panorama, Plate view with the real mask, stretch cards, energy, radio link), Compare
(table, bands, map of the sites), Launch slip, Site (3D view, time slider), Research (three figures), Validation.
No errors in the browser console. Fixed during the pass:
- Research figure 3: the legend overlapped the panel titles and the assumptions box ran off the right edge; the
  legend was raised and the box moved under the axes.
- Sky: the verdict chip was drawn in the large value font and overflowed its card.
- Site: the camera opened looking south although the caption said north is at the far edge; the mouse wheel was
  captured by the 3D view and blocked page scrolling. The camera now starts in the south-south-east; zoom is on
  the + / - buttons (or Ctrl + wheel).
Not checked in the browser: Play in the Site tab over a full lunar day, phone-width layout, the "any part"
Earth switch (run headlessly only).

- **End of stage 4:** 2026-11-15. 27 unit tests pass; headless app run without exceptions.

**Last edits (2026-11-15, after stage 4, no browser at the owner's request).**
`assets/galileo-horizon.html` replaced by the owner's new English version; besides the mask it now receives the
computed Sun and Earth tracks of the lunar-day window of `data/athena_panorama.json` through `setTracks` (1417 points
per body, `{t, az, alt}` with ISO times); the "tracks are illustrative" caption was removed, README and REQUIREMENTS
updated. Cyrillic search over the project (LOG.md excluded): the only hits were the comments and printed strings of
`lunar_drill.py`, now in English; none left. Checked: 27 tests, headless app run, the injected mask and tracks parsed
back from the page. Not checked: how the plate looks with the real tracks (no browser). Broke: a check script left
an empty file `data/_plate_check.js` by mistake; it is not used by anything and was not deleted (owner's rule).

**Where the owner was needed in stage 4:** the official challenge text (pasted). Decisions taken without asking,
for the owner to confirm or change: the 3D tab uses LOLA 10 m because SFS does not reach Athena; the browser pass
was moved after items 9-11; the Plate page is embedded unchanged, with its Russian captions.

## Final polish - one consistent scenario in every tab

- **Start:** 2026-11-15 about 18:20. Rules from the owner: work by priority, one browser pass at the very end, one
  log line per item, nothing deleted or published. The session was interrupted several times by the usage limit and
  resumed with "try again".

**Item 1 (P0) - Sky (Plate) and Site (3D) follow the sidebar.** Both now take the site, landing time, period and
heights of the sidebar. The Athena 2025 story is left only in the Research tab. A site without terrain shows a
message naming the nearest site with terrain; another site's terrain is never shown. Checked headlessly: Apollo 11
gives the message in both places, no exceptions.

**Item 2 (P0) - two heights.** Sidebar: "Panel height" and "Antenna height" (0, 1, 2, 5, 10 m, both 2 m by default).
`compute()`, `apply_visibility()` and `get_series()` take `antenna_height_m` and `antenna_horizon_mask`: the Sun is
judged with the panel height and its mask, the Earth with the antenna height and its mask, in every tab, the Plate
and the 3D time strip. The cached positions are now stored at height 0 (`CACHE_VERSION = 2`). No hidden 1 m or 2 m
in the app; the one fixed height left is the eye of the per-cell horizons of the 3D visualisation (2 m), named in
its caption. Test: `test_sun_at_panel_height_earth_at_antenna_height`.

**Item 3 (P0) - terrain everywhere.** `scripts/fetch_near_windows.py` cut eleven more 10 m windows (240 MB, named
before the download; all downloads together about 1.3 GB of the 2 GB budget). `scripts/build_masks.py` wrote 95 masks
to `data/masks/`: 19 preset sites south of 80 S x heights 0, 1, 2, 5, 10 m. Compare and Launch slip use them like Sky
and show which horizon each scenario used. Hand-entered points south of 80 S: mask computed on the fly and stored if
the elevation data is on the machine, otherwise "SMOOTH SPHERE" with an explicit note. Limit found: IM-1 (80.13 S) is
outside the 10 m mosaic and at the edge of the 40 m grid; 41 % of its ray samples have no data, and the sidebar says
"PARTIAL TERRAIN".

**Item 4 (P0) - period and N/A.** Default period 14 days. `verdict(days, period_days)` returns "N/A: period shorter
than requirement" when the period is under 6 days and the stretch is under 6 days; Sky, Compare and Launch slip show
it. Checked headlessly with a 3-day period.

**Item 5 (P0) - default site.** IM-2 Athena.

**Item 6 (P1) - Plate.** The owner's `plate-embed.html` arrived in the middle of the turn (the first message came
without the attachment) and was copied to `assets/` unchanged. It receives `setTitle(site name)`,
`setHorizonMask(720 values at the panel height)` and `setTracks(period paths)`. The "plate always shows Athena"
caption is gone. `assets/galileo-horizon.html` stays on disk, unused (nothing is deleted).

**Item 7 (P1) - collapsed sections.** "Coordinate source" and "How to read this page" are collapsed by default, as
are all other expanders.

**Item 8 (P2) - 3D Site tab.** `scripts/build_site3d.py` now writes one file per site, `data/site3d/<key>.json`
(19 files, 7 MB together): heights 151 x 151 at 20 m and per-cell horizons 76 x 76 at 40 m x 36 directions, rays to
30 km, eye 2 m. `assets/site3d.html` rewritten: (a) click a cell for a card with sun days, communication days, both
and the verdict for the sidebar period; (b) landing ellipse, radius 50 to 500 m, cells coloured by ">= 6 days of
sun", one number for the safe share; (c) sky dome with the Sun's path, the Sun and the Earth, and a ray to the Earth,
green when visible and red when blocked; (d) generic lander, upright or on its side, shaded panels hatched; (e) time
strip with sun and communication bars and a cursor tied to Play; (f) labels that avoid each other, legend, scale bar,
north arrow, vertical stretch x1 / x2 / x4, colour by illumination / elevation / slope. Honest limit, also in the
caption: the per-cell horizons are coarse. At the site centre they differ from the 720-direction mask by 0.07 to
1.6 degrees on average and up to 7 degrees in single directions on the roughest sites (Connecting Ridge Extension,
Nobile Rim 1), so the numbers of the card and the ellipse are a visualisation, not the verdict.

**Item 9 (P3) - running without `data/dem`.** `requirements.txt` now lists only what the app needs;
`requirements-dev.txt` adds rasterio, scipy, astroquery, matplotlib and pytest. Headless run with `data/dem`,
`data/reference` and the cache pointed at empty folders and those libraries blocked: all six tabs render for Athena,
Apollo 11, IM-1, Haworth, Shackleton rim and custom coordinates, no exceptions. Largest file that would go to a
repository: `de421.bsp`, 17 MB. `.streamlit/config.toml` has the dark theme. README has a section on deploying to
Streamlit Community Cloud. Nothing was deployed or published.

**Item 10 (P3) - documents and tests.** REQUIREMENTS.md (C2, C9, C11, C12, O3a, O4d, O5, O6), README, CLAUDE.md and
`data/SOURCES.md` updated. New tests: verdict N/A, the two heights, stored masks for every polar site.

**What broke**
- A stale `.pyc` once hid an edit made within the same second as the previous one; a later edit fixed it.
- In the headless walk a selectbox object kept from before a rerun made later selections silently ineffective; the
  script now re-reads the widget after every rerun.
- My first size estimate for the new windows (275 MB) was high; the files are 240 MB.
- One mask of the default custom point (89.5 S, 0 E, 2 m) was written to `data/masks/` by the headless check. It is
  correct and harmless, and was left in place.

**Where the owner was needed:** the `plate-embed.html` file. Decisions taken without asking, for the owner to
confirm or change: mask heights 0, 1, 2, 5, 10 m; the cell horizons of the 3D view use one eye height of 2 m; the
runtime and development requirements are split into two files.


**Browser pass and final verification (2026-11-15 22:40 - 23:21)**
- **What was checked:** All six tabs (`Sky`, `Compare`, `Launch slip`, `Site`, `Research`, `Validation`) in a live browser on `http://localhost:8501`, including `Plate (ink drawing)`, 3D controls (`Play`, `×1/×2/×4`, `illumination/elevation/slope`, `upright/on its side`, `Landing ellipse`, terrain cell click), and switching to a site without terrain (`Apollo 11`).
- **What broke and was fixed:**
  - With `pandas 3.1`, `DatetimeIndex` defaults to microsecond resolution (`datetime64[us]`), whereas `lunarnav/energy.py` (`simulate_battery` and `battery_summary`) divided `.asi8` / `.astype("int64")` differences by `3.6e12` assuming nanoseconds. Fixed by converting explicitly to `datetime64[ns]`; added regression test `test_battery_independent_of_time_resolution` in `tests/test_energy.py` (32 tests pass).
  - In `assets/site3d.html`, projected 3D labels could overlap the `#title`, `#card` and `#legend` boxes, the default centre point showed a duplicate `selected point` label over the site marker, `#title` could touch `#card` on narrow viewports, and the iframe had a vertical scrollbar. Fixed by seeding label collision avoidance with the three HUD boxes, setting `z-index`, suppressing the duplicate label within 30 m of the site centre, making `#title` / `#card` widths responsive, and adjusting stage/iframe heights in `assets/site3d.html`, `ui/site3d.py` (`height=860`) and `ui/sky.py` (`height=720`). Re-verified in the browser: no scrollbars, no clipping, no overlapping labels.
