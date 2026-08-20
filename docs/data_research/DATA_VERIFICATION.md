# Data Verification Tracker

Companion to `Base.md` and `Appendix.md`. Those describe what data **should** be available. This records what **is** — tested, with real numbers.

**Last updated:** 2026-07-27 · **Tier A complete · Tier B core verified** · 7.0 GB fetched

Evidence: `logs/inspection_report.md`, `logs/key_findings.md`, `logs/exposure_findings.md`
Fetch scripts: `scripts/fetch/` · Provenance: `data/raw/*/_SOURCES.json`
Credentials: `.env` (gitignored) — Earthdata, Dataspace and ECMWF all authenticated

---

## How to read this

### Access tier — how hard is it to get?
| Tier | Meaning |
|------|---------|
| 🟢 **A** | Open. No account, no key. |
| 🟡 **B** | Free account or API key required. No cost, no approval wait. |
| 🔴 **C** | Human action needed — waitlist, portal, department request, or vendor quote. |

### Status — what testing showed
| Mark | Meaning |
|------|---------|
| ⬜ | Untested |
| ✅ | **Confirmed** — sample pulled, covers the AOI, usable |
| ⚠️ | **Degraded** — reachable but limited |
| ❌ | **Blocked** — unreachable or unusable |
| ➖ | Not applicable / deliberately skipped |

### What "✅ Confirmed" requires
Recorded from a real sample: resolution · AOI coverage · date range · units · missing-data % · latency · volume. Anything less stays ⬜ or ⚠️.

---

## Scoreboard

| Tier | Total | ⬜ | ✅ | ⚠️ | ❌ | ➖ |
|------|------:|---:|---:|---:|---:|---:|
| 🟢 A | 22 | 0 | **11** | 5 | 3 | 3 |
| 🟡 B | 24 | 17 | **6** | 1 | 0 | 0 |
| 🔴 C | 42 | 42 | 0 | 0 | 0 | 0 |

**Tier A verdict (revised 2026-07-29): the physical base is solid, and the ground truth now is too.** Terrain, soil, land cover, hydrology, weather and seismicity all confirmed at full state coverage. The original verdict — that everything describing *what actually happened* was degraded or blocked — no longer holds: ~36,000 mapped landslides, state lithology and 4,777 lineaments were all obtained free from government portals that merely *appeared* closed.

**What remains genuinely weak:** landslide *timing* (72 exact dates, 166 years), flood on small rivers (3% of the network reachable), and exposure layers (48 health facilities, 17,719 buildings for 1.76 M people).

**Tier B verdict: the live trigger works.** All four core sources — rainfall, river forecast, radar, soil moisture — are authenticated, fetched and verified. The `WHEN` side of the system is no longer hypothetical. Optical imagery is the one casualty.

---

## Environment

| Item | Status |
|------|--------|
| Python 3.12.0 virtual environment at `.venv` | ✅ resolved — 3.14 was unusable, 3.12 was already installed |
| rasterio 1.5.0 · geopandas 1.1.4 · xarray · netCDF4 · GDAL 3.12.1 · cfgrib · h5py · cdsapi | ✅ installed and verified |
| Credentials in `.env` | ✅ all three accounts authenticated and tested |

---

## Credentials — all live

| Account | Unlocks | Status |
|---------|---------|--------|
| **NASA Earthdata** | IMERG, SMAP, GLDAS, MERRA-2, MODIS, ARIA | ✅ working — GESDISC, ASF, NSIDC ×3, LP DAAC authorised |
| **Copernicus Dataspace** | Sentinel-1, Sentinel-2 | ✅ working — token issued, 0.92 GB download proven |
| **Copernicus CDS / EWDS** | ERA5-Land, **GloFAS** | ✅ working — one shared PAT, both stores |
| Google Earth Engine | Global Flood Database (reclassified from Tier A) | ⬜ not created |

**Two access gotchas worth recording**, both cost time and neither is documented obviously:

1. **NASA redirect strips auth.** GES DISC and NSIDC bounce to `urs.earthdata.nasa.gov`; `requests` drops the `Authorization` header across hosts, giving 401 on every data call while metadata calls succeed. Fixed by `EarthdataSession` in `scripts/common.py`.
2. **Copernicus download redirect does the same.** Handled by following redirects manually and re-attaching the bearer token.
3. **GloFAS is not on CDS** — 404 there, served from EWDS. One ECMWF token covers both, but licences are accepted per store *and* per dataset.

---

# LEVEL 1 — Tier A results

## A. Terrain & susceptibility base

| Source | Tier | Status | Findings |
|--------|------|--------|----------|
| **Copernicus DEM 30 m** | 🟢 A | ✅ | 28 tiles, 1.19 GB. Elevation **36 m – 7,140 m**. No-data **0.000%** — coverage complete. Median slope 14.9°, **49.6% of terrain steeper than 15°**, 20.2% steeper than 25° |
| **SoilGrids 250 m** | 🟢 A | ✅ | 18/18 rasters (clay, sand, silt, bulk density, coarse fragments, organic carbon × 3 depths), 55 MB, full AOI |
| Soil depth / permeability | 🟢 A | ✅ | Derived from the above — not a separate product, as the Appendix states |
| **ESA WorldCover 10 m** | 🟢 A | ✅ | 6 tiles, 463 MB. Tree 63.1%, grass 14.7%, crop 9.5%, bare 5.1%, snow/ice 1.8%, **built-up 0.3%** |
| CGMW / OpenGeology | 🟢 A | ❌ | No programmatic download exists. Substituted below |
| Macrostrat *(substitute)* | 🟢 A | ⚠️ | 91/91 sample points returned a unit (100% coverage) — but only **3 lithology classes for the whole state**: sedimentary (65), crystalline metamorphic (22), intrusive igneous (4). Useless at slope scale |
| GEBCO | 🟢 A | ➖ | Bathymetry grid; state is landlocked and Copernicus DEM is strictly better on land. Skipped deliberately |

## B. Landslide trigger

