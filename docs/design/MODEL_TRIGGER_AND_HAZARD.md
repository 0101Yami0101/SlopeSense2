# Trigger & Hazard (P8) — the WHEN half, and the two halves combined

**Status:** complete 2026-08-02 · **Scripts:** [trigger.py](../../scripts/model/trigger.py) · [hazard.py](../../scripts/model/hazard.py)
**Inputs:** [RAINFALL_FEATURES.md](RAINFALL_FEATURES.md) · [MODEL_SUSCEPTIBILITY.md](MODEL_SUSCEPTIBILITY.md)

```
HAZARD = SUSCEPTIBILITY (WHERE, 100 m, static)  ×  TRIGGER (WHEN, 11 km, daily)
             37,788 polygons, AUC 0.860              72 dated events, AUC 0.768
```

---

## 1. Headline

| | |
|---|---|
| Trigger | `mean( pctile(r3), pctile(r7) )` vs each cell's own monsoon climatology |
| Trigger AUC | **0.768 ± 0.098** (72 events vs 20,000 monsoon cell-days) |
| Median score | **0.857** on landslide days, **0.503** on ordinary monsoon days |
| Fitted? | **No** — and that is deliberate, see §4 |
| Hazard | `susceptibility × trigger` |

Operating points (trigger alone):

| trigger ≥ | % of monsoon days flagged | % of events caught | lift |
|---:|---:|---:|---:|
| 0.75 | 22.5% | 65.3% | 2.9× |
| **0.90** | **7.5%** | **41.7%** | **5.6×** |
| 0.95 | 3.2% | 30.6% | 9.6× |
| 0.99 | 0.4% | 11.1% | 25.5× |

---

## 2. ⚠️ The classic intensity–duration form is wrong for this data

ID theory says long storms trigger at *lower* intensity: `I = a·D^-b`, b > 0.
Fitted on our events, **b came out negative** — intensity *rising* with duration.

Not a fitting error. Measured `corr(log D, log I) = +0.59`.

**Cause:** our storm definition is "consecutive days above 1 mm", and in a
monsoon that yields runs of weeks — **the longest in the archive is 202 days**. A
long run is not a long storm, it is the monsoon. A 1–2 day run is an isolated
shower (median 6 mm total). So intensity rises with duration *by construction*.

**Fix:** switch to the event-rainfall–duration form, standard in the literature
and the right shape for this data — `corr(log D, log E) = +0.91`:

```
E = 0.01 · D^1.644          E = storm rainfall (mm), D = duration (hours)
```
Fitted as a 10th-percentile lower envelope; captures **89%** of dated events.
6 events fell on dry days (delayed failure, or a non-rainfall trigger) and are
excluded from the fit and counted as unavoidable misses.

---

## 3. ⚠️ A rainfall threshold cannot be a binary gate here

Every candidate curve, fitted as a lower envelope on real events, fires
**99–166 days per year** at a given cell.

That is not a defect of the fit. It is the honest consequence of a place
averaging 1,931 mm/yr: **most monsoon days do exceed the minimum condition that
has ever produced a slide.** The literature reports the same for monsoon climates.

⇒ The E–D curve is kept as **explainable physics and a floor**. The operational
trigger is a **continuous severity score**, not a threshold crossing.

---

## 4. ⚠️ Fitting on 72 events loses to not fitting

Measured against 20,000 random monsoon cell-days at the same cells and months:

| approach | AUC |
|---|---:|
| `r3` alone | 0.761 |
| **`r3` + `r7`, percentile average, unfitted** | **0.768** |
| `r1`+`r3`+`r7` | 0.767 |
| logistic on 6 features, 5-fold CV | **0.755** |

**The fitted model loses.** With 72 events, fitting adds variance without signal.
So the trigger is an unfitted average of two percentile-normalised features —
nothing is fitted, nothing can overfit, and it is trivially explainable to
APSDMA.

