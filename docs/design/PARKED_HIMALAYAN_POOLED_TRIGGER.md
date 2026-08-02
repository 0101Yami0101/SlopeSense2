# PARKED — Himalayan pooled trigger model

**Status:** ⏸️ **paused 2026-08-02 by decision, not by failure.** Untested, unrefuted.
**Resume cost:** ~3 h fetch (unattended) + ~1 day of work.

> This is the one remaining route to a genuine machine-learning trigger that needs
> **no new data, no department's permission and no fieldwork.** It was stopped
> mid-fetch to keep focus on the MVP. Nothing here has been disproved — it simply
> has not been run.

---

## 1. The idea in one line

Stop trying to enlarge *Arunachal's* dated inventory. Train the trigger on **every
dated rainfall landslide along the Himalaya**, then validate it on Arunachal's own
events, which the model has never seen.

## 2. Why it is worth resuming

Every other route to more dated events has been closed
([TEMPORAL_INVENTORY_ATTEMPTS.md](TEMPORAL_INVENTORY_ATTEMPTS.md)). This one is
different because the data is **already public and already counted**:

| | count |
|---|---:|
| Landslides in the Himalayan arc (72–98°E, 26–36°N) | 1,818 |
| …dated **and** located to ≤5 km | 812 |
| …inside the trimmed fetch box (76–98°E, 26–32°N) | **617** |
| Arunachal's own dated events, for comparison | **72** |

**~9× the local sample.** That is the difference between ~12 events per feature —
where fitting measurably *loses* to not fitting ([MODEL_TRIGGER_AND_HAZARD.md §4](MODEL_TRIGGER_AND_HAZARD.md))
— and ~60 per feature, which is a legitimate training set.

### Why the features transfer

**IMERG is global.** The whole P7 pipeline — `r3`, `r7`, `api`, `storm_id_ratio`,
percentile-normalised against each cell's own climatology — computes identically
anywhere on Earth. Nothing in the trigger is Arunachal-specific.

Percentile-normalising against **each location's own** climatology is what makes
pooling defensible: it absorbs the difference between the dry west and the wet
monsoon east automatically, so the model learns *"unusually wet for here"* rather
than a millimetre threshold that suits only one climate.

### Why the box is trimmed to 76°E

The western Himalaya (Pakistan, Kashmir) gets **winter western disturbances** — a
different rainfall regime. Including it would add ~190 events but make the pool
climatically heterogeneous, which is the opposite of what pooling needs.
**Trimming is a scientific choice, not just a size one.**

## 3. State on disk

| | |
|---|---|
| Script | [fetch_11d_imerg_himalaya.py](../../scripts/fetch/fetch_11d_imerg_himalaya.py) |
| Output | `data/raw/06_weather/gpm_imerg_himalaya/` |
| Box | lon 76–98 E, lat 26–32 N (13,200 cells, 6.8× the Arunachal box) |
| Span | 2000-06-01 → 2020-12-31 (7,519 days) |
| **Downloaded** | **751 days (10.0%)** — 2000-06-01 → 2002-06-22, 38 MB |
| Projected full size | ~380 MB |
| Event catalogue | `reports/_himalaya_glc.csv` (1,818 records, already fetched) |

**The fetcher is restartable.** Anything already on disk is skipped, so resuming
costs nothing:

```bash
python scripts/fetch/fetch_11d_imerg_himalaya.py     # picks up at day 752
```

⚠️ Coordinates in `_himalaya_glc.csv` are **Web Mercator (EPSG:3857)**, not degrees.
Convert before use, or every point lands in the wrong place:
```python
lon = x / 20037508.34 * 180
lat = degrees(2*atan(exp(y / 6378137.0)) - pi/2)
```

## 4. The plan when resumed

1. Finish the fetch (~3 h unattended).
2. Run `rainfall_stack.py` / `rainfall_features.py` against the Himalayan box —
   both are already hazard- and region-agnostic, so this needs a path argument, not
   a rewrite.
3. Build the training table: 617 dated events as positives, random monsoon
   cell-days as negatives, features percentile-normalised per cell.
4. **The decisive test — train on the arc EXCLUDING Arunachal, test on Arunachal's
   72 events.** The model must never see an Arunachal landslide during training.

## 5. The bar it has to clear

**Beat AUC 0.768** — the physics trigger's score on those same 72 events.

- **If it beats it:** we have a machine-learning trigger validated on held-out
  ground in the client's own state, and a genuine improvement to ship.
- **If it does not:** nothing is lost. The physics trigger already ships, and we
  will have a measured answer instead of an open question.

Either outcome is worth the day it costs.

## 6. Known risks

| risk | mitigation |
|---|---|
| **Reporting bias** — the catalogue draws on news reports, so it may encode where journalists are, not where slopes fail | hold out **whole regions**, never random rows |
| **Location error ≤5 km** — coarse for 100 m terrain, fine for 11 km rainfall | lean on rainfall features; use terrain only coarsely |
| **Transfer may fail** — climate and geology differ along the arc | this is exactly what the held-out Arunachal test detects rather than hides |
| Catalogue updates slowed after ~2019 | historical rate was ~137 events/yr arc-wide; confirm before quoting forward growth |

## 7. Why it was parked

Decision on 2026-08-02 to keep focus on the Level-1 MVP. **Not a technical
setback** — this route remains the most promising untested option for the *when*
half, and the only one that requires nothing from anyone outside the project.
