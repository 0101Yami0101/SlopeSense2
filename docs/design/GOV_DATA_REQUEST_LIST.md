# Government Data Request List — SlopeSense / FloodSense AI

## 1. Landslide — core asks

| Target Department | Specific Dataset(s) Required | Format | Justification for SlopeSense AI |
|---|---|---|---|
| **GSI** (Geological Survey of India) | `Landslidedata_1` event table — date, time, lat/long, rainfall amount/duration/intensity, trigger, failure mechanism | CSV export | Required for the timing component of the Landslide Forecast — the part that determines *when*, not just where, a slope is at risk. Exact event date, time and on-site rainfall are essential to a reliable daily forecast. |
| **GSI** | Full statewide set of Post Disaster Study / Macro & Meso susceptibility reports, and the underlying GIS shapefiles behind them | PDF + GIS shapefile | Required to validate and refine the location-risk component of the Landslide Forecast against government-verified site investigations and hazard maps. |
| **IMD** | Ground rainfall station records, all AP stations, historical + ongoing | Digital time series (CSV) | Required to calibrate rainfall inputs to the Landslide Forecast, so accuracy is consistent across both high-altitude and low-lying terrain. |
| **State PWD** | Road-blockage/closure logs caused by landslides, all districts, all years | Register export / Excel | Required for the timing component of the Landslide Forecast — dated, located road-closure records are used to train and validate when slopes fail. |
| **BRO** (Border Roads Organisation) | Same road-block logs, all AP border corridors | Register export / Excel | Required for the same purpose, extending coverage to border-road corridors maintained independently of State PWD. |
| **Rural Development Dept / PMGSY cell** | Road-block/closure logs, rural link roads | Register export / Excel | Required for the same purpose, extending coverage to rural roads not maintained by State PWD or BRO. |
| **CGWB** (Central Ground Water Board) | Groundwater level records, statewide | CSV | Required as an input to the Landslide Forecast — groundwater saturation is a recognised precondition for slope failure. |
| **State Forest Dept** | Forest loss / land-use change data; protected-area boundaries | GIS raster/shapefile | Required as an input to the location-risk component of the Landslide Forecast, and to define protected-area boundaries for reporting. |
| **State Directorate of Geology & Mining** | Full mining lease / quarry / blast-schedule register | GIS/CSV | Required as an input to the Landslide Forecast — quarrying and blasting are a recognised trigger of slope failure. |
| **Indian Bureau of Mines (IBM)** | Mining/excavation history, AP-specific extract | CSV/register | Required for the same purpose, to ensure statewide mining activity is fully represented. |
| **NHIDCL / State PWD** | Official road alignment / road-cut & construction-zone data, statewide | GIS shapefile | Required as an input to the Landslide Forecast — road cuts are a recognised trigger of slope failure. |
| **India NCS (National Center for Seismology) / BIS** | Seismic microzonation studies for AP towns, if any exist | PDF/GIS | Required to extend the Landslide Forecast to cover earthquake-triggered slope failure, in addition to rainfall-triggered events. |

---

## 2. Flood — core asks

| Target Department | Specific Dataset(s) Required | Format | Justification for FloodSense AI |
|---|---|---|---|
| **CWC** (Central Water Commission) | River cross-section / bathymetry, all gauged rivers statewide | Survey data / CSV | Required for the Flood Forecast to convert river-level readings into an actual flood depth and extent map. |
| **CWC** | Danger/warning thresholds for every AP gauge station not yet published | CSV | Required to classify river gauge readings into flood risk levels for the Flood Forecast. |
| **CWC / India-WRIS** | Reservoir/dam storage and overflow levels, all AP reservoirs | CSV/digital records | Required as an input to the Flood Forecast, to account for reservoir storage upstream of forecast points. |
| **NHPC & other hydropower operators** | Dam/reservoir release schedules, all AP facilities | Digital records | Required as an input to the Flood Forecast, to account for controlled water releases on regulated rivers. |
| **NHPC & other hydropower operators** | On-site meteorological station data, all facilities | CSV | Required to improve the accuracy of rainfall inputs to the Flood Forecast in areas where satellite rainfall resolution is coarse. |
| **State Water Resources Dept** | Embankments & hydraulic structures inventory, statewide | GIS shapefile | Required for the Flood Forecast to model how water moves once a river exceeds its banks. |
| **State Water Resources Dept / NWIC** | Any discharge/level stations beyond those already public | CSV/API | Required to extend the Flood Forecast's river coverage to additional small and medium rivers. |
| **IMD** | Doppler weather radar coverage / short-fuse rainfall nowcast for NE India, if it exists or is planned | Digital feed | Required to give the Flood Forecast short-lead-time rainfall data for fast-responding catchments, where a multi-day forecast alone is not sufficient warning. |

