"""Stage 1a — terrain derivatives from the Copernicus DEM onto the canonical grid.

Produces, at 100 m, aligned exactly to scripts/build/grid.py:

    dem_elev_m              mean elevation
    terrain_slope_deg       mean slope
    terrain_slope_max_deg   steepest 25 m sub-cell in the 100 m cell
    terrain_relief_m        max - min elevation inside the cell
    terrain_northness       cos(aspect)   ] aspect, but usable by a model
    terrain_eastness        sin(aspect)   ]
    terrain_curv_prof       profile curvature (concave/convex down-slope)
    terrain_curv_plan       plan curvature (converging/diverging flow)

Two decisions worth understanding:

1.  Slope is computed at 25 m and then aggregated, NOT computed on a 100 m DEM.
    Resampling elevation to 100 m first smooths the terrain and systematically
    *under*-states steepness — exactly the quantity landslides care about most.
    Computing fine then aggregating keeps the real gradient, and lets us keep
    the max as well as the mean. 25 m is close to the DEM's native ~30 m and
    nests exactly 4x4 inside a 100 m cell.

2.  Aspect is stored as northness/eastness rather than degrees. A model reading
    raw degrees sees 359 and 1 as far apart when they are neighbours. The
    sine/cosine pair has no seam. Northness also carries real physical meaning
    here: north-facing Himalayan slopes hold moisture and vegetation
    differently from south-facing ones.

Work is chunked so memory stays flat regardless of grid size. Each chunk is
reprojected with a halo, so gradients at chunk edges see their neighbours and
no seams appear in the output.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time
import warnings

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.warp import reproject

import grid as G
from common import INTERIM, TERRAIN

warnings.filterwarnings("ignore")

FINE = 25                      # metres; nests 4x4 inside a 100 m cell
F = G.CELL // FINE             # = 4
HALO = 8                       # fine cells of overlap, so gradients see neighbours
CHUNK = 400                    # output cells per chunk side (40 km)

LAYERS = ["dem_elev_m", "terrain_slope_deg", "terrain_slope_max_deg",
          "terrain_relief_m", "terrain_northness", "terrain_eastness",
          "terrain_curv_prof", "terrain_curv_plan"]


def derivatives(z: np.ndarray, res: float):
    """Slope, aspect and curvature from an elevation patch.

    Zevenbergen-Thorne style: fit local first and second derivatives, then
    combine them. `res` is the cell size in metres, which is why the DEM has to
    be in a metric CRS before we get here.
    """
    # np.gradient returns d/drow, d/dcol. Row index grows downward (south), so
    # dz/dy needs its sign flipped to mean "northward".
    dzdy, dzdx = np.gradient(z, res)
    dzdy = -dzdy

    p, q = dzdx, dzdy
    slope = np.degrees(np.arctan(np.hypot(p, q)))

    # arctan2(-x, y) puts 0 deg at north and increases clockwise, the
    # convention every GIS uses for aspect.
    aspect = np.arctan2(-p, q)

    d2y, d2x = np.gradient(dzdx, res)
    _, d2xy = np.gradient(dzdy, res)
    r, t, s = d2x, -d2y, d2xy

    g2 = p * p + q * q
    denom_prof = g2 * np.power(1 + g2, 1.5)
    denom_plan = np.power(g2, 1.5)
    with np.errstate(invalid="ignore", divide="ignore"):
        prof = -(r * p * p + 2 * s * p * q + t * q * q) / denom_prof
        plan = -(r * q * q - 2 * s * p * q + t * p * p) / denom_plan

    # Both curvatures divide by the gradient, so near-flat ground sends them to
    # infinity. That is a numerical artefact, not terrain: flat ground has no
    # meaningful profile or plan curvature, and 0 is the honest value. The
    # threshold is g2 for a 0.5 deg slope. Without this the tail reaches -400
    # against a p1..p99 range of only +/-0.02, and any model would key on it.
    FLAT = 1e-4
    prof = np.where(g2 < FLAT, 0.0, prof)
    plan = np.where(g2 < FLAT, 0.0, plan)

    # Curvature of 0.5 /m is a 2 m radius of curvature — far below anything a
    # 25 m DEM can resolve, so whatever survives the guard above and still
    # exceeds this is noise. Clip rather than drop, to keep the cell usable.
    prof = np.clip(prof, -0.5, 0.5)
    plan = np.clip(plan, -0.5, 0.5)

    return slope, aspect, prof, plan


def block_reduce(a: np.ndarray, how: str) -> np.ndarray:
    """Aggregate a fine array to the 100 m grid (F x F blocks)."""
    h, w = a.shape[0] // F, a.shape[1] // F
    v = a[: h * F, : w * F].reshape(h, F, w, F)
    fn = {"mean": np.nanmean, "max": np.nanmax, "min": np.nanmin}[how]
    return fn(v, axis=(1, 3))


def main() -> None:
    tiles = sorted(TERRAIN.rglob("*.tif"))
    print(f"Terrain derivatives — {len(tiles)} Copernicus tiles")
    print(f"  fine grid {FINE} m -> aggregate {F}x{F} -> {G.CELL} m")

    srcs = [rasterio.open(t) for t in tiles]
    nodata = srcs[0].nodata
    print(f"  source crs {srcs[0].crs}, nodata {nodata}")

    out = {k: np.full(G.SHAPE, np.nan, dtype=np.float32) for k in LAYERS}
    t0 = time.time()
    n_chunks = ((G.NROWS + CHUNK - 1) // CHUNK) * ((G.NCOLS + CHUNK - 1) // CHUNK)
    done = 0

    for r0 in range(0, G.NROWS, CHUNK):
        for c0 in range(0, G.NCOLS, CHUNK):
            r1 = min(r0 + CHUNK, G.NROWS)
            c1 = min(c0 + CHUNK, G.NCOLS)
            done += 1

            # Fine destination for this chunk, plus a halo on every side.
            fh = (r1 - r0) * F + 2 * HALO
            fw = (c1 - c0) * F + 2 * HALO
            west = G.ORIGIN_X + c0 * G.CELL - HALO * FINE
            north = G.TOP_Y - r0 * G.CELL + HALO * FINE
            ftr = Affine(FINE, 0, west, 0, -FINE, north)

            fine = np.full((fh, fw), np.nan, dtype=np.float32)
            # Pull from every source tile that overlaps; non-overlapping ones
            # contribute nothing, so this is just a scatter-gather.
            east = west + fw * FINE
            south = north - fh * FINE
            for s in srcs:
                b = s.bounds
                # cheap bbox reject in the source's own (geographic) CRS
                from rasterio.warp import transform_bounds
                sw, ss, se, sn = transform_bounds(G.CRS, s.crs,
                                                  west, south, east, north)
                if b.right < sw or b.left > se or b.top < ss or b.bottom > sn:
                    continue
                patch = np.full((fh, fw), np.nan, dtype=np.float32)
                reproject(
                    source=rasterio.band(s, 1),
                    destination=patch,
                    dst_transform=ftr, dst_crs=G.CRS, dst_nodata=np.nan,
                    src_nodata=nodata,
                    resampling=Resampling.bilinear,
                )
                np.copyto(fine, patch, where=~np.isnan(patch))

            if np.all(np.isnan(fine)):
                continue

            slope, aspect, prof, plan = derivatives(fine, FINE)

            # Drop the halo now that gradients have used it.
            sl = slice(HALO, fh - HALO), slice(HALO, fw - HALO)
            fine_c, slope_c = fine[sl], slope[sl]
            aspect_c, prof_c, plan_c = aspect[sl], prof[sl], plan[sl]

            dst = (slice(r0, r1), slice(c0, c1))
            out["dem_elev_m"][dst] = block_reduce(fine_c, "mean")
            out["terrain_slope_deg"][dst] = block_reduce(slope_c, "mean")
            out["terrain_slope_max_deg"][dst] = block_reduce(slope_c, "max")
            out["terrain_relief_m"][dst] = (block_reduce(fine_c, "max")
                                            - block_reduce(fine_c, "min"))
            # Aspect is circular: average the unit vector, not the angle.
            out["terrain_northness"][dst] = block_reduce(np.cos(aspect_c), "mean")
            out["terrain_eastness"][dst] = block_reduce(np.sin(aspect_c), "mean")
            out["terrain_curv_prof"][dst] = block_reduce(prof_c, "mean")
            out["terrain_curv_plan"][dst] = block_reduce(plan_c, "mean")

            if done % 10 == 0 or done == n_chunks:
                el = time.time() - t0
                print(f"    chunk {done}/{n_chunks}  {el:.0f}s  "
                      f"ETA {el/done*(n_chunks-done):.0f}s", flush=True)

    for s in srcs:
        s.close()

    # --- mask to the state and write ---------------------------------------
    with rasterio.open(INTERIM / "state_mask.tif") as m:
        inside = m.read(1).astype(bool)

    profile = dict(driver="GTiff", height=G.NROWS, width=G.NCOLS, count=1,
                   dtype="float32", crs=G.CRS, transform=G.TRANSFORM,
                   nodata=np.nan, compress="deflate", tiled=True,
                   blockxsize=256, blockysize=256)

    dest = INTERIM / "terrain"
    dest.mkdir(parents=True, exist_ok=True)

    # Hydrology needs the DEM *unmasked*. Water flows into Arunachal from Tibet,
    # Bhutan and Assam, so clipping to the state before routing flow would cut
    # every catchment off at the border and understate upslope area.
    with rasterio.open(dest / "_dem_unmasked_m.tif", "w", **profile) as dst:
        dst.write(out["dem_elev_m"], 1)

    print()
    for k in LAYERS:
        a = out[k]
        a[~inside] = np.nan
        with rasterio.open(dest / f"{k}.tif", "w", **profile) as dst:
            dst.write(a, 1)
        v = a[inside]
        v = v[np.isfinite(v)]
        cov = 100 * len(v) / int(inside.sum())
        print(f"  {k:24} min {np.min(v):9.2f}  med {np.median(v):8.2f}  "
              f"max {np.max(v):9.2f}   cover {cov:5.1f}%")

    print(f"\n  wrote {len(LAYERS)} layers to {dest}  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