| Source | Tier | Status | Findings |
|--------|------|--------|----------|
| **NOAA GFS 0.25°** | 🟢 A | ✅ | Live. Latest cycle **2026-07-26 06Z** retrieved. Lead times 6/24/72/120/**168 h** all served — the **7-day horizon is real**. Server-side AOI subsetting keeps files at 2–3 KB |
| **USGS earthquakes** | 🟢 A | ✅ | **551 events** M2.5+ in AOI, **2,367** M4.0+ regional (±2°). Range M3.5–**M8.6**, 1906 → **2026-07-25** (yesterday). 25 events M6.0+ in-state. Real-time confirmed |
| **IRIS / EarthScope** | 🟢 A | ✅ | **159 stations** within 2° of the AOI |
| NOAA api.weather.gov | 🟢 A | ➖ | **US only** — not applicable. The Appendix lists it without this caveat |

## C. Flood

| Source | Tier | Status | Findings |
|--------|------|--------|----------|
| **HydroSHEDS** | 🟢 A | ✅ | **50,800 river reaches**, 93,388 km total. Basins L8 (348) and L12 (1,680). Carries `UPLAND_SKM` — see the flood-reach finding below |
| **CWC FFS live gauge network** | 🟢 A | ✅ | **⭐ CRITICAL — see full writeup immediately below.** Real measured river level, 1971→today, for Arunachal's major gauged rivers. This was the top Level 2 ask; it turned out to be free |
| **NWDP river discharge (small/medium rivers)** | 🟢 A | ✅ | **⭐ CRITICAL — see full writeup immediately below.** Real measured discharge, 14 small/medium AP rivers, 750k+ readings, downloadable, openly licensed. Fills the gap CWC FFS didn't |
| Global Flood Database | 🟢 A → 🟡 B | ❌ | **Reclassify.** Site is a JS shell with no API; data is Google Earth Engine-only. The Dartmouth Flood Observatory archive it derives from returns **HTTP 410 Gone** — permanently removed |
| USGS WaterWatch | 🟢 A | ➖ | US only — method reference, no data value here |

> ## ⭐⭐⭐ CRITICAL — CWC FFS: real river gauge data, free, live. DO NOT MISS THIS WHEN BUILDING FLOOD. ⭐⭐⭐
>
> **Checked 2026-08-20.** `ffs.india-water.gov.in` — the Central Water Commission's own live flood forecasting site — runs on an **open REST API, no key, no login**, found by capturing the app's real network traffic with a headless browser (its own JS bundles don't reveal the API host — plain page-fetch or URL-guessing will not find this; see the method note in Section G's sibling entry below and in memory `cwc-ffs-live-river-gauge-data`).
>
> **What it gives us for Arunachal:**
> - **17 stations formally tagged `meteorologicalSubDivision = "Arunachal Pradesh"`**, plus more physically inside the state under neighbouring subdivision tags. Covers the major named rivers at named towns (Passighat/Siang, Yingkiong, Tuting, Namsai, Seppa/Kameng, Daporijo/Subansiri, Bhalukpong, Kibithu, and others) — **not** the small hillside streams; same tier as GloFAS/large-river forecasting, but **measured, not modelled**.
> - **Passighat (`005-UBDDIB`) alone has 93,145 real water-level readings, 1971-06-02 → today, still updating live.** Endpoint: `GET https://ffs.india-water.gov.in/iam/api/new-entry-data/specification/?specification={"where":{"expression":{"fieldName":"id.stationCode","operator":"eq","value":"005-UBDDIB"}},"and":{"expression":{"fieldName":"id.datatypeCode","operator":"eq","value":"HHS"}}}`
> - **Official danger/warning levels per station** — e.g. Passighat: warning 152.96 m, danger 153.96 m, historic peak 157.54 m (2000-06-11). This is an **objective, government-defined threshold for turning the level series into dated flood/no-flood labels** — no modelling required. Endpoint: `/iam/api/flood-forecast-static/specification/?specification={"expression":{"fieldName":"stationCode","operator":"eq","value":"<code>"}}`
> - **Official CWC forecast-vs-outcome records** at `/iam/api/new-forecasted-entry-data` — issued date, forecasted date, predicted value, trend. Inflow forecasts exist for at least Pare HEP and Subansiri Lower Dam (`FIN` datatype), current as of July 2026.
> - **Caveat:** only the core water-level series (`HHS`) stays continuously live on the stations checked. Other datatypes on the same stations (`HHT`, `IPC`, `MPM`, `MPS`, etc. — mostly not rainfall) mostly stop around 2021. Check `new-entry-data-aggregate` per station before assuming a series is current.
>
> **This resolves the Level 2 flood ask below marked ✅ FREE.** It does **not** touch the small-stream gap — see Finding 1, still open.
>
> **Not yet done:** full inventory of every AP station's data depth and live datatypes; bulk-archiving the full history; checking whether `aff.india-water.gov.in` (the linked 5-day advisory site) exposes the same kind of open API.

> ## ⭐⭐⭐ CRITICAL — NWDP: real discharge data for SMALL rivers, free, downloadable, verified. DO NOT MISS THIS WHEN BUILDING FLOOD. ⭐⭐⭐
>
> **Checked and download-verified 2026-08-20.** `nwdp.nwic.gov.in` — National Water Data Portal, run by NWIC (sister body to CWC) — is a standard CKAN open-data site (same software as data.gov.in), with a **documented, stable REST API**: `GET https://nwdp.nwic.gov.in/api/3/action/datastore_search?resource_id=<id>&limit=&offset=`. No key, no login. **Bulk CSV export confirmed working** at `https://nwdp.nwic.gov.in/datastore/dump/<resource_id>`. **License confirmed: `other-open`, published by CWC, notes explicitly say "for hydrological analysis, flood forecasting, and water resource management"** — we are clear to use this.
>
> **Dataset:** `river-discharge-telemetry-hourly-central-water-commission-cwc`, two Arunachal resources:
> - `9c755c40-389e-4f5d-92c6-b936d28e51b3` — **521,703 rows**, real dates 2023 → Sept 2025 (labelled "1970-2025" but that's a generic template name, not literal — a few rows carry a garbage 2000-01-09 timestamp, ignore)
> - `9a7feb81-191e-45df-b808-cd9523a97356` — **230,170 rows**, current telemetry, Jan 2026 onward
>
> **14 distinct stations, confirmed by a full scan (not sampling) — genuinely small/medium rivers across many districts, the tier CWC FFS's gauge network does NOT reach:**
>
> | Station | District | Historical rows |
> |---|---|---:|
> | Ziro | Lower Subansiri | 66,746 |
> | Changlang | Changlang | 60,220 |
> | Miao_2 | Changlang | 57,200 |
> | Deomali_1 | Tirap | 55,645 |
> | Basar_1 | Lepa-Rada | 46,315 |
> | Tenga_1 | West Kameng | 43,143 |
> | Sagalee_1 | Papum Pare | 40,792 |
> | Kamlang_1 | Lohit | 38,467 |
> | Changlang_1 | Changlang | 31,186 |
> | Kanubari_1 | Longding | 30,661 |
> | Tengapani Bridge_1 | Lohit | 17,075 |
> | Darak(Kamba) | West Siang | 14,392 |
> | Tissa Camp_1 | Tirap | 10,113 |
> | Aalo_1 | West Siang | 9,748 |
>
> **Data is DISCHARGE (m³/sec), 15-minute intervals** — the actual physical quantity a hydrological model wants, more directly usable than water level alone. Aalo_1 reads ~3 m³/s — a genuinely small stream, confirming this is real small-catchment coverage, not another cut of the same major rivers.
>
> **Data-quality caveat, real:** at least 2 of the 14 stations have visibly wrong coordinates baked into the government's own data (`Changlang`'s listed lat/lon is actually in Kashmir; `Ziro`'s is actually in Uttarakhand). The `District` field is reliable; **do not trust `Latitude`/`Longitude` without cross-checking against the station name and district.**
>
> **Together with the FFS finding above, this substantially answers the Level 2 river-gauge ask for BOTH tiers** — major rivers (FFS) and small/medium rivers (NWDP). The remaining gap is coverage completeness (14 stations, not all catchments) and cross-referencing each station to its actual HydroBASINS catchment.
>
> **Not yet done:** downloading and archiving the full 750k+ rows; matching each of the 14 stations to a HydroSHEDS catchment; checking whether other states' resources on this portal share the schema (useful for pooled small-basin training later, see `himalayan-pooling-is-the-live-ml-route` memory); checking for a rainfall-equivalent dataset on the same portal.

## D. Training labels

| Source | Tier | Status | Findings |
|--------|------|--------|----------|
| **NASA Global Landslide Catalog** | 🟢 A | ⚠️ | **All official NASA endpoints are dead** — Socrata 404, `maps.nccs.nasa.gov` refuses connections, viewer is a JS app. Retrieved via an **unofficial ArcGIS re-host** (provenance unverified). **99 events** in bbox, **72 inside the state**. Dates **2008 → 2018 — 8 years stale**. Location accuracy: exact 12, 1 km 16, 5 km 26, 10 km 16, 25 km 9, 50 km 13. **Only 28 events are precise enough for slope-scale training** |
| **GSI report archive — statewiseLandslideReport** | 🟢 A | ⚠️ | **⭐ CRITICAL — see full writeup below.** 46 of 48 real Arunachal GSI investigation reports (1950→2024-25) download directly, no login. Several carry exact dates in the title. Unread — a lead, not yet a corrected label count |

> ## ⭐⭐⭐ CRITICAL — GSI's own report archive is openly downloadable. A 6th route to dated events, unread. DO NOT MISS THIS. ⭐⭐⭐
>
> **Checked and download-verified 2026-08-20**, re-checking `bhusanket.gsi.gov.in` at the user's
> prompt. Different feature from the broken map/search covered elsewhere in this doc — this is a
> **report bibliography**: `bhusanket.gsi.gov.in/json/LandslideReport/LandslideReport.json`
> (1,179 records nationally, plain static JSON, no auth) lists GSI's actual field investigation
> reports — title, accession number, project type, field season.
>
> **48 records are Arunachal Pradesh, field seasons 1950 → 2024-2025.** Types: 18 Macro scale
> studies, 3 Meso scale studies, 16 Site Specific Studies, **11 Post Disaster Studies**.
>
> **Confirmed actually downloadable, not just indexed.** PDF URL pattern (from the page's own
> JS): `https://bhusanket.gsi.gov.in/Output/LandslideReport/<state>/<project type>/<accession
> no>.pdf`. Tested all 48 — **46 return a real PDF (HTTP 200, 0.1–196.7 MB), only 2 give 403.**
> No login anywhere in this path.
>
> **Why this matters:** Finding 6 below and `TEMPORAL_INVENTORY_ATTEMPTS.md` closed five routes
> to more dated landslide events — all of them remote-sensing or inference routes (optical
> dating, radar dating, ML-on-72-events, Bhuvan's `Year` field). **This is a sixth route those
> analyses never tested: GSI's own written investigations**, several with an exact date already
> visible in the title —
> *"22nd and 23rd April 2016 Tawang Town"*, *"14th June 2008 landslides and flood related hazard
> studies of Itanagar"* (also flood-relevant), *"Bhalukpong Landslide, Arunachal"* (2016-17), a
> 2024 post-disaster study, and older ones back to a 1950 Minutang landslide report.
>
> **⭐ Update 2026-08-20, same day — CONFIRMED BY READING, not just downloading.** Read 7 of the
> 46 Arunachal PDFs end to end. **Yes, they have exactly what was missing.** Best example:
> `PDLS_2024_50185.pdf` alone bundles **four** fully-attributed events — Banderdewa, Nirjuli,
> Chiputa (Papum Pare, all **18 June 2024**, exact times) and Abrali (Lower Dibang Valley, NH-313,
> **24 April 2024**) — each with a **structured 42/43-point datasheet**: exact lat/lon, date+time,
> material/movement/failure type, dimensions, triggering factor, deaths/damage. Since ~2016 this
> structured format is standard; older reports are narrative but still carry real dates — 5 more
> confirmed by reading: Bomdila (26–28 June 1973), Jamiri/Munna Camp debris avalanches (dated
> **15 June 1989** in one GSI report, **9 May 1989** in another about the *same* event — a real
> inconsistency in GSI's own archive, flag it rather than silently picking one), Minutang (8 Sept
> 1948, 332 deaths), Bhalukpong (1 July 2016, 12:20pm).
>
> **⭐⭐ Update 2026-08-20, later the same day — FULL SCAN COMPLETE. Concrete numbers below.**
> Downloaded and text-scanned all 255 targeted reports (Arunachal, every project type + the rest
> of the Himalayan/NE arc's Post Disaster Studies — the highest-yield category). 243/255
> succeeded (12 stuck behind a >60MB cap or a 403). Method + script:
> `scripts/proto/px2_gsi_report_archive.py`. Raw results: `data/interim/gsi_reports/`. Full
> numbers: `reports/px2_gsi_report_archive.json`.
>
> **Arunachal alone:** of the 27 reports that can hold a real event (Post Disaster + Site
> Specific Studies — excludes pure susceptibility-mapping reports), 20 show a genuine date.
> Calibrated against direct reading (one report matched exactly: 4 automated hits, 4 real
> events), estimated **~25–40 new individual events → Arunachal total ~100–110** (was 72).
> **Still not enough for a trustworthy ML trigger model** — same conclusion as at 72 events.
>
> **Pooled across the whole Himalayan/NE arc (Post Disaster Studies only, 11 states):** 215
> reports, 209 downloaded, **156 show a genuine date** — Uttarakhand alone contributes 69.
> Estimated **~200–280 new individual events, region-wide**. **This is a different regime** —
> enough to seriously attempt a real, cross-validated tree-based model (not deep learning),
> trained on the pool and fine-tuned to Arunachal. Revives
> `docs/design/PARKED_HIMALAYAN_POOLED_TRIGGER.md` with a stronger, day-precision source than
> the 617 season-tagged Bhuvan events it was built on.
>
> **Not yet a final count.** What's measured is *how many reports name a real date*, not the
> exact event total — reports bundle a variable number of events. The honest next step is
> reading all ~176 flagged reports one at a time and extracting each into a structured table;
> `data/interim/gsi_reports/scan_results.json` is the exact queue (`has_date_signal: true`).
>
> Full detail: memory `gsi-report-archive-open`, `himalayan-pooling-is-the-live-ml-route`.

## E. Impact & exposure

| Source | Tier | Status | Findings |
|--------|------|--------|----------|
| **WorldPop 100 m** | 🟢 A | ✅ | 531 MB. **1,757,407 people** in-state (Census 2011 was 1.38 M — plausible for 2020). Mean 4.5 people per populated cell |
| **GADM boundaries** | 🟢 A | ✅ | State + **22 districts**, area 81,995 km². Note: GADM 4.1 predates recent district reorganisation — Arunachal now has ~25–26 |
| OSM roads | 🟢 A | ⚠️ | **14,943 features / 16,015 km inside the state** (19.5 km per 100 km²). Mostly residential and unclassified; only 761 trunk, 320 secondary |
| OSM buildings | 🟢 A | ⚠️ | **17,719 inside the state** — for 1.76 M people. That is ~99 people per mapped building, so coverage is on the order of **a few percent of reality** |
| OSM health / education | 🟢 A | ⚠️ | **48 health**, **81 education** facilities in-state. 1 health point per 1,708 km² |
| Protected Planet (WDPA) | 🟢 A | ❌ | Downloads fine (63 areas for India) but contains **only international designations** (Ramsar 54, World Heritage 8, MAB 1). India does not publish national PAs. **Zero protected areas inside Arunachal** — Namdapha, Pakke, Mouling, Mehao all absent |

## F. Context

| Source | Tier | Status | Findings |
|--------|------|--------|----------|
| **NOAA CPC (ENSO/ONI)** | 🟢 A | ✅ | 917 seasons through **AMJ 2026** |

> ⚠️ **A bbox is not a state.** OSM and WDPA were fetched on the AOI bounding box, which reaches deep into Assam. Before clipping: 107,302 roads and 585,320 buildings. After clipping to the state polygon: 14,943 and 17,719. **86% of roads and 97% of buildings were outside Arunachal.** Any figure quoted from a bbox pull will overstate coverage by an order of magnitude.

## G. Land cover — recurring deep-learning feed (NESDR)

*Checked 2026-08-20, not yet in the Scoreboard count above.*

| Source | Tier | Status | Findings |
|--------|------|--------|----------|
| **NESDR / NESAC deep-learning LULC** | 🟡 B → 🔴 C | ⚠️ | Semi-annual cycles (Apr–Dec 2024, Jan–Jun 2025, Jul–Dec 2025). Latest cycle ships 7 separate classes: Forest, Grassland, Scrub Land, Agricultural Land, Built-up Area, Snow Cover, Waterbody. Sentinel-2 → automatic deep-learning classifier, NESAC's own stated accuracy **80–85%** from 6,000 sample points, explicitly **"post classification verification was not done on ground."** Full-resolution GeoTIFF download gated behind government registration (Safe Custody form) — 🔴 C. But the WMS map service underneath (`nesdr.gov.in/igistile/<workspace>/wms`) has an **open, unauthenticated GetCapabilities** — same trap as APSSDI/Bhuvan, 🟡 B in practice — not yet harvested end-to-end |

**This is a feature layer, not a label source.** It answers "what covers this ground," never "a landslide/flood happened here on this date." It does not touch the landslide-timing gap (Finding 6) or the flood-reach gap (Finding 1) — it sits in the same category as ESA WorldCover / soil / lithology above: input to a model, not the training answer.

**One genuine lead worth testing:** the Jul–Dec 2025 (monsoon-half) Waterbody layer against the water class in the drier Jan–Jun 2025 / Apr–Dec 2024 combined maps. If the classes line up cleanly, the wet-minus-dry difference is, in principle, an observed flood-season water-extent signal — free, dated, local — which is exactly what Finding 8's Bhuvan layer failed to be (70.5% of its "flooded" pixels sit on slopes >15°). Not yet checked whether it actually holds up.

**Access trap for the record:** the dataset search UI (`/search/og_group_ref/…`) renders its results with JavaScript, invisible to a plain page-fetch — only visible with a real rendered browser (headless Chrome `--dump-dom` worked; no MCP browser tool is available in this environment). Individual `/dataset/…` slugs can hide a Unicode en-dash (`–`) where a normal hyphen looks right, silently 404ing a guessed URL.

## H. SRSAC/APSAC follow-up — NWIA and SISDP-U, both actually tested

*Checked and access-tested 2026-08-20 (`srsac.arunachal.gov.in/geospatial.php` and onward — see memory `srsac-site-map-and-nwia`). Mixed verdict; this time the "looks closed but isn't" pattern only partly held.*

| Source | Tier | Status | Findings |
|--------|------|--------|----------|
| **NWIA wetland atlas** | 🟢 A | ⚠️ | National MoEFCC/SAC program, APSAC state partner. 1:25,000, IRS LISS-IV, classes include lakes/ponds/**glacial lakes**/reservoirs/waterlogged land, field-validated. **Tested: genuinely PDF-only** (`vedas.sac.gov.in`, state-wise reports, one national assessment PDF is 709 MB) — no live map/WFS/WMS behind this specific product. Real, flood-relevant content (frames wetlands as flood buffers; glacial-lake class matters for GLOF risk, see `PILOT_TAWANG.md`), just not queryable data |
| **VEDAS Wetland Information System** (bonus find) | 🟢 A | ⚠️ | Different, live system on the same domain (`vedas.sac.gov.in/vapps/wetlandinfo/`). Serves recent wetland/water-extent rasters (data as current as 2026-07-08) over an **open WMS, no login hit** (`ridam_server2/wms`), plus a REST catalogue (`geoentity-services/api/...`) of 56 dataset types incl. gauge stations and basin boundaries. **Arunachal-specific granularity not yet confirmed** — flagged, not relied on |
| **SISDP-U** (2.5 m LULC/drainage/infrastructure/settlement, 1:10,000) | 🔴 C | ❌ | **Tested: the official bulk-download page genuinely requires login** — it's a bare iframe to `login.php`, not a UI that merely looks gated. This one really is closed without an account. Bhuvan generally allows free individual/organisation registration for many thematic downloads — worth trying that before treating it as a hard wall |

