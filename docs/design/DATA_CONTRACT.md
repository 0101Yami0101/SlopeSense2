# Data Contract — the grid every table joins on

**Status: FINAL as of 2026-07-31.** These choices are frozen. Changing any of them
invalidates every derived file in `data/interim/` and `data/processed/`.

Canonical implementation: [`scripts/build/grid.py`](../../scripts/build/grid.py). This
document explains *why*; that module is the single source of truth for *what*. If they
ever disagree, the code wins and this document is the bug.

---

## 1 · Coordinate system — `EPSG:32646` (WGS 84 / UTM zone 46N)

Raw data arrives in degrees (EPSG:4326). A degree is not a fixed distance, so
"500 m from a road" cannot be expressed in it, and cells are not square.

Arunachal straddles UTM zones 46 and 47, which sounds disqualifying but isn't — measured
against the state polygon, the two disagree by **0.4%**, immaterial at 100 m cells.

| CRS | State area | vs published 83,743 km² |
|---|---|---|
| **32646 — UTM 46N** ✅ | 82,023 km² | −2.05% |
| 32647 — UTM 47N | 82,337 km² | −1.68% |
| 6933 — EASE-Grid equal-area | 81,995 km² | −2.09% |
| 7755 — India NSF LCC ❌ | 79,239 km² | −5.38% |

The consistent ~2% shortfall across unrelated projections is **GADM's polygon being
generalised**, not a projection error — which is itself the reason to distrust 7755, the
lone outlier.

**Chosen because** we compute distance-to-road / river / lineament across the whole grid,
while area only matters at the final aggregation step. UTM optimises the one we use more.

## 2 · Cell size — 100 m

| Size | Cells in state | Verdict |
|---|---|---|
| 30 m | 91 M | too large to iterate on |
| **100 m** ✅ | **8.2 M** | fits in memory; minutes per experiment |
| 250 m | 1.3 M | averages away the steep face that actually fails |

> **100 m is terrain resolution, not forecast resolution.** Prediction skill is capped by
> IMERG's ~11 km rainfall cell. The fine grid exists so slope and curvature are measured on
> the real slope rather than a smeared average — see DESIGN.md Part 1.

The Copernicus DEM is EPSG:4326 at ~30 m, so it is reprojected regardless. There is no
"align to native grid" option to preserve.

## 3 · Origin — `x = 350_000`, `y = 2_950_000`

Snapped to a round 100 m multiple in UTM 46N, deliberately *not* derived from the boundary
file — if GADM is ever updated, a bbox-derived origin would silently shift every cell.

Two constants reproduce the grid exactly. Extent 590 × 320 km → **5,900 × 3,200 cells**
(18.9 M in the bounding box, 8.2 M inside the state).

## 4 · Cell ID — `row * 100_000 + col`

| Option | Why not |
|---|---|
| Sequential `0…8.2M` | meaningless. If the grid ever changes, IDs shift **silently** and joins corrupt with no error |
| H3 / geohash | doesn't align to a raster; forces an extra resample |
| **`row * 100000 + col`** ✅ | decode any ID by arithmetic — a bad join is visible instantly |

Max value 320,005,900, comfortably inside `int32`. The multiplier 100,000 leaves room for
16× more columns than we use, so it survives a future finer grid.

**Chosen for debuggability.** Sequential IDs hide join errors; row/col makes them obvious.

## 5 · Column naming — `{group}_{name}_{unit}`

```
   dem_elev_m        terrain_slope_deg     soil_clay_pct
   soil_bulkdens_cgcm3                     rain_sum7d_mm
   dist_road_m       geol_lithology_cat    label_landslide_u8
```

> **The unit suffix is not decoration.** Our own raw viewer surfaced a bulk density of
> `107` — that is **cg/cm³**, not g/cm³. `soil_bulkdens_cgcm3` makes a unit error
> unmissable at the call site. This class of bug has already bitten us once.

**Dtypes** — at 8.2 M rows × ~30 columns:

| Policy | Memory |
|---|---|
| float64 everywhere | ~2.0 GB |
| **float32 / categorical / uint8** ✅ | **~1.0 GB** |

float32 carries ~7 significant digits — more than any input actually measures. Lithology
and land cover are `category`; flags and labels are `uint8`.

**Storage:** Parquet + zstd, partitioned by fold for cheap held-out reads.

## 6 · Spatial validation folds — 50 km blocks → 5 folds 🔒

**The only decision here that can invalidate results rather than merely cost rework.**

Neighbouring 100 m cells are near-identical, so a random train/test split lets the model
see the answer through the training set. The score looks excellent and means nothing.

| Option | Verdict |
|---|---|
| Random rows | ❌ leaks badly; inflates AUC |
| By district (29) | good for *reporting*, wildly uneven for *fitting* |
| By watershed | natural, but uneven sizes |
| **50 km blocks → 5 folds** ✅ | even sizes, stable variance, standard practice |

Blocks are assigned to folds with a **fixed seed (42)**, written once to
`data/interim/spatial_folds.parquet`, and content-hashed.

> 🔒 **Frozen before any model is trained.** If folds are chosen after seeing results, you
> will unconsciously prefer the ones that flatter the model — and you will not notice
> yourself doing it. The hash exists so a reviewer can prove the folds predate the numbers.

Report metrics **additionally** by district, because that is the unit the client thinks
in — but never *fit* on district splits.

---

## 7 · Training sample — constrained negatives 🔒

Frozen 2026-08-02. **Sample hash `b58e7dcc22134c1f`** over `(cell_id, label, fold)`.

| | |
|---|---|
| file | `data/processed/susceptibility_samples.parquet` |
| rows | 544,794 (90,799 pos / 453,995 neg) |
| domain | slope > 10°, land cover ∉ {snow/ice, water, moss} — **applied to both classes** |
| buffer | negatives > 500 m from any mapped slide |
| ratio | 1:5, stratified within fold → prevalence 16.67% in every fold |
| seed | 1337 |

📄 **Rationale and measurements: [LABELS_AND_SAMPLING.md](LABELS_AND_SAMPLING.md)** —
including the measured finding that constrained vs naive sampling makes **no difference
to AUC** in Arunachal (0.860 vs 0.862), and the two reasons the constraints stay anyway.

> ⚠️ **Out-of-domain cells must be masked at inference, never scored.** A model that never
> trained on glaciers must not assign them a susceptibility number. Hard requirement on P9.

---

## Change policy

Editing §1–§5 means deleting `data/interim/` and `data/processed/` and rebuilding.
Editing §6 or §7 after any model has been trained means **every previously reported number
is void** and must be recomputed and republished.
