# Susceptibility Model — results, ablations and honest limits

**Status:** P6 complete 2026-08-02 · **Sample hash** `b58e7dcc22134c1f` · **Fold hash** `ce08e9f0124386ac`
**Scripts:** [train_susceptibility.py](../../scripts/model/train_susceptibility.py) · [predict_susceptibility.py](../../scripts/model/predict_susceptibility.py)
**Inputs:** [LABELS_AND_SAMPLING.md](LABELS_AND_SAMPLING.md) · [DATA_CONTRACT.md](DATA_CONTRACT.md)

This is the WHERE half of `HAZARD = SUSCEPTIBILITY × P(trigger)`. It answers
*"how capable is this slope of failing at all?"* — no dates, no rainfall.

---

## 1. Headline

| Metric | Value |
|---|---|
| Spatial-CV AUC | **0.860 ± 0.016** |
| Average precision | 0.612 (baseline 0.167 → **3.7× lift**) |
| Precision @ top 1% | **0.90 – 0.97** |
| High + Very High = 10% of area | holds **71%** of known landslides |
| Very High = 3% of area | holds **40%** of known landslides (**13.4× lift**) |
| Independent check (NASA GLC) | 28.6% in High/Very High vs 10% random (**2.9×**) |

Outputs: `data/processed/susceptibility.tif` (float32 index) and
`susceptibility_class.tif` (uint8, 1–5, **0 = not assessed**).

---

## 2. ⚠️ What the number is NOT

Trained on a 1:5 sample (16.67% positive) against a real mapped prevalence of
~1.3%. **A score of 0.5 does not mean "50% chance of failure."**

It is a **relative susceptibility index** — valid for ranking, percentile
classing and precision@k. It cannot be rescaled into an event probability,
because the label is presence-only: the denominator that would make it a
probability does not exist ([LABELS_AND_SAMPLING.md §1](LABELS_AND_SAMPLING.md)).

Present it as five classes. That is what a disaster-management authority uses
and what the literature reports.

---

## 3. Two model sets — never confuse them

| | trained on | use for |
|---|---|---|
| `susceptibility_fold{0..4}.txt` | 4 of 5 spatial folds | **reporting every number** |
| `susceptibility_full.txt` | everything | **deployment only** |

The full model sees 25% more data and is slightly better everywhere, but has no
clean holdout left, so it can never legitimately quote a score. Quoting a full
model's own training performance is the most common way a project like this
claims 0.99 and then fails in the field.

Per-fold, holdout region only:

| fold | n train | n test | AUC | AP | P@1% |
|---:|---:|---:|---:|---:|---:|
| 0 | 452,334 | 92,460 | 0.878 | 0.625 | 0.933 |
| 1 | 414,324 | 130,470 | 0.838 | 0.576 | 0.936 |
| 2 | 452,616 | 92,178 | 0.854 | 0.626 | 0.970 |
| 3 | 408,414 | 136,380 | 0.879 | 0.651 | 0.959 |
| 4 | 451,488 | 93,306 | 0.849 | 0.579 | 0.904 |
| **mean** | | | **0.859 ± 0.016** | **0.611** | |

> Published susceptibility models often report 0.90+ using **random** CV, which
> leaks near-identical neighbouring cells between train and test. Ours is
> spatial block CV. **Not comparable — state the protocol when benchmarking.**

---

## 4. Success rate — how the map concentrates risk

| Class | % of area | % of known slides | Lift |
|---|---:|---:|---:|
| Very Low | 50.0% | 1.1% | 0.0× |
| Low | 25.0% | 7.2% | 0.3× |
| Moderate | 15.0% | 20.6% | 1.4× |
| **High** | 7.0% | 30.8% | **4.4×** |
| **Very High** | 3.0% | 40.3% | **13.4×** |

**10% of the state contains 71% of known landslides.** That is the operational
claim: it lets APSDMA concentrate survey and mitigation on a tenth of the
terrain and still cover seven in ten failures.

---

## 5. ⚠️ Validation honesty — one check is circular

Both point inventories were withheld from training, but they are **not
equivalent**. Measured distance from each point to the nearest *training* polygon:

| Inventory | on a training polygon (0 m) | >1 km away | Verdict |
|---|---:|---:|---|
| GSI points (1,027) | **84.6%** | 4.1% | ❌ **NOT independent** |
| NASA GLC (56) | 1.4% | 47.2% | ✅ independent |

GSI points are centroids of the same failures GSI mapped as polygons. Scoring
them measures **training-set recall (71.4%)**, not generalisation. It must not
be presented as external validation — a reviewer comparing the two files will
catch it immediately.

**The honest external number is NASA GLC: 28.6% of its landslides fall in the
top 10% of terrain — 2.9× better than chance.** Substantially weaker than the
71% the polygon success rate suggests.

That gap is *probably* geolocation, not model failure — NASA GLC location
accuracy is explicitly coarse, and the trend runs the right way (1 km accuracy →
44.4%, 50 km → 20.0%). But bin sizes are 3–17 points, **far too small to
conclude**. Report 28.6% as the independent figure and state the caveat.