**SISDP-U practical workaround already in hand:** NESDR's own open WMS (Section G) already serves `SISDP_Update_Arunachal_Drainage/Road/Settlement` and `arlulcsisdpv2` layers — very likely the same underlying program's output, reachable through a route already cracked, without needing the Bhuvan login.

**What the finer SISDP-U resolution (2.5 m vs the 10 m ESA WorldCover we use) would actually buy us, if obtained:** marginal for hazard *prediction* — the terrain (DEM) is still 30 m, so sharper land cover alone doesn't raise susceptibility-model precision much; the terrain stays the bottleneck. The real value is in **exposure/impact mapping** (a much finer settlement layer than OSM's sparse building coverage, see Section E) and **refining the small-stream channel network** for the flood static layer. Not a hazard-prediction upgrade — an exposure/terrain-detail upgrade.

---

# LEVEL 1 — Tier B results

*All four core sources verified. Fetched 2026-07-27.*

| Source | Status | Findings |
|--------|--------|----------|
| **GPM IMERG** (rainfall — core trigger) | ✅ | **132/132 days** retrieved. 0.1° (~11 km), mm/day, **0.00% missing pixels**. Sample peak **516 mm/day**. Latency **2 days** (newest 2026-07-25 on 2026-07-27). OPeNDAP server-side subsetting reduces each day from ~4 MB global to a few KB |
| **GloFAS forecast** (river discharge) | ✅ | 0.05° (~5.5 km), **7 lead times out to 720 h — the full 30-day horizon is real**. 100% valid pixels, 0–25,650 m³/s |
| **GloFAS historical** (calibration) | ✅ | Full 2024 monsoon, **122 days**, 100% valid, peak 56,040 m³/s. This is what you calibrate and validate against |
| **SMAP L3 Enhanced** (soil moisture) | ✅ | 9 km EASE-Grid 2.0. **93.9% valid over Arunachal** vs 11.9% globally — far better than expected. Range 0.027–0.695 m³/m³. Caveat: 668 MB per global granule, so subsetting is essential before any time series |
| **Sentinel-1** (flood extent + InSAR) | ✅ | **2,962 scenes in 12 months.** IW mode, both ascending (237) and descending (278). **Revisit: median 1 day, max gap 3 days.** Relative orbits 106/172/77/70/143 give usable InSAR stacks. Download proven with a 0.92 GB GRD scene |
| **Sentinel-2** (scars, glacial lakes) | ⚠️ | Reachable, but **cloud makes it seasonal**. See below |
| ERA5-Land | ⬜ | In progress |

