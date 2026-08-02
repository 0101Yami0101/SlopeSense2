# PX0c — SAR detection gate: **VETO** (for the MVP)

**Status:** run 2026-08-02 · **Verdict: radar dating is not viable on the evidence we can obtain**
**Script:** [px0c_sar_detection.py](../../scripts/proto/px0c_sar_detection.py) · **Data:** `reports/px0c_sar_detection.{json,png}`

---

## 1. What PX0b left open

[PX0b](PX0B_SAR_FEASIBILITY.md) proved Sentinel-1 passes over every 4–5 days and
that 99.4% of our landslide cells are geometrically viewable. **The camera points
at the right door and records often enough.**

It said nothing about whether the footage is clear enough to recognise anything.
That is this gate.

## 2. Test A — can radar see a scar that definitely exists?

Before asking "can we detect the moment a scar appears", ask the cheaper
question. Using our **best-located** data (GSI/Bhuvan polygons, precisely mapped)
against **slope-matched** controls >500 m away — slope-matched because
backscatter depends on terrain angle, and random controls would just re-detect
steepness, the same trap as negative sampling in P6.

Dry-season scenes only (least soil-moisture noise) — the best case.

**Result across 4 independent scenes, 17,000–20,000 pixels each:**

| channel | mean AUC |
|---|---:|
| VV | 0.526 |
| VH | 0.533 |
| VH/VV ratio | 0.516 |

**0.50 is chance.** Gate was AUC ≥ 0.65.

### Larger scars do not help

| polygon size | n | VH AUC |
|---|---:|---:|
| 2,000–10,000 m² | 24 | 0.568 |
| 10,000–50,000 m² | 14 | 0.536 |
| 50,000–200,000 m² | 3 | 0.511 |

No trend. Big slides are no more visible than small ones, so this is not a
resolution problem we could solve with a sharper sensor.

The *direction* is physically correct — median VH inside slides **0.0384** vs
control **0.0418**, i.e. scars are darker, consistent with bare ground replacing
volume-scattering canopy. The effect is simply far too small to separate.

## 3. ⚠️ What this does and does not establish

**Established:** mature landslide scars in Arunachal show **no usable static
amplitude contrast** in Sentinel-1 RTC. Robust across scenes, polarisations and
size classes.

**Not established — two honest limits:**

1. **Our polygons have unknown ages.** In a wet subtropical climate scars
   revegetate within a few years. Many GSI scars may be decades old and now look
   like forest. So this cannot fully separate *"radar cannot see scars"* from
   *"our scars are too old to see"*. A fresh scar might contrast sharply.

2. **Only amplitude was tested.** The strongest SAR technique for surface
   disruption is **interferometric coherence** — a landslide destroys phase
   coherence almost completely, and that signal is far stronger than amplitude.
   Testing it needs SLC data and full interferometric processing, well beyond a
   feasibility prototype.

## 4. 🚨 Why Test B could not be run — the circularity

Test B was to be the real question: *does backscatter change at the failure
moment?* It is **blocked by a data problem, not a technical one**:

| our data | precise location | known date |
|---|---|---|
| GSI / Bhuvan polygons (37,788) | ✅ | ❌ |
| NASA GLC points (90) | ❌ km-level error | ✅ |

**We never have both together.** To validate a system whose entire purpose is to
generate dates, we need examples that are both precisely located *and* already
dated — which is exactly what we lack.

That is circular, and it is the deepest finding here: **the label shortage blocks
not just training but validation of any proposed fix for the label shortage.**

## 5. Verdict

**VETO for the MVP.** Not "radar is impossible" — "radar is not cheap, and cannot
be validated with the evidence we can obtain."

Reviving it would require, in order:
1. A set of landslides with **both** precise outlines and known dates. ⚠️ Previously
   this named GSI `Landslidedata_1`; verified 2026-08-02 that it holds only ~402 rows
   nationally (both public examples Tamil Nadu), so likely 0–20 for Arunachal. The
   better candidate is **state PWD/BRO road-blockage logs**
2. Interferometric coherence processing rather than amplitude
3. Its own validation, which (1) would finally make possible

Note the ordering: **every route now runs through getting dated, precisely-located
events from a department.** If such data arrives it likely fixes the temporal
inventory directly, making radar dating unnecessary.

## 6. Cost and value

~1.5 hours total (PX0b + PX0c). It closed out the last technical alternative to
asking for data, and established precisely *why* it closed — which is what makes
prioritising the data requests a conclusion rather than a preference.

**Effect on the MVP: none.** P8 ships the physics trigger as planned.

## 7. Reproducing

```bash
python scripts/proto/px0c_sar_detection.py     # ~8 min, windowed COG reads
```
