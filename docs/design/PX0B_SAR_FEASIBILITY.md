# PX0b — Sentinel-1 radar feasibility: **PASS** (access only)

> ❌ **PX0c subsequently VETOED the route** ([PX0C_SAR_DETECTION.md](PX0C_SAR_DETECTION.md),
> same day). Access is fine — **detection is not**. Mapped scars are indistinguishable from
> slope-matched hillside (AUC 0.53 vs 0.50 chance), and the decisive temporal test cannot be
> run because we never have precise locations and known dates together. This page stands as
> the record that the *access* question was answered positively.

**Status:** run 2026-08-02 · **Verdict: data gate cleared — but see the veto above**
**Script:** [px0b_sar_feasibility.py](../../scripts/proto/px0b_sar_feasibility.py) · **Data:** `reports/px0b_sar_feasibility.{json,png}`

---

## 1. Why we re-opened this after PX0 failed

[PX0](PX0_CLOUD_FEASIBILITY.md) vetoed **optical** change detection: monsoon cloud
leaves 55–80 day gaps between clear views, against the ≤7 days a daily trigger
needs.

**Radar does not care about cloud.** Sentinel-1 images through the monsoon exactly
as well as through the dry season. The single thing that killed PX0 simply does
not apply — which is why this earned its own gate rather than a shrug.

But radar trades one problem for another, and I expected the new one to be worse.

## 2. The concern that turned out to be overstated

Radar looks *sideways*, at ~39° from vertical. On a mountainside that fails two ways:

- **Layover** — slope tilted toward the radar, steeper than the look angle. The image folds over itself; the pixel is unrecoverable.
- **Shadow** — slope tilted away, never illuminated. No signal at all.

Both happen on **steep slopes — precisely where landslides are**. So "radar sees
through cloud" could have been true and irrelevant.

**Measured on our own DEM, across all 91,610 mapped landslide cells:**

| orbit | layover | shadow | usable |
|---|---:|---:|---:|
| ascending | 7.6% | 0.1% | 92.2% |
| descending | 3.6% | 0.5% | 95.9% |
| **either orbit** | | | **99.4%** |
| both orbits | | | 88.8% |

Robust across the swath: 100.0% usable at 29° incidence, 99.4% at 39°, 98.4% at 46°.

**Why the fear was wrong:** layover needs the *effective* slope in the look
direction to exceed 39°, and that is reduced by how far the slope faces away from
the sensor. Only slopes both steep **and** facing the radar are lost — and
ascending and descending look at opposite sides, so a slope hidden from one is
almost always visible to the other.

## 3. Revisit frequency

| period | acquisitions | asc | desc | median gap | p90 gap |
|---|---:|---:|---:|---:|---:|
| 2017–2018 | 424 | 176 | 248 | 5 d | 7 d |
| 2019–2020 | 427 | 182 | 245 | 5 d | 10 d |
| 2022–2023 | 460 | 169 | 291 | 5 d | 7 d |
| 2024–2026 | 719 | 246 | 473 | **4 d** | 6 d |

> ⚠️ **Methodology note.** An earlier run pooled acquisitions across three probe
> points and reported a 2-day gap. That was wrong — it counted a date imaged over
> one probe as coverage of another. Revisit is computed **per location** and then
> aggregated, because a single site is what matters for dating a single landslide.

Notably the 2021 loss of Sentinel-1B did not degrade coverage here; 2024–2026 is
the best period in the record.

## 4. Verdict

| gate | requirement | measured | |
|---|---|---|---|
| temporal | ≤14 d | **4 d** median | ✅ |
| geometric | ≥60% viewable | **99.4%** | ✅ |

**PASS.** Against optical's 55–80 day window, radar gives **4–5 days** — a ~15×
improvement that clears the ≤7 day requirement outright.

## 5. ⚠️ What this does NOT prove

**This gate tests whether the data can see the slope, and how often. It does not
test whether a model can actually spot a landslide scar in radar.**

That is genuinely harder than in optical imagery:

- **Speckle** — SAR is inherently noisy; single-image interpretation is unreliable
- **Confounders** — soil moisture, vegetation growth and harvest all change radar backscatter without any landslide
- **Processing burden** — usable change detection needs multi-temporal stacks, radiometric terrain correction, and careful handling of the steep-terrain geometry above

So PASS means *"the data supports an attempt"*, not *"this will work"*.

**Next gate — PX0c, detection prototype:** take a sample of landslides with known
dates, build a SAR amplitude change stack, and test whether the scar is detectable
against the seasonal backscatter noise floor. Same principle as before: *validate
against answers we already have.* If PX0c fails, PX ends there.

## 6. Reproducing

```bash
python scripts/proto/px0b_sar_feasibility.py     # ~2 min, metadata + local DEM
```
