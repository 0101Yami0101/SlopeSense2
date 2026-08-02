"""Export the small bundle the deployed web app reads.

Output: webapp/assets/   (~4 MB, committed to git)

════════════════════════════════════════════════════════════════════════════
THE DEPLOYED APP NEVER RUNS THE PIPELINE
════════════════════════════════════════════════════════════════════════════
Free hosts give ~1 GB of RAM and no geospatial system libraries. Our pipeline
needs rasterio, geopandas, pysheds, lightgbm and 970 MB of Parquet. None of that
can ship.

So this distils everything into arrays a numpy-only app can read:

    susceptibility.npz   uint8 @ 500 m, 255 = not assessed
    nearest_point.npz    uint8, which rainfall query point each pixel uses
    clim_quantiles.npz   101 percentile breakpoints per point, per feature
    points.json          lat/lon of each query point — drives the live API call
    districts.geojson    dissolved + simplified, for the alert table
    boundary.geojson     state outline
    metrics.json         the honest numbers the methodology panel shows

════════════════════════════════════════════════════════════════════════════
TWO CHOICES WORTH KNOWING ABOUT
════════════════════════════════════════════════════════════════════════════
1. QUANTILE BREAKPOINTS, NOT RAW CLIMATOLOGY. The trigger needs "what percentile
   is today's rain for this place". Shipping 16 years of daily values for every
   point would be ~17 MB; shipping 101 breakpoints per point is ~0.1 MB and
   answers the same question to 1% resolution.

2. NEAREST-NEIGHBOUR for the rainfall lookup, not smooth interpolation. Rainfall
   input is genuinely ~33 km. Interpolating it smoothly would paint detail the
   data does not have. The fine texture on the map comes from 100 m
   susceptibility, which is real; the rainfall term is deliberately blocky
   because that is what it is.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))

import json
import warnings

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling

from common import BOUNDARIES, INTERIM, PROCESSED, ROOT

warnings.filterwarnings("ignore")

OUT = ROOT / "webapp" / "assets"
OM = INTERIM / "rainfall_om"
DOWNSAMPLE = 5                     # 100 m -> 500 m
N_Q = 101                          # percentile breakpoints
MONSOON = (5, 10)
FEATURES = ("r3", "r7")


def rolling(a: np.ndarray, w: int) -> np.ndarray:
    if w == 1:
        return a.copy()
    cs = np.cumsum(np.nan_to_num(a), axis=0, dtype=np.float64)
    out = np.full_like(a, np.nan, dtype=np.float32)
    out[w - 1:] = (cs[w - 1:] -
                   np.vstack([np.zeros((1, a.shape[1])), cs[:-w]])).astype(np.float32)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Exporting web app bundle")

    # ── susceptibility, downsampled ──────────────────────────────────────
    with rasterio.open(PROCESSED / "susceptibility.tif") as s:
        h, w = s.height // DOWNSAMPLE, s.width // DOWNSAMPLE
        sus = s.read(1, out_shape=(h, w), resampling=Resampling.average)
        tf = s.transform * s.transform.scale(s.width / w, s.height / h)
        bounds = s.bounds
        crs = s.crs
    ok = np.isfinite(sus)
    q = np.full((h, w), 255, dtype=np.uint8)
    q[ok] = np.clip(np.round(sus[ok] * 254), 0, 254).astype(np.uint8)
    np.savez_compressed(OUT / "susceptibility.npz", sus=q)
    print(f"  susceptibility  {h}x{w}  assessed {100*ok.mean():.1f}%  "
          f"{(OUT/'susceptibility.npz').stat().st_size/1e6:.2f} MB")

    # ── lon/lat of every display pixel, for the nearest-point lookup ─────
    rr, cc = np.mgrid[0:h, 0:w]
    xs = tf.c + (cc + 0.5) * tf.a
    ys = tf.f + (rr + 0.5) * tf.e
    import rasterio.warp as rw
    lonf, latf = rw.transform(crs, "EPSG:4326", xs.ravel(), ys.ravel())
    lonp = np.array(lonf).reshape(h, w)
    latp = np.array(latf).reshape(h, w)

    # ── climatology → quantile breakpoints ───────────────────────────────
    if not (OM / "precip_mm.npy").exists():
        print("\n  [!] Open-Meteo climatology not fetched yet - run\n"
              "    python scripts/fetch/fetch_20_openmeteo_climatology.py\n"
              "  Skipping clim_quantiles / points / nearest_point.")
    else:
        import pandas as pd
        P = np.load(OM / "precip_mm.npy")
        dates = pd.to_datetime(np.load(OM / "dates.npy").astype("datetime64[D]"))
        pts = json.loads((OM / "points.json").read_text())
        mons = (dates.month >= MONSOON[0]) & (dates.month <= MONSOON[1])
        qs = {}
        for f in FEATURES:
            wdw = int(f[1:])
            roll = rolling(P, wdw)[mons]
            qs[f] = np.nanpercentile(roll, np.linspace(0, 100, N_Q),
                                     axis=0).astype(np.float32)
        np.savez_compressed(OUT / "clim_quantiles.npz", **qs)
        (OUT / "points.json").write_text(json.dumps(pts, indent=2))
        print(f"  clim_quantiles  {N_Q} breakpoints x {P.shape[1]} points x "
              f"{len(FEATURES)} feats  "
              f"{(OUT/'clim_quantiles.npz').stat().st_size/1e6:.2f} MB")

        plat = np.array(pts["lat"], dtype=np.float32)
        plon = np.array(pts["lon"], dtype=np.float32)
        # Nearest query point per pixel. Chunked so we never build an
        # (h*w x n_points) array in one go.
        near = np.empty((h, w), dtype=np.uint8)
        for r0 in range(0, h, 128):
            r1 = min(r0 + 128, h)
            d = ((latp[r0:r1, :, None] - plat[None, None, :]) ** 2 +
                 ((lonp[r0:r1, :, None] - plon[None, None, :]) *
                  np.cos(np.radians(latp[r0:r1, :, None]))) ** 2)
            near[r0:r1] = np.argmin(d, axis=2).astype(np.uint8)
        np.savez_compressed(OUT / "nearest_point.npz", near=near)
        print(f"  nearest_point   {len(plat)} points  "
              f"{(OUT/'nearest_point.npz').stat().st_size/1e6:.2f} MB")

    # ── vectors ──────────────────────────────────────────────────────────
    d = gpd.read_file(BOUNDARIES / "gadm_district-boundary_vector_arunachal.gpkg")
    d = d[["NAME_2", "geometry"]].dissolve(by="NAME_2").reset_index()
    d["geometry"] = d.geometry.simplify(0.004)
    d.rename(columns={"NAME_2": "district"}).to_file(
        OUT / "districts.geojson", driver="GeoJSON")

    b = gpd.read_file(BOUNDARIES / "gadm_state-boundary_vector_arunachal.gpkg")
    b["geometry"] = b.geometry.simplify(0.004)
    b[["geometry"]].to_file(OUT / "boundary.geojson", driver="GeoJSON")
    print(f"  districts {len(d)}  "
          f"{(OUT/'districts.geojson').stat().st_size/1e6:.2f} MB")

    # ── the honest numbers ───────────────────────────────────────────────
    sm = json.loads((ROOT / "models" / "_susceptibility_meta.json").read_text())
    tg = json.loads((ROOT / "models" / "trigger.json").read_text())
    val = json.loads((ROOT / "reports" / "susceptibility_validation.json").read_text())
    (OUT / "metrics.json").write_text(json.dumps({
        "susceptibility": {
            "auc": sm["auc_mean"], "auc_std": sm["auc_std"],
            "n_rows": sm["n_rows"], "n_features": len(sm["features"]),
            "success_rate": val["success_rate"],
        },
        "trigger": {
            "auc": tg["auc"], "auc_ci95": tg["auc_ci95"],
            "n_events": tg["n_events"],
            "features": tg["trigger_definition"]["features"],
            "fitted": tg["trigger_definition"]["fitted"],
            "operating_points": tg["operating_points"],
        },
        "labels": {"polygons": 37788, "cells": 91610},
        "caveats": [
            "Relative susceptibility index, not probability of failure "
            "(presence-only data — there is no denominator).",
            "Rainfall is ~33 km sampled Open-Meteo; terrain is 100 m. "
            "The map's fine texture is terrain, not weather.",
            "Hindcast AUC 0.768 used 11 km IMERG; the live forecast uses a "
            "coarser source and is expected to be somewhat weaker.",
            "Out-of-domain cells (ice, water, slope <=10 deg) are NOT scored.",
            "Not for operational safety decisions.",
        ],
    }, indent=2))

    grid = {"height": int(h), "width": int(w),
            "lon_min": float(lonp.min()), "lon_max": float(lonp.max()),
            "lat_min": float(latp.min()), "lat_max": float(latp.max()),
            "downsample": DOWNSAMPLE, "nodata_u8": 255,
            "class_breaks_pct": [50, 75, 90, 97],
            "class_names": ["Very Low", "Low", "Moderate", "High", "Very High"],
            "class_colors": ["#1a9850", "#a6d96a", "#fee08b", "#f46d43", "#a50026"]}
    (OUT / "grid.json").write_text(json.dumps(grid, indent=2))

    total = sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())
    print(f"\n  bundle total: {total/1e6:.2f} MB  -> {OUT}")


if __name__ == "__main__":
    main()
