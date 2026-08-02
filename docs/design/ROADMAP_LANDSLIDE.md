# Roadmap — Landslide Forecast to MVP

**Scope:** from project start to a working, demonstrable Landslide Forecast for Arunachal
Pradesh. Ends where the Flood Forecast roadmap begins.

**Companion docs:** [DESIGN.md](DESIGN.md) explains *why* each technique is used.
This document is *when and in what order*.

> **Flood is deferred, not dropped.** It ships in the same MVP. Every phase below marked
> 🔗 **SPINE** produces something flood will reuse — build those hazard-agnostic (take a
> `hazard` argument; never hardcode `"landslide"`) or you'll rewrite them in the flood
> roadmap. This is the single most expensive mistake available in this plan.

---

## The whole thing at a glance

```
  ══ DONE ═══════════════════════════════════════════════════════════
   P0  Problem definition & scope
   P1  Data discovery — what exists, who owns it, is it reachable
   P2  Acquisition — 7.7 GB across 11 categories
   P3  Verification & the viz layer — prove what we actually have
   P4  Rainfall archive backfill        9,555 days, 0 gaps  ✅ 2026-08-02
   P5  Grid + terrain derivatives           🔗 SPINE        ✅ 2026-08-01
   P6  Susceptibility model (WHERE)         AUC 0.860       ✅ 2026-08-02
   P7  Rainfall feature pipeline            🔗 SPINE        ✅ 2026-08-02
   P8  Trigger (WHEN) + hazard         AUC 0.768       ✅ 2026-08-02
   PX0 Optical cloud gate              ❌ VETO         ✅ 2026-08-02
   PX0b Radar access gate              ✅ PASS         ✅ 2026-08-02
   PX0c Radar detection gate           ❌ VETO         ✅ 2026-08-02
   P9  Daily forecast run              Open-Meteo      ✅ 2026-08-02
   P10 Delivery layer                  Streamlit app   ✅ 2026-08-02
   P11 Backtest & honest numbers       signal 3-5d ahead ✅ 2026-08-03
  ══ ✅ MVP COMPLETE (landslide) ═════════════════════════════════════
   →   Deploy: push to GitHub, connect Streamlit Cloud (webapp/DEPLOY.md)
   →   Flood roadmap starts here
  ══ PARKED (untested, resume anytime) ══════════════════════════════
   PZ  Himalayan pooled trigger  617 dated events, 10% fetched
  ══ CLOSED ═════════════════════════════════════════════════════════
   PX  Label factory — all technical routes exhausted
  ══ THE ONLY REMAINING ROUTE ═══════════════════════════════════════
   PY  GSI Landslidedata_1 — now a conclusion, not a preference
```

### ✅ LANDSLIDE MVP COMPLETE — 2026-08-03

| | |
|---|---|
| Where a slope can fail | **AUC 0.860 ± 0.016** (spatial CV, 37,788 mapped landslides) |
| When it might fail | **AUC 0.768** hindcast · **0.764 on the live data path** |
| Warning lead time | **signal present 3–5 days ahead** ([BACKTEST.md](BACKTEST.md)) |
| Deliverable | 7-day forecast web app, 0.45 MB bundle, free hosting |

**Remaining to go live:** push to GitHub and connect Streamlit Cloud —
see [webapp/DEPLOY.md](../../webapp/DEPLOY.md). ~10 minutes, needs your account.

> 🚨 **Two things never to quote.** (1) A **false-alarm rate** — it cannot be
> measured, because an alert day with no *recorded* landslide may simply be an
> unrecorded one. (2) The **end-to-end hazard AUC (0.728)** as system
> performance — it is depressed by km-level label positions. Quote the two halves
> separately and say the product is unmeasured.

> 📄 **Every attempt to enlarge the temporal inventory is recorded in
> [TEMPORAL_INVENTORY_ATTEMPTS.md](TEMPORAL_INVENTORY_ATTEMPTS.md)** — client-facing,
> including what each cost and exactly where it failed.

