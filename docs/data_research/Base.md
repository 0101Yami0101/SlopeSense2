# Data Levels — Flood & Landslide Prediction

**Arunachal Pradesh** | Statewide, all 38 districts

---

# What we're building

| Product | Role | What it does | Free-data accuracy |
|---------|------|--------------|--------------------|
| **Landslide prediction** | 🎯 Primary | Daily "which slopes may fail now" from live rain | POD 55–70%, FAR 40–60% |
| **Flood prediction** | 🎯 Primary | Large rivers: 3–7 day forecast. Small rivers: **watch only** | Large ~75–85%; small rivers weak |
| **Landslide susceptibility** | 🧩 Supporting | Static map of dangerous slopes — the base layer prediction runs on | **0.82–0.90 AUC** |

All three are buildable with **free data only**. Susceptibility is now operational-grade; landslide timing is real but uncertain; flood is the weak leg until gauge data arrives.

> **Naming discipline.** Never quote a single headline accuracy. Three tasks, three metrics — see the performance section in `CLAUDE.md`. **POD** = of landslides that happened, the share you warned for. **FAR** = of warnings issued, the share that were wrong. They trade off against each other: where the threshold sits is a *client policy decision*, not a technical one.

---

# How landslide prediction works

Susceptibility is not a separate goal — it's the foundation the prediction sits on.

```
  Susceptibility (WHERE)      ×      Live trigger (WHEN)        =   Landslide prediction
  which slopes are weak              rain now + wet soil            daily risk map that
  static, built once                 IMERG + SMAP, live             changes with weather
```

- **Susceptibility (WHERE):** terrain, soil, geology → ranks every slope's built-in risk. Doesn't change with weather.
- **Trigger (WHEN):** today's rainfall + soil moisture on a weak slope → fires the alert.
- **Prediction = the two multiplied** → a live daily forecast, the same method operational Himalayan systems use.

---

# How flood prediction works

Different logic from landslide — **consume at Level 1, build at Level 2.**

```
  LEVEL 1 — consume                LEVEL 2 — build on top
  Flood Hub + GloFAS forecast      your own rain → river-rise model
  large rivers, yes/no             small rivers, depth & extent,
  zero build effort                dam-release flash floods
```

Flood-zone extent at both levels comes from Sentinel-1 SAR. Flood Hub stays the large-river backbone and an independent cross-check throughout — Level 2 covers the catchments it can't reach, which across Arunachal is the majority of streams.

---

# LEVEL 1 — FREE (functional, all 3 products)

### Delivers
- **Flood prediction** — 7-day river forecast (larger rivers) + flood-zone map
- **Landslide susceptibility** — full risk map, ~0.80–0.85 AUC (train regional Himalaya-wide, apply to area)
- **Landslide prediction** — live daily risk from rainfall trigger on the susceptibility base

### Data

