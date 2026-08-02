# Appendix — Full Data Sources

Companion to `DATA_REQUIREMENTS.md`. Same three levels (Free / Ask / Paid), every source with access, latency/resolution. **Bold = recommended pick** used in the main doc; rows below it are alternatives or substitutes with a note.

---

# LEVEL 1 — FREE

## A. Terrain & susceptibility base
*Feeds: susceptibility (WHERE). Static, download once.*

### Elevation (DEM)
Recommended: Copernicus 30m or ISRO CartoDEM. Slope/aspect/curvature are derived from this in QGIS — not separate downloads.

| Source | Access | Cost | Res |
|--------|--------|------|-----|
| **Copernicus DEM** | copernicus.eu | Free | 30m global |
| **ISRO CartoDEM / Bhuvan** | bhuvan.nrsc.gov.in | Free | 30m |
| SRTM | usgs.gov | Free | 90m |
| OpenTopography | opentopography.org | Free | 1–30m (spotty in India) |
| GEBCO | gebco.net | Free | 15 arc-sec |
| Planet / Airbus | planet.com, airbus.com | Paid | 0.8–3m → see L3 |

### Rock & soil type
Recommended: SoilGrids (global, instant) + GSI geology. NBSS for India soil detail.

| Source | Access | Cost | Format |
|--------|--------|------|--------|
| **SoilGrids (ISRIC)** | soilgrids.org | Free | Raster |
| **GSI geological maps** | bhukosh.gsi.gov.in | Free | Vector |
| NBSS soil database | nbsslup.in | Free | Vector |
| FAO-UNESCO soil | fao.org | Free | Raster |
| CGMW / OpenGeology | cgmw.org | Free | Vector, coarse |

### Land cover
| Source | Access | Cost | Res |
|--------|--------|------|-----|
| **ESA WorldCover** | esa-worldcover.org | Free | 10m |
| NRSC LULC | nrsc.gov.in | Free | 56m |
| MODIS LULC | lpdaac.usgs.gov | Free | 500m |

### Supporting static (derive or skip for demo)
Soil depth, permeability, infiltration — estimates included in SoilGrids. Slope-stability params (friction, cohesion) — from published Himalayan geotech literature (ResearchGate) unless field-tested (L3). Mining/excavation history — IBM (ibm.gov.in), or satellite change detection.

---

## B. Landslide trigger (live)
*Feeds: prediction (WHEN). Applied on top of the susceptibility base.*

### Live rainfall — main trigger
Recommended: GPM IMERG. Satellite rainfall outperforms gauges for landslides in India (HESS 2021). **Bias-correct above 2500m against IMD.**

| Source | Access | Cost | Latency |
|--------|--------|------|---------|
| **GPM IMERG** | GES DISC / Earthdata | Free | 30-min, ~4h |
| IMD gridded / stations | mausam.imd.gov.in, imdpune.gov.in | Free / ask | Hourly → ground records are L2 |
| Copernicus / ERA5 precip | cds.climate.copernicus.eu | Free | Daily / monthly lag |
| NOAA | noaa.gov, api.weather.gov | Free | Real-time |
| OpenWeatherMap | openweathermap.org | Free tier | 10-min |
| Weather Underground | wunderground.com | Free tier | 15–30 min |
| MERRA-2 | nasa.org | Free | ~1 wk lag |

### Rain forecast (7-day)
| Source | Access | Cost | Note |
|--------|--------|------|------|
| **ECMWF IFS** | copernicus.eu | Free | 6-hourly |
| **NOAA GFS** | nomads.ncep.noaa.gov | Free | 6-hourly |
| IMD forecast | mausam.imd.gov.in | Free | 7-day |

### Soil moisture — how wet already
Weakest free substitute (proxy for pore pressure). 9km is coarse; piezometers (L3) are the real fix.

| Source | Access | Cost | Latency |
|--------|--------|------|---------|
| **NASA SMAP L4** | nsidc.org/data/smap | Free | 9km, 3-hourly |
| ESA CCI SM | esa-soilmoisture-cci.org | Free | 1–2 wk |
| GLDAS | disc.gsfc.nasa.gov | Free | 5–30 day lag |
| ISMN | ismn.eco2s.org | Free | Variable |

