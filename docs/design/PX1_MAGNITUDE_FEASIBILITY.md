# PX1 — can we forecast HOW BIG a landslide will be?

**Asked:** "Is there a way to tell along with the forecast how big or heavy the
landslide might be? Like 0.99 — small slide, 0.76 — major slide?"

**Answer: no, and we should not pretend otherwise.** Both routes were tested
and both failed. Reproduce with:

```
.venv/Scripts/python scripts/proto/px1_magnitude_feasibility.py
```

Results land in `reports/px1_magnitude.json`.

---

## The question splits in two

The request contains two different problems wearing one sentence:

| | Question | Would give us | Needs |
|---|---|---|---|
| **Gate A** | Does the rainfall trigger predict the size of the event it triggers? | A daily bulletin that says *"today's rain would produce a **large** failure"* — an actual magnitude forecast | Events carrying **both** a date and a size |
| **Gate B** | Does the terrain predict the typical size of failures at a place? | A static *"failures here are usually large"* map. Not a forecast | Measured failure areas |

Gate A is what was asked for. Gate B is the consolation prize. Neither passed.

---

## Gate A — rainfall → event size: **FAIL**

The NASA Global Landslide Catalog is the only source that carries a size class.
Of 99 catalogued Arunachal events, **90 have both a date and a size**, and 72 of
those also match an IMERG rainfall cell and day.

Trigger computed exactly as the shipped model does it: the mean percentile of
the 3- and 7-day rainfall totals against that cell's own **monsoon**
climatology.

| size | n | median trigger | mean trigger |
|---|---|---|---|
| small | 15 | 0.855 | 0.661 |
| medium | 45 | 0.849 | 0.772 |
| large | 12 | 0.885 | 0.825 |
| very_large | — | (1 event statewide, dropped) | |

```
Spearman(trigger, size)        rho = +0.126    p = 0.293
Kruskal-Wallis across sizes      H = 1.15      p = 0.562
Shuffled-label null:  |rho| >= 0.126 on 29.5% of random relabellings
                      95th percentile of pure noise at n=72 is |rho| = 0.236
```

The means do rise in the right order (0.66 → 0.77 → 0.83). That is the trap.
At n=72 that ordering appears in **roughly three of every ten random
relabellings** of the same data. It is not evidence.

To detect a correlation of this size at conventional power we would need
**~490 dated-and-sized events**. We have 72, and
[TEMPORAL_INVENTORY_ATTEMPTS.md](TEMPORAL_INVENTORY_ATTEMPTS.md) records five
separate closed routes to getting more.

---

## Gate B — terrain → typical size: **FAIL**

Far more data here: **37,774 mapped polygons with a measured area**, spanning
944 m² (median) to 4,254,189 m² — the largest is 3,511× the median, so there
genuinely is something to predict.

LightGBM on log₁₀(area), 34 terrain/soil/geology layers, the same 50 km spatial
block CV the susceptibility model uses:

```
Spatial-CV Spearman(predicted, actual)  = +0.282  (fold sd 0.043)
Spatial-CV R² on log area               = -0.015
Typical error: predicts area to within a factor of 4.6x
               ...the raw spread of the data is a factor of 4.5x
```

**A negative R² means the model is worse than always guessing the average.** It
ranks slightly better than chance (ρ ≈ 0.28) but removes essentially none of the
spread. It cannot produce a number.

### Why it fails — the target is not physical

Before blaming the model, check whether polygon area even measures the
landslide:

| variance in log(area) explained by | share |
|---|---|
| **which survey drew the polygon** | **0.167** |
| all 34 terrain, soil and geology layers | 0.000 |

| survey | n | median log₁₀ area |
|---|---|---|
| GSI | 26,070 | 2.98 |
| Bhuvan 2014 | 3,026 | 3.20 |
| Bhuvan 2017 | 4,687 | 3.25 |
| Bhuvan 2023 | 3,578 | 3.47 |

Each survey has its own minimum mapping unit and its own habit about splitting
or merging adjacent scars. **Polygon "size" tracks the mapping team an order of
magnitude more strongly than it tracks the hillside.** Even a perfect model
would be learning survey methodology.

---

## What we say instead

1. **No magnitude claim anywhere in the product.** Not as a number, not as a
   size word, not as an implication.
2. The hazard index stays what it is: *relative severity*, ordering ground from
   safer to more dangerous. It has never estimated size and now demonstrably
   cannot.
3. **What we could honestly offer** (not yet built): show the *observed* size
   distribution of mapped failures within ~10 km of the searched location —
   "past failures near here: median 1,200 m², largest 40,000 m²". That is
   history, clearly labelled as history, with the survey-inconsistency caveat
   attached. It answers the operational instinct behind the question without
   inventing a forecast.
4. **What would unlock a real answer:** a size-attributed, dated inventory —
   most plausibly PWD road-block logs, which record blockage length and
   clearance effort per event. Same ask that would unlock the timing model.

---

## Related

- [MODEL_TRIGGER_AND_HAZARD.md](MODEL_TRIGGER_AND_HAZARD.md) — what the hazard
  index does and does not mean
- [TEMPORAL_INVENTORY_ATTEMPTS.md](TEMPORAL_INVENTORY_ATTEMPTS.md) — the five
  closed routes to more dated events
- [LABELS_AND_SAMPLING.md](LABELS_AND_SAMPLING.md) — the four inventories and
  how they differ
