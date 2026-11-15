"""Landing sites with the source of every coordinate.

Rule: coordinates come only from official sources (space agencies, the NASA
NSSDC archive, the NASA Lunar Reconnaissance Orbiter Camera team). Each site
records where its numbers were read. Latitude is north-positive, longitude is
east-positive in the range -180..180 degrees (Mean Earth / Polar Axis frame).

``kind`` tells what the coordinates describe:
    "measured" - position of the vehicle located in orbital images or surveyed
    "reported" - position listed by an official archive without a statement
                 that it was measured in orbital images
    "planned"  - published target / prime landing site
    "region"   - reference point of a candidate landing region
    "check"    - validation check point (not a landing site), used to compare
                 the terrain calculation with published illumination maps
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Site:
    key: str
    name: str
    group: str
    lat: float  # degrees, north positive
    lon: float  # degrees, east positive (-180..180)
    kind: str
    source: str
    source_url: str
    note: str = ""


def _east(lon_0_360: float) -> float:
    """Convert a 0..360 east longitude to -180..180."""
    return ((lon_0_360 + 180.0) % 360.0) - 180.0


_NSSDC_APOLLO = (
    "NASA NSSDC, 'Apollo Landing Site Coordinates' (Lunar Module positions from LRO images, "
    "Mean Earth / Polar Axis frame, DE421; Wagner et al., Icarus 283, 2017)"
)
_NSSDC_APOLLO_URL = "https://nssdc.gsfc.nasa.gov/planetary/lunar/lunar_sites.html"

SITES: List[Site] = [
    # ----------------------------------------------------------------- Apollo
    Site("apollo11", "Apollo 11", "Apollo", 0.67416, 23.47314, "measured", _NSSDC_APOLLO, _NSSDC_APOLLO_URL),
    Site("apollo12", "Apollo 12", "Apollo", -3.0128, -23.4219, "measured", _NSSDC_APOLLO, _NSSDC_APOLLO_URL),
    Site("apollo14", "Apollo 14", "Apollo", -3.64589, -17.47194, "measured", _NSSDC_APOLLO, _NSSDC_APOLLO_URL),
    Site("apollo15", "Apollo 15", "Apollo", 26.13239, 3.63330, "measured", _NSSDC_APOLLO, _NSSDC_APOLLO_URL),
    Site("apollo16", "Apollo 16", "Apollo", -8.9734, 15.5011, "measured", _NSSDC_APOLLO, _NSSDC_APOLLO_URL),
    Site("apollo17", "Apollo 17", "Apollo", 20.1911, 30.7723, "measured", _NSSDC_APOLLO, _NSSDC_APOLLO_URL),
    # ------------------------------------------------------ Commercial (CLPS)
    Site(
        "im1", "IM-1 Odysseus", "Commercial landers", -80.13, 1.44, "measured",
        "NASA, 'NASA's LRO Images Intuitive Machine's Odysseus Lander' (26 Feb 2024): "
        "80.13 degrees south latitude, 1.44 degrees east longitude, elevation 2,579 m",
        "https://www.nasa.gov/?p=620655",
    ),
    Site(
        "im2", "IM-2 Athena", "Commercial landers", -84.7906, 29.1957, "measured",
        "LROC (NASA Lunar Reconnaissance Orbiter Camera), 'IM-2 Athena Seen Obliquely' (10 Mar 2025): "
        "84.7906 S, 29.1957 E",
        "https://lroc.im-ldi.com/images/1408",
        note="Mons Mouton. The planned site was 84.78 S, 29.13 E (LROC, 'IM-2 Landing Region').",
    ),
    Site(
        "im2_planned", "IM-2 planned landing point", "Commercial landers", -84.78, 29.13, "planned",
        "LROC (NASA Lunar Reconnaissance Orbiter Camera), 'IM-2 Landing Region' (26 Feb 2025): "
        "the Intuitive Machines IM-2 intended landing site (-84.78, 29.13 E)",
        "https://lroc.im-ldi.com/images/1401",
        note="Target published before landing. NASA and Intuitive Machines name Mons Mouton but print no "
             "coordinates. The measured Athena position lies about 0.4 km from this point.",
    ),
    Site(
        "blueghost1", "Blue Ghost Mission 1", "Commercial landers", 18.5623, 61.8103, "measured",
        "LROC (NASA Lunar Reconnaissance Orbiter Camera), 'Blue Ghost Lunar Lander Seen From Above' "
        "(7 Mar 2025): 18.5623 N, 61.8103 E, -3650 m elevation. NASA NSSDC gives the same point as "
        "18.562 N, 61.810 E",
        "https://lroc.im-ldi.com/images/1407",
        note="Mare Crisium, near Mons Latreille.",
    ),
    # ---------------------------------------------------------- Other agencies
    Site(
        "chandrayaan3", "Chandrayaan-3", "Agency landers", -69.367621, 32.348126, "planned",
        "ISRO, 'Chandrayaan-3 Details', row 'Landing Site (Prime)': 4 km x 2.4 km, 69.367621 S, 32.348126 E",
        "https://www.isro.gov.in/Chandrayaan3_Details.html",
        note="Prime landing site published by ISRO (a 4 km x 2.4 km area), not a surveyed touchdown point.",
    ),
    Site(
        "change3", "Chang'e 3", "Agency landers", 44.1214, _east(340.4884), "measured",
        "LROC (NASA Lunar Reconnaissance Orbiter Camera), 'Chang'e 3 Lander and Rover From Above' "
        "(30 Dec 2013): 44.1214 N, 340.4884 E, -2640 m elevation",
        "https://lroc.im-ldi.com/images/637",
    ),
    Site(
        "change4", "Chang'e 4", "Agency landers", -45.4561, 177.5885, "measured",
        "LROC (NASA Lunar Reconnaissance Orbiter Camera), 'Topographic Map of the Chang'e 4 Site' "
        "(30 Apr 2019): 45.4561 S, 177.5885 E, -5927 m elevation",
        "https://lroc.im-ldi.com/images/1100",
        note="Far side (Von Karman crater): the Earth never rises here.",
    ),
    Site(
        "change5", "Chang'e 5", "Agency landers", 43.0576, _east(308.0839), "measured",
        "LROC (NASA Lunar Reconnaissance Orbiter Camera), 'First Look: Chang'e 5' (4 Dec 2020): "
        "43.0576 N, 308.0839 E, -2570 m elevation",
        "https://lroc.im-ldi.com/images/1172",
    ),
    Site(
        "change6", "Chang'e 6", "Agency landers", -41.6385, _east(206.0148), "measured",
        "LROC (NASA Lunar Reconnaissance Orbiter Camera), 'First Look: Chang'e 6' (14 Jun 2024): "
        "41.6385 S, 206.0148 E, -5256 m elevation, accuracy about 30 m",
        "https://lroc.im-ldi.com/images/1374",
        note="Far side (Apollo basin): the Earth never rises here.",
    ),
    Site(
        "slim", "SLIM", "Agency landers", -13.3160, 25.2510, "measured",
        "JAXA / ISAS, 'SLIM Project review press briefing' (26 Dec 2024), slide 5: landing site estimated "
        "by the NASA LRO team, 13.3160 S, 25.2510 E (ME coordinates)",
        "https://www.isas.jaxa.jp/en/topics/files/SLIM-press-briefing-20241226.pdf",
        note="Near Shioli crater.",
    ),
    # ------------------------------------------------ Validation check points
    # Not landing sites. Each is the centre of the brightest pixel of the PGDA
    # average-illumination map (product 69, AVGVISIB_85S_060M_201608, 60 m) inside
    # the footprint of a PGDA product 78 site tile. All lie south of 88 S, where
    # the LROC WAC illumination map is also available.
    Site(
        "check_connecting_ridge", "Check point: Connecting ridge", "Validation check points",
        -89.47485, _east(222.55686), "check",
        "PGDA product 69 (Mazarico et al. 2011), AVGVISIB_85S_060M_201608: brightest pixel (88.4 %) inside the "
        "footprint of PGDA product 78 Site01 'Connecting ridge'; map x, y = -10770, -11730 m",
        "https://pgda.gsfc.nasa.gov/products/69",
        note="Validation check point, not a landing site.",
    ),
    Site(
        "check_shackleton_rim", "Check point: Shackleton rim", "Validation check points",
        -89.68643, _east(197.06286), "check",
        "PGDA product 69 (Mazarico et al. 2011), AVGVISIB_85S_060M_201608: brightest pixel (87.1 %) inside the "
        "footprint of PGDA product 78 Site04 'Shackleton rim'; map x, y = -2790, -9090 m",
        "https://pgda.gsfc.nasa.gov/products/69",
        note="Validation check point, not a landing site.",
    ),
    Site(
        "check_de_gerlache_rim", "Check point: de Gerlache rim", "Validation check points",
        -88.66463, _east(291.60436), "check",
        "PGDA product 69 (Mazarico et al. 2011), AVGVISIB_85S_060M_201608: brightest pixel (82.7 %) inside the "
        "footprint of PGDA product 78 Site11 'de Gerlache rim'; map x, y = -37650, 14910 m",
        "https://pgda.gsfc.nasa.gov/products/69",
        note="Validation check point, not a landing site.",
    ),
]

# ----------------------------------------------------------------- Surveyor
# NASA NSSDC Master Catalog, spacecraft pages: positions "as determined from
# Lunar Reconnaissance Orbiter images". Printed as (latitude, longitude).
_SURVEYOR = [
    ("surveyor1", "Surveyor 1", -2.4745, 316.6602, "2.4745 S, 316.6602 E", "1966-045A"),
    ("surveyor3", "Surveyor 3", -3.0162, 336.582, "3.0162 S, 336.582 E", "1967-035A"),
    ("surveyor5", "Surveyor 5", 1.4551, 23.1943, "1.4551 N, 23.1943 E", "1967-084A"),
    ("surveyor6", "Surveyor 6", 0.4742, 358.5725, "0.4742 N, 358.5725 E", "1967-112A"),
    ("surveyor7", "Surveyor 7", -40.9812, -11.5127, "40.9812 S, 11.5127 W", "1968-001A"),
]
SITES += [
    Site(key, name, "Surveyor", lat, _east(lon), "measured",
         f"NASA NSSDC Master Catalog, {name} ({catalog}): {printed} (as determined from Lunar Reconnaissance "
         "Orbiter images)",
         f"https://nssdc.gsfc.nasa.gov/nmc/spacecraft/display.action?id={catalog}")
    for key, name, lat, lon, printed, catalog in _SURVEYOR
]

# --------------------------------------------------------------------- Luna
# NASA NSSDC, "Soviet Lunar Missions". The page does not say that these
# positions were measured in LRO images, so they are marked "reported".
_LUNA = [
    ("luna9", "Luna 9", 7.08, 295.63, "7.08 N, 295.63 E", "Oceanus Procellarum"),
    ("luna13", "Luna 13", 18.87, 297.95, "18.87 N, 297.95 E", "Oceanus Procellarum"),
    ("luna16", "Luna 16", -0.68, 56.30, "0.68 S, 56.30 E", "Mare Fecunditatis"),
    ("luna17", "Luna 17 (Lunokhod 1)", 38.28, 325.00, "38.28 N, 325.00 E", "Mare Imbrium"),
    ("luna20", "Luna 20", 3.57, 56.50, "3.57 N, 56.50 E", "Mare Fecunditatis"),
    ("luna21", "Luna 21 (Lunokhod 2)", 25.85, 30.45, "25.85 N, 30.45 E", "Le Monnier crater"),
    ("luna24", "Luna 24", 12.75, 62.20, "12.75 N, 62.20 E", "Mare Crisium"),
]
SITES += [
    Site(key, name, "Luna", lat, _east(lon), "reported",
         f"NASA NSSDC, 'Soviet Lunar Missions': Latitude / Longitude {printed} - {place}",
         "https://nssdc.gsfc.nasa.gov/planetary/lunar/lunarussr.html",
         note="Position as listed by NSSDC; not stated to be measured in LRO images.")
    for key, name, lat, lon, printed, place in _LUNA
]

# ------------------------------------------- Artemis III candidate regions (2022)
# Centres of the 13 candidate landing regions announced in August 2022, as printed
# in the README of the PGDA product 104 archive (Bertone et al., NASA GSFC; Zenodo
# doi:10.5281/zenodo.17954508): "central longitude/latitude, computed as the
# midpoint of the feature bounding box". A region is about 15 km across, so the
# centre is a reference point, not a landing site.
_ARTEMIS_2022 = [
    ("artemis_amundsen_rim", "Amundsen Rim", 69.303844, -84.225586),
    ("artemis_nobile_rim_2", "Nobile Rim 2", 58.743523, -83.953082),
    ("artemis_haworth", "Haworth", -23.671814, -86.752966),
    ("artemis_faustini_rim_a", "Faustini Rim A", 90.000000, -87.863451),
    ("artemis_de_gerlache_rim_2", "de Gerlache Rim 2", -63.434949, -88.222637),
    ("artemis_connecting_ridge_ext", "Connecting Ridge Extension", -104.473348, -88.993919),
    ("artemis_connecting_ridge", "Connecting Ridge", -136.678946, -89.462697),
    ("artemis_nobile_rim_1", "Nobile Rim 1", 37.444641, -85.437750),
    ("artemis_peak_near_shackleton", "Peak Near Shackleton", 124.684171, -88.808537),
    ("artemis_de_gerlache_rim", "de Gerlache Rim", -66.370065, -88.674855),
    ("artemis_leibnitz_beta", "Leibnitz Beta Plateau", 31.827284, -85.425819),
    ("artemis_malapert", "Malapert Massif", -0.255799, -85.979917),
    ("artemis_de_gerlache_kocher", "de Gerlache-Kocher Massif", -116.537066, -85.826913),
]
SITES += [
    Site(key, f"{name} (Artemis III region)", "Artemis III candidate regions (2022)", lat, lon, "region",
         f"README of the PGDA product 104 archive (Bertone et al. 2025, NASA GSFC, Zenodo 10.5281/zenodo.17954508): "
         f"{name}, centre lon {lon:.6f}, lat {lat:.6f} (midpoint of the region's bounding box)",
         "https://zenodo.org/records/17954508",
         note="Centre of a candidate region about 15 km across (2022 list), not a selected landing site.")
    for key, name, lon, lat in _ARTEMIS_2022
]

SITES_BY_KEY: Dict[str, Site] = {site.key: site for site in SITES}
GROUPS: List[str] = list(dict.fromkeys(site.group for site in SITES))

# Official Artemis III candidate regions (NASA release 24-136, 28 Oct 2024).
ARTEMIS_III_REGIONS_URL = "https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/"
ARTEMIS_III_REGIONS: List[str] = [
    "Peak near Cabeus B",
    "Haworth",
    "Malapert Massif",
    "Mons Mouton Plateau",
    "Mons Mouton",
    "Nobile Rim 1",
    "Nobile Rim 2",
    "de Gerlache Rim 2",
    "Slater Plain",
]

# Regions of the 2024 list for which no official numeric coordinates were found.
# NASA names the nine regions but publishes them only as a map. Five of them carry
# the name of a 2022 region, whose centre is in the site list above (the 2024
# outline may differ). The other four are shown in the interface as "not
# available" instead of being guessed; use "Custom coordinates" for them.
_NO_COORDINATES = (
    "NASA release 24-136 names this region but prints no coordinates; "
    "no official numeric source found yet."
)
_NAMED_IN_2022 = {name for _, name, _, _ in _ARTEMIS_2022}
PENDING: Dict[str, str] = {
    name: _NO_COORDINATES for name in ARTEMIS_III_REGIONS if name not in _NAMED_IN_2022
}


def get_site(key: str) -> Site:
    return SITES_BY_KEY[key]
