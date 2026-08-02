# PX0 — Cloud feasibility prototype: **VETO**

**Status:** run 2026-08-02 · **Verdict: PX (label factory) does not proceed as designed**
**Script:** [px0_cloud_feasibility.py](../../scripts/proto/px0_cloud_feasibility.py) · **Data:** `reports/px0_cloud_feasibility.{json,csv,png}`

---

## 1. The question

PX proposed recovering failure dates for our 37,788 undated polygons by detecting
when each scar first appears in satellite imagery. That requires clear imagery
close in time to the failure.

**86% of dated landslides here occur May–October** — peak monsoon, peak cloud.
The imagery we need is exactly the imagery hardest to get.

## 2. The test

Take the NASA GLC events whose dates we **already know**. Ask the Copernicus
catalogue what Sentinel-2 acquisitions exist near each in time, and how cloudy.
The gap between the last clear view *before* and the first clear view *after* is
the date uncertainty PX could actually achieve.

> *If we cannot recover dates we already have, we cannot discover dates we don't.*

45 of the 90 dated events fall in the Sentinel-2 era (≥ 2015-06). Metadata only —
no pixels downloaded.

## 3. Result — fails by roughly 8×

| cloud ≤ | events with clear views both sides | median window | ≤7 d | ≤14 d |
|---:|---:|---:|---:|---:|
| 20% | 9 / 45 | 160 d | 0% | 0% |
| 40% | 33 / 45 | **80 d** | 0% | **3%** |
| 60% | 39 / 45 | 70 d | 3% | 3% |
| 80% | 40 / 45 | **55 d** | 2% | 2% |

Distribution at cloud ≤40%: p10 **55 d**, p50 **80 d**, p90 **155 d**.

**A daily trigger model needs date certainty of ≤7 days. The best achievable —
taking essentially every acquisition regardless of cloud — is a 55-day median.
That is ~8× worse than required**, and during monsoon it rained hard throughout
the entire window, so the label carries almost no information about *which* storm
did it.

At the ≤20% cloud level you would actually want for reliable change detection,
**80% of events have no usable image pair at all** within ±120 days.

By season (cloud ≤40%): monsoon median **80 d**, dry season **105 d** (n=4).

## 4. Verdict

**VETO.** PX does not proceed as designed. The gap is not marginal — no amount of
model sophistication closes an 8× shortfall in label precision, because the
information simply is not in the imagery.

### Fairness caveats, and why they do not rescue it

1. **Cloud is reported per scene** (~110 km tile), not per pixel. A 60%-cloud tile
   may be clear over one slope, so these numbers are pessimistic. But the ≤80%
   row is effectively the per-pixel optimistic bound, and it still gives a 55-day
   median. Per-pixel analysis might halve the window; it will not divide it by 8.
2. **Sentinel-2 only.** Pre-2015 events would need Landsat at 30 m and 16-day
   revisit — strictly worse. This is the optimistic case.

## 5. What this bought

**~20 minutes of catalogue queries prevented roughly two weeks** building a label
factory — including the one genuine neural-network component in the system — that
would have emitted labels too vague to train on. The failure would have surfaced
only after the segmentation model was working, when the dates it produced turned
out to be 80 days wide.

This is the strongest argument in the project for cheap feasibility gates ahead of
expensive builds.

## 6. What replaces PX

The constraint is unchanged: **72 dated events is the temporal training set**, and
imagery cannot enlarge it. Remaining routes, in order of value:

| Route | Why | Cost |
|---|---|---|
| **GSI `Landslidedata_1`** | ⚠️ **corrected 2026-08-02** — only ~402 rows nationally, both public examples Tamil Nadu, so likely 0–20 for Arunachal. Worth an email, but **not the fix**. Best remaining ask is state PWD/BRO road-blockage logs. See [TEMPORAL_INVENTORY_ATTEMPTS.md](TEMPORAL_INVENTORY_ATTEMPTS.md) | an ask, not a build |
| **State PWD road-block records** | unglamorous but genuinely dated, and road blockages are a real landslide proxy | an ask |
| **IMD gauge records** | dated heavy-rain events to pair with reported damage | an ask |
| Radar (Sentinel-1) change detection | sees through cloud — the one technical route cloud does not kill | needs its own prototype; **not** scoped |

> ✅ **UPDATE — Sentinel-1 radar was tested and PASSED its data gate**
> ([PX0B_SAR_FEASIBILITY.md](PX0B_SAR_FEASIBILITY.md), same day). 4–5 day revisit
> and **99.4%** of landslide cells viewable — the layover/shadow concern raised in
> the row above proved real but overstated. The optical veto below stands
> unchanged; the *idea* of a label factory survives, via radar. Next gate is
> **PX0c**, testing whether a scar is actually detectable in SAR.

**Effect on the MVP:** none. P8 ships the physics trigger as planned. The MVP was
never dependent on PX — that is why the trigger was built first.

## 7. Reproducing

```bash
python scripts/proto/px0_cloud_feasibility.py     # ~3 min, metadata only
```
