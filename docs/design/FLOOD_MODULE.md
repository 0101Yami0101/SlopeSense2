# FloodSense — design, and what the measurements actually said

> **Status: prototype, shipping, static layer UNVALIDATED.**
> Built 2026-08-17. Pipeline: `scripts/build/build_flood_layers.py`.
> App: `webapp/products/flood/`. Bundle: `webapp/assets/flood/` (0.78 MB).

## The shape

Identical to SlopeSense, because the physics splits the same way:

```
landslide hazard = susceptibility     (where, static)  x trigger        (when, daily)
flood hazard     = flood-prone ground (where, static)  x catchment rain (when, daily)
```

That symmetry is why FloodSense reuses the whole spine — grid, boundary,
search, maps, rainfall fetch, climatology — and adds only two files of its own
maths.

## The static half — where water collects

**HAND** (height above nearest drainage), multiplied by the **size of the
drainage** it sits above. Both terms are needed: two metres above the Siang and
two metres above a hillside creek are not the same statement.

| Parameter | Value | Why |
|---|---|---|
| Channel definition | ≥ 100 km² upstream | See "the threshold that mattered" below |
| HAND ceiling | 25 m | Above this, nothing is flood-prone at any river size |
| Size scaling | log, 100 → 10,000 km² | Discharge grows with area far more slowly than area does |
| Min low-lying share | 5% of a display cell | Stops one clipped river corner painting a hillside |

Result: **4.88% of the grid is flood-prone**, spread across 5 classes.

### The threshold that mattered

The channel network was first defined at **≥ 10 km² upstream**. Measured
consequences of that choice:

- 90.7% of the resulting flood-prone ground sat beside a channel **smaller than
  2,000 km²**, with a **median catchment of 47 km²**
- 10.67% of the grid was called floodplain
- Tawang — a ridge town at 3,000 m — came out as class 2, and Ziro as class 3

Raising it to **100 km²** and using one definition of "river" end to end
(network, HAND measured to it, size weighting) fixed all three:

| Place | at 10 km² | at 100 km² | reality |
|---|---|---|---|
| Pasighat (on the Siang) | class 5 | class 5 | on a 18,126 km² river |
| Tezu (on the Lohit) | class 3 | **class 5** | on a 19,338 km² river |
| Tawang (3,000 m ridge) | class 2 | **class 0** | 705 m above drainage |
| Anini (high Dibang) | class 3 | **class 0** | — |

The old threshold also contradicted the module's own headline — that mountain
streams are a *watch*, not a forecast — while painting their banks as
floodplain.

### HAND: flow-path vs nearest-channel

The textbook definition follows the flow path. It was built first and rejected
on measurement:

- The 100 m DEM is not depression-filled. Raw, **34% of in-state cells** end in
  a pit rather than a channel — and this is not confined to ridges: **29% of
  cells within 250 m of a river** were affected.
- Filling with morphological reconstruction (Wang–Liu) raised 4.43% of cells
  but made coverage **worse** (65.7% → 60.9%), because a filled depression is
  flat and a flat cell has no steepest-descent neighbour.
- Scored against observed inundation, flow-path HAND did **no better** than the
  plan-view approximation (0.649 vs 0.666 on the original, uncorrected metric).

So the shipped layer measures to the **nearest channel in plan view**: complete
coverage, simpler, and no worse. In terrain this steep the nearest channel is
nearly always the one you would flow to.

## The daily half — catchment rain

A slope fails from rain landing **on** it. A river rises from rain landing
**anywhere upstream**. So rainfall is pooled over 1,680 HydroBASINS level-12
catchments and carried downstream before it becomes a forecast.

- Routing graph: `NEXT_DOWN`, with topological order taken from `UP_AREA`
  ascending — **verified in the build**, 0 basins ordered after their receiver
- Same 97 rainfall points and same climatology as SlopeSense, now in
  `assets/base/` because rainfall is spine, not hazard
- One cached fetch serves both modules, so opening the second costs no API call

### The response curve

Passing the catchment percentile straight through produced a forecast that was
really the static map wearing a date:

| | median-day High+ | week's range |
|---|---|---|
| percentile passed through | 34% | 33.5 – 37.0% (3.5 pts) |
| response curve | 10–17% | 10.5 – 17.4% (6.9 pts) |

Rivers rise on rain that is *unusual for their catchment*, and the median day
scores 0.50 by construction. The response is therefore near zero below the 35th
percentile and climbs steeply above it, with a small floor so floodplain still
shows as Very Low on a calm day — "this is floodplain and nothing is coming"
and "this is not floodplain" must not render the same.

## Validation — the honest part

**There is none, and the module says so on its own Method page.**

The only obtainable observed flood record for Arunachal is Bhuvan's aggregated
2003–2020 extent, served as **rendered map tiles**. Measured against the
terrain:

- **70.5%** of the pixels it marks flooded lie on slopes steeper than **15°**
- **31.3%** lie on slopes steeper than **25°**

Water does not pond on a cliff. That is tile smear, not observation, and it
cannot referee anything.

Scores against it, reported on the Method page precisely because they are bad:

| Test | Result | Reading |
|---|---|---|
| Pixel level, tie-corrected AUC | **0.530** | Chance is 0.50 |
| Catchment level, 706 basins, Spearman | **−0.023** | No relationship |

> ⚠️ **A tie-handling bug inflated this to 0.879 before it was caught.** 93% of
> cells score exactly 0, so ties dominate every comparison; breaking them by
> sort order rather than averaging ranks turned chance into an apparently
> strong result. `_auc()` in the builder now uses average ranks and is verified
> against perfect / reversed / all-tied cases.

**What this means:** the layer rests on standard, well-understood physics and
on *no local evidence whatsoever*. It is a well-founded hypothesis about
Arunachal, not a measured fact about it.

**What would validate it:** district inundation reports with dates and
locations; Sentinel-1 water mapping for named events; river gauge stage records.

## Limits stated in the product

- **No depth, ever** — needs 2-D hydraulic modelling on LiDAR
- **Small streams are a watch, not a forecast** — most catchments sit below what
  any global discharge model resolves
- **No dam releases** — several of these rivers are regulated
- **Rainfall sampled at ~33 km** — a small basin inherits its neighbour's weather
- **GloFAS not in this build** — 2 files on disk where a climatology needs years
  of reanalysis. A download, not a permission, and the next thing to do.

## Next

1. **GloFAS reanalysis archive** → discharge anomaly on the five large rivers,
   turning the "large river" tier from catchment-rain into real river forecast
2. **River gauges** (the one genuine ask of the state) → 6–24 h forecast on
   gauged basins
3. Any dated, located flood observation at all → the first real validation