> ❌ **Optical vetoed** ([PX0](PX0_CLOUD_FEASIBILITY.md)): monsoon cloud gives 55–80 day
> date uncertainty against ≤7 needed.
>
> ✅ **Radar access passed** ([PX0b](PX0B_SAR_FEASIBILITY.md)): 4–5 day revisit, 99.4% of
> landslide cells viewable.
>
> ❌ **Radar detection vetoed** ([PX0c](PX0C_SAR_DETECTION.md)): mapped scars are
> indistinguishable from slope-matched hillside — AUC **0.53** against 0.50 chance, with no
> improvement for larger slides. And the decisive temporal test **cannot be run at all**:
> validating a date-generating system needs landslides that are both precisely located and
> already dated, which is exactly what we lack. **The label shortage blocks its own fix.**
>
> **All five technical routes are now closed.** What remains is cooperation, not
> engineering. Total cost of closing them: **under 5 hours**, against ~1 month of build
> avoided. **The MVP is unaffected** — P8 never depended on PX, which is why it was built
> first.
>
> ⚠️ **2026-08-02 correction — GSI `Landslidedata_1` is NOT the answer.** Re-checked live:
> the table holds **~402 rows nationally** (max OBJECTID), only 2 public, **both Tamil
> Nadu**, and its rainfall fields are partly categorical text rather than measurements.
> Arunachal's realistic share is **0–20 records** against the 72 we already have. Still
> worth an email; **must not be presented to the client as the fix.** The best remaining
> candidate is **state PWD / BRO road-blockage logs** — plausibly hundreds to thousands of
> dated events. See [TEMPORAL_INVENTORY_ATTEMPTS.md §7](TEMPORAL_INVENTORY_ATTEMPTS.md).

---

# Part A — What's already done

## P0 · Problem definition ✅

Established the product is **two forecasts** (landslide, flood), statewide, all districts.
Susceptibility is machinery, never the headline. Defined the FREE / ASK / PAID tier ladder
so capability claims stay honest about what lifts each limit.

## P1 · Data discovery ✅

Worked out what data exists, who holds it, and whether it's actually reachable. Key
findings: APSSDI's WFS is fully open (its TLS chain just needs an intermediate cert
appended); Bhuvan's WFS is disabled but `GetFeatureInfo` can be grid-harvested; GSI serves
through an ArcGIS proxy. Several portals that look closed aren't.

## P2 · Acquisition ✅

**7.7 GB across 11 categories.** Elevation, soil, lithology, lineaments, land cover,
rivers, roads, landslide inventory, flood extent, population, buildings, admin boundaries,
earthquakes, ENSO.

Headline: **35,744 mapped landslides** — up from an initial 28 usable labels. That number
is what makes the whole approach viable.

## P3 · Verification & viz ✅

