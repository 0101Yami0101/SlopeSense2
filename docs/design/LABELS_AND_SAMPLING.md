# Labels and Sampling — how the susceptibility training set was built

**Status:** frozen 2026-08-02 · **Sample hash** `b58e7dcc22134c1f` · **Fold hash** `ce08e9f0124386ac`
**Scripts:** [labels.py](../../scripts/build/labels.py) · [sample.py](../../scripts/build/sample.py)
**Output:** `data/processed/susceptibility_samples.parquet` — 544,794 rows × 41 cols

This document exists so that nobody — including us, in three months, writing the
client deliverable — has to reverse-engineer why the training set looks the way
it does. Every number here is measured, not assumed. Where a measurement
contradicted the standard practice, the contradiction is recorded rather than
quietly dropped.

---

## 1. The one thing to understand first

**We have no true negatives.**

We have 91,610 grid cells where somebody mapped a landslide. We have **zero**
cells where a surveyor checked and certified "no landslide here". Most of
Arunachal has never been walked. Absence of a record is not evidence of absence.

This is a *presence-only* problem wearing a presence/absence costume, and it
drives everything below. Three consequences we accept openly rather than
discover during review:

1. **Model outputs are relative susceptibility, not event probability.** Rank
   metrics (AUC, precision@k) are meaningful. "12% chance of failure" is not,
   until calibrated against something real.
2. **Some negatives are landslides nobody recorded.** This puts a ceiling on
   achievable accuracy that no amount of extra data or model capacity lifts.
3. **Reported skill is optimistic relative to the field.** This must be stated
   in the deliverable, not buried.

---

## 2. Label sources

| Source | Features | Cells on grid | Role |
|---|---:|---:|---|
| GSI NLFC polygons | 26,459 | 63,773 | positive |
| Bhuvan 2014 | 3,029 | 7,372 | positive |
| Bhuvan 2017 | 4,708 | 12,507 | positive |
| Bhuvan 2023 | 3,592 | 14,969 | positive |
| **Union** | **37,788** | **91,610** (1.117% of state) | |
| GSI points | 1,322 | — | **validation only** |
| NASA GLC points | 99 | — | **validation only** |

### Why the point inventories are excluded from training

GSI point locations are km-level centroids; NASA GLC states its location
accuracy is coarse. Rasterising a point to a 100 m cell asserts a precision the
source does not have. They are held back as an *independent* check — a model
trained only on polygons can be scored against points it never saw.

### Licence note (deferred — not an MVP concern)

`_SOURCES.json` records the GSI datasets as RESTRICTED and Bhuvan terms as
unstated. **Deliberately deferred:** this is an MVP for presentation, and
publication permission will be requested in one batch alongside the other GSI
datasets when the project moves toward production. Recorded here for that
conversation; it does not affect development or MVP delivery.

---

## 3. Rasterisation: `all_touched=True`

Measured on the GSI inventory:

| | |
|---|---:|
| median landslide polygon | **944 m²** (~30 × 30 m) |
| p90 | 8,373 m² |
| **smaller than one 100 m cell** | **91.5%** |

Nine in ten mapped landslides are smaller than a single grid cell. Under
centre-in-polygon rasterisation (`all_touched=False`, which the *terrain* layers
correctly use) a cell only activates when the polygon covers its centre — so the
overwhelming majority of positives would be **silently discarded**, and the
survivors biased toward large slides, which behave differently.

So: a cell is positive if a landslide polygon touches it at all.

> **Read the label as "a failure occurred somewhere in this cell", not "this
> whole cell failed."** At 100 m that is the honest reading either way.

---

## 4. Inventory overlap — checked, not assumed

Only **6.6%** of positive cells are marked by two or more inventories; 92.9% by
just one. That is low enough to suspect a systematic geolocation offset between
GSI and Bhuvan, which would mean the same physical slide landing in different
cells and our union double-counting it.

