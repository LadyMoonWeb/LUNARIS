# Data sources

Everything in `data/dem/` and `data/reference/` is downloaded by
`python scripts/fetch_terrain.py`; exact byte sizes and URLs of the last run are
in `data/sources.json`. The 10 m windows of the Artemis III regions are cut by
`python scripts/fetch_near_windows.py`. The masks in `data/masks/` (and the
older `data/horizon/`), the 3D patches in `data/site3d/` and the exports are
computed by this project from these files; the app needs only those small
computed files, not the downloads.

## Elevation (LOLA)

| File | What | Size | Source |
| --- | --- | --- | --- |
| `dem/LDEM_80S_40MPP_ADJ.TIF` | Surface height, 40 m/pixel, 80-90 S (608 x 608 km) | 716 MB | PGDA product 90, https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_40MPP_ADJ.TIF |
| `dem/near_athena_10m.tif` | 10 m/pixel, 32 x 32 km around the IM-2 Athena site | 18 MB | window cut from PGDA product 90, `LDEM_83S_10MPP_ADJ.TIF` |
| `dem/near_connecting_ridge_10m.tif` | 10 m/pixel, 32 x 32 km around the check point | 23 MB | same |
| `dem/near_shackleton_rim_10m.tif` | 10 m/pixel, 32 x 32 km around the check point | 23 MB | same |
| `dem/near_de_gerlache_rim_10m.tif` | 10 m/pixel, 32 x 32 km around the check point | 23 MB | same |
| `dem/near_artemis_<region>_10m.tif`, 11 files | 10 m/pixel, 32 x 32 km around the centre of each Artemis III candidate region of 2022 south of 80 S that the windows above do not serve: Amundsen Rim, Connecting Ridge Extension, de Gerlache-Kocher Massif, de Gerlache Rim 2, Faustini Rim A, Haworth, Leibnitz Beta Plateau, Malapert Massif, Nobile Rim 1, Nobile Rim 2, Peak near Shackleton | 19 to 23 MB each, 240 MB together | same |

IM-1 Odysseus (80.13 S) lies outside the 10 m mosaic and at the edge of the
40 m grid: its masks use the 40 m grid for the near range too, and 41 % of the
ray samples (those north of 80 S) have no data.

Cite: Barker, M. K., Mazarico, E., Neumann, G. A., Smith, D. E., Zuber, M. T.,
Head, J. W. (2023). A New View of the Lunar South Pole from the Lunar Orbiter
Laser Altimeter (LOLA). Planetary Science Journal, 4, 183.
doi:10.3847/PSJ/acf3e1. Product page: https://pgda.gsfc.nasa.gov/products/90

Grids are south polar stereographic (true scale at the pole, sphere of
1737.4 km), MOON_ME frame of DE421, heights in metres above the sphere.

## Reference illumination maps (used only for validation)

| File | What | Size | Source |
| --- | --- | --- | --- |
| `reference/AVGVISIB_85S_060M_201608.TIF` | Average solar illumination, 60 m, 85-90 S | 34 MB | PGDA product 69 |
| `reference/AVGVISIB_75S_120M_201608.TIF` | Average solar illumination, 120 m, 75-90 S | 83 MB | PGDA product 69 |
| `reference/AVGVISIB_85S_060M_201608_EARTH.TIF` | Average Earth visibility, 60 m, 85-90 S | 25 MB | PGDA product 69 |
| `reference/AVGVISIB_75S_120M_201608_EARTH.TIF` | Average Earth visibility, 120 m, 75-90 S | 43 MB | PGDA product 69 |
| `reference/WAC_POLE_ILL_PCT_SOUTH_100M.IMG` | LROC WAC percentage-based illumination, 100 m, 88-90 S | 5.9 MB | LROC RDR `WAC_POLE_ILL_PCT_SOUTH` |
| `reference/WAC_POLE_ILL_PCT_SOUTH_100M.TIF` | Same map as 8-bit GeoTIFF | 1.5 MB | LROC RDR, browse folder |
| `reference/WAC_POLE_ILL_PCT_SOUTH_README.TXT` | Product description | 4 kB | LROC RDR |

PGDA product 69, https://pgda.gsfc.nasa.gov/products/69 : values are int16,
multiply by 0.00004 to get a fraction of time (0..1); averaged over hourly
steps spanning 18.6 years, Sun treated as a disk. Cite: Mazarico, E., Neumann,
G. A., Smith, D. E., Zuber, M. T., Torrence, M. H. (2011). Illumination
conditions of the lunar polar regions using LOLA topography. Icarus, 211,
1066-1081. doi:10.1016/j.icarus.2010.10.030

LROC WAC map, https://data.lroc.im-ldi.com/lroc/view_rdr/WAC_POLE_ILL_PCT_SOUTH :
percent of WAC images (15 Feb 2010 to 5 Feb 2011) in which a pixel was lit.
Cite: Speyerer, E. J., Robinson, M. S. (2013). Persistently illuminated regions
at the lunar poles: Ideal sites for future exploration. Icarus, 222, 122-136.
doi:10.1016/j.icarus.2012.10.010
