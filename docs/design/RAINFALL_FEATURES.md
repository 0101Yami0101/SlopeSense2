# Rainfall Features (P7) — the trigger pipeline

**Status:** complete 2026-08-02 · 🔗 **SPINE** — flood reuses this stage unchanged
**Scripts:** [rainfall_stack.py](../../scripts/build/rainfall_stack.py) · [rainfall_features.py](../../scripts/build/rainfall_features.py) · [check_rainfall.py](../../scripts/build/check_rainfall.py)

Turns 9,555 daily IMERG files into the features a trigger model reads. This is
the WHEN half's input; the model itself is P8.

---

## 1. The archive

| | |
|---|---|
| Coverage | **2000-06-01 → 2026-07-29, 9,555 days, zero gaps** |
| Source | GPM IMERG Late Daily V07B/V07C (NASA GES DISC) |
| Native resolution | **0.1° ≈ 11 km** |
| Grid | 31 lat × 63 lon = 1,953 cells (892 cover Arunachal) |
| Size | 326 MB raw, 75 MB as one array |

The last 81 days were recovered by [fetch_11c_imerg_gapfill.py](../../scripts/fetch/fetch_11c_imerg_gapfill.py).
The backfill probes V07B first (right for 2000–2025) and caches per year, so it
kept requesting V07B into 2026 and 404'd. The gap-filler tries both versions
with no caching. **Four days I had written off as archive holes turned out to be
the same version bug** — always re-probe before declaring data missing.

---

## 2. ⚠️ Rainfall is NOT resampled to 100 m

IMERG is 11 km; our terrain grid is 100 m. Upsampling would mean 8.2 M × 9,555 =
**78 billion values**, ~12,000 identical copies per rainfall pixel.

Instead rainfall stays native and `imerg_index.tif` stores one integer per
terrain cell naming its rainfall pixel. Models join on `(imerg_index, date)`.
Same information, four orders of magnitude less storage. Verified: **0 in-state
cells unmapped.**

> This is also an honesty constraint. A 100 m rainfall raster *looks* like a
> 100 m product and invites exactly that misreading. It is 11 km data and the
> deliverable must say so.

---

## 3. Orientation traps (both caught by self-check)

1. IMERG's OPeNDAP subset returns dims ordered **(time, lon, lat)** — lon before
   lat. Reading as (lat, lon) gives a silently transposed grid.
2. lat **ascends** (26.55 → 29.55); rasters are north-up, so it must be flipped.

Both are handled once in `rainfall_stack.py` so nothing downstream thinks about it.

### The self-check that was wrong

The original check asserted the wettest pixel should be the SW foothills. It
fired a warning — but the data was right and **the assertion was wrong**.

The robust signal is the latitudinal gradient, and it is textbook orographic:

| latitude | mean annual |
|---|---:|
| 29.55°N (northern crest) | 799 mm |
| 28.05°N | 2,126 mm |
| **27.15°N (foothill belt)** | **2,763 mm** |
| 26.55°N (Assam plains) | 2,341 mm |

The wettest *individual* pixels (4,167 mm/yr at 28.55°N, 94.75°E) sit in the
**Siang gorge**, where the Tsangpo cuts the Himalaya and funnels monsoon air deep
inside the range — a real local maximum far north of the foothills. The check now
tests the gradient, not the argmax.

Seasonal cycle peaks July at 12.68 mm/day. Correct monsoon signature.

---

## 4. Features

Each is a `(9555, 1953)` float32 array in `data/interim/rainfall/features/`.

| Feature | Meaning |
|---|---|
| `r1 r3 r7 r15 r30` | trailing rainfall totals, mm |
| `rmax_30` | wettest single day in the last 30 |
| `wetdays_30` | days >1 mm in the last 30 |
| `api` | antecedent precipitation index, 0.92^age decay |
| `storm_dur` | length of the wet spell in progress, days |
| `storm_rain` | rain accumulated in that spell, mm |
| `storm_id_ratio` | ID-threshold exceedance for the spell |

Plus `date_features.parquet`: month, day-of-year sin/cos, monsoon flag, and
**ENSO ONI** (99.4% of days matched).

First 29 days are NaN — the archive starts 2000-06-01, so they genuinely have no
antecedent history and must not pretend to.

**Why both short and long windows:** `r1`/`r3` is the burst that breaks the
slope; `r15`/`r30` is the wetting that decided whether the burst was enough. The
same 100 mm day is unremarkable on dry ground and lethal on saturated ground.

---

## 5. ⚠️ The ID threshold — first attempt failed, measured

Rainfall-triggered landsliding follows an intensity–duration relation
`I = a·D^-b`. We use Guzzetti (2008) global, `I = 2.20·D^-0.44`.

**First implementation applied it to the rolling windows** and took the worst
exceedance across durations. Measured result:

| | |
|---|---:|
| correlation with `r30` | **0.973** |
| exceedances driven by the 30-day window | **67.4%** |
| days over the curve | 53.4% |

It was a rescaled 30-day total wearing a physics costume. The cause is
conceptual, not a coding slip: during a monsoon it rains near-continuously, so a
rolling 30-day window is **not a storm duration** — and cumulative rain grows
faster with D than the threshold decays, so the longest window always wins.

**Fix: apply the curve to actual storm events** — maximal runs of consecutive
days above 1 mm. Duration then means "how long has it been raining", which is
what the ID relation is about.

| | before | after |
|---|---:|---:|
| max correlation with any rolling total | 0.973 | **0.788** |
| `storm_dur` vs `r30` | — | 0.485 |
| days over the curve | 53.4% | 24.1% |

Now carries independent information.

