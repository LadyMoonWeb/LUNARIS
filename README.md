# LUNARIS — Lunar Landing Site Navigator

A tool for the NASA Space Apps 2026 challenge "Lunar Landing Site Navigator".
Pick a place on the Moon and a date, and it shows where the Sun and the Earth
stand against the local horizon, how long there is light for power and line of
sight for radio, and whether that is enough for a 6 to 6.5 day surface mission.

It is built around one worked example: the IM-2 "Athena" landing of March 2025
on Mons Mouton, which ended after 12.75 hours with empty batteries.

## What it does

| Tab | What you get |
| --- | --- |
| **Sky** | Sun elevation now, time to sunset and Earthset, a 360 degree panorama of the horizon with the paths of the Sun and the Earth and a time slider. A second view, "Plate", draws the same horizon and paths as an ink plate. Below: longest stretches of light and contact, an energy model (panel type, battery, load, charge curve) and a radio-link margin. |
| **Compare** | 2 to 4 "site + date" scenarios side by side: verdict table, time bands, map of the sites. |
| **Launch slip** | A 12-month heat map: for each landing date, the longest stretch of sunlight and communication together. |
| **Site** | A 3D view of the terrain around the selected site: shadows over the selected period, a clickable cell card, a landing ellipse with the share of safe area, a sky dome with the Sun's path and a ray to the Earth, a lander model, a time strip, elevation and slope colouring. |
| **Research** | The Athena case study: question, method, verification, result, with three figures. |
| **Validation** | The checks listed below, with numbers and plots. |

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501 on the IM-2 Athena site with its real
terrain horizon. It runs without the large elevation files: the horizon masks,
the 3D patches and the analysis results are stored in `data/` as small files.

One scenario drives every tab: site, landing date and time, analysis period
(14 days by default), **panel height** and **antenna height**. The Sun is
judged with the horizon seen from the panel height, the Earth with the horizon
seen from the antenna height. A caption always says which horizon is in use
(LOLA terrain or smooth sphere). If the period is shorter than the 6-day
requirement the verdict is "N/A: period shorter than requirement".

## Deploying to Streamlit Community Cloud

1. Put the project in a GitHub repository. `.gitignore` keeps the large
   downloads (`data/dem/`, `data/reference/`) and the local cache out of it;
   everything the app needs is in the repository and no file is larger than
   100 MB (the largest is the ephemeris `de421.bsp`, about 17 MB).
2. On https://share.streamlit.io choose "New app", select the repository and
   the branch, and set the main file to `app.py`.
3. Under "Advanced settings" pick Python 3.13. The app installs
   `requirements.txt` (runtime only; `requirements-dev.txt` is for rebuilding
   data and running the validation).
4. Deploy. The dark theme comes from `.streamlit/config.toml`. The first view
   of a site takes about a second while its one-year series is computed.

On the cloud there is no elevation data, so hand-entered coordinates south of
80 S fall back to the smooth sphere, and the app says so. The Site tab and the
Plate load fonts and the Three.js library from public CDNs.

## NASA data used

| Data | Used for | Source |
| --- | --- | --- |
| JPL DE421 ephemeris and lunar orientation kernels | Positions of the Sun and the Earth in the `MOON_ME_DE421` frame (through skyfield) | NASA NAIF |
| JPL Horizons | Reference for checking the positions | https://ssd.jpl.nasa.gov/horizons/ |
| LOLA elevation models, 10 m and 40 m (PGDA product 90) | Horizon masks, 3D terrain | Barker et al. 2023, https://pgda.gsfc.nasa.gov/products/90 |
| LOLA / LROC shape-from-shading model, 5 m (PGDA product 104) | Comparison with the 10 m terrain; Artemis III region centres | Bertone et al., Zenodo doi:10.5281/zenodo.17954508 |
| Average illumination and Earth visibility maps (PGDA product 69) | Reference for checking the terrain result | Mazarico et al. 2011 |
| LROC WAC percentage-based illumination map | Second reference near the pole | Speyerer and Robinson 2013 |
| Landing-site coordinates | Site list | NSSDC, LROC, NASA releases, ISRO, JAXA (each site carries its source in `lunarnav/sites.py`) |