**Tested.** Distance from each Bhuvan cell to the nearest GSI cell:

| p10 | p25 | p50 | p75 | p90 | p99 |
|---:|---:|---:|---:|---:|---:|
| 0 m | 100 m | 424 m | 1,345 m | 3,493 m | 12,771 m |

A systematic offset would produce a sharp mode at a fixed distance. This is
smooth from zero — 29.7% within 100 m, but 17.6% beyond 2 km. **The inventories
genuinely map different landslides**, which is expected: GSI is a cumulative
spatial inventory, Bhuvan is per-season (2014/2017/2023). The union is
legitimate and both sources add real information.

We deliberately do **not** attempt feature-level dedup — geometric matching of
differently-digitised outlines is guesswork. We union at the raster level, so a
cell is positive once regardless of how many inventories mark it.
`label_nsource_cat` retains the agreement count, which is useful when auditing:
cells several inventories agree on are the ones to trust most.

---

## 5. The modelling domain

Applied **identically to both classes**:

| Rule | Effect |
|---|---|
| `slope > 10°` | keeps 99.3% of positives, drops 8.7% of state |
| land cover ∉ {snow/ice, permanent water, moss/lichen} | drops 6.3% |
| **domain total** | **7,030,010 cells — 85.7% of the state** |

Land cover, state share vs share of positives:

| Class | of state | of positives |
|---|---:|---:|
| snow and ice | 1.95% | **0.00%** |
| moss and lichen | 3.70% | 0.11% |
| permanent water | 0.61% | 0.11% |
| tree cover | 84.66% | 94.78% |

### ⚠️ The filter is applied to positives too

Filtering only negatives would leave positives sitting in regions containing no
negatives at all, and the model would learn *"land cover 70 ⇒ landslide"* — the
exact inverse of the truth, from a pure sampling artefact. **Symmetry is not
optional.** This drops 811 positives (0.9%), which is the correct price.

### ⚠️ Deployment requirement, not a nicety

Out-of-domain cells **must be masked at inference and reported as "not
assessed"**, never scored. A model that never saw a glacier in training has no
business assigning one a number. This is a hard requirement on the daily run
(P8), recorded here because it originates here.

---

## 6. Negative sampling

| Parameter | Value |
|---|---|
| buffer from any mapped slide | **500 m** |
| ratio | **1 : 5** positive : negative |
| stratification | within fold, proportional to that fold's positives |
| seed | `1337` |

**The 500 m buffer.** A cell 100 m from a mapped landslide is on the same
hillside, in the same rock, under the same rain. Calling it a negative teaches a
distinction that does not physically exist — and it is very likely an unreported
positive. 500 m ≈ 5 cells: far enough to leave the failure's own slope, close
enough that negatives are not drawn from a different landscape.

**Fold-proportional stratification** keeps prevalence identical (16.67%) across
all five folds. Otherwise fold 3's AUC would not be comparable to fold 1's and
spatial CV would partly measure sampling noise.

Result — every fold balanced, negative pools never exhausted:

| fold | positives | negative pool | drawn | ratio |
|---:|---:|---:|---:|---:|
| 0 | 15,410 | 957,414 | 77,050 | 5.0 |
| 1 | 21,745 | 1,149,943 | 108,725 | 5.0 |
| 2 | 15,363 | 1,127,851 | 76,815 | 5.0 |
| 3 | 22,730 | 1,295,929 | 113,650 | 5.0 |
| 4 | 15,551 | 1,165,295 | 77,755 | 5.0 |

---

## 7. ⚠️ What this sampling does and does NOT buy — measured, against expectation

The standard argument for constrained negative sampling is that random negatives
make the task trivial and inflate the reported score. **We tested it. For
Arunachal it is false.**

Like-for-like — same hard test set, only the *training* sample differs:

| Training sample | AUC on hard test set |
|---|---:|
| constrained | 0.860 ± 0.016 |
| **naive** (random negatives, no constraints) | **0.862 ± 0.016** |
| difference | **−0.002** |