### The Sentinel-2 cloud problem

Sampled 1,196 scenes across four seasonal windows:

| Window | Scenes | Median cloud | Below 20% cloud |
|---|---:|---:|---:|
| **Monsoon (May–Sep)** | 309 | **86%** | **3 (1%)** |
| **Dry (Nov–Mar)** | 310 | **6%** | **213 (69%)** |
| Annual | 1,192 | 61% | 342 (29%) |

**Optical imagery is effectively unavailable exactly when disasters happen.** During monsoon, 1% of scenes are usable. This is not a limitation you can engineer around — it is physics.

Two consequences worth designing for:

1. **Flood extent must come from Sentinel-1 radar, not Sentinel-2.** Radar sees through cloud; this is why the Appendix's choice of SAR for flood mapping is correct, and it is now quantified.
2. **Landslide scar mapping is a dry-season activity.** You map what happened during monsoon in the following Nov–Mar window, when 69% of scenes are clear. Scar tracing is retrospective label-building, not live detection.

---

# Headline findings

### 1. Flood: only 3% of the network is reachable by a large-river forecast

| Upstream drainage area | Reaches | % of network | Length |
|---|---:|---:|---:|
| any | 50,800 | 100% | 93,388 km |
| > 100 km² | 9,520 | 18.7% | 16,907 km |
| > 1,000 km² | 3,272 | 6.4% | 5,545 km |
| > 5,000 km² | 1,535 | **3.0%** | 2,639 km |
| > 10,000 km² | 1,234 | 2.4% | 2,129 km |