This is direct evidence for the project rule: **do not train a trigger model
until PX delivers real dates.**

### Why percentile-normalise per cell

Arunachal spans 799 → 4,167 mm/yr. 150 mm in three days is unremarkable in the
Siang gorge and extraordinary on the northern crest. A raw millimetre threshold
would alert the wet south permanently and the dry north never.

---

## 5. Hazard = susceptibility × trigger

Both terms are necessary, neither sufficient: a cliff in dry weather does not
fail; a downpour on flat stable ground does nothing. **Multiplying preserves
that** — if either term is ~0 the hazard is ~0. Adding would let a torrential day
raise the hazard of flat ground.

### ⚠️ Resolution is deliberately mixed

Susceptibility is genuinely 100 m. The trigger is genuinely 11 km and is **not
downscaled** — every 100 m cell in an IMERG pixel shares one trigger value. The
output has 100 m spatial texture and 11 km rainfall texture.

> **Say this on the map.** A viewer sees crisp 100 m detail and will assume the
> rainfall is that sharp. It is not.

Out-of-domain cells stay nodata, never "low hazard"
([MODEL_SUSCEPTIBILITY.md §9](MODEL_SUSCEPTIBILITY.md)).

---

## 6. 🚨 The end-to-end validation UNDERSTATES the system — read before quoting

| model | AUC | 95% CI |
|---|---:|---:|
| susceptibility only (WHERE) | 0.683 | ±0.122 |
| trigger only (WHEN) | 0.738 | ±0.115 |
| **hazard = product** | **0.728** | ±0.117 |

The product scores *below* the trigger alone. **This is an artefact of the
validation labels, not evidence that susceptibility is unhelpful.**

NASA GLC is the only dated inventory and its location accuracy is km-level. A
point off by 5 km lands in the wrong 100 m susceptibility cell but usually the
**same** 11 km rainfall pixel — so geolocation error cripples the fine-resolution
term while barely touching the coarse one.

Measured, and cleanly monotone:

| label location accuracy | n | susceptibility AUC |
|---|---:|---:|
| exact + 1 km | 12 | **0.778** |
| 5 km + 10 km | 27 | 0.722 |
| 25 km + 50 km | 13 | **0.602** |

Skill tracks label precision, not model quality. P6 measured **0.860** on precise
polygon labels.

> **The combined system cannot be honestly scored until PX supplies well-located
> dated events.** Quote the two halves separately (0.860 and 0.768) and state
> that the product is unmeasured. Do not quote 0.728 as system performance —
> it is a floor set by the validation data.

Hazard operating points, with the same caveat:

| hazard ≥ pctile | % of cell-days | % of events | lift |
|---:|---:|---:|---:|
| p90 | 10.0% | 37.5% | 3.8× |
| p95 | 5.0% | 26.8% | 5.4× |
| p99 | 1.0% | 7.1% | 7.1× |

---

## 7. What PX would fix

Everything limiting in §4 and §6 is the same root cause: **72 dated events with
km-level positions.**

| constraint | what more/better dates buy |
|---|---|
| Unfitted trigger (§4) | enough events to fit a real model and beat 0.768 |
| Unmeasurable product (§6) | an honest end-to-end number |
| Global E–D curve shape | a locally calibrated curve with tight CIs |
| Alert thresholds | operating points chosen on evidence, not judgement |

This is why PX is inside the MVP and starts immediately — see
[ROADMAP_LANDSLIDE.md](ROADMAP_LANDSLIDE.md) PX0.

---

## 8. Reproducing

```bash
python scripts/model/trigger.py                 # calibrate + validate trigger
python scripts/model/hazard.py                  # end-to-end validation
python scripts/model/hazard.py 2017-07-11       # map a single day
```

Sample output for 2017-07-11 (a wet day in the worst recorded year): trigger
median 0.962 statewide, hazard median 0.045, p99 0.817, max 0.985.