And single-feature difficulty barely moves either:

| | slope-alone AUC |
|---|---:|
| constrained sample | 0.609 |
| naive sample | 0.639 |

Identical within fold noise. **Why:** the textbook argument assumes mixed terrain
with flat plains available to contaminate the negative pool. Arunachal has almost
none — median slope 29°, and 85.7% of the state is already in domain. *There are
no easy negatives here to do the damage.*

> **Do not defend this sampling on accuracy grounds.** The number does not move,
> and a reviewer who checks will discover that. Defend it on the two grounds AUC
> structurally cannot measure:

**1. Label validity.** 15.8% of the naive negative pool lies within 500 m of a
mapped failure — **~71,600 cells** in a 1:5 draw. Those are exactly the cells
most likely to be unreported positives. Training on them means fitting known-bad
labels, and **AUC is blind to it because the test set carries the identical
corruption.** A metric cannot see its own blind spot. This is the single
strongest reason the buffer stays.

**2. Deployment honesty.** 6.3% of the pool is ice, water or alpine moss —
**~28,700 cells**. Covered in §5.

Together ~22% of a naive negative draw is either probably mislabelled or out of
domain. **That is the justification. Not the score.**

---

## 8. Baseline result (LightGBM, spatial CV)

Leave-one-fold-out over the 50 km spatial blocks frozen in `spatial_folds.parquet`:

| holdout fold | AUC | AP | n |
|---:|---:|---:|---:|
| 0 | 0.878 | 0.626 | 92,460 |
| 1 | 0.837 | 0.573 | 130,470 |
| 2 | 0.857 | 0.627 | 92,178 |
| 3 | 0.878 | 0.654 | 136,380 |
| 4 | 0.850 | 0.581 | 93,306 |
| **mean** | **0.860 ± 0.016** | **0.612** | |
| baseline AP (prevalence) | | 0.167 | |

**AP 0.612 vs 0.167 = 3.7× lift.** Fold spread of ±0.016 means it generalises
across space rather than memorising surveyed pockets.

This is honest spatial CV. Much of the published literature reports 0.90+ using
*random* CV, which leaks neighbouring cells between train and test and is not
comparable. **Do not benchmark against those numbers without noting the
protocol difference.**

### ⚠️ Strongest single feature is elevation (AUC 0.728) — treat with suspicion

Elevation outranks slope (0.609). Some of that is real (altitude controls
weathering, freeze-thaw, vegetation). But elevation is also a strong proxy for
**survey accessibility** — surveyors map what they can reach. Part of what the
model reads as "high elevation is dangerous" may be "mid-elevations get
surveyed". Flag when interpreting SHAP for APSDMA; do not present elevation
importance as pure physics. Same caveat already recorded for road proximity in
[distances.py](../../scripts/build/distances.py).

---

## 9. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | Lithology unknown = 6.11% of sample, kept as explicit category `0`, **not** imputed | nothing — resolved this way deliberately |
| 2 | Elevation accessibility bias — quantified in [MODEL_SUSCEPTIBILITY.md §7](MODEL_SUSCEPTIBILITY.md) | operational use |
| 3 | GSI/Bhuvan publication permission | production only — **deferred, not MVP** |

---

## 10. Reproducing

```bash
python scripts/build/labels.py     # ~20 s  -> data/interim/labels/
python scripts/build/sample.py     # ~21 s  -> data/processed/susceptibility_samples.parquet
```

Both are deterministic. `sample.py` prints a **sample hash** over
`(cell_id, label, fold)`; if it is not `b58e7dcc22134c1f`, the sample changed and
every number in §7–8 is void.

**Change policy.** Editing §3, §5 or §6 changes the training set and invalidates
all reported metrics. Editing §5 or §6 *after* a model is trained and reported
**voids every published number** — same rule as `DATA_CONTRACT.md` §6.