---

## 3. Impact, response & cross-cutting

| Target Department | Specific Dataset(s) Required | Format | Justification |
|---|---|---|---|
| **SDMA / DDMA** (state + all districts) | Official landslide/flood event & damage records, all districts, all years | Digital register | Required to validate the accuracy of both the Landslide and Flood Forecasts against real recorded events. |
| **Revenue Dept** (Land Records & Disaster Relief) | Disaster-relief / compensation claim records, dated and located | Register/CSV | Required for the same purpose, using disaster relief and compensation records as an independent record of real events. |
| **Police / Fire & Emergency Services** | Incident and rescue call-out logs for landslide/flood events | Register/CSV | Required for the same purpose, using emergency response records as an independent record of real events. |
| **Agriculture Dept** | Flood crop-damage assessments, dated and located | Register/CSV | Required to validate the Flood Forecast against recorded agricultural damage. |
| **NDMA** (National Disaster Management Authority) | Ready-made hazard maps (cross-check); national disaster database extract for AP | GIS/PDF/CSV | Required as an independent reference to cross-check both the Landslide and Flood Forecast outputs. |
| **District Administration** (all districts) | Building/facility inventory | GIS/CSV | Required for the impact-assessment component of the system, to estimate the population and structures exposed to each hazard. |
| **Urban Development Dept / Urban Local Bodies** (Itanagar Municipal Corp, etc.) | Stormwater drainage network, urban flood pinch points | GIS shapefile | Required to extend the Flood Forecast to cover urban flooding caused by inadequate drainage — a hazard distinct from river flooding. |
| **State Electricity Dept / PHED** | Utility line locations (power, water), statewide | GIS shapefile | Required for the impact-assessment component of the system, to estimate infrastructure exposed to each hazard. |
| **Census Directorate / District Health Offices** | Vulnerable household data, statewide | CSV/register | Required for the impact-assessment component of the system, to identify at-risk populations. |
| **Survey of India** | Large-scale toposheets, statewide | Scanned/digital | Required to refine the terrain base underlying both the Landslide and Flood Forecasts. |

---

## 4. Remote sensing & GIS infrastructure

| Target Department | Specific Dataset(s) Required | Format | Justification |
|---|---|---|---|
| **APSAC/SRSAC** | NWIA glacial-lake/wetland maps, statewide — confirm bulk access | GIS shapefile | Required to extend the Flood Forecast to cover glacial lake outburst floods (GLOF) — a hazard distinct from rainfall-driven flooding. |
| **APSAC/SRSAC** | Full-resolution source imagery/DEM behind published land-cover layers | Raster | Required to improve the resolution of the land-cover and terrain inputs underlying both Forecasts. |
| **State GIS Cell / NIC (Arunachal unit)** | Full data catalogue for the state spatial data portal | Account + GIS export | Required to confirm whether additional statewide geospatial layers exist that would improve either Forecast. |
| **APSAC/SRSAC** | SISDP-U access (2.5 m Bhuvan Panchayat imagery), statewide | Account/WMS | Required to improve the resolution of the imagery underlying both Forecasts. |
| **APSAC** (or outside vendor, paid) | Detailed terrain (LiDAR), priority high-risk districts first | Point cloud | Required to build accurate flood-depth and landslide-runout maps in priority districts, beyond what satellite terrain data can support. |

---


