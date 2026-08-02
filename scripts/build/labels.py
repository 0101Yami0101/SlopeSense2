"""Stage 2a — turn four landslide inventories into one label layer on the grid.

Outputs, all on the canonical 100 m grid:

    label_slide            1 where any inventory maps a landslide, else 0
    label_nsource_cat      how many independent inventories mark this cell (0-4)
    label_source_cat       bitmask of WHICH inventories (see _label_meta.json)
    label_dist_slide_m     distance to the nearest mapped landslide, any source

The distance layer is the one that matters most downstream: negative sampling
uses it to keep a buffer between "no landslide" cells and known failures.

────────────────────────────────────────────────────────────────────────────
WHY all_touched=True HERE, WHEN THE TERRAIN LAYERS USE all_touched=False
────────────────────────────────────────────────────────────────────────────
Measured on the GSI inventory:

    median landslide polygon         944 m2   (~30 x 30 m)
    p90                            8,373 m2
    smaller than one 100 m cell      91.5%

Nine out of ten mapped landslides are smaller than a single grid cell. Under
centre-in-polygon rasterisation a cell only turns on when the polygon covers
its centre point, so the overwhelming majority of our positives would be
silently discarded — and the ones that survived would be biased toward large
slides, which behave differently from small ones.

So a cell is positive if a landslide polygon touches it at all. Read the label
as "a failure occurred somewhere in this cell", NOT "this whole cell failed".
At 100 m that is the honest reading regardless of the rasterisation rule.

────────────────────────────────────────────────────────────────────────────
INVENTORY OVERLAP IS EXPECTED, NOT A BUG
────────────────────────────────────────────────────────────────────────────
GSI and Bhuvan are independent mapping programmes over the same terrain, so
the same physical landslide can appear in both. We deliberately do NOT try to
match features across sources — geometric dedup on differently-digitised
outlines is guesswork. Instead we union at the RASTER level: a cell is
positive once, no matter how many inventories mark it.

label_nsource_cat then falls out for free, and it is genuinely useful: cells
several inventories agree on are the ones to trust when auditing the model.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import time
import warnings

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt

import grid as G
from common import INTERIM, LABELS

warnings.filterwarnings("ignore")

OUT = INTERIM / "labels"

# bit position -> (file, human name). Bitmask so one uint8 records any
# combination of sources without needing four separate layers.
SOURCES = [
    (0, "gsi-nlfc_landslides_polygon_arunachal.geojson", "GSI polygons"),
    (1, "bhuvan_ar_slim_2014_gcs_polygon_arunachal.geojson", "Bhuvan 2014"),
    (2, "bhuvan_ar_slim_2017_polygon_arunachal.geojson", "Bhuvan 2017"),
    (3, "bhuvan_ls_arunachal_2023_polygon_arunachal.geojson", "Bhuvan 2023"),
]

# Point inventories are NOT used as positives. GSI points are km-level
# centroids and NASA GLC location accuracy is explicitly coarse — turning a
# point into a 100 m cell asserts a precision the source does not have.
# They are kept for independent validation instead. See _label_meta.json.
POINT_ONLY = [
    "gsi-nlfc_landslides_point_arunachal.geojson",
    "nasa-glc_landslides_point_arunachal.geojson",
]


def write(name: str, arr: np.ndarray, inside: np.ndarray, dtype: str):
    prof = dict(driver="GTiff", height=G.NROWS, width=G.NCOLS, count=1,
                dtype=dtype, crs=G.CRS, transform=G.TRANSFORM,
                compress="deflate", tiled=True, blockxsize=256, blockysize=256)
    a = arr.astype(dtype).copy()
    if dtype == "float32":
        a[~inside] = np.nan
        prof["nodata"] = np.nan
    else:
        a[~inside] = 0
        prof["nodata"] = 0
    OUT.mkdir(parents=True, exist_ok=True)
    with rasterio.open(OUT / f"{name}.tif", "w", **prof) as dst:
        dst.write(a, 1)
    return a


def main() -> None:
    t0 = time.time()
    print("Stage 2a — landslide label layer")

    with rasterio.open(INTERIM / "state_mask.tif") as m:
        inside = m.read(1).astype(bool)
    n_inside = int(inside.sum())

    bits = np.zeros(G.SHAPE, dtype=np.uint8)
    meta_sources = []

    for bit, fname, label in SOURCES:
        path = LABELS / fname
        if not path.exists():
            print(f"  {label:16} MISSING — skipped")
            continue
        gdf = gpd.read_file(path).to_crs(G.CRS)
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]

        mask = rasterize(
            ((geom, 1) for geom in gdf.geometry),
            out_shape=G.SHAPE, transform=G.TRANSFORM,
            fill=0, dtype="uint8", all_touched=True,   # see module docstring
        )
        bits |= (mask.astype(np.uint8) << bit)

        on_state = int((mask.astype(bool) & inside).sum())
        print(f"  {label:16} {len(gdf):>7,} polygons -> {on_state:>8,} cells "
              f"({100*on_state/n_inside:.3f}% of state)")
        meta_sources.append({"bit": bit, "file": fname, "name": label,
                             "features": int(len(gdf)), "cells_in_state": on_state})

    # --- union, agreement -----------------------------------------------
    slide = (bits > 0).astype(np.uint8)
    nsrc = np.zeros(G.SHAPE, dtype=np.uint8)
    for bit, _, _ in SOURCES:
        nsrc += ((bits >> bit) & 1).astype(np.uint8)

    write("label_slide", slide, inside, "uint8")
    write("label_source_cat", bits, inside, "uint8")
    write("label_nsource_cat", nsrc, inside, "uint8")

    pos = int((slide.astype(bool) & inside).sum())
    print(f"\n  union positives: {pos:,} cells "
          f"({100*pos/n_inside:.3f}% of the state, {pos*G.CELL**2/1e6:,.0f} km2)")

    print("\n  inventory agreement (positive cells only):")
    v = nsrc[inside & slide.astype(bool)]
    for k in range(1, len(SOURCES) + 1):
        c = int((v == k).sum())
        if c:
            print(f"    {k} source{'s' if k > 1 else ' '}  {c:>8,}  "
                  f"{100*c/len(v):5.1f}%")

    # --- distance to nearest mapped slide --------------------------------
    # Computed on the FULL grid, not the masked one: a cell near the border
    # must measure to a slide just outside the state, not report infinity.
    print("\n  distance transform...", flush=True)
    dist = distance_transform_edt(slide == 0, sampling=(G.CELL, G.CELL))
    a = write("label_dist_slide_m", dist, inside, "float32")
    v = a[inside]
    v = v[np.isfinite(v)]
    q = np.percentile(v, [50, 90, 99])
    print(f"  label_dist_slide_m   median {q[0]:,.0f} m   p90 {q[1]:,.0f} m   "
          f"p99 {q[2]:,.0f} m   max {v.max():,.0f} m")

    # --- validation-only point inventories --------------------------------
    val = []
    for fname in POINT_ONLY:
        p = LABELS / fname
        if p.exists():
            gdf = gpd.read_file(p).to_crs(G.CRS)
            val.append({"file": fname, "features": int(len(gdf))})
            print(f"  held for validation only: {fname}  ({len(gdf):,} points)")

    (OUT / "_label_meta.json").write_text(json.dumps({
        "grid_crs": G.CRS, "cell_m": G.CELL,
        "rasterisation": "all_touched=True (91.5% of slides < 1 cell)",
        "positive_cells": pos,
        "state_cells": n_inside,
        "prevalence_frac": round(pos / n_inside, 6),
        "sources_used_as_positives": meta_sources,
        "sources_held_for_validation": val,
        "source_bitmask": {str(b): n for b, _, n in SOURCES},
    }, indent=2))

    print(f"\n  wrote {OUT}   ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
