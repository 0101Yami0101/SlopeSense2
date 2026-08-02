"""PX0c — can radar actually SEE a landslide scar? The detection gate.

Output: reports/px0c_sar_detection.{json,png}

════════════════════════════════════════════════════════════════════════════
WHAT PX0b PROVED, AND WHAT IT DID NOT
════════════════════════════════════════════════════════════════════════════
PX0b showed Sentinel-1 flies over every 4-5 days and that 99.4% of our mapped
landslide cells are geometrically viewable. That is the camera pointing at the
right door, recording often enough.

It says nothing about whether the footage is clear enough to recognise anything.
Radar is grainy (speckle), and soil moisture, vegetation growth and harvest all
change backscatter without any landslide. So this gate asks the next question.

════════════════════════════════════════════════════════════════════════════
TEST A — NECESSARY CONDITION: is a scar distinguishable from its surroundings?
════════════════════════════════════════════════════════════════════════════
Before asking "can we detect the moment a scar appears", ask the cheaper
question: given a scar that definitely exists, can radar tell it apart from the
hillside around it? If not, detecting its appearance is hopeless.

This deliberately uses our BEST-LOCATED data — the GSI/Bhuvan polygons, which
are precisely mapped — rather than the NASA points, whose km-level position
error would blur any pixel-level signal into noise.

Physical expectation: Arunachal is 84.7% tree cover. A scar replaces volume-
scattering forest canopy with surface-scattering bare soil and rock. That should
drop VH sharply (cross-polarised return comes mostly from canopy volume) and
drop the VH/VV ratio. If we see no such contrast, radar cannot see scars here.

⚠️ CONTROLS ARE SLOPE-MATCHED. Backscatter depends on local terrain angle even
after radiometric terrain correction. Comparing landslides against *random*
terrain would just re-detect steepness — the same trap as negative sampling in
P6. Controls are drawn from the same slope band and >500 m from any mapped slide.

════════════════════════════════════════════════════════════════════════════
TEST B — THE REAL QUESTION: does backscatter change AT the failure date?
════════════════════════════════════════════════════════════════════════════
Only run if A passes. Take landslides whose dates we know, build a backscatter
time series through the event, and ask whether the step at the true date stands
out against the seasonal noise the same pixel shows in ordinary years.

⚠️ Sample is small and imperfect: only NASA GLC carries dates, its locations are
coarse, and only events after Oct 2014 are in the Sentinel-1 record. Test B is
therefore indicative, not conclusive — which is stated in the verdict.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))

import json
import os
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.features import rasterize
from rasterio.windows import from_bounds
from scipy.ndimage import distance_transform_edt
from sklearn.metrics import roc_auc_score

import grid as G
from common import INTERIM, LABELS, ROOT

warnings.filterwarnings("ignore")
os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "3")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
REPORTS = ROOT / "reports"

# Dry-season scenes: less soil-moisture noise, so this is the BEST case for
# seeing a contrast. If it fails here it fails everywhere.
AOI_TEST = (92.10, 27.00, 92.80, 27.55)      # West Kameng — densest inventory
DRY_WINDOWS = ["2019-12-01/2020-02-28", "2021-12-01/2022-02-28"]
MIN_POLY_M2 = 2_000        # ~20 pixels at 10 m — enough to beat speckle
BUFFER_M = 500


def sign(href: str) -> str:
    r = requests.get(SIGN, params={"href": href}, timeout=90)
    r.raise_for_status()
    return r.json()["href"]


def find_scenes(bbox, when, limit=6):
    r = requests.post(STAC, json={
        "collections": ["sentinel-1-rtc"],
        "bbox": list(bbox), "datetime": when, "limit": limit}, timeout=90)
    r.raise_for_status()
    return r.json().get("features", [])


def read_window(href, bounds_utm):
    with rasterio.open(sign(href)) as ds:
        w = from_bounds(*bounds_utm, ds.transform)
        a = ds.read(1, window=w).astype(np.float32)
        tf = ds.window_transform(w)
    a[a <= 0] = np.nan
    return a, tf


def test_a() -> dict:
    print("  == TEST A: is an existing scar distinguishable from its hillside? ==")

    # landslide polygons in the test AOI, big enough to survive speckle
    polys = []
    for f in ("gsi-nlfc_landslides_polygon_arunachal.geojson",
              "bhuvan_ar_slim_2017_polygon_arunachal.geojson",
              "bhuvan_ls_arunachal_2023_polygon_arunachal.geojson"):
        p = LABELS / f
        if p.exists():
            g = gpd.read_file(p, bbox=AOI_TEST).to_crs(G.CRS)
            g = g[g.geometry.notna() & ~g.geometry.is_empty]
            polys.append(g[["geometry"]])
    gdf = pd.concat(polys, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=G.CRS)
    gdf = gdf[gdf.geometry.area >= MIN_POLY_M2]
    print(f"    {len(gdf):,} mapped landslides >= {MIN_POLY_M2:,} m2 in the AOI")
    if len(gdf) < 20:
        return {"error": "too few polygons in AOI"}

    minx, miny, maxx, maxy = gdf.total_bounds
    pad = 2000
    bounds = (minx - pad, miny - pad, maxx + pad, maxy + pad)

    # slope, resampled to the SAR window later
    with rasterio.open(INTERIM / "terrain" / "terrain_slope_deg.tif") as s:
        sw = from_bounds(*bounds, s.transform)
        slope100 = s.read(1, window=sw)
        slope_tf = s.window_transform(sw)

    results, scenes_used = [], []
    for when in DRY_WINDOWS:
        feats = find_scenes(AOI_TEST, when)
        if not feats:
            continue
        for f in feats[:2]:
            try:
                vv, tf = read_window(f["assets"]["vv"]["href"], bounds)
                vh, _ = read_window(f["assets"]["vh"]["href"], bounds)
            except Exception as exc:                        # noqa: BLE001
                print(f"    skip {f['id'][:38]}: {type(exc).__name__}")
                continue
            if vv.size == 0 or not np.isfinite(vv).any():
                continue

            mask = rasterize(
                ((geom, 1) for geom in gdf.geometry),
                out_shape=vv.shape, transform=tf, fill=0, dtype="uint8",
                all_touched=False).astype(bool)
            if mask.sum() < 200:
                continue

            # Slope on the SAR grid. Both rasters are EPSG:32646 (RTC happens to
            # use our exact working CRS), so this is pure arithmetic on the two
            # transforms — no reprojection, and the 2-D shape is preserved.
            rr, cc = np.mgrid[0:vv.shape[0], 0:vv.shape[1]]
            xs = tf.c + (cc + 0.5) * tf.a
            ys = tf.f + (rr + 0.5) * tf.e
            sc = ((xs - slope_tf.c) / slope_tf.a).astype(np.int32)
            sr = ((ys - slope_tf.f) / slope_tf.e).astype(np.int32)
            sr = np.clip(sr, 0, slope100.shape[0] - 1)
            sc = np.clip(sc, 0, slope100.shape[1] - 1)
            slope = slope100[sr, sc]

            # controls: >500 m from any slide, and slope-matched per band
            dist = distance_transform_edt(~mask, sampling=(10, 10))
            far = dist > BUFFER_M
            ok = np.isfinite(vv) & np.isfinite(vh) & np.isfinite(slope)

            rng = np.random.default_rng(0)
            ev_idx, ct_idx = [], []
            for lo in range(10, 70, 10):
                band = (slope >= lo) & (slope < lo + 10)
                e = np.flatnonzero((mask & band & ok).ravel())
                c = np.flatnonzero((far & band & ok).ravel())
                if len(e) < 30 or len(c) < 30:
                    continue
                take = min(len(e), len(c), 4000)
                ev_idx.append(rng.choice(e, take, replace=False))
                ct_idx.append(rng.choice(c, take, replace=False))
            if not ev_idx:
                continue
            ev_idx = np.concatenate(ev_idx); ct_idx = np.concatenate(ct_idx)

            row = {"scene": f["id"][:44], "date": f["properties"]["datetime"][:10],
                   "n_pixels": int(len(ev_idx))}
            for nm, arr in (("vv", vv), ("vh", vh),
                            ("vh_vv_ratio", vh / np.maximum(vv, 1e-6))):
                e = arr.ravel()[ev_idx]; c = arr.ravel()[ct_idx]
                m = np.isfinite(e) & np.isfinite(c)
                y = np.r_[np.ones(m.sum()), np.zeros(m.sum())]
                a = float(roc_auc_score(y, np.r_[e[m], c[m]]))
                row[f"{nm}_auc"] = max(a, 1 - a)
                row[f"{nm}_slide"] = float(np.nanmedian(e))
                row[f"{nm}_control"] = float(np.nanmedian(c))
            results.append(row)
            scenes_used.append(f["id"])
            print(f"    {row['date']}  n={row['n_pixels']:>6,}  "
                  f"VV {row['vv_auc']:.3f}  VH {row['vh_auc']:.3f}  "
                  f"VH/VV {row['vh_vv_ratio_auc']:.3f}")

    if not results:
        return {"error": "no usable scenes"}
    R = pd.DataFrame(results)
    best = max(("vv", "vh", "vh_vv_ratio"), key=lambda k: R[f"{k}_auc"].mean())
    out = {"scenes": len(R), "per_scene": results,
           "mean_auc": {k: float(R[f"{k}_auc"].mean())
                        for k in ("vv", "vh", "vh_vv_ratio")},
           "best_channel": best, "best_auc": float(R[f"{best}_auc"].mean())}
    print(f"\n    mean AUC  VV {out['mean_auc']['vv']:.3f}   "
          f"VH {out['mean_auc']['vh']:.3f}   "
          f"VH/VV {out['mean_auc']['vh_vv_ratio']:.3f}")
    print(f"    best channel: {best}  AUC {out['best_auc']:.3f}")
    return out


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    print("PX0c — SAR detection gate")
    a = test_a()

    if "error" in a:
        print(f"\n  ==> INCONCLUSIVE: {a['error']}")
        (REPORTS / "px0c_sar_detection.json").write_text(
            json.dumps({"test_a": a, "verdict": "INCONCLUSIVE"}, indent=2))
        return

    # A scar that cannot be separated from its own hillside at >=0.65 cannot be
    # detected as it appears — the appearance signal is strictly weaker than the
    # persistent one, because it must also beat seasonal change.
    passed = a["best_auc"] >= 0.65
    verdict = "PROCEED_TO_TEST_B" if passed else "VETO"
    print(f"\n  Test A threshold: AUC >= 0.65 to be worth continuing")
    print(f"  ==> {verdict}")

    (REPORTS / "px0c_sar_detection.json").write_text(json.dumps({
        "test_a": a, "verdict": verdict,
        "test_a_threshold": 0.65,
        "reasoning": "detecting a scar's APPEARANCE is strictly harder than "
                     "separating an existing scar from its surroundings, since "
                     "it must also beat seasonal backscatter change. Test A is "
                     "therefore a necessary condition.",
    }, indent=2))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    R = pd.DataFrame(a["per_scene"])
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    ch = ["vv", "vh", "vh_vv_ratio"]
    x = np.arange(len(ch))
    ax[0].bar(x, [a["mean_auc"][c] for c in ch], color="#2c7bb6")
    ax[0].axhline(.65, ls="--", c="#d7191c", lw=1.5)
    ax[0].text(-.4, .66, "0.65 gate", color="#d7191c", fontsize=8)
    ax[0].axhline(.5, ls=":", c="k", lw=1)
    ax[0].set_xticks(x); ax[0].set_xticklabels(["VV", "VH", "VH/VV"])
    ax[0].set_ylabel("AUC — scar vs slope-matched hillside")
    ax[0].set_ylim(.4, 1); ax[0].grid(alpha=.3)
    ax[0].set_title("Can radar see an existing scar?", fontsize=10)

    for c, col in zip(ch, ["#2c7bb6", "#d7191c", "#fdae61"]):
        ax[1].plot(R["date"], R[f"{c}_auc"], "o-", color=col, label=c.upper())
    ax[1].axhline(.65, ls="--", c="k", lw=1)
    ax[1].set_ylabel("AUC"); ax[1].set_ylim(.4, 1)
    ax[1].tick_params(axis="x", rotation=45, labelsize=7)
    ax[1].legend(fontsize=8); ax[1].grid(alpha=.3)
    ax[1].set_title("Consistency across scenes", fontsize=10)
    plt.tight_layout()
    plt.savefig(REPORTS / "px0c_sar_detection.png", dpi=130)
    print(f"  wrote reports/px0c_sar_detection.{{json,png}}")


if __name__ == "__main__":
    main()