Large-river forecasting needs drainage areas in the thousands of km². **97% of Arunachal's stream network sits below that threshold.** This is the quantified case for the Level 2 flood build — it is not a refinement, it is the difference between covering 3% and covering the state.

> **Update 2026-08-20:** the 3% that *is* reachable just got a lot better — see Finding 11. CWC's own gauge network gives **real measured** river level on that tier instead of GloFAS's modelled estimate.
>
> **Update 2026-08-20, later the same day:** the 97% gap is no longer completely untouched either — see Finding 12. NWDP has real discharge data for 14 small/medium rivers across many districts. Not full coverage of the network, but the first real evidence found on this tier at all.

### 2. Landslide labels: RESOLVED — 28 → ~36,000, free

> **Superseded 2026-07-29.** This finding previously read *"28 usable training labels for 81,995 km²"* and named the GSI inventory as the highest-value Level 2 ask. **The inventory turned out to be freely downloadable.** Kept below because the reasoning about *what kind* of label is still needed remains correct.

| Source | Records | Geometry | Timing |
|---|---:|---|---|
| GSI Bhusanket polygons | 26,213 | True failure extents | None |
| GSI Bhusanket points | 1,322 | Points, 113 attributes | Year on 166 only |
| NRSC Bhuvan (2014/2017/2023) | 11,329 | Polygons + dimensions | **Season** |
| **Union (overlap removed)** | **35,744** | | |
| NASA GLC (retained) | 72 | Points, coarse | **Exact date** |

