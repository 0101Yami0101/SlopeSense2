# Projected — this build vs the existing SlopeSense app

Comparison against `D:\CODE\BeeDigital\LandslideSM` (**SlopeSense**), a deployed
Streamlit landslide **susceptibility** app for the same state. Recorded so the
difference between the two products is explicit and quotable.

**Date:** 2026-08-02

---

## 1. Data

| | SlopeSense | Ours |
|---|---|---|
| Landslide labels | 81 points | 37,788 polygons → 91,610 cells |
| Training rows | 243 | 544,794 |
| Grid | ~275 m, 2.7 M cells | 100 m, 8.2 M cells |
| Features | 11 | 34 (adds soil ×18, lithology, land cover, flow accumulation) |
| Rainfall | 2 climate averages | 9,555 days of IMERG, 26 years, zero gaps |
| Dated events | none | 72 |

## 2. Methods

| | SlopeSense | Ours |
|---|---|---|
| Rainfall's role | static feature inside susceptibility | separate dynamic trigger |
| Trigger | hand-written rule, uncalibrated | calibrated on 72 dated events |
| Trigger threshold | fixed mm, statewide | percentile vs each cell's own 26-yr climatology |
| Out-of-domain (ice, water, flat) | scored | masked, reported "not assessed" |
| Class breaks | equal 20% quintiles | 50/75/90/97 — Very High = 3% of area |
| Validation | spatial CV | spatial CV + ablations + independent inventory |

## 3. Results

| | SlopeSense | Ours |
|---|---|---|
| Susceptibility AUC | 0.811 ± 0.101 | **0.860 ± 0.016** |
| Trigger AUC | not measured | **0.768 ± 0.098** |
| Top class concentration | 20% of area | **3% of area holds 40% of slides** |

**Product:** susceptibility map (static, always the same) → **7-day forecast** that
changes daily.

---

## ⚠️ Honest caveats

- SlopeSense's 0.811 comes from **81 events**; ours from 91,610. The scores are not
  like-for-like, and its ±0.101 fold spread is the honest consequence of a small
  sample, not carelessness.
- **Our trigger rests on just 72 dated events** — which is exactly why it is a
  calibrated rule rather than a learned model. Fitting one on 72 events measurably
  *lost* to not fitting ([MODEL_TRIGGER_AND_HAZARD.md §4](MODEL_TRIGGER_AND_HAZARD.md)).
- SlopeSense reports its **optimism gap** (how much random CV would overstate each
  model). That is good practice we should match, not something we beat it on.
- Its trigger heuristic is **openly labelled uncalibrated** in its own docstring.
  The upgrade is real, but it was never claimed to be more than a heuristic.

## What SlopeSense does that we should keep

| | |
|---|---|
| Deployment architecture | ~9 MB git-committed bundle + slim deps, no GDAL → fits free tiers |
| Open-Meteo | free, keyless, 3 past + 8 forecast days, multi-coordinate, degrades gracefully |
| Route Risk view | real OSRM road routes; km of corridor crossing High/Very-High terrain |
| Model Lab | spatial-vs-random validation shown to the user as a trust signal |
| Small polish | tile-host preconnect, safety disclaimer, CSV download |
