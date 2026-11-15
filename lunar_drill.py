"""Altitude and azimuth of the Earth from Aristarchus crater (the example from the
Skyfield documentation), compared with JPL Horizons through astroquery."""

from skyfield.api import PlanetaryConstants, load
from astroquery.jplhorizons import Horizons

LAT, LON = 26.3, -46.8          # Aristarchus: 26.3 deg N, 46.8 deg W
EXPECTED_ALT, EXPECTED_AZ = 32.453, 118.216   # values from the documentation

# --- Skyfield -------------------------------------------------------------
ts = load.timescale()
t = ts.utc(2019, 12, 20, 11, 5)

eph = load('de421.bsp')
earth, moon = eph['earth'], eph['moon']

pc = PlanetaryConstants()
pc.read_text(load('moon_080317.tf'))
pc.read_text(load('pck00008.tpc'))
pc.read_binary(load('moon_pa_de421_1900-2050.bpc'))

frame = pc.build_frame_named('MOON_ME_DE421')
aristarchus = moon + pc.build_latlon_degrees(frame, LAT, LON)

apparent = aristarchus.at(t).observe(earth).apparent()
alt, az, distance = apparent.altaz()

sf_alt, sf_az = alt.degrees, az.degrees
print('Skyfield (MOON_ME_DE421):')
print(f'  altitude  {alt}  = {sf_alt:.3f} deg  (documentation {EXPECTED_ALT} deg)')
print(f'  azimuth   {az}  = {sf_az:.3f} deg  (documentation {EXPECTED_AZ} deg)')

# --- JPL Horizons ---------------------------------------------------------
location = {'lon': LON, 'lat': LAT, 'elevation': 0, 'body': 301}  # 301 = Moon
obj = Horizons(id='399', location=location,
               epochs={'start': '2019-12-20 11:05', 'stop': '2019-12-20 11:06',
                       'step': '1m'})
row = obj.ephemerides(quantities='4')[0]
hz_alt, hz_az = float(row['EL']), float(row['AZ'])

print('JPL Horizons:')
print(f'  altitude  {hz_alt:.3f} deg')
print(f'  azimuth   {hz_az:.3f} deg')

print('Difference (Skyfield - Horizons):')
print(f'  altitude  {sf_alt - hz_alt:+.4f} deg  ({(sf_alt - hz_alt) * 3600:+.1f} arcsec)')
print(f'  azimuth   {sf_az - hz_az:+.4f} deg  ({(sf_az - hz_az) * 3600:+.1f} arcsec)')