| What | Feeds | Source |
|------|-------|--------|
| Elevation (DEM) | all | Copernicus DEM 30m, ISRO CartoDEM / Bhuvan |
| Slope, aspect, curvature | susceptibility | Derived from DEM in QGIS |
| **Lithology (24 units, 32 formations)** | susceptibility | ✅ **APSSDI open WFS** — no account. Replaced the 3-class free geology |
| **Lineaments / faults (4,777)** | susceptibility | ✅ **APSSDI open WFS** — top-3 predictor, was believed to need a GSI request |
| Soil properties | susceptibility | SoilGrids 250m |
| Land cover / forest | susceptibility | ESA WorldCover 10m, Bhuvan |
| **Landslide inventory — 35,744 polygons** | susceptibility, prediction | ✅ **GSI Bhusanket (26,213 in-state) + NRSC Bhuvan (11,329, season-tagged)** — no account |
| **GSI national susceptibility 50m** | benchmark only | ✅ GSI ImageServer via portal proxy — never train on it |
| **Observed flood extent 2003–2020** | flood labels | ✅ NRSC Bhuvan `agg_ar` — the only observed flood history held |
| Landslide event dates (72 exact) | prediction | NASA Global Landslide Catalog — retained *only* for exact dates |
| **Dated events (self-computed)** | prediction | ⚙️ **Sentinel-1/2 change detection over the 36,000 polygons** — free, 1–2 week precision |
| **National training set (~80k)** | prediction | ⚙️ Bhuvan multi-state season-tagged layers, ~15 states — train trigger model Himalaya-wide |
| Live rainfall | prediction | NASA GPM IMERG (30 min, ~4h delay) |
| Rain forecast 7-day | prediction | ECMWF, NOAA GFS |
| Soil moisture | prediction | NASA SMAP (9km, 3-hourly) |
| Rivers & catchments | flood | HydroSHEDS |
| River forecast 7-day | flood | ⚠️ Google Flood Hub — **waitlisted, unavailable**. Flood rests on GloFAS |
| River discharge 30-day | flood | GloFAS |
| Historical flood extent (labels) | flood | Sentinel-1 SAR, Global Flood Database |
| Slope creep radar | prediction | Sentinel-1 InSAR (12-day) |
| Glacial lakes (GLOF) | flood | Sentinel-2, ICIMOD database |
| Earthquakes | prediction | USGS, India NCS |
| Population, buildings, roads | impact | Census, WorldPop, OpenStreetMap |

### What "free" costs you
- ~~Landslide labels are vague~~ → **fixed.** ~36,000 government-mapped polygons. Road-bias tested: 2.3× enrichment within 250 m, but 74% lie >1 km from any road. Mild and partly real causation; mitigate with distance-to-road as a feature.
- **Timing is the remaining label gap** — only 72 events carry an exact date, 166 a year. Fixable free via Sentinel change detection; fixable better via the GSI event-table ask.
- Landslide **timing is noisy** (POD ~55–70%, FAR 40–60%) — free data cannot see pore pressure inside the slope. True of every rainfall-based system at any budget.
- **Rainfall resolution is the binding constraint.** IMERG averages over 10 km in terrain with 3,000 m of relief, and its bias *flips sign* between high terrain and the southern foothills. This caps everything at Level 1.
- **Flood is the weak leg.** GloFAS reaches ~3% of the stream network; Flood Hub is waitlisted. Small mountain rivers get a *watch*, not a forecast.

**Susceptibility is now genuinely operational-grade on free data. Landslide timing is real but uncertain. Flood is large-rivers-only until gauges arrive.**

---

# LEVEL 2 — + ASK (operational-grade)

Free, but a department must hand it over. **Landslide:** sharper precision, same product. **Flood:** genuinely new capability — this is where the operational flood build happens.

### Adds
- ~~Landslide labels go vague → precise~~ → **already achieved free.** What ASK adds now is *timing*: hour-precision dates and measured per-event rainfall
- Rainfall thresholds corrected for altitude → fewer false alarms. **Biggest single accuracy gain in the whole roadmap, for zero money**
- **Flood goes consume → build** — client gauge records train a rain → river-rise model on your own basins (same method as Flood Hub), reaching small rivers Flood Hub never covers
- Cross-sections turn flood output from yes/no into **depth & extent**; dam schedules add **release-driven flash-flood warning**
- Real slide history + known danger zones

### Data