---

## 6. Ablations — is any suspect feature load-bearing?

Lithology takes 23% of model gain, and both elevation and road distance are
known accessibility proxies. Removing each (spatial CV AUC):

| Removed | AUC | Cost |
|---|---:|---:|
| nothing | 0.859 | — |
| lithology + geology | 0.855 | 0.004 |
| elevation | 0.857 | 0.002 |
| road distance | 0.850 | 0.009 |
| all three | 0.842 | 0.017 |
| **terrain + hydro only (10 feats)** | **0.839** | 0.020 |

**No single suspect feature carries the model.** Lithology consumes 23% of gain
but costs 0.004 AUC to remove — it is redundant with terrain; trees simply like
high-cardinality categoricals because they offer many split points.

> 💡 **Gain ≠ importance.** Gain measures how much a tree *used* a feature, not
> how much it *needed* it. Always ablate before claiming a driver.

Terrain + hydrology alone reaches 97.7% of full performance from 10 physically
interpretable features. **This is the answer to "your model just detects roads."**

---

## 7. ⚠️ Known bias — elevation

Predicted High+ vs where landslides actually are:

| Elevation | % of domain | % predicted High+ | % *actual* slides |
|---|---:|---:|---:|
| 0–500 m | 7.0% | 26.0% | 19.7% |
| 500–1,000 m | 14.9% | 34.5% | 28.7% |
| 1,000–2,000 m | 32.6% | 28.8% | 31.1% |
| **2,000–3,000 m** | 24.8% | **7.9%** | **13.9%** |
| **3,000–4,000 m** | 17.2% | **2.6%** | **6.4%** |
| 4,000+ m | 3.5% | 0.1% | 0.3% |

**The model over-predicts low ground and under-predicts 2,000–4,000 m.** That
band holds 20.3% of known landslides but receives only 10.5% of High+
predictions — an operational **under-warning at altitude**, which is where
roads are most fragile and access hardest.

Likely cause: label survey bias. Fewer positives are mapped high up (access is
hard), the model reads that as "high elevation is safe", and the bias
propagates. This is label-driven, so **more model capacity will not fix it.**

**Mitigation:** treat class thresholds as elevation-dependent when operationalising,
and flag high-altitude corridors for manual review regardless of class. Revisit
if PX (label factory) recovers high-altitude events from imagery.

By contrast **road distance is clean** — predicted High+ tracks actual slides
across every band (5–20 km from a road is 43.6% of the domain, 40.8% of actual
slides, 38.8% of predictions). The model is not a road detector.

---

## 8. What the model learned

Top features by mean |SHAP| — see `reports/susceptibility_shap.png`:

| Feature | mean abs SHAP | Reading |
|---|---:|---|
| `terrain_northness` | 0.701 | aspect — differential weathering, moisture, snow retention |
| `geol_lithunit_cat` | 0.519 | rock unit — but see §6, largely redundant |
| `dem_elev_m` | 0.492 | partly real, partly accessibility (§7) |
| `terrain_slope_max_deg` | 0.409 | max slope in cell beats mean slope |
| `dist_road_m` | 0.230 | real mechanism (cut benches) + mapping bias |
| `terrain_eastness` | 0.207 | aspect, orthogonal component |

Notable: **`slope_max` outranks mean slope.** The steepest sub-cell patch
matters more than the cell average — which is why terrain derivatives are
computed at 25 m and aggregated, rather than on a smoothed 100 m DEM
([DATA_CONTRACT.md §2](DATA_CONTRACT.md)).

Aspect dominating is physically sensible in the Himalaya: north-facing slopes
hold moisture and snow differently, driving differential weathering.

---

## 9. Out-of-domain masking — hard requirement

`susceptibility_class.tif` uses **0 = not assessed** for the 14.3% of the state
outside the modelling domain (slope ≤10°, ice, water, alpine moss).

> ⚠️ **Render "not assessed" as grey, never as "low risk".** They are different
> claims. The model never saw a glacier; a susceptibility number on one is
> meaningless and invites a reviewer to distrust the entire map.

This carries into P9 (daily run) unchanged.

---

## 10. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | Elevation under-warning at 2,000–4,000 m (§7) | operational use |
| 2 | Independent validation rests on 56 NASA points | confidence in §1 |
| 3 | No comparison yet against GSI's 50 m benchmark map | roadmap exit check |
| 4 | Lithology unknown 6.11%, kept as explicit category `0` | resolved deliberately |
| 5 | GSI/Bhuvan publication permission | production only — **deferred, not MVP** |

---

## 11. Reproducing

```bash
python scripts/model/train_susceptibility.py    # ~200 s
python scripts/model/predict_susceptibility.py  # ~60 s
```

Deterministic (`random_state=42`). If `sample_hash` ≠ `b58e7dcc22134c1f`, the
training set changed and **every number here is void**.