Two corrections stand between the raw download and that figure, and both must survive
into any client-facing number:

- GSI delivers by **map tile, not by state**. The file contains 26,459 polygons, of
  which **246 lie in Nagaland (198) or Assam (48)**. Filter on `STATE` before counting.
  Caught by reading the first raw records — the file's leading rows are Karbi Anglong.
- **1,798 Bhuvan polygons (15.9%) coincide with a GSI polygon.** Quote the union, not
  the sum. The overlap is not waste: two agencies independently mapping the same
  failure is the nearest thing to validation this data offers.

**Road-bias check passed.** Landslides are 2.3× enriched within 250 m of a road (15.6% vs 6.8% for random land), but 74% lie >1 km from any road. Mild, and partly real causation rather than sampling bias. Mitigate by including distance-to-road as an explicit feature. The inventory is not a road survey.

**The remaining label gap is timing, not location.** ~36,000 records answer *where*; only 72 carry a date and 166 a year. See Finding 6.

### 3. The physical base is genuinely strong

Terrain, soil, land cover, hydrology, rain forecast and seismicity are all confirmed at full state coverage with near-zero missing data. Nothing blocks starting susceptibility work immediately.

### 4. Geology: RESOLVED — free and open after all

> **Superseded 2026-07-29.** Previously *"three lithology classes across 82,000 km²; GSI geology is required."*

The **state's own geoportal (APSSDI / APSAC) runs an open WFS with no authentication.** Its catalogue UI requires a login; the map server underneath does not.

| Layer | Features |
|---|---:|
| Lithology | 562 polygons — 24 lithological units, 32 named formations |
| **Lineaments (faults/fractures)** | **4,777** |
| Litho-geomorphology | 3,897 |
| Geomorphology | 3,176 |
| Drainage / Settlements / Admin circles / Snow / Geology-mining | 1,885 / 4,648 / 186 / 5,282 / 170 |

Lineament proximity ranks among the top predictors of landslide location, and it is now held statewide. **Two access traps** cost real time and are worth recording: the server sends an incomplete TLS chain (fails in most HTTP clients, looks like an outage — supply the Go Daddy G2 intermediate), and it flaps offline for ~30 minutes at a time.

### 6. Timing data exists, is collected by GSI, and is not published

`GSI/Landslidedata_1` is a live ArcGIS service whose 113-field schema is exactly what a forecast model needs:

```
LandslideDate, LandslideTime, DateTimeType, ExactDateInfo, date_acc
Amount_of_rainfall, Duration_of_rainfall, RainfallIntensity
LandslideCauses, Geological/Morphological/HumanCauses
PeopleDead, PeopleInjured, RoadBlocked, ...
```

It returns **2 records publicly** — one genuine (Valparai TN, 2024-07-30 03:00), one a test row — with OBJECTID running to 402. Field names (`ContactMobile`, `Photograph1-4`, `Reviewed_Date`, `Rejected_Reason`) identify it as the **Bhooskhalan app** submission-and-review backend. The populated table is internal.

Per-event *measured* rainfall amount, duration and intensity is the prize here — it cannot be reconstructed from IMERG, which averages over 10 km in terrain with 3,000 m of relief.

> **Update 2026-08-20:** don't treat `Landslidedata_1` as the only path to more dates any more — see the critical callout above Section E. GSI's own report archive (46 downloadable PDFs, several with exact incident dates in the title) is a free, no-ask alternative route, unread but real.

### 7. What we already hold on *how* landslides occur

The 1,322 GSI points are richly attributed even without dates:

| Attribute | Populated | Dominant values |
|---|---:|---|
| Triggering factor | 1,286 | **89% rainfall** |
| Failure mechanism | 1,299 | Shallow translational / rotational |
| Material | 1,293 | Debris / Rock / Soil |
| Movement type & rate | 1,304 | Slide, Fall · Rapid/Moderate/Slow |
| Hydrological condition | 1,233 | Dry / Wet / Damp |
| Alert level | 935 | I / II / III |

Rainfall as the dominant trigger is now established **from the data**, not from literature.

### 8. Official hazard products retrieved

- **GSI national susceptibility, 50 m, 3 classes** — via the portal's public proxy. Use as *benchmark*, never as an input: training on it would predict GSI's model rather than landslides.
- **Bhuvan aggregated flood inundation 2003–2020** — observed flood footprint, 1.29% of the AOI box. The flood equivalent of a landslide inventory, and the only observed flood history held.

### 9. Multi-state training data available (not yet fetched)

Bhuvan's `disaster` workspace carries season-tagged landslide layers for ~15 states — the ~80,000 landslides NRSC mapped nationally. The rainfall→failure relationship can be trained across the Himalayan arc and fine-tuned to Arunachal, which sidesteps the local timing gap. **Not yet verified** that other states share Arunachal's schema.

### 12. ⭐ NWDP: real discharge data for small rivers, free, verified downloadable