| What | Ask who | Upgrades |
|------|---------|----------|
| ~~Landslide inventory~~ | GSI | ✅ **Obtained free — no longer an ask** |
| ~~Lineament & fault/thrust maps~~ | GSI | ✅ **Obtained free via APSSDI — no longer an ask** |
| **`Landslidedata_1` event table** | GSI | 🥇 **Top ask.** Hour-precision dates + *measured* rainfall amount/duration/intensity per event. Schema confirmed; only 2 of ~402 rows public |
| **Ground rainfall records** | IMD | 🥇 **Joint-top.** Corrects the bias that caps timing accuracy — the single biggest accuracy gain available |
| **Road-blockage / maintenance logs** | State PWD, BRO | **New.** Every landslide that closed a road, with a date — cheapest route to dated events |
| Meso-scale 1:10,000 susceptibility | GSI | Finer spatial unit than the free 50 m national raster |
| Hydropower met stations | NHPC and other operators | Dense local rainfall in the valleys that matter |
| River gauge data (level & flow) | Client dept, CWC | Small-river flood prediction |
| **River cross-section / bathymetry** | CWC, State Water Resources | Flood **depth & extent**, not just yes/no |
| **Dam / reservoir release schedule** | Hydropower operators (NHPC), CWC | Downstream flash floods — key in dam-heavy Arunachal |
| Geological maps (detailed) | GSI | Sharper susceptibility |
| Groundwater levels | CGWB | Better wet-season trigger |
| Roads + known slide zones | State PWD | Real slide history, road risk |

**GSI landslide inventory — OBTAINED, no request needed.** This was the highest-value ask; it turned out to be freely downloadable. **35,744** mapped landslide polygons statewide, from GSI Bhusanket and NRSC Bhuvan — after dropping 246 GSI records that fall in Nagaland or Assam and removing 1,798 slides the two agencies both mapped. See `DATA_VERIFICATION.md`.

### The three asks that matter most

1. **IMD ground rainfall** — corrects the bias that caps *all* landslide timing accuracy. Biggest gain per effort.
2. **GSI `Landslidedata_1` event table** — hour-precision dates + measured rainfall per event. Request it by table and field name; the schema is confirmed and public, only the rows are not.
3. **Client / CWC river gauges** — the single unlock for flood, which is otherwise stuck at 3% of the stream network.

**Do not block on any of them.** Sentinel change detection over the ~36,000 known polygons produces dated events free, at 1–2 week precision — enough to attribute events to specific monsoon storms. Ask *and* build in parallel.

---

# LEVEL 3 — + PAID (optional, never required)

Buys one thing free data cannot: **hours of warning on a specific named slope** — the pore-pressure trigger satellites can't see.

**Two honest limits.** It only works on slopes that *creep before failing* — deep-seated failures give hours-to-days of accelerating movement you can extrapolate (inverse-velocity method, standard in open-pit mining). Shallow rain-triggered debris flows go from stable to gone in minutes with no precursor, and GSI's own field validation found **~59% of Arunachal failures are debris flows**. And sensors are per-slope, so you must already know which slope — realistically 10–50 sites, not 36,000.

**Which is why Level 1 pays for Level 3:** the free statewide susceptibility × exposure map is what tells the client *where to put the sensors*. Phase 1 identifies the sites; Phase 3 instruments them.

### Adds
- "This slope fails in hours" — 5–10 named sites
- Flood extent refreshed every ~6 hrs
- cm-accurate terrain, mm-scale creep on priority slopes

### Data

| What | Vendor | Adds |
|------|--------|------|
| Piezometers, tiltmeters, soil probes | Encardio Rite, geotech suppliers | Hours-ahead slope warning |
| On-demand flood radar | ICEYE, Capella | 6-hourly flood extent, day/night |
| Drone / LiDAR survey | Local UAV operators | cm terrain vs 30m free |
| **Statewide InSAR processing** | Gamma, TRE Altamira, SARPROZ | 🥇 **Best paid value.** Sentinel-1 data is free — you pay for processing. Turns output from "this zone is susceptible" into "**these 40 slopes are moving right now**": a live watchlist, statewide, no hardware |
| High-res imagery | Maxar 30cm, Planet daily | Sharper, more frequent |
| Hyperlocal weather + SLA | Meteomatics, Tomorrow.io | ~90m rain, guaranteed uptime |

Sequence: run free system through one monsoon → log missed events → buy sensors only there.

---

*Full source URLs, latency, resolution: `APPENDIX_detailed_sources.md`*
