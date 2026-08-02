"""Stage 1b — flow routing and the Topographic Wetness Index.

Produces, at 100 m on the canonical grid:

    hydro_flowacc_cells     upslope contributing cells (D8)
    hydro_twi               ln(specific catchment area / tan(slope))

TWI, in plain terms: *how much upslope land drains into this cell, versus how
fast that water can leave.* A hollow with a big catchment and a gentle floor
holds water; a steep exposed spur sheds it. Wet ground raises pore water
pressure, which is the mechanism that turns a stable slope into a moving one —
so this is one of the more physically meaningful features we can build.

    high TWI  ──►  valley bottoms, hollows, convergent slopes  (wet)
    low  TWI  ──►  ridges, spurs, planar steep faces           (dry)

Two things that matter for correctness:

1.  Flow is routed on the UNMASKED DEM. Water enters Arunachal from Tibet,
    Bhutan and Assam; clipping to the state first would cut every catchment at
    the border and systematically understate upslope area near the boundary —
    which is exactly where the big rivers are.

2.  Depressions get filled and flats resolved before routing. A raw DEM is full
    of one-cell pits, mostly noise. Left alone, flow accumulation dead-ends in
    them and produces broken drainage networks.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time
import warnings

import numpy as np
import rasterio

import grid as G
from common import INTERIM

warnings.filterwarnings("ignore")

SRC = INTERIM / "terrain"

# D8: water leaves a cell toward whichever of its 8 neighbours is lowest.
# pysheds wants the direction codes in this (E, SE, S, SW, W, NW, N, NE) order.
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)


def main() -> None:
    # pysheds still calls np.in1d, which NumPy 2.0 removed. It is exactly
    # np.isin for the 1-D input pysheds passes it, so shim rather than pin
    # numpy back — everything else in this project wants NumPy 2.
    if not hasattr(np, "in1d"):
        np.in1d = np.isin

    from pysheds.grid import Grid          # imported late: pulls in numba

    t0 = time.time()
    print("Stage 1b — flow routing + TWI")

    dem_path = SRC / "_dem_unmasked_m.tif"
    pgrid = Grid.from_raster(str(dem_path))
    dem = pgrid.read_raster(str(dem_path))
    print(f"  DEM {dem.shape}  loaded {time.time()-t0:.0f}s")

    # Sea level / outside-coverage cells would otherwise act as giant sinks.
    dem_f = np.where(np.isfinite(dem), dem, np.nan)
    print(f"  elevation range: {np.nanmin(dem_f):.0f} .. {np.nanmax(dem_f):.0f} m")

    print("  conditioning DEM (pits -> depressions -> flats)...", flush=True)
    dem = pgrid.fill_pits(dem)
    dem = pgrid.fill_depressions(dem)
    dem = pgrid.resolve_flats(dem)
    print(f"    done {time.time()-t0:.0f}s", flush=True)

    print("  flow direction + accumulation...", flush=True)
    fdir = pgrid.flowdir(dem, dirmap=DIRMAP)
    acc = pgrid.accumulation(fdir, dirmap=DIRMAP)
    acc = np.asarray(acc, dtype=np.float32)
    print(f"    done {time.time()-t0:.0f}s  max upslope {acc.max():,.0f} cells "
          f"({acc.max()*G.CELL**2/1e6:,.0f} km2)", flush=True)

    # --- TWI ---------------------------------------------------------------
    with rasterio.open(SRC / "terrain_slope_deg.tif") as s:
        slope_deg = s.read(1)

    # Specific catchment area: upslope area per unit contour width. With square
    # cells that is (n_cells * cell^2) / cell = n_cells * cell. The +1 counts
    # the cell itself, so ridge cells get a finite value instead of log(0).
    sca = (acc + 1.0) * G.CELL

    # tan(0) is 0 and would divide to infinity. A 0.1 deg floor is well below
    # anything the DEM resolves, so it only bites on genuinely flat ground.
    tan_b = np.tan(np.radians(np.maximum(slope_deg, 0.1)))

    with np.errstate(invalid="ignore", divide="ignore"):
        twi = np.log(sca / tan_b).astype(np.float32)
    twi[~np.isfinite(twi)] = np.nan

    # --- mask to state and write -------------------------------------------
    with rasterio.open(INTERIM / "state_mask.tif") as m:
        inside = m.read(1).astype(bool)

    profile = dict(driver="GTiff", height=G.NROWS, width=G.NCOLS, count=1,
                   dtype="float32", crs=G.CRS, transform=G.TRANSFORM,
                   nodata=np.nan, compress="deflate", tiled=True,
                   blockxsize=256, blockysize=256)

    for name, arr in (("hydro_flowacc_cells", acc.astype(np.float32)),
                      ("hydro_twi", twi)):
        a = arr.copy()
        a[~inside] = np.nan
        with rasterio.open(SRC / f"{name}.tif", "w", **profile) as dst:
            dst.write(a, 1)
        v = a[inside]
        v = v[np.isfinite(v)]
        q = np.percentile(v, [1, 50, 99])
        print(f"  {name:22} p1 {q[0]:9.2f}  med {q[1]:8.2f}  p99 {q[2]:10.2f}"
              f"   cover {100*len(v)/int(inside.sum()):5.1f}%")

    print(f"\n  total {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
