"""Stage 1d — soil, land cover and lithology onto the canonical grid.

    soil_*        18 SoilGrids properties x depths, resampled 250 m -> 100 m
    lc_class_cat  ESA WorldCover, 10 m majority class per 100 m cell
    geol_rockgr_cat / geol_lithunit_cat   APSSDI lithology polygons

Column names carry the SOURCE unit, not a tidied one:

    soil_bdod_0-5cm_cgcm3      NOT "_gcm3"
    soil_clay_0-5cm_gkg        NOT "_pct"

SoilGrids ships integers in odd units — bulk density in centigrams/cm3, texture
in grams/kg. Our own raw viewer showed a bulk density of `107`, which is
1.07 g/cm3, not 107 of anything. Renaming to friendly units here would mean
converting, and a silent conversion error is far worse than an ugly name. The
model does not care about units; a human reading `soil_bdod_0-5cm_cgcm3` and
seeing 107 immediately knows it is right.

Resampling choice per data type:
    continuous (soil)   bilinear — averaging a soil percentage is meaningful
    categorical (LC)    mode     — averaging class codes would be nonsense
                                   ("forest 10 + water 80 / 2 = shrubland 45")
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
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.warp import reproject

import grid as G
from common import AOI_NAME, LANDCOVER, SOIL_GEOLOGY, INTERIM

warnings.filterwarnings("ignore")

OUT = INTERIM / "features"

# SoilGrids native units — see module docstring
SOIL_UNITS = {"bdod": "cgcm3", "cfvo": "cm3dm3", "clay": "gkg",
              "sand": "gkg", "silt": "gkg", "soc": "dgkg"}

# ESA WorldCover class codes (v200)
LC_LEGEND = {10: "tree cover", 20: "shrubland", 30: "grassland", 40: "cropland",
             50: "built-up", 60: "bare/sparse", 70: "snow and ice",
             80: "permanent water", 90: "herbaceous wetland",
             95: "mangroves", 100: "moss and lichen"}


def write(name: str, arr: np.ndarray, inside: np.ndarray, dtype="float32"):
    prof = dict(driver="GTiff", height=G.NROWS, width=G.NCOLS, count=1,
                dtype=dtype, crs=G.CRS, transform=G.TRANSFORM,
                compress="deflate", tiled=True, blockxsize=256, blockysize=256)
    a = arr.copy()
    if dtype == "float32":
        a = a.astype(np.float32)
        a[~inside] = np.nan
        prof["nodata"] = np.nan
    else:
        a = a.astype(dtype)
        a[~inside] = 0
        prof["nodata"] = 0
    OUT.mkdir(parents=True, exist_ok=True)
    with rasterio.open(OUT / f"{name}.tif", "w", **prof) as dst:
        dst.write(a, 1)
    return a


def do_soil(inside):
    print("\n  --- SoilGrids (bilinear, 250 m -> 100 m) ---")
    for f in sorted((SOIL_GEOLOGY / "soilgrids_250m").glob("soilgrids_*.tif")):
        stem = f.stem.replace("soilgrids_", "").replace(f"_250m_{AOI_NAME}", "")
        prop, depth = stem.split("-", 1)
        unit = SOIL_UNITS.get(prop, "raw")
        name = f"soil_{prop}_{depth}_{unit}"
        dst = np.full(G.SHAPE, np.nan, dtype=np.float32)
        with rasterio.open(f) as s:
            reproject(source=rasterio.band(s, 1), destination=dst,
                      dst_transform=G.TRANSFORM, dst_crs=G.CRS,
                      src_nodata=s.nodata, dst_nodata=np.nan,
                      resampling=Resampling.bilinear)
        a = write(name, dst, inside)
        v = a[inside]; v = v[np.isfinite(v)]
        print(f"    {name:34} med {np.median(v):8.1f}  "
              f"cover {100*len(v)/int(inside.sum()):5.1f}%")


def do_landcover(inside):
    print("\n  --- ESA WorldCover (mode, 10 m -> 100 m) ---")
    t0 = time.time()
    tiles = sorted(LANDCOVER.rglob("*_Map.tif"))
    out = np.zeros(G.SHAPE, dtype=np.uint8)
    for t in tiles:
        patch = np.zeros(G.SHAPE, dtype=np.uint8)
        with rasterio.open(t) as s:
            reproject(source=rasterio.band(s, 1), destination=patch,
                      dst_transform=G.TRANSFORM, dst_crs=G.CRS,
                      src_nodata=0, dst_nodata=0,
                      resampling=Resampling.mode)
        np.copyto(out, patch, where=patch > 0)
    a = write("lc_class_cat", out, inside, dtype="uint8")
    v = a[inside]
    print(f"    {len(tiles)} tiles in {time.time()-t0:.0f}s")
    for code, n in sorted(zip(*np.unique(v[v > 0], return_counts=True)),
                          key=lambda x: -x[1]):
        print(f"      {code:>4} {LC_LEGEND.get(int(code),'?'):<20} "
              f"{100*n/len(v):5.2f}%")
    return {int(k): v for k, v in LC_LEGEND.items()}


def do_lithology(inside):
    print("\n  --- APSSDI lithology (polygon -> categorical) ---")
    src = SOIL_GEOLOGY / f"apssdi_lithology_vector_{AOI_NAME}.geojson"
    gdf = gpd.read_file(src).to_crs(G.CRS)
    legends = {}
    for field, name in (("ROCK_GR", "geol_rockgr_cat"),
                        ("LITH_UNIT", "geol_lithunit_cat")):
        # Source has case-inconsistent duplicates ('basalt' vs 'Basalt',
        # 'Metavolcanics' vs 'Meta Volcanics'). Normalising avoids handing the
        # model two codes that mean the same rock.
        vals = gdf[field].fillna("unknown").astype(str).str.strip().str.lower()
        classes = sorted(vals.unique())
        code = {c: i + 1 for i, c in enumerate(classes)}    # 0 stays "no data"
        arr = rasterize(
            ((geom, code[v]) for geom, v in zip(gdf.geometry, vals)
             if geom is not None),
            out_shape=G.SHAPE, transform=G.TRANSFORM,
            fill=0, dtype="uint8", all_touched=False)
        a = write(name, arr, inside, dtype="uint8")
        v = a[inside]
        cov = 100 * (v > 0).sum() / len(v)
        print(f"    {name:22} {len(classes):>3} classes   cover {cov:5.1f}%")
        legends[name] = {i: c for c, i in code.items()}
    return legends


def main() -> None:
    print("Stage 1d — soil, land cover, lithology")
    with rasterio.open(INTERIM / "state_mask.tif") as m:
        inside = m.read(1).astype(bool)

    do_soil(inside)
    lc_legend = do_landcover(inside)
    geol_legends = do_lithology(inside)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "_legends.json").write_text(json.dumps(
        {"lc_class_cat": lc_legend, **geol_legends}, indent=2))
    n = len(list(OUT.glob("*.tif")))
    print(f"\n  wrote {n} layers + _legends.json to {OUT}")


if __name__ == "__main__":
    main()