Full file list, sizes and citations: `data/SOURCES.md`.

## How it is calculated

- Apparent altitude and azimuth of the Sun and the Earth from DE421, azimuth from north through east. No atmosphere, so no refraction.
- **Sunlit** = the centre of the solar disk is above the horizon in use.
- **Earth visible** has two definitions, both computed: the centre of the disk above the horizon (strict, default) or any part of the disk (sidebar switch).
- **Horizon**: on the smooth sphere it is level, lowered by the dip of the observer height. With terrain it is a mask of 720 angles (every 0.5 degrees), each the highest ground along a 150 km ray, with the curvature of the Moon: `atan2(r1 cos(theta) - r0, r1 sin(theta))`, `r0 = R + site height + observer height`, `r1 = R + h`, `theta = d / R`.
- **Power**: `P = S A eta max(0, n.s) V`, with `V` the visible fraction of the 0.53 degree solar disk; a battery with a load, a depth-of-discharge limit and a tapering charge curve.
- **Radio link**: free-space loss to a 34 m Deep Space Network antenna and the resulting margin, plus a flag when the Earth is less than 6 degrees above the horizon.

```python
from lunarnav import compute, summary
from lunarnav.terrain import load_mask

mask = load_mask("im2", observer_height_m=2)          # IM-2 Athena landing site
table = compute(-84.7906, 29.1957, "2025-03-06 17:30", "2025-03-16 17:30", 30,
                observer_height_m=2, horizon_mask=mask)
summary(table)["longest_both_days"]
```

## Checks

| Check | Result |
| --- | --- |
| Positions against JPL Horizons, 5 sites x 300 random instants x 2 bodies | maximum difference 0.000196 degrees, mean 0.000007 (tolerance 0.01) |
| Horizon masks recomputed by an independent verifier with its own code | agreement better than 0.001 degrees (the first run found a rounding bug of up to 0.36 degrees, since fixed) |
| Sunlit share over 18.6 years at the Athena point against the PGDA map | 44.4 % against 46.8 % (45.0 % with the observer at 2 m) |
| Same at three summit check points near the pole | observer at 2 m: 81 to 85 % against 83 to 88 % (PGDA); on the ground: 44 to 54 % against 47 to 48 % (LROC WAC) |
| Earth visibility against the PGDA Earth map | centre of the disk: 5 to 15 points lower; any part of the disk: within 0.2 points |
| 5 m shape-from-shading terrain against the LOLA terrain in use | heights differ by 0.7 m (standard deviation); the Athena mask changes by at most 0.005 degrees |
| Unit tests | `python -m pytest tests` |

```bash
python validation/horizons_check.py        # queries JPL Horizons, a few minutes
python validation/illumination_check.py    # needs the data from scripts/fetch_terrain.py
```

## Assumptions and limits

- **Terrain exists for the 19 preset sites south of 80 S** (masks of 720 directions at heights 0, 1, 2, 5 and 10 m in `data/masks/`), and every tab uses it. Sites away from the poles use the smooth sphere, where the Sun and the Earth stand high. Hand-entered points south of 80 S get a mask on the fly when the elevation data is on the machine, otherwise the smooth sphere with a warning. IM-1 lies at the edge of the elevation grid: 41 % of its ray samples fall outside it, and the app marks its terrain as partial.
- **Two kinds of numbers in the Site tab.** The time strip and the status of the site come from the 720-direction masks. Shadows, the card of a clicked cell, the landing ellipse and the ray to the Earth come from per-cell horizons (36 directions, terrain out to 30 km, eye 2 m above the ground) and are a visualisation.
- **The 10 m terrain does not show small craters or boulders.** Athena rests in a crater about 20 m across (LROC). Its depth is not published, so the Research tab uses a **model**: a parabolic bowl without a rim, 2 m and 4 m deep. The 5 m shape-from-shading tile for this region ends 12 km short of the site.
- **The energy model is generic.** Official: 200 W on the surface, a tall hexagonal cylinder on six legs (NSSDC), about 10 days of planned surface operations (NASA press kit). Assumed: where the panels are (not published), efficiency 0.28, battery 700 Wh, load 100 W, load shed at 80 % depth of discharge. These are inputs in the app.
- **The radio link is geometry and free-space loss only.** Antenna gain, power, data rate and noise temperature are generic. **Reflections from the terrain (multipath) are not modelled**, nor antenna pointing or ground-station schedules; a flag marks when the Earth is below 6 degrees.
- "Communication" means line of sight to the Earth, not to a particular ground station.
- The 3D Site tab uses the 10 m LOLA terrain (40 m for IM-1); the lander in it is a generic hexagonal body drawn 30 times larger than life.
- The "Plate" drawing follows the selected site and period: its horizon is the terrain mask at the panel height and its tracks are the computed paths. The Sun's disk is drawn larger than its true size. Without a terrain mask the Plate and the Site tab show a message and name the nearest site that has terrain.
- Coverage: years 1900 to 2050 (DE421).