Built a visualisation layer with an **"under the hood" flip switch** exposing the raw
records behind every chart. Not decoration — it immediately caught 246 out-of-state
polygons (GSI's tiles spill into Nagaland and Assam) that had inflated both the inventory
count and the district list.

**Principle to keep:** every derived number stays traceable to the file it came from.

---

# Part B — In progress

## P4 · Rainfall archive backfill 🔄

| | |
|---|---|
| **What** | Every daily IMERG rainfall field, 2000-06 → now (~9,300 days) |
| **Why** | You cannot fit a rainfall trigger without rainfall history. This is the entire WHEN half |
| **Script** | `scripts/fetch/fetch_11b_imerg_archive.py` |
| **Cost** | ~320 MB, **~1.5–2 h** — latency-bound, not bandwidth-bound |
| **Blocked by** | Nothing. NASA Earthdata, credentials already work |

Measured on a 2001 smoke test: **363/365 days in 3.7 min** at 6 workers. Two failures were
genuine archive gaps; re-running retries only those, since existing files are skipped.

The old script probed `V07C` before `V07B`, which 404s on every pre-2025 day and roughly
doubled the run. The new one probes **once per year** and caches.

✓ **Exit check:** ≥9,000 daily files on disk; no year with a suspicious hole.

---

# Part C — The build

## P5 · Grid + terrain derivatives 🔗 SPINE

**Goal:** one table where every row is a 100 m cell and every column is something known
about it. Everything downstream is a query against this table.

```
   DEM ──► slope, aspect, curvature, TWI, relief
   soil rasters ─────────────┐
   lithology polygons ───────┼──► resample / join ──► grid_100m.parquet
   lineaments ───────────────┤                        (~8.2 M rows)
   rivers, roads ────────────┘    distance-to-nearest
```

**Decide before writing code** — cheap now, expensive to reverse:

| Decision | Note |
|---|---|
| Working CRS | must be **metric** (distances and areas are meaningless in degrees) |
| Grid origin + cell size | 100 m; changing it invalidates every derived file |
| Cell ID scheme | this is the join key for the entire system |
| Column naming + dtypes | rewriting a schema mid-pipeline is pure tax |
| **Spatial block definition** | **pick your held-out regions now, before you've seen any result** — otherwise you'll unconsciously choose blocks that flatter the model |

**Why this phase first:** it's a thin vertical slice touching every move the pipeline
needs — raster resample, polygon-to-cell join, distance-to-feature. Get it working and the
plumbing is proven. It also needs no new data.

✓ **Exit check:** load the parquet; render the slope map; the steep areas are where the
mountains actually are. No nulls outside the state boundary.

### ✅ P5 COMPLETE — 2026-08-01

`data/interim/grid_100m/` — **8,202,343 rows × 40 columns**, 966 MB, partitioned by fold.
Held-out read (train on 4 folds, test on 1) takes **1.6 s**.

Built by, in order: `grid.py` (canonical constants) → `make_folds.py` → `terrain.py` →
`hydrology.py` → `distances.py` → `features.py` → `assemble.py`.

**Four independent checks passed**, each catching a different class of error:

| Check | Result |
|---|---|
| 100 m × tan(median slope) vs measured relief | 55.6 m vs 52.9 m — slope/elevation self-consistent |
| Computed drainage vs HydroSHEDS rivers | lines coincide exactly ⇒ CRS, origin, transform orientation and flow routing all correct |
| Soil texture fractions sum | clay 280 + sand 392 + silt 348 = 1,020 g/kg ≈ 1,000 |
| Land cover vs published forest area | 84.7% tree cover vs ~80% published |

Depth trends also behave: bulk density rises with depth (104→111→119), organic carbon
falls (641→287→132).

**Known gaps carried forward:**
- `geol_rockgr_cat` / `geol_lithunit_cat` — **5.78% of cells have no mapped lithology**.
  Treat as an explicit "unknown" category; do **not** silently impute a rock type.
- Two numerical guards were needed and are documented in the code: plan curvature
  divides by gradient (→ ±0.5 clip plus a 0.5° flat-ground floor), and TWI divides by
  tan(slope) (→ 0.1° floor).
- `pysheds` calls `np.in1d`, removed in NumPy 2.0 — shimmed in `hydrology.py`.

## P6 · Susceptibility model — the WHERE half

**Goal:** a 0–1 score per cell: *how capable is this slope of failing at all?* No dates.

📄 **Full detail: [LABELS_AND_SAMPLING.md](LABELS_AND_SAMPLING.md)** — every decision,
measured, including one that contradicted the plan below.

```
   37,788 polygons → 91,610 cells   →  label = 1
   constrained negative sample      →  label = 0   (1:5, 500 m buffer)
            │
            ▼
      gradient-boosted trees (LightGBM)
            │
            ▼
      susceptibility.tif  +  SHAP explanations
```

### ✅ P6a/P6b COMPLETE — 2026-08-02 · sample hash `b58e7dcc22134c1f`

`data/processed/susceptibility_samples.parquet` — 544,794 rows × 41 cols, prevalence
16.67% in **every** fold. Baseline **AUC 0.860 ± 0.016** under spatial CV, AP 0.612 vs
0.167 prevalence (3.7× lift).

### ⚠️ The stated trap did NOT apply here — measured

This roadmap previously said naive negatives would score "a fantastic AUC while telling
you nothing". **Tested on the same hard test set, only training differing:**

| trained on | AUC |
|---|---:|
| constrained | 0.860 ± 0.016 |
| naive | 0.862 ± 0.016 |

Indistinguishable. That argument assumes flat terrain is available to contaminate the
negative pool; Arunachal's median slope is 29° and 85.7% of the state is already in
domain. **There are no easy negatives here.**

Constrained sampling is still correct, for two reasons AUC *cannot* measure: 15.8% of the
naive pool sits within 500 m of a known failure (likely unreported positives — and the
test set carries the same corruption, so the metric is blind to it), and 6.3% is ice/water
where the model must not emit a score at all. See LABELS_AND_SAMPLING.md §7.

**Test honestly:** hold out whole *regions*, not random rows. Neighbouring cells share
almost identical terrain, so a random split leaks the answer. Published models reporting
0.90+ usually use random CV — **not comparable to ours.**

### ✅ P6 COMPLETE — 2026-08-02

📄 **Results, ablations and limits: [MODEL_SUSCEPTIBILITY.md](MODEL_SUSCEPTIBILITY.md)**

| | |
|---|---|
| Spatial-CV AUC | **0.860 ± 0.016** |
| Precision @ top 1% | 0.90 – 0.97 |
| High+VeryHigh = 10% of area | holds **71%** of known landslides |
| Independent (NASA GLC) | 28.6% vs 10% random (**2.9×**) |

Artefacts: `data/processed/susceptibility.tif`, `susceptibility_class.tif`,
`models/susceptibility_{fold0-4,full}.txt`, `reports/susceptibility_{map,shap}.png`.

✓ **Exit check:** AUC ≥ 0.80 under spatial block CV — **met (0.860)**.
⬜ Still open: comparison against GSI's 50 m benchmark map.

**Three findings that change how we present this:**

1. ⚠️ **GSI point "validation" is circular** — 84.6% of those points sit exactly on a
   training polygon. The honest external number is NASA GLC's 2.9×, not GSI's 7.1×.
   Never quote the GSI figure as independent.
2. ⚠️ **Under-warns at 2,000–4,000 m** — that band holds 20.3% of known slides but gets
   10.5% of High+ predictions. Label survey bias, so more model capacity won't fix it.
   Flag high-altitude corridors manually.
3. ✅ **Not a road detector** — removing road distance costs 0.009 AUC; terrain+hydro
   alone reaches 0.839 of 0.859. Lithology takes 23% of *gain* but only 0.004 of AUC —
   gain measures use, not need. Ablate before claiming any driver.

> ⚠️ **Never report the full model's own score.** Fold models for numbers, full model for
> deployment. And out-of-domain cells render as "not assessed", never "low risk".

## P7 · Rainfall feature pipeline 🔗 SPINE

**Goal:** turn a stack of daily rainfall grids into the features a trigger model reads.

📄 **Full detail: [RAINFALL_FEATURES.md](RAINFALL_FEATURES.md)**

### ✅ P7 COMPLETE — 2026-08-02

**Archive: 2000-06-01 → 2026-07-29, 9,555 days, zero gaps.** 11 feature arrays
(`r1 r3 r7 r15 r30`, `rmax_30`, `wetdays_30`, `api`, `storm_dur`, `storm_rain`,
`storm_id_ratio`) plus season and ENSO ONI.

✓ **Exit check PASSED** on the test that matters — 72 *dated* NASA GLC events, every
feature elevated vs same-cell same-month climatology, weakest at the 83rd percentile,
`r7` at the 92nd (160 mm vs 37 mm typical).

**Three findings worth carrying forward:**

1. ⚠️ **Rainfall is 11 km and stays 11 km.** Never upsampled to 100 m — `imerg_index.tif`
   maps each terrain cell to its rainfall pixel instead. Upsampling would be 78 billion
   duplicated values *and* would misrepresent the resolution in the deliverable.
2. ⚠️ **The ID threshold failed on first build** — applied to rolling windows it collapsed
   into a rescaled `r30` (r=0.973). Fixed by applying it to actual storm events; max
   correlation dropped to 0.788. Still a *relative* index, not a decision threshold: the
   global curve is exceeded 24% of days in a place this wet.
3. ⚠️ **Bhuvan's `Year` is a survey year, not a failure date.** 2014 ranks mid-pack among
   monsoons and that is expected, not a bug. Only the dated-event check proves the pipeline.

## 🚨 P8 · The data constraint, and the decision taken

**We have 90 dated landslide events.** That is the whole temporal training set: GSI has no
dates, Bhuvan has survey years only. The 35,744 labels that made P6 work are **spatial
only** — they say where, never when.

P8 therefore **cannot** be trained the way P6 was. Never train on 90 events and report an
AUC — 5-fold spatial CV gives ~18 events per fold and a confidence interval wider than the
result.

### ✅ DECIDED 2026-08-02 — build BOTH, in this order, both inside the FREE-tier MVP

```
P(trigger) = physics ID threshold      ← P8, ships the MVP, permanent floor
           + learned model on top      ← PX, added as soon as labels exist
```

These are **complementary, not alternatives.** The threshold gives a working end-to-end
forecast now and remains a sanity floor forever; the learned layer improves it later. It
also supplies the **baseline that proves the learned trigger is worth anything** — without
it you cannot tell whether ML beats simple physics. NASA LHASA v2 did exactly this.

| Order | Work | Status |
|---|---|---|
| **1** | **P8** — locally calibrated physics trigger, then hazard = susceptibility × trigger | ✅ **done 2026-08-02** |
| **2** | **PX** — cloud-cover feasibility prototype, then the label factory | 🔄 starting now |
| later | GSI `Landslidedata_1` (hour-precision dates + per-event rainfall) | production conversation |

### ✅ P8 COMPLETE — 2026-08-02

📄 **[MODEL_TRIGGER_AND_HAZARD.md](MODEL_TRIGGER_AND_HAZARD.md)**

**Trigger AUC 0.768 ± 0.098.** At a 0.90 trigger: 7.5% of monsoon days flagged, 41.7% of
events caught, 5.6× lift. Artefacts: `models/trigger.json`, `scripts/model/hazard.py`,
`reports/trigger_validation.png`, `reports/hazard_validation.{json,png}`.

**Three measured findings that changed the design:**

1. ⚠️ **The classic intensity–duration form is wrong here** — fitted b came out *negative*
   because our storm runs reach 202 days in a monsoon, so "duration" isn't storm length.
   Switched to event-rainfall–duration (`corr(log D, log E) = +0.91`).
2. ⚠️ **A rainfall threshold can't be a binary gate** — any envelope fitted to real events
   fires 99–166 days/yr. Kept as explainable physics; the trigger is a continuous score.
3. ⚠️ **Fitting on 72 events loses to not fitting** — logistic 5-fold CV 0.755 vs 0.768 for
   an unfitted percentile average. Direct evidence for the no-trigger-model rule.

> 🚨 **Do not quote the end-to-end 0.728 as system performance.** NASA GLC's km-level
> location error cripples a 100 m layer while barely touching an 11 km one — susceptibility
> AUC runs 0.778 / 0.722 / 0.602 as label accuracy degrades from 1 km to 50 km. Quote the
> two halves separately (0.860 and 0.768) and say the product is unmeasured until PX.

⚠️ **PX starts with the prototype, and the prototype can veto it.** 86% of dated landslides
occur May–October — peak monsoon, peak cloud. The imagery we need is exactly the imagery
hardest to get. The prototype tests against the 90 events whose dates we already know: *if
we cannot recover dates we already have, we cannot discover dates we don't.* See
[RAINFALL_FEATURES.md §7](RAINFALL_FEATURES.md).

> ⚠️ Dating our own polygons does **not** turn the 36k spatial inventory into 36k temporal
> labels. Sentinel-2 starts 2015; anything that failed earlier is already a scar in every
> image and is undateable. Realistic yield is low thousands, carved out of the spatial set.

## P8 · Trigger model — the WHEN half

**The hardest phase.** Read [DESIGN.md](DESIGN.md) Part 8 before starting.

Training data is *manufactured*, three ways stacked:

| Source | Yield | Quality |
|---|---|---|
| Weak labels — Bhuvan year-tags × that year's extreme-rain days | ~5,800 | imprecise but usable in bulk |
| Pooled Himalayan dated events (NASA COOLR, Froude & Petley) | ~2,000–5,000 | good; ⚠️ **exclude earthquake-triggered** |
| NASA GLC exact dates | ~90 | strong, but coarse locations |

Model: **gradient-boosted trees**, not a neural network — the data is tabular and small,
trees win at this size and can explain a score. Physics acts as a **feature** (the ID ratio)
and as an **alert floor** (never fire below the established curve).

> ⚠️ **The problem bigger than the label shortage: negatives.** "It rained 180 mm and
> nothing failed" is easy to generate and often *wrong* — landslides are heavily
> under-reported, so many quiet days actually had unrecorded slides. No amount of extra
> data fixes this. Draw negatives only from well-mapped corridors and periods where an
> absence is genuinely credible.

✓ **Exit check:** POD/FAR measured on **held-out years**, not held-out rows. A model that
looks good on random rows and bad on a held-out monsoon is overfit.

## P9 · Daily forecast run 🔗 SPINE

**Goal:** the thing that actually runs every morning, unattended.

```
   fetch yesterday's IMERG + today's GFS forecast
        ▼
   compute rainfall features
        ▼
   HAZARD = susceptibility × P(trigger)      ← the two halves finally meet
        ▼
   aggregate 100 m cells → reporting circles
        ▼
   join population & buildings → risk, not just hazard
        ▼
   store the run (every run is kept — this is how you backtest later)
```

**Keep every historical run.** Not optional: it's the only way to prove skill honestly, and
each live monsoon becomes training data for the next model version.

✓ **Exit check:** runs 7 consecutive days with zero intervention, including recovering from
one deliberately failed fetch.

## P10 · Delivery layer 🔗 SPINE

API · dashboard map · bulletin generator · alert dispatch.

**Entirely hazard-agnostic.** Flood plugs into this exact layer — if the schema says
`landslide_risk` instead of `hazard_type` + `risk`, the flood roadmap starts with a
migration. The alert bulletin should render from a hazard-neutral template.

✓ **Exit check:** a district officer can open the map, see their circle, and understand the
alert without a briefing.

## P11 · Backtest & honest numbers

Replay past monsoons. Report **POD and FAR** as measured, not as hoped.

> **Threshold placement is a client policy decision, not a technical parameter.** A false
> alarm costs a road crew a standby day; a miss costs lives. Present the tradeoff curve and
> **put their choice in writing.**

Expected free-tier honest range: **POD 55–70%, FAR 40–60%.**

✓ **Exit check:** a written performance sheet you'd be comfortable defending in a review
meeting where someone disagrees with you.

---

# 🏁 Landslide MVP complete → Flood roadmap begins

At this point the shared spine (P5, P7, P9, P10) is built and hazard-agnostic. The flood
roadmap reuses it and adds only the flood-specific legs: GloFAS for large rivers,
rainfall-accumulation watch for small mountain streams, and the flood extent benchmark.

---

# Part D — Parallel tracks

These don't block the MVP and shouldn't be scheduled into it — but starting them early
compounds.

## PX · Label factory — ⚠️ OPTICAL DEAD, RADAR ALIVE

> ❌ **Optical vetoed** ([PX0_CLOUD_FEASIBILITY.md](PX0_CLOUD_FEASIBILITY.md)). Sentinel-2
> gives **55–80 day** date uncertainty against ≤7 needed; at the ≤20% cloud level real
> change detection wants, **80% of test events have no usable image pair at all**. It was
> "the item most likely to fail", and it failed for the predicted reason on a ~20-min test.
>
> ✅ **Radar cleared its data gate** ([PX0B_SAR_FEASIBILITY.md](PX0B_SAR_FEASIBILITY.md)).
> Sentinel-1 ignores cloud entirely: **4–5 day revisit**, and **99.4%** of mapped landslide
> cells are viewable from at least one orbit direction. The layover/shadow objection was
> real but overstated — ascending and descending look at opposite sides and between them
> rescue nearly everything.

### ⬜ PX0c · SAR detection prototype — the next gate

PX0b proved the satellite **can see the slope, often enough**. It did **not** prove a model
can spot a scar in radar, which is materially harder than in optical:

- **speckle** — SAR is inherently noisy, single images are unreliable
- **confounders** — soil moisture, vegetation growth and harvest all shift backscatter
- **processing** — needs multi-temporal stacks and radiometric terrain correction

**Test:** landslides with known dates → build an amplitude change stack → is the scar
detectable above the seasonal backscatter noise floor? Same principle as every gate here:
*validate against answers we already have.* **If PX0c fails, PX ends.** ~2 days.

📄 All attempts, costs and failure points: **[TEMPORAL_INVENTORY_ATTEMPTS.md](TEMPORAL_INVENTORY_ATTEMPTS.md)**

The original optical plan is kept below for the record.

---

**The highest-leverage item in the whole plan, and the one most likely to fail.**

We own 37,788 polygons with almost no dates. A scar appears in satellite imagery at a
specific time — Sentinel-2 back to 2015, Landsat to 1984. Recover those dates and the
temporal training data we're starved of becomes *local* and correctly biased, instead of
imported from other states.

**This is the one genuine neural-network job in the system** — image segmentation over a
time series. It sits **offline**, feeding the training set, never touching a live forecast,
so it adds no opacity to anything the client sees.

### PX0 · Cloud-cover feasibility prototype — the veto gate

> ⏱️ **~1 day. Nothing else in PX starts until this passes.**

**The risk it tests:** 86% of dated landslides occur May–October — peak monsoon, peak
cloud. *The imagery we need is exactly the imagery hardest to get.* Sentinel-2 revisits
every 5 days, but if monsoon cloud blocks most passes the clear-image gap may stretch to
weeks. A label reading *"failed sometime between 3 June and 18 July"* is nearly useless
for a model that must pick a **day** — it rained hard the whole window.

**Method:** take the 90 NASA GLC events whose dates we already know. Pull imagery around
each. Measure (a) the clear-observation gap either side, (b) whether the scar is visible
in the first clear image after.

> *If we cannot recover dates we already have, we cannot discover dates we don't.*

✓ **Pass:** median date uncertainty ≤ ~1 week on a useful fraction of events.
✗ **Fail:** stop. Ship the P8 physics trigger alone and spend the time on PY instead.

### ⚠️ Expected yield — not 36k

Change detection only dates a slide that **appeared** during the imagery record.
Sentinel-2 starts 2015; anything that failed earlier is already a scar in every image, and
GSI's 26k polygons have unknown ages with many old or relict. Realistic yield is **low
thousands**, carved out of the spatial inventory — not a temporal twin of it. Plan capacity
and expectations on that number, not on 36k.

## PZ · Himalayan pooled trigger — ⏸️ PARKED

📄 **[PARKED_HIMALAYAN_POOLED_TRIGGER.md](PARKED_HIMALAYAN_POOLED_TRIGGER.md)** — full resume
instructions, state on disk, and risks.

**Paused 2026-08-02 by decision, not by failure.** The one route to a genuine ML trigger
that needs no new data, no permission and no fieldwork: **617 dated Himalayan landslides**
already public (~9× Arunachal's 72), same IMERG features, validated by **training on the arc
excluding Arunachal and testing on Arunachal's own 72 events**.

**Bar to clear: AUC 0.768**, the physics trigger's score. Beat it and we ship an ML trigger
proven on held-out ground in the client's own state; miss it and nothing is lost.

**State:** 751 of 7,519 days fetched (10%, 38 MB of ~380 MB). Fetcher is restartable —
rerun `scripts/fetch/fetch_11d_imerg_himalaya.py` and it resumes at day 752.
**Resume cost:** ~3 h unattended fetch + ~1 day of work.

## PY · Government asks

> 🔺 **Promoted 2026-08-02.** With PX vetoed, imagery cannot enlarge our 72 dated events.
> `Landslidedata_1` is now the **single highest-value item in the project** — it is the
> only route left to a real trigger model, and it is an ask rather than a build.

> 📌 **Scope note.** This roadmap targets an **MVP for presentation**, not a production
> deployment. Everything below is a single batch of asks for the production conversation —
> including publication permission for the GSI/Bhuvan inventories. **Not an MVP blocker;
> do not raise it in MVP status reporting.**

| Ask | Buys | Realistic scale |
|---|---|---|
| 🥇 **APSAC — SILAAS project data + methodology** | **The client's own state agency** (Dept. of Science & Technology, Govt. of Arunachal). Ran the 2023 post-monsoon inventory: 3,592 landslides that **occurred in 2023**, field-verified via their FLIM mobile app. Ask for: the FLIM records (may carry actual **dates**), the 2014/2017 methodology, and whether 2024/2025 cycles exist | **thousands, already dated to a season** |
| 🥈 **State PWD / BRO road-blockage logs** | every landslide that closed a road, **with a date**. Kept for decades for operational reasons | hundreds–thousands |
| **GSI `Landslidedata_1`** | correct schema and some measured rainfall — but see the ⚠️ below. Cheap to request, will not close the gap | **0–20 for Arunachal** |
| GSI/Bhuvan publication permission | clears redistribution for production; bundle with the above | — |
| IMD rain gauges | resolution above 2,500 m where satellite estimates drift | — |

> ⚠️ **`Landslidedata_1` was over-promised in earlier drafts of this roadmap.** Verified
> live on 2026-08-02: max OBJECTID **402 nationally**, only 2 rows public, **both Tamil
> Nadu**, `date_acc`/`geo_acc` unpopulated, and rainfall duration/intensity stored as
> dropdown text (*"The last few days, but less than a week"*) rather than measurements. It
> is the Bhooskhalan field-reporting app backend. Request it — it costs an email — but
> **do not tell the client it solves the timing problem.**

**Ask GSI one extra question:** *is the table every recorded event, or only notable ones?*
If systematic, absence becomes real evidence of non-failure — which gives us credible
negatives, worth more than the positives.

> 💡 **Now quantified (P6):** 15.8% of any naive negative draw sits within 500 m of a known
> failure. We buffer those out, but that is mitigation, not a fix — a systematic GSI
> confirmation is the only thing that turns absence into genuine evidence. See
> [LABELS_AND_SAMPLING.md §1](LABELS_AND_SAMPLING.md).

---

# Sequencing rules

1. **P5 before everything.** It's the join key for the whole system.
2. **P6 needs no rainfall** — build it while P4 downloads.
3. **P8 is the risky phase.** Budget slack there, not in P5/P6.
4. **Anything marked 🔗 SPINE takes a `hazard` argument.** No exceptions.
5. **Choose spatial validation blocks before seeing any result.**
6. **Never report a number you haven't spatially cross-validated.**

# The five ways this goes wrong

| Risk | Mitigation |
|---|---|
| Negatives sampled carelessly → beautiful AUC, useless model | constrained sampling, both in space (P6) and time (P8) |
| Random train/test split → inflated scores | spatial blocks, chosen up front |
| Spine hardcoded to landslide → flood becomes a rewrite | `hazard` argument from day one |
| Under-reporting poisons the trigger's negatives | restrict to well-mapped corridors; push hard for the GSI table |
| Client hears "prediction" and expects slope-and-hour precision | state the tier ladder every time: FREE = area/day; PAID + sensors = one slope, hours ahead |
