"""Stage 1c — distance-to-feature layers on the canonical grid.

    dist_river_m       to the nearest mapped river channel
    dist_road_m        to the nearest road
    dist_lineament_m   to the nearest mapped fault / fracture line

Why each one earns its place:

    rivers      undercut the toe of a slope, removing what holds it up
    roads       cut benches into hillsides, over-steepening them and dumping
                spoil downslope. Verified earlier on our own inventory: slides
                are ~2.3x more likely near a road than chance — the strongest
                single proximity signal we found
    lineaments  bedrock beside a fault is shattered and weak

Method: rasterise the vector onto the grid, then run a Euclidean distance
transform outward from it. This is exact to the cell and takes seconds, versus
minutes for a nearest-neighbour search over 8.2 M points.

Distances are computed on the FULL grid before masking, so a cell near the
border measures to a road just outside the state rather than reporting a
misleadingly large distance.

⚠️ Road proximity is partly a *mapping* artefact as well as a physical one:
surveyors reach landslides near roads more easily, so roads are over-represented
in any inventory. Keep the feature — the mechanism is real — but do not read its
importance score as pure physics.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time
import warnings

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt

import grid as G
from common import AOI_NAME, CONTEXT, EXPOSURE, HYDROLOGY, INTERIM

warnings.filterwarnings("ignore")

OUT = INTERIM / "terrain"

SOURCES = [
    ("dist_river_m", HYDROLOGY / f"hydrosheds_rivers_vector_{AOI_NAME}.gpkg", None),
    ("dist_road_m", EXPOSURE / f"osm_roads_vector_{AOI_NAME}.gpkg", None),
    ("dist_lineament_m", CONTEXT / f"apssdi_lineaments_vector_{AOI_NAME}.geojson", None),
]


def distance_to(path: Path, label: str) -> np.ndarray | None:
    if not path.exists():
        print(f"  {label:18} MISSING {path.name}")
        return None

    t0 = time.time()
    gdf = gpd.read_file(path)
    if gdf.empty:
        print(f"  {label:18} EMPTY")
        return None
    gdf = gdf.to_crs(G.CRS)

    # all_touched: a line thinner than a cell must still mark every cell it
    # crosses, or the distance transform starts from a broken, dotted source.
    mask = rasterize(
        ((geom, 1) for geom in gdf.geometry if geom is not None),
        out_shape=G.SHAPE, transform=G.TRANSFORM,
        fill=0, dtype="uint8", all_touched=True,
    )
    n_on = int(mask.sum())
    if n_on == 0:
        print(f"  {label:18} rasterised to nothing (outside grid?)")
        return None

    # distance_transform_edt measures distance to the nearest ZERO, so invert:
    # feature cells become 0, everything else becomes the thing to measure.
    dist = distance_transform_edt(mask == 0, sampling=(G.CELL, G.CELL))
    print(f"  {label:18} {len(gdf):>7,} features  {n_on:>9,} cells on  "
          f"{time.time()-t0:5.1f}s")
    return dist.astype(np.float32)


def main() -> None:
    print("Stage 1c — distance-to-feature layers")

    with rasterio.open(INTERIM / "state_mask.tif") as m:
        inside = m.read(1).astype(bool)

    profile = dict(driver="GTiff", height=G.NROWS, width=G.NCOLS, count=1,
                   dtype="float32", crs=G.CRS, transform=G.TRANSFORM,
                   nodata=np.nan, compress="deflate", tiled=True,
                   blockxsize=256, blockysize=256)

    results = {}
    for name, path, _ in SOURCES:
        d = distance_to(path, name)
        if d is None:
            continue
        results[name] = d

    print()
    for name, d in results.items():
        a = d.copy()
        a[~inside] = np.nan
        with rasterio.open(OUT / f"{name}.tif", "w", **profile) as dst:
            dst.write(a, 1)
        v = a[inside]
        v = v[np.isfinite(v)]
        q = np.percentile(v, [50, 90, 99])
        print(f"  {name:18} median {q[0]:8.0f} m   p90 {q[1]:8.0f} m   "
              f"p99 {q[2]:9.0f} m   max {v.max():9.0f} m")

    print(f"\n  wrote {len(results)} layers to {OUT}")


if __name__ == "__main__":
    main()