### Ground movement & seismic
| Source | Access | Cost | Latency |
|--------|--------|------|---------|
| **Sentinel-1 InSAR** (slow creep) | dataspace.copernicus.eu | Free | 12-day, mm-scale |
| NASA ARIA (processed InSAR) | aria.jpl.nasa.gov | Free | 1–3 day |
| **USGS earthquakes** | earthquake.usgs.gov | Free | Real-time (GeoJSON) |
| India NCS | seismo.gov.in (real-time: riseq.seismo.gov.in) | Free | Real-time |
| IRIS / EarthScope | service.iris.edu | Free | Real-time |

*Weather secondary vars (temp, pressure, humidity, wind, radiation, ET) — all free from ERA5-Land / MERRA-2 / GLEAM. Used for refinement, not core triggering.*

---

## C. Flood
*Feeds: flood prediction. Consume-not-build **at this level** — the build starts at Level 2.*

### River forecast — the product
*Flood Hub is the primary; **GloFAS is the independent fallback** (Copernicus, no access gate) — worth running live, since Flood Hub's API is waitlisted and single-vendor dependency is a fair question from a government client.*

| Source | Access | Cost | Note |
|--------|--------|------|------|
| **Google Flood Hub** | g.co/floodhub (API: developers.google.com/flood-forecasting, waitlisted) | Free | ML, 7-day, 150+ countries, larger rivers |
| **GloFAS** | Copernicus EMS | Free | 30-day discharge |
| USGS WaterWatch | waterwatch.usgs.gov | Free | US only — method reference |
| Global Flood Monitor | globalfloodmonitor.org | Free | Real-time, but social-media-based — low reliability, cross-check only |

### Flood-zone mapping & labels
| Source | Access | Cost | Note |
|--------|--------|------|------|
| **Sentinel-1 SAR** | dataspace.copernicus.eu | Free | Maps past flood extent = training labels |
| **HydroSHEDS** | hydrosheds.org | Free | Rivers, catchments, HAND base |
| Global Flood Database | global-flood-database.cloudtostreet.info | Free | Historical extents |
| Reservoir levels | indiawris.gov.in | Free / ask | Dam storage/overflow |

### Glacial lakes (GLOF)
| Source | Access | Cost | Note |
|--------|--------|------|------|
| **Sentinel-2** | dataspace.copernicus.eu | Free | Lake growth detection |
| ICIMOD GLOF / glacial-lake data | lib.icimod.org, SERVIR-HKH | Free | Himalayan lake inventory (exact download portal varies) |

---

## D. Training labels
*Feeds: susceptibility + prediction models.*

### Landslide inventory (free tier)
Free version is sparse/km-level — demo-grade. Precise GSI inventory is the top L2 ask.

| Source | Access | Cost | Note |
|--------|--------|------|------|
| **NASA Global Landslide Catalog / COOLR** | landslides.nasa.gov/viewer | Free | Global, coarse location |
| Sentinel-2 scar tracing | dataspace.copernicus.eu | Free | Manual, fills gaps |
| News/media archives | — | Free | Date/location cross-check |

*Flood labels covered in section C (Sentinel-1 + Global Flood Database).*

---

## E. Impact & exposure
*Feeds: "who/what is at risk" overlay. All free.*

| Data | Source | Access | Note |
|------|--------|--------|------|
| **Population** | WorldPop, Census of India | worldpop.org, censusindia.gov.in | Raster + demographics |
| **Buildings** | OpenStreetMap | openstreetmap.org | Check local coverage; trace from Sentinel-2 if thin |
| **Roads** | OpenStreetMap | openstreetmap.org | State PWD for official → L2 |
| **Facilities** (hospital/school) | OSM POI | openstreetmap.org | District directory for official → L2 |
| **Village boundaries** | Census of India | censusindia.gov.in | Vector |
| **Mobile coverage** | OpenSignal, operator maps | opensignal.com | Flags alert-delivery gaps |

---