## Sites

Every preset carries the source of its coordinates in `lunarnav/sites.py`; only
official sources are used.

| Sites | Source |
| --- | --- |
| Apollo 11-17 | NSSDC, "Apollo Landing Site Coordinates" (positions from LRO images) |
| Surveyor 1, 3, 5, 6, 7 | NSSDC Master Catalog (positions from LRO images) |
| Luna 9, 13, 16, 17, 20, 21, 24 | NSSDC, "Soviet Lunar Missions" |
| IM-1, IM-2 (landed and planned), Blue Ghost 1, Chang'e 3-6 | NASA and LROC |
| SLIM, Chandrayaan-3 | JAXA / ISAS briefing; ISRO (planned prime site) |
| 13 Artemis III candidate regions of 2022 (centres) | README of the PGDA product 104 archive (NASA GSFC authors) |

Gap: of the nine Artemis III regions named in 2024, NASA publishes no
coordinates; four of them (Peak near Cabeus B, Mons Mouton Plateau, Mons Mouton,
Slater Plain) have no counterpart in the 2022 list and are not offered.

## Rebuilding the data

```bash
python scripts/fetch_terrain.py            # LOLA terrain and reference maps, about 1 GB, prints sizes first
python scripts/fetch_near_windows.py       # 10 m windows for every site south of 80 S, about 20 MB each
python scripts/fetch_sfs.py                # 5 m shape-from-shading tile, 46 MB
python scripts/build_masks.py              # data/masks/: 720-direction masks, 19 sites x 5 heights
python scripts/export_athena_panorama.py   # data/athena_panorama.json (mask and Sun / Earth paths)
python scripts/build_site3d.py             # data/site3d/: terrain patch and cell horizons per site
python scripts/athena_crater.py            # the analyses behind the Research tab
python scripts/athena_energy.py
python scripts/equipment_height.py
python scripts/landing_shift.py
python scripts/compare_sfs.py
```

## Project layout

```
app.py          Streamlit entry point
ui/             one module per tab, theme, shared widgets
lunarnav/       calculations: ephemeris, compute(), metrics, terrain masks, crater model, energy, radio link, sites
validation/     checks against JPL Horizons and published illumination maps
scripts/        data download, mask building, exports, analyses
data/           horizon masks, analysis results, exports; large downloads are not in the repository
assets/         panorama background, the "Plate" drawing, the 3D page
tests/          unit tests
REQUIREMENTS.md checklist against the official challenge text
LOG.md          work log
```

## AI assistance

The code in this repository was written with the help of Claude Code
(Anthropic). The calculations were checked against JPL Horizons and against
published NASA illumination maps, as described under "Checks"; one check was
run by a separate verifier agent that did not write the code under test.

## Credits

Barker et al. (2023), Planetary Science Journal 4, 183. Mazarico et al. (2011),
Icarus 211, 1066. Speyerer and Robinson (2013), Icarus 222, 122. Bertone et al.
(2025), Zenodo 10.5281/zenodo.17954508. Site coordinates: NSSDC, LROC, NASA,
ISRO, JAXA.

This project is not affiliated with or endorsed by NASA.
