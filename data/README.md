# Data directory

Everything here is machine-fetched. Nothing is hand-edited. If a file is wrong,
fix the script in `scripts/fetch/` and re-run — do not patch the file in place.

## Layout

```
data/
  raw/          exactly as downloaded — never modified
  interim/      clipped, reprojected, merged (regenerable)
  processed/    analysis-ready model inputs (regenerable)
```

Only `raw/` is precious. `interim/` and `processed/` can be deleted and rebuilt.

### raw/ — numbered by role, not by source

| Folder | Holds | Feeds |
|--------|-------|-------|
| `01_boundaries` | State and district polygons, the AOI definition | Clipping everything else |
| `02_terrain` | Elevation | Susceptibility (slope, aspect, curvature derive from here) |
| `03_soil_geology` | Soil properties, geology | Susceptibility |
| `04_landcover` | Surface cover | Susceptibility |
| `05_hydrology` | Rivers, catchments | Flood |
| `06_weather` | Rain forecast, seasonal indices | Trigger (WHEN) |
| `07_seismic` | Earthquakes, station inventory | Trigger (WHEN) |
| `08_labels` | Observed landslide and flood events | Training and validation |
| `09_exposure` | Population, roads, buildings, facilities | Impact overlay |
| `10_context` | Optional and reference layers | Reporting, cross-checks |

Numbering keeps folders in pipeline order rather than alphabetical order, so the
listing reads as the flow of the project.

## File naming

```
<source>_<variable>_<resolution>_<area>[_<date>].<ext>
```

| Example | Reads as |
|---|---|
| `copernicus_dem_30m/...` | source-named tile directory, original tile names kept |
| `soilgrids_clay-0-5cm_250m_arunachal.tif` | SoilGrids clay, 0–5 cm depth, 250 m, AOI |
| `hydrosheds_rivers_vector_arunachal.gpkg` | HydroSHEDS rivers, vector, AOI |
| `usgs_earthquakes_point_arunachal_1900-2026.geojson` | USGS quakes, points, AOI, date range |
| `noaa-gfs_precip_0p25_arunachal_2026072606z_f168.grib2` | GFS precip, 0.25°, AOI, cycle, +168 h lead |
| `osm_roads_vector_arunachal-clipped.gpkg` | `-clipped` = trimmed to the state polygon |

Rules that matter:

- **Lowercase, hyphens inside a token, underscores between tokens.**
- **Vendor tile names are preserved unchanged** (Copernicus, WorldCover) so they
  can be matched against the source listing.
- **`-clipped` suffix** marks a layer trimmed to the state polygon. The AOI is a
  bounding box that overlaps Assam heavily — an unclipped exposure layer
  overstates coverage by roughly 10x. Always check which one you are using.

## Provenance

Every folder carries a `_SOURCES.json` recording, per source: the URL, the UTC
fetch time, licence, notes, and for each file its size and a hash of the first
16 MB. That file is the answer to "where did this come from and when".

## Reproducing

```bash
.venv/Scripts/python.exe scripts/fetch/fetch_01_boundaries.py   # run first — defines the AOI
.venv/Scripts/python.exe scripts/fetch/fetch_02_terrain.py
# ... 03 through 10
.venv/Scripts/python.exe scripts/inspect/inspect_all.py
.venv/Scripts/python.exe scripts/inspect/analyse_key_questions.py
.venv/Scripts/python.exe scripts/inspect/analyse_exposure.py
```

Fetch scripts skip files that already exist, so re-running is cheap and safe.
The AOI and all shared paths live in `scripts/common.py` — change the area in
one place and everything follows.

Reports land in `logs/`. Verification status lives in
`docs/data_research/DATA_VERIFICATION.md`.

## Size

~4.2 GB. The bulk is elevation (1.19 GB), exposure (824 MB) and land cover
(463 MB). Not in version control.