## F. Also available — optional, marginal for v1
Kept from full research list. None needed for the demo; most improve reporting, not prediction. Pull only if a specific need appears.

| Data | Source | Replaces / adds |
|------|--------|-----------------|
| Hazard maps (ready-made) | GSI, NDMA (gsi.gov.in, ndma.gov.in) | Cross-check for your own susceptibility output |
| Historical flood/landslide records | CWC, NDMA, UNESCO | Extra validation events beyond NASA GLC |
| Return-period / frequency | CWC studies, or derive (Gumbel) | Flood severity context |
| Vegetation / NDVI | Sentinel-2 (GEE), MODIS | Minor susceptibility feature; root depth from ORNL |
| Forest cover / deforestation | Global Forest Watch, FSI | Land-cover change signal |
| Erosion status | GSI erosion maps, change detection | Minor feature |
| Climate projections | IPCC, Copernicus CMIP6, IMD | Long-term planning, not live prediction |
| Monsoon / ENSO | IMD, NOAA CPC | Seasonal context |
| Admin boundaries | GADM, Census | Reporting/aggregation |
| Protected areas / wetlands | Protected Planet, Ramsar | Constraint layers |
| Permafrost | NSIDC | High-altitude niche |

*Excluded — not applicable: sea level, tides, storm surge, coastal (landlocked).*

---

# LEVEL 2 — + ASK
*Free, but a department must release it. **Landslide:** sharper precision, same product. **Flood:** new capability — small rivers, depth & extent, dam releases. This is the operational flood build.*


### Improves landslide prediction
| Data | Ask who | Upgrades |
|------|---------|----------|
|  **Landslide inventory** (precise, dense) | GSI | Labels: demo → operational — **biggest single gain** |
|  **Lineament & thrust/fault maps** | GSI | Tectonic structure — ranks ~21% of predictive weight, a top-3 factor; free geology alone misses it |
| Ground rainfall records | IMD | Corrects satellite altitude bias >2500m |
| Detailed geology + borehole / geotech logs | GSI, PWD, hydropower project surveys | Real soil depth & shear strength vs modelled estimates |
| Groundwater levels | CGWB | Better wet-season trigger |
| Road-cut & active construction zones | BRO, NHIDCL, State PWD | Anthropogenic trigger — ~⅓ of Himalayan slides cluster within 200–400m of roads |
| Forest loss / land-use change | State Forest dept | Slope destabilisation signal |

### Improves flood prediction
*Where flood shifts from consuming Flood Hub to running your own model: gauge series train a rain → discharge model (LSTM, or a conceptual rainfall-runoff model where records are short) on basins Flood Hub doesn't reach; cross-sections drive the hydraulic routing that turns discharge into depth & extent. Flood Hub remains the large-river backbone and cross-check.*

| Data | Ask who | Upgrades |
|------|---------|----------|
|  **River gauge** (level & flow) | _Client dept_ , CWC | Small-river prediction — **highest-value remaining ask**; public coverage patchy post-2020 |
|  **River cross-section / bathymetry** | CWC, State Water Resources | Inundation **depth & extent** — the main missing input for flood-depth modelling |
|  **Dam / reservoir operation & release schedule** | Hydropower operators (NHPC, etc.), CWC | Controlled releases drive downstream flash floods — critical in dam-heavy Arunachal |
| Embankments & hydraulic structures | Water Resources / flood-control dept | Corrects flow routing |
| Historical flood levels / high-water marks | CWC, SDMA | Model calibration & validation |

### Improves impact & response
| Data | Ask who | Upgrades |
|------|---------|----------|
| Utility lines (power/water) | State electricity board, PHED | Lifeline exposure |
| Vulnerable households | Census, district health office | Targeted impact |
| Evacuation routes, shelters, contacts | DDMA | Actionable output (delivery feature, not a model input) |
| Official event & damage records | SDMA / DDMA / NDMA | Validation events beyond NASA GLC |
| Large-scale toposheets (contours, drainage) | Survey of India | Sharper terrain where 30m DEM is coarse |

---