> ⚠️ **Still a relative index, not a decision threshold.** Guzzetti is a *global*
> curve and Arunachal averages 1,931 mm/yr against a global land mean nearer 800.
> 24% exceedance is far too frequent to mean "expect a landslide". It ranks storm
> severity; it does not decide. Local calibration needs dated events — see §7.
> Constants are module-level, so recalibration is a one-line change.

---

## 6. Exit check — PASS

### Dated events (decisive)

72 NASA GLC events matched to a cell and day, against climatology for the **same
cells in the same calendar months**:

| feature | on event | climatology | percentile |
|---|---:|---:|---:|
| r1 | 16.4 mm | 2.2 | 85th |
| r3 | 68.0 mm | 11.6 | 90th |
| **r7** | **160.1 mm** | **37.4** | **92nd** |
| r15 | 290.3 mm | 97.5 | 90th |
| r30 | 546.4 mm | 215.6 | 90th |
| api | 228.8 | 86.9 | 90th |
| storm_dur | 9.0 d | 1.0 | 83rd |
| **storm_id_ratio** | **4.7** | **0.4** | 89th |

**Every feature elevated; weakest at the 83rd percentile.** `r7` separates best
(4.3× climatology) — consistent with the literature: multi-day wetting plus a
burst. `storm_id_ratio` shows the largest ratio at 12×, vindicating §5's fix.

This validates date parsing, grid orientation and window alignment together.

> ⚠️ `ev_date` arrives from ArcGIS as **epoch milliseconds**. Parsed as a plain
> datetime it silently yields 1970 for every row and the test looks broken.

### Bhuvan survey years (weak — and why)

Peak 7-day monsoon rain at the cells that failed, ranked against 25 monsoons:

| inventory | rank | z |
|---|---:|---:|
| 2014 | #12 / 25 | −0.19 |
| **2017** | **#3 / 25** | **+1.42** |
| 2023 | #8 / 25 | +0.55 |

2017 ranking #3 is a real temporal signal — and independently corroborated by
NASA GLC recording **30 of its 90 events in 2017**, its worst year.

⚠️ **CORRECTED 2026-08-02.** This section previously claimed Bhuvan's `Year` was a
*survey* year rather than a failure year. **That was wrong** — see
[TEMPORAL_INVENTORY_ATTEMPTS.md §3b](TEMPORAL_INVENTORY_ATTEMPTS.md). The three
inventories overlap only ~4% over identical ground, and APSAC states the 2023
SILAAS inventory covers *"landslides occurred during 2023"*, post-monsoon and
field-verified. **The year is the event year.**

2014's mid-pack rainfall rank therefore remains a genuine loose end rather than an
explained one. Most likely 2014 was a baseline cycle; its methodology is Bhuvan's
and unverified, unlike 2023's. Worth resolving via the APSAC ask.

---

## 7. 🚨 What this means for P8 — read before starting

**We have 90 dated landslide events. That is the entire temporal training set.**

| source | polygons/points | usable dates |
|---|---:|---|
| GSI | 26,459 | **none** |
| Bhuvan 2014/2017/2023 | 11,329 | survey year only — **not failure dates** |
| NASA GLC | 99 | **90**, 2008–2018, coarse location |

The 35,744 labels that made susceptibility work are **spatial only**. They say
where, never when. So P8 cannot be trained the way P6 was, and no amount of
model capacity substitutes for dates that do not exist.

### ✅ Decided 2026-08-02 — both, in order, both inside the FREE-tier MVP

```
P(trigger) = physics ID threshold      ← P8, ships the MVP, permanent floor
           + learned model on top      ← PX, added as soon as labels exist
```

**1. P8 — calibrate the ID threshold locally** on the 90 events. Transparent,
defensible, no invented labels, and it produces a working end-to-end forecast
immediately. It also becomes the baseline that proves whether a learned trigger
is worth anything.

**2. PX — label factory**, starting immediately after, with a cloud-cover
prototype that can veto it.

> ⚠️ Never train a trigger model on 90 events and report an AUC. With 5-fold
> spatial CV that is ~18 events per fold; the CI would be wider than the result.

### ⚠️ Why the PX prototype comes first

**86% of dated landslides occur May–October** (31 of 90 in July alone) — peak
monsoon, peak cloud. The imagery we need is exactly the imagery hardest to get.

Sentinel-2 revisits every 5 days, but if monsoon cloud blocks most passes the
clear-image gap may stretch to weeks. A label reading *"failed sometime between
3 June and 18 July"* is nearly useless for a model that must pick a **day** — it
rained hard throughout that window.

**The prototype:** take the 90 events whose dates we already know, pull imagery
around each, and measure the clear-observation gap and scar visibility. *If we
cannot recover dates we already have, we cannot discover dates we don't.* ~1 day
of work; prevents weeks spent building a factory that emits unusable labels.

### ⚠️ It will not yield 36k dated labels

Change detection can only date a slide that **appeared** during the imagery
record. Sentinel-2 starts 2015; anything that failed earlier is already a scar in
every image. GSI's 26k polygons have unknown ages and many are old or relict.
Realistic yield is **low thousands**, carved out of the spatial inventory — not a
temporal twin of it.

---

## 8. Reproducing

```bash
python scripts/fetch/fetch_11c_imerg_gapfill.py   # ensure no gaps
python scripts/build/rainfall_stack.py            # ~1,050 s (I/O bound)
python scripts/build/rainfall_features.py         # ~10 s
python scripts/build/check_rainfall.py            # exit check
```

The stack is I/O bound — ~100 ms per file, dominated by `xarray.open_dataset`
overhead on 9,555 small files. A rebuild would be ~10× faster with netCDF4
directly, but it is a one-time cost and clarity won.
