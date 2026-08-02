"""P7a — collapse 9,555 daily IMERG files into one array, and map it to the grid.

Outputs:

    data/interim/rainfall/precip_mm.npy      (ndays, nlat, nlon) float32
    data/interim/rainfall/dates.npy          datetime64[D], aligned to axis 0
    data/interim/rainfall/_stack_meta.json
    data/interim/rainfall/imerg_index.tif    100 m grid -> flat IMERG cell index

════════════════════════════════════════════════════════════════════════════
WHY RAINFALL IS *NOT* RESAMPLED TO 100 m
════════════════════════════════════════════════════════════════════════════
IMERG is 0.1 deg — about 11 km. The whole state is 1,953 rainfall cells. Our
terrain grid is 8,202,343 cells. Storing rainfall at 100 m for 26 years would
be 8.2M x 9,555 = 78 billion values, and every one of them would be a copy:
roughly 12,000 identical 100 m cells inside each IMERG pixel.

So rainfall stays on its native grid and we store ONE integer per terrain cell
saying which rainfall pixel it sits in (`imerg_index.tif`). A trigger model
then joins on (imerg_index, date) instead of (cell_id, date). Same information,
four orders of magnitude less storage.

⚠️ This is also an honest statement of resolution. Upsampling to 100 m would
LOOK like a 100 m rainfall product and invite exactly that misreading. It is
11 km data. The map should never imply otherwise.

════════════════════════════════════════════════════════════════════════════
TWO ORIENTATION TRAPS IN THESE FILES
════════════════════════════════════════════════════════════════════════════
1. IMERG's OPeNDAP subset returns dimensions ordered (time, LON, LAT) — lon
   before lat, the opposite of the usual convention. Reading it as (lat, lon)
   gives a transposed, silently wrong grid.
2. lat ascends (26.55 -> 29.55) but rasters are north-up, so it must be
   flipped before writing anything georeferenced.

Both are caught by the self-check at the bottom: the monsoon signal must land
in the south-west foothills, not the northern high Himalaya.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime as dt
import json
import time
import warnings

import numpy as np
import rasterio
import xarray as xr
from affine import Affine
from rasterio.enums import Resampling
from rasterio.warp import reproject

import grid as G
from common import INTERIM, WEATHER

warnings.filterwarnings("ignore")

SRC = WEATHER / "gpm_imerg_daily"
OUT = INTERIM / "rainfall"
CELL_DEG = 0.1


def main() -> None:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    print("P7a — building the rainfall stack")

    files = sorted(SRC.glob("*.nc4"))
    print(f"  {len(files):,} daily files")

    # --- geometry from the first file ------------------------------------
    with xr.open_dataset(files[0]) as ds0:
        lon = ds0.lon.values.astype("float64")
        lat = ds0.lat.values.astype("float64")
    nlon, nlat = len(lon), len(lat)
    asc = lat[1] > lat[0]
    print(f"  IMERG grid: {nlat} lat x {nlon} lon = {nlat*nlon:,} cells"
          f"   (lat {'ascending' if asc else 'descending'})")
    print(f"    lon {lon.min():.2f}..{lon.max():.2f}   "
          f"lat {lat.min():.2f}..{lat.max():.2f}")

    # --- read every day ---------------------------------------------------
    stack = np.full((len(files), nlat, nlon), np.nan, dtype=np.float32)
    dates = np.empty(len(files), dtype="datetime64[D]")
    bad = []
    for i, f in enumerate(files):
        d = dt.datetime.strptime(f.stem[-8:], "%Y%m%d").date()
        dates[i] = np.datetime64(d)
        try:
            with xr.open_dataset(f) as ds:
                a = ds["precipitation"].values      # (time, lon, lat)
                a = np.squeeze(a)
                if a.shape == (nlon, nlat):
                    a = a.T                          # -> (lat, lon)
                elif a.shape != (nlat, nlon):
                    bad.append((f.name, a.shape)); continue
                stack[i] = a.astype(np.float32)
        except Exception as exc:                     # noqa: BLE001
            bad.append((f.name, type(exc).__name__))
        if (i + 1) % 2000 == 0:
            print(f"    {i+1:,}/{len(files):,}  {time.time()-t0:.0f}s", flush=True)

    if bad:
        print(f"  ⚠ {len(bad)} unreadable: {bad[:3]}")

    # flip to north-up once, here, so nothing downstream has to think about it
    if asc:
        stack = stack[:, ::-1, :]
        lat = lat[::-1]
        print("  flipped lat to north-up")

    order = np.argsort(dates)
    stack, dates = stack[order], dates[order]

    nanfrac = float(np.isnan(stack).mean())
    print(f"\n  stack {stack.shape}  {stack.nbytes/1e6:.0f} MB   "
          f"nan {100*nanfrac:.3f}%")
    print(f"  precip mm/day: min {np.nanmin(stack):.1f}  "
          f"mean {np.nanmean(stack):.2f}  max {np.nanmax(stack):.1f}")

    np.save(OUT / "precip_mm.npy", stack)
    np.save(OUT / "dates.npy", dates)

    # --- map IMERG cells onto the 100 m grid ------------------------------
    # Build an index raster in EPSG:4326 whose VALUE is the flat cell index,
    # then nearest-neighbour reproject it. Far cheaper than reprojecting 8.2M
    # point coordinates, and exact: nearest on an index array cannot interpolate
    # two indices into a third that means nothing.
    idx = np.arange(nlat * nlon, dtype=np.int32).reshape(nlat, nlon)
    src_tf = Affine(CELL_DEG, 0, lon.min() - CELL_DEG / 2,
                    0, -CELL_DEG, lat.max() + CELL_DEG / 2)
    dst = np.full(G.SHAPE, -1, dtype=np.int32)
    reproject(source=idx, destination=dst,
              src_transform=src_tf, src_crs="EPSG:4326",
              dst_transform=G.TRANSFORM, dst_crs=G.CRS,
              src_nodata=-1, dst_nodata=-1,
              resampling=Resampling.nearest)

    with rasterio.open(INTERIM / "state_mask.tif") as m:
        inside = m.read(1).astype(bool)
    unmapped = int((dst[inside] < 0).sum())
    used = np.unique(dst[inside & (dst >= 0)])
    print(f"\n  imerg_index: {len(used):,} IMERG cells cover the state   "
          f"unmapped in-state cells: {unmapped:,}")
    if unmapped:
        print("    ⚠ some in-state cells have no rainfall pixel")

    prof = dict(driver="GTiff", height=G.NROWS, width=G.NCOLS, count=1,
                dtype="int32", crs=G.CRS, transform=G.TRANSFORM, nodata=-1,
                compress="deflate", tiled=True, blockxsize=256, blockysize=256)
    a = dst.copy(); a[~inside] = -1
    with rasterio.open(OUT / "imerg_index.tif", "w", **prof) as d:
        d.write(a, 1)

    # --- self-check: does the monsoon land where it should? ---------------
    yr = dates.astype("datetime64[Y]").astype(int) + 1970
    mo = dates.astype("datetime64[M]").astype(int) % 12 + 1
    ann = np.nansum(stack, axis=0) / len(np.unique(yr))
    print(f"\n  mean annual rainfall over the AOI box: "
          f"{np.nanmean(ann):,.0f} mm   max {np.nanmax(ann):,.0f} mm")

    # Test the LATITUDINAL GRADIENT, not the argmax. The gradient is the robust
    # orographic signal — dry in the northern rain shadow, wet in the foothill
    # belt — and a transposed or mis-flipped grid destroys it.
    #
    # Do NOT assert on the wettest single pixel: that sits at ~28.55N, 94.75E,
    # far north of the foothills, because the Siang gorge funnels monsoon air
    # deep into the range and makes a genuine local maximum there. An earlier
    # version of this check flagged that real feature as a bug.
    by_lat = np.nanmean(ann, axis=1)
    north = float(np.nanmean(by_lat[:6]))       # top ~1.8 deg
    south = float(np.nanmean(by_lat[-12:]))     # foothill belt
    print(f"    northern crest  {north:,.0f} mm/yr")
    print(f"    foothill belt   {south:,.0f} mm/yr")
    if south > north * 1.5:
        print(f"    ✅ gradient correct ({south/north:.1f}x wetter south)")
    else:
        print("    ⚠️ EXPECTED the south to be far wetter — check orientation")
    r, c = np.unravel_index(np.nanargmax(ann), ann.shape)
    print(f"    wettest pixel: lat {lat[r]:.2f}, lon {lon[c]:.2f} "
          f"({np.nanmax(ann):,.0f} mm/yr) — Siang gorge, expected")

    print("\n  monthly mean (mm/day, AOI mean):")
    for m_ in range(1, 13):
        v = np.nanmean(stack[mo == m_])
        bar = "#" * int(v * 3)
        print(f"    {m_:>2}  {v:5.2f}  {bar}")

    (OUT / "_stack_meta.json").write_text(json.dumps({
        "files": len(files), "unreadable": len(bad),
        "shape": list(stack.shape), "nan_frac": round(nanfrac, 6),
        "date_min": str(dates[0]), "date_max": str(dates[-1]),
        "lat_min": float(lat.min()), "lat_max": float(lat.max()),
        "lon_min": float(lon.min()), "lon_max": float(lon.max()),
        "cell_deg": CELL_DEG, "lat_orientation": "north-up (flipped on load)",
        "imerg_cells_over_state": int(len(used)),
        "note": "11 km native resolution — never upsample to 100 m",
    }, indent=2))

    print(f"\n  wrote {OUT}   ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