# LEVEL 3 — + PAID
*Optional. Buys only what free data cannot: hours-ahead warning on a specific named slope, faster flood refresh, and sharper terrain/rainfall.*

Grouped by what each improves; **⭐ = the thing free data genuinely cannot do**. Instrument set (extensometer, crackmeter, piezometer, GB-InSAR) per [operational slope early-warning practice](https://pmc.ncbi.nlm.nih.gov/articles/PMC7699353/); X-band radar nowcasting per [flash-flood radar studies](https://www.researchgate.net/publication/222709338_Performance_evaluation_of_high-resolution_rainfall_estimation_by_X-band_dual-polarization_radar_for_flash_flood_applications_in_mountainous_basins).

### Improves landslide prediction
*What it does:* moves the warning from area-and-day ("high risk in these villages this week") to **slope-and-hour** ("this specific slope is accelerating — likely failure in hours to a few days"). *Expect:* real imminent-failure alerts on the **5–10 instrumented slopes only** — not the district; a well-monitored slope often gives hours to 1–2 days notice as creep accelerates before collapse. Does **not** raise the susceptibility-map AUC or help flood.

| Data | Vendor | Adds |
|------|--------|------|
| ⭐ **Pore-pressure / geotech probes** (piezometer, tiltmeter, extensometer, crackmeter) | Encardio Rite, geotech suppliers | Hours-ahead failure warning on one slope — the pore-pressure trigger satellites can't see |
| ⭐ **GB-InSAR / ground radar** | IDS GeoRadar, MetaSensing | Sub-mm, continuous real-time deformation on a critical slope (vs 12-day satellite) |
| Commercial satellite InSAR service | TRE Altamira, Gamma | Processed mm-creep time-series over the area, no in-house processing |
| Drone / LiDAR survey | Local UAV operators | cm-accurate bare-earth terrain on priority slopes vs 30m free |
| High-res optical imagery | Maxar (30cm), Planet (daily) | Sharper, more frequent slope imagery for scar mapping |

### Improves flood prediction
*What it does:* adds **short-fuse flash-flood timing** and **faster, cloud-proof flood-extent** that the free 7-day river forecast can't give on small mountain catchments. *Expect:* X-band radar nowcasting yields roughly **~1 hour lead at ~65–68% detection** in small basins; on-demand satellite radar refreshes inundation extent about **every 6 hours, day or night, through cloud**. Best return where the free forecast is weakest — small, fast, ungauged streams.

| Data | Vendor | Adds |
|------|--------|------|
| ⭐ **X-band rainfall radar** | Local install / EEC, Vaisala | High-res rainfall nowcast (QPE/QPF) for flash floods; note beam-blockage in deep valleys |
| **On-demand flood radar (satellite)** | ICEYE, Capella | Flood extent every ~6h, day/night, cloud-piercing |
| Hyperlocal weather + SLA | Meteomatics, Tomorrow.io | ~90m rainfall, guaranteed uptime |
| High-res floodplain LiDAR | Local UAV / survey firms | Bare-earth terrain → accurate inundation depth |

### Sharper base / ground truth (both)
*What it does:* provides local calibration reference. *Expect:* a **marginal** accuracy gain, not a new capability — its main value is bias-correcting IMERG rainfall above 2500m and validating model output, not driving predictions itself.

| Data | Vendor | Adds |
|------|--------|------|
| Own rain gauge / weather station | Davis, Ambient | Local ground truth — low priority, satellite already strong; useful for IMERG bias-correction |
| Automatic weather station network | Campbell Scientific | Multi-variable ground reference on instrumented slopes |

### Sensor plumbing (only once L3 sensors are deployed)
IoT transport + management — not needed until hardware exists.

| Item | Source |
|------|--------|
| LoRaWAN gateway / nodes | Seeed, TTGO, DFRobot |
| GSM/GPRS kits | SIM7600, EC25 |
| IoT platform (ingest, logs, health, deployment map) | ThingSpeak, Azure IoT, AWS IoT |
| Sensor calibration | Accredited labs |

---

*Concepts, accuracy, and product framing: see `DATA_REQUIREMENTS.md`.*