Full detail in the callout in Section C. Short version: `nwdp.nwic.gov.in` (NWIC, standard CKAN open-data platform) has **750k+ real discharge readings across 14 small/medium Arunachal rivers** — Ziro, Changlang, Miao, Deomali, Basar, Tenga, Sagalee, Kamlang, Kanubari, Tengapani, Darak, Tissa Camp, Aalo — spanning many districts, not just the major trunk rivers. License is `other-open`, published by CWC explicitly for flood forecasting use, and bulk CSV download is confirmed working. This is the first real evidence found on the small-stream tier at all (Finding 1's 97% gap). Coordinates on 2 of the 14 stations are wrong in the source data — verify by name/district, not lat/lon.

### 11. ⭐ CWC FFS: the real river gauge data, free — the top flood ask, resolved

Full detail in the callout in Section C. Short version: `ffs.india-water.gov.in` runs an open API with **55 years of real measured water level** for Arunachal's major gauged rivers (Passighat/Siang alone: 93,145 readings, 1971→today, still live), plus official danger/warning thresholds per station and CWC's own past forecast records to check against. This was expected to require a formal state/CWC request; it did not. **Still only covers the same gauged-major-river tier as Finding 1** — it upgrades that tier from modelled to measured, it does not reach the small-stream 97%.

### 10. NESDR: a recurring land-cover feed, not a label source — with one lead worth testing

NESAC's `nesdr.gov.in` runs Sentinel-2 through a deep-learning classifier for the whole Northeast every ~6 months (Section G). It is real satellite imagery, automatically sorted into land types — not invented data — but NESAC's own listing says ground verification was never done, so treat the 80–85% accuracy as self-reported. It answers "what's on the ground," not "when did a hazard occur," so it does not fill the landslide-timing gap or the flood-reach gap. The one thing worth chasing: its Waterbody layer for the monsoon half of 2025 against the drier halves before it, as a candidate flood-season proxy — see Section G for why.

### 5. Exposure layers cannot yet support an impact product

48 health facilities and 17,719 buildings mapped for 1.76 M people, and no protected-area layer at all. Population is fine; everything else needs a state source.

---

# LEVEL 2 — + ASK

**All 🔴 C, all ⬜.** Every item requires a department to release it. Status here means: ⬜ not asked · 📤 asked, waiting · ✅ received · ❌ refused.

### Improves landslide prediction
| Data | Ask who | Status | Notes |
|------|---------|--------|-------|
| ~~Landslide inventory~~ | GSI | ✅ **FREE** | **Obtained without asking — ~36,000 polygons.** No longer an ask |
| ~~Lineament & thrust/fault maps~~ | GSI | ✅ **FREE** | **Obtained without asking — 4,777 lineaments via APSSDI open WFS** |
| **`Landslidedata_1` event table** | GSI | ⬜ | **NOW THE HIGHEST-VALUE ASK.** Schema confirmed live; only 2 of ~402 rows public. Request by name — see the drafted wording below |
| **Ground rainfall records** | IMD | ⬜ | **Promoted to joint-highest.** Binding constraint on timing accuracy — IMERG bias flips sign between high terrain and foothills |
| **Road-blockage / maintenance logs** | State PWD, BRO | ⬜ | **New ask.** Every landslide that closed a road, with a date — the cheapest route to dated events |
| Detailed geology + borehole logs | GSI, PWD, hydropower surveys | ⬜ | Lithology now free; borehole logs still valuable |
| Meso-scale (1:10,000) susceptibility | GSI | ⬜ | **New ask.** Finer spatial unit than the free 50 m national raster |
| Hydropower project met stations | NHPC and other operators | ⬜ | **New ask.** Dense local rainfall in exactly the valleys that matter |
| Groundwater levels | CGWB | ⬜ | |
| Road-cut & construction zones | BRO, NHIDCL, State PWD | ⬜ | OSM has 761 trunk roads statewide — official alignment data would improve on this |
| Forest loss / land-use change | State Forest dept | ⬜ | Also the only route to a protected-area layer |

### Improves flood prediction
| Data | Ask who | Status | Notes |
|------|---------|--------|-------|
| ~~River gauge (level & flow)~~ | Client dept, CWC | ✅ **FREE** | **⭐ Obtained without asking — CWC's own FFS site exposes an open API with 55 years of real level data for Arunachal's gauged rivers.** See the critical callout in Section C above. No longer an ask — for the *gauged* rivers only |
| **River cross-section / bathymetry** | CWC, State Water Resources | ⬜ | **Now the top ask.** Turns "the level is high" into an actual depth/extent map — the gauges alone can't do this |
| **Dam / reservoir release schedule** | NHPC and other operators, CWC | ⬜ | The gauge network shows water flowing *in* to dams (inflow forecasts), not what operators release downstream |
| ~~Small-stream gauges~~ | Hydropower operators' own monitoring, State Water Resources | ✅ **FREE** | **⭐ Obtained without asking — NWDP has real discharge data for 14 small/medium rivers.** See the critical callout in Section C. Still only 14 stations, not every catchment — more coverage remains a live ask if this proves valuable |
| Embankments & hydraulic structures | Water Resources | ⬜ | Changes where water goes once a river tops its banks |
| Historical flood levels | CWC, SDMA | ⬜ | Partly superseded — the gauge history itself now carries each station's historic peak level and date |

### Improves impact & response
| Data | Ask who | Status | Notes |
|------|---------|--------|-------|
| Utility lines | State electricity board, PHED | ⬜ | |
| Vulnerable households | Census, district health office | ⬜ | |
| Evacuation routes, shelters, contacts | DDMA | ⬜ | |
| Official event & damage records | SDMA / DDMA / NDMA | ⬜ | **Promoted in importance** — the free catalogue is stale and coarse |
| Large-scale toposheets | Survey of India | ⬜ | Lower priority: 30 m DEM verified complete and clean |
| Building / facility inventory | District administration | ⬜ | **New ask** — OSM covers a few percent of buildings |

### Drafted request — GSI event table

Naming their own table and columns makes this materially harder to deflect than a general enquiry:

> Requesting an export of the **`Landslidedata_1`** table (GSI landslide inventory / Bhooskhalan submissions) for Arunachal Pradesh, specifically the fields `LandslideDate`, `LandslideTime`, `Latitude`, `Longitude`, `Amount_of_rainfall`, `Duration_of_rainfall`, `RainfallIntensity`, `TriggeringFactor`, `MovementType`, `FailureMechanism`, `date_acc`, `geo_acc`, for all available years.

**Do not block on it.** The Sentinel dating pipeline (Level 1, free) produces dated events regardless, at 1–2 week precision. The ask buys hour-precision timing and *measured* rainfall at the slide — the one thing that genuinely cannot be self-computed.

---

# LEVEL 3 — + PAID

All 🔴 C, vendor quotes only, none requested. See `Appendix.md`.

---

## Revisions this verification forces on the docs

| Doc claim | Reality | Action |
|---|---|---|
| Global Flood Database is Level 1 free | GEE-gated; DFO archive returns 410 Gone | Move to Level 2 / Tier B |
| NASA GLC is a usable free label source | Official endpoints dead; 28 usable labels; stale to 2018 | Downgrade to **event-timing only** — it holds the only exact dates we have |
| CGMW / OpenGeology gives free geology | No download path; substitute has 3 classes | ~~GSI becomes required~~ → **superseded: APSSDI open WFS supplies it free** |
| GSI inventory & lineaments are the top Level 2 ask | Both freely downloadable; the portals merely *looked* closed | **Removed from ASK.** Highest-value ask is now the `Landslidedata_1` event table |
| Google Flood Hub can be consumed for Task 3 | Waitlisted; unavailable | Flood rests on GloFAS, which reaches only 3% of reaches. **Flood is the weak leg** |
| "Portal has no data" when a UI shows nothing | GSI search is broken in production; APSSDI catalogue needs login but its map server does not | **Always test machine endpoints before believing an interface** |
| Protected Planet gives protected areas | Zero coverage for Arunachal | Reassign to State Forest Dept |
| `api.weather.gov`, WaterWatch listed without caveat | Both US-only | Mark not applicable |
| Level 2 flood is an upgrade | It is the difference between 3% and full coverage | Already corrected in `Base.md`; now quantified |
| NESDR's "deep learning" datasets might be landslide/flood event labels | They're recurring land-cover classification (forest/water/etc.), self-described as unverified on the ground | Treat as a feature layer, not a label source — see Section G |
| River gauge data requires a formal CWC/state ask, expect a long wait | CWC's own `ffs.india-water.gov.in` exposes an open API with 55 years of real level data for Arunachal's gauged rivers, no request needed | **Removed from ASK.** See the critical callout in Section C and Finding 11 |
| Small-stream gauge data does not exist anywhere free (Finding 1's 97% gap is a hard wall) | NWIC's `nwdp.nwic.gov.in` has real, licensed, downloadable discharge data for 14 small/medium AP rivers | **Removed from ASK for these 14 catchments.** See the critical callout in Section C and Finding 12. Not full network coverage — more stations would still be a live ask |

---

## Next steps

1. ~~Create the three free accounts~~ — ✅ done, all authenticated.
2. ~~Verify the Tier B core four~~ — ✅ done. IMERG, GloFAS, Sentinel-1 and SMAP all confirmed with real data.
3. **Start the Flood Hub waitlist application** — long lead time. Less urgent than it was: GloFAS is now verified end to end, so Level 1 flood has a working path without it. Flood Hub becomes a cross-check rather than a dependency.
4. ~~Draft the GSI inventory request~~ — ✅ **not needed, data obtained free.** Instead:
   - **Send the `Landslidedata_1` request** (wording drafted in Level 2) — hour-precision dates and measured per-event rainfall.
   - **Send the IMD rainfall request** — joint-highest value; corrects the bias that caps timing accuracy.
   - **Send the gauge request** — still quantified by the 97%-of-reaches finding, and now the single unlock for flood.
   - **Send the PWD road-blockage request** — cheapest source of dated events.
5. **Build the susceptibility baseline** — nothing is blocking it, and it now has ~36,000 labels plus free state lithology and lineaments. Benchmark against the GSI 50 m raster; GSI's own map used logistic regression, so a gradient-boosted model should be demonstrably better.
6. **Build the Sentinel dating pipeline** — the highest-value free work available. Change detection over the ~36,000 known polygons converts a spatial inventory into a dated event catalogue at 1–2 week precision, which is enough to attribute events to specific monsoon storms in IMERG. Removes the dependency on the GSI ask and keeps generating new dated events every season after handover.
7. **Fetch the multi-state Bhuvan layers** — ~80,000 season-tagged landslides nationally for training the rainfall→failure relationship. Verify schema parity with Arunachal first.
8. **Remaining Tier B** (secondary, none blocking): MODIS, GLDAS, MERRA-2, ESA CCI soil moisture, NASA ARIA, Global Flood Database via Earth Engine.
9. **Harvest the NESDR WMS and test the Waterbody wet-vs-dry comparison** — the open `igistile` service (Section G) has not been pulled end to end. If the monsoon-half Waterbody layer and the drier halves' water class line up, it's the first candidate flood-season ground truth since Bhuvan's layer was rejected (Finding 8).
10. **⭐ Archive the full CWC FFS gauge history for every Arunachal station** — highest priority flood work now available. Inventory every AP-tagged/AP-located station, confirm its live datatype(s) and data depth, pull full history, and derive dated flood/no-flood labels from each station's danger/warning thresholds (Finding 11, Section C). This is what unblocks training a real rain→river-rise model on Arunachal's own gauged rivers.
11. **⭐ Archive the full NWDP discharge history for all 14 small/medium-river stations** — same priority as #10, for the other tier. Bulk-download both Arunachal resources (Finding 12, Section C), fix the 2 known bad coordinates by cross-checking district/name, and match each station to its HydroSHEDS catchment so the discharge series can be paired with the rainfall already held for that basin.
12. **⭐ Read the GSI Post Disaster Studies reports first** — highest-priority landslide work now available. 11 short reports, real dates likely inside; start there before the larger Site Specific / Macro scale PDFs. This is what would actually move the "90 dated events" number, if it moves at all — don't claim a new count until they're read (Section D critical callout).
13. **⚠️ DO NOT mark SISDP-U closed without trying registration first.** Section H found the official bulk-download page (`bhuvan-app1.nrsc.gov.in/thematic/thematic/index.php?theme1=sisdpPh2&tab1=GetData`) genuinely login-gated — unlike most other "closed" portals in this doc, that was not a false negative. But Bhuvan generally offers **free individual/organisation registration** for its thematic downloads; that has not been tried. Low priority (Section H explains why — exposure/drainage detail, not a hazard-prediction upgrade) but **register and check what's behind the login before writing this off as a paid-tier item.** NESDR's WMS (Section G) already gives a likely-equivalent workaround in the meantime.

## What changed after Tier B

| Before | After |
|---|---|
| Flood depended on a waitlisted single vendor | GloFAS verified — 30-day horizon, 100% valid, independent |
| Soil moisture assumed weak ("weakest free substitute") | 93.9% valid over the AOI — genuinely usable |
| Sentinel-2 assumed available for scar mapping | 1% usable during monsoon; dry-season activity only |
| Rainfall trigger unverified | 2-day latency, zero missing pixels, full season retrieved |
