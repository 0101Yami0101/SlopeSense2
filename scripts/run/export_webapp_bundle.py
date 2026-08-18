"""Export the small bundle the deployed web app reads.

Output: webapp/assets/base/       shared geography, every module reads it
        webapp/assets/landslide/  SlopeSense model output
        (~4 MB total, committed to git)

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

from common import (BOUNDARIES, EXPOSURE, HYDROLOGY, INTERIM, LABELS,
                    PROCESSED, ROOT)

warnings.filterwarnings("ignore")

# Two bundles, and the split is the platform's whole shape. `base` is shared
# geography every module draws — one grid, one boundary, one gazetteer, so two
# hazards can never disagree about where Arunachal is. `landslide` is
# SlopeSense's own model output. A flood module gets assets/flood/ beside it.
ASSETS = ROOT / "webapp" / "assets"
BASE = ASSETS / "base"
OUT = ASSETS / "landslide"
# ⚠️ points.json and clim_quantiles.npz live in BASE, not here. Rainfall is
# the one input BOTH hazards read — the landslide trigger and the flood
# catchment signal are the same 97 points against the same climatology.
# Filing them under one hazard would make the other import from it.
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
    BASE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    print("Exporting web app bundle")

    # ── susceptibility, reprojected to lat/lon and downsampled ───────────
    # ⚠️ MUST be EPSG:4326. The model raster is UTM 46N; a web map's image
    # overlay takes a plain lat/lon rectangle and stretches the image across
    # it linearly. Handing it a UTM grid would skew every pixel — the map
    # would look plausible and be wrong, worst of both. So reproject here,
    # once, and the app's lat/lon -> pixel maths becomes trivial arithmetic.
    from rasterio.warp import calculate_default_transform, reproject
    with rasterio.open(PROCESSED / "susceptibility.tif") as s:
        dst_tf, dw, dh = calculate_default_transform(
            s.crs, "EPSG:4326", s.width, s.height, *s.bounds)
        h, w = dh // DOWNSAMPLE, dw // DOWNSAMPLE
        dst_tf = dst_tf * dst_tf.scale(dw / w, dh / h)
        sus = np.full((h, w), np.nan, dtype=np.float32)
        reproject(source=rasterio.band(s, 1), destination=sus,
                  src_transform=s.transform, src_crs=s.crs,
                  dst_transform=dst_tf, dst_crs="EPSG:4326",
                  src_nodata=np.nan, dst_nodata=np.nan,
                  resampling=Resampling.average)
    ok = np.isfinite(sus)
    q = np.full((h, w), 255, dtype=np.uint8)
    q[ok] = np.clip(np.round(sus[ok] * 254), 0, 254).astype(np.uint8)
    np.savez_compressed(OUT / "susceptibility.npz", sus=q)

    west, north = dst_tf.c, dst_tf.f
    east, south = west + w * dst_tf.a, north + h * dst_tf.e
    print(f"  susceptibility  {h}x{w} @ EPSG:4326  assessed {100*ok.mean():.1f}%  "
          f"{(OUT/'susceptibility.npz').stat().st_size/1e6:.2f} MB")
    print(f"    bounds  W {west:.3f}  E {east:.3f}  S {south:.3f}  N {north:.3f}")

    # regular lat/lon lattice — now just linear, no per-pixel reprojection
    lonp = (west + (np.arange(w) + 0.5) * dst_tf.a)[None, :].repeat(h, 0)
    latp = (north + (np.arange(h) + 0.5) * dst_tf.e)[:, None].repeat(w, 1)

    # ── elevation, on the SAME lattice — this is what makes 3D possible ───
    # The 3D view places each forecast cell at its true height. Draping a flat
    # image onto a terrain mesh was tried and does not render in this deck.gl
    # build, so the surface is drawn as points that already carry their own z.
    # That needs a height for every cell, hence this layer.
    #
    # uint16 metres with 65535 as nodata: Arunachal tops out near 7,000 m, so
    # whole metres are far finer than anything the view can show, and the file
    # compresses to a fraction of a float32 raster.
    dem_src = INTERIM / "terrain" / "dem_elev_m.tif"
    if dem_src.exists():
        with rasterio.open(dem_src) as s:
            elev = np.full((h, w), np.nan, dtype=np.float32)
            reproject(source=rasterio.band(s, 1), destination=elev,
                      src_transform=s.transform, src_crs=s.crs,
                      dst_transform=dst_tf, dst_crs="EPSG:4326",
                      src_nodata=s.nodata, dst_nodata=np.nan,
                      resampling=Resampling.average)
        eok = np.isfinite(elev)
        ez = np.full((h, w), 65535, dtype=np.uint16)
        ez[eok] = np.clip(np.round(elev[eok]), 0, 65534).astype(np.uint16)
        np.savez_compressed(BASE / "elevation.npz", elev=ez)
        print(f"  elevation       {h}x{w}  {elev[eok].min():.0f}-{elev[eok].max():.0f} m  "
              f"{(OUT/'elevation.npz').stat().st_size/1e6:.2f} MB")
    else:
        print(f"  [!] {dem_src.name} missing — 3D view will fall back to flat")

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
        np.savez_compressed(BASE / "clim_quantiles.npz", **qs)
        (BASE / "points.json").write_text(json.dumps(pts, indent=2))
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
    d["geometry"] = d.geometry.simplify(0.003)
    d.rename(columns={"NAME_2": "district"}).to_file(
        BASE / "districts.geojson", driver="GeoJSON")

    # ── state outline ────────────────────────────────────────────────────
    # GADM splits Arunachal by POLITICAL STATUS, not administration:
    #     GID_0 = IND  area 1.36   the part India holds uncontested
    #     GID_0 = Z07  area 6.17   Z07 is GADM's disputed-territory code
    # Unioning them (area 7.525) leaves a notch along the north-east that
    # renders as a stray line running Dibrugarh -> Hawai. Verified it is not a
    # union or simplify artefact: districts-union gives the identical 7.525,
    # and every dissolve/closing variant reproduces the same notch.
    #
    # So the outline is taken from the boundary used by the earlier SlopeSense
    # build (area 7.629), which carries Arunachal's full extent. For an Indian
    # government client that is also the correct representation — official
    # Indian maps show the whole state.
    ALT = Path(r"D:/CODE/BeeDigital/LandslideSM/app/assets/boundary.geojson")
    b = gpd.read_file(BOUNDARIES / "gadm_state-boundary_vector_arunachal.gpkg")
    merged = b.geometry.union_all()          # analysis extent — matches the raster
    if ALT.exists():
        outline = gpd.read_file(ALT).geometry.union_all()
        src = "full-extent outline (SlopeSense source)"
    else:
        outline = merged
        src = "GADM union — fallback, will show the NE notch"
    gpd.GeoDataFrame(geometry=[outline.simplify(0.0015)], crs="EPSG:4326"
                     ).to_file(BASE / "boundary.geojson", driver="GeoJSON")
    print(f"  districts {len(d)}   outline: {src}")
    print(f"    display area {outline.area:.3f} vs analysis extent {merged.area:.3f} "
          f"— the difference is high northern ground we do not assess anyway")

    # ── roads: major network, CLIPPED TO THE STATE ───────────────────────
    # ⚠️ The source files are cut to a bounding RECTANGLE, not to Arunachal.
    # Measured: of 5,536 major roads in the box, only 1,236 (22%) touch the
    # state — the rest are Assam, Nagaland, Bhutan and Tibet. Shipped
    # unclipped they dominate the map and make Arunachal look roadless, which
    # is both ugly and misleading. Clip to the boundary.
    rp = EXPOSURE / "osm_roads_vector_arunachal.gpkg"
    if rp.exists():
        r = gpd.read_file(rp)
        keep = ["motorway", "trunk", "primary", "secondary",
                "motorway_link", "trunk_link", "primary_link"]
        r = r[r.highway.isin(keep)][["highway", "geometry"]]
        before = len(r)
        r = gpd.clip(r, merged)
        r = r[~r.geometry.is_empty & r.geometry.notna()]
        r["geometry"] = r.geometry.simplify(0.001)
        r.to_file(BASE / "roads.geojson", driver="GeoJSON")
        print(f"  roads      {len(r):,} inside the state "
              f"(clipped from {before:,} in the bbox)  "
              f"{(OUT/'roads.geojson').stat().st_size/1e6:.2f} MB")

    # ── rivers: main stems, also clipped ─────────────────────────────────
    hp = HYDROLOGY / "hydrosheds_rivers_vector_arunachal.gpkg"
    if hp.exists():
        rv = gpd.read_file(hp)
        col = "ORD_STRA" if "ORD_STRA" in rv.columns else None
        rv = (rv[rv[col] >= 4] if col else
              rv.nlargest(2500, "LENGTH_KM"))[["geometry"]]
        before = len(rv)
        rv = gpd.clip(rv, merged)
        rv = rv[~rv.geometry.is_empty & rv.geometry.notna()]
        rv["geometry"] = rv.geometry.simplify(0.002)
        rv.to_file(BASE / "rivers.geojson", driver="GeoJSON")
        print(f"  rivers     {len(rv):,} inside the state "
              f"(clipped from {before:,})  "
              f"{(OUT/'rivers.geojson').stat().st_size/1e6:.2f} MB")

    # ── an inverted mask: everything OUTSIDE the displayed outline ───────
    # Arunachal pinches to a narrow neck near 95E where Assam pushes up, so
    # the two boundary lines run close together and read as a stray line
    # slicing the state. Dimming the outside makes "inside" unmistakable and
    # the neck legible as real geography rather than a rendering fault.
    from shapely.geometry import box
    outer = box(west - 4, south - 4, east + 4, north + 4)
    gpd.GeoDataFrame(geometry=[outer.difference(outline)], crs="EPSG:4326"
                     ).to_file(BASE / "outside_mask.geojson", driver="GeoJSON")
    print(f"  outside_mask  dims everything beyond the state")

    # ── settlements: a search index, not a map layer ─────────────────────
    sp = EXPOSURE / "apssdi_settlements_vector_arunachal.geojson"
    if sp.exists():
        s_ = gpd.read_file(sp).to_crs(4326)
        s_ = s_[s_.geometry.notna()]
        namecol = "Name" if "Name" in s_.columns else s_.columns[0]
        towns = [{"n": str(nm), "y": round(float(g.y), 4), "x": round(float(g.x), 4)}
                 for nm, g in zip(s_[namecol], s_.geometry)
                 if str(nm) not in ("nan", "None", "")]
        (BASE / "towns.json").write_text(json.dumps(towns, separators=(",", ":")))
        print(f"  towns      {len(towns):,} searchable  "
              f"{(OUT/'towns.json').stat().st_size/1e6:.2f} MB")

    # ── the landslide inventory itself — the project's strongest evidence ──
    # Centroids, 4 dp (~11 m), so ~37,300 real mapped failures ship in ~0.6 MB.
    #
    # ⚠️ CLIPPED TO THE DISPLAYED OUTLINE, like roads and rivers above. These
    # files are named "_arunachal" but were cut to a BOUNDING BOX at download,
    # so they carry 494 genuine GSI/Bhuvan failures that lie in Assam and
    # Nagaland — up to 90 km past the border. Unclipped, the map clustered them
    # into big numbered bubbles floating in Assam, which reads as a rendering
    # fault rather than as neighbouring states' real landslides.
    #
    # This never touched the model: sample.py builds its domain as
    # `inside & lc_ok & (slope > SLOPE_MIN)` against state_mask.tif, so
    # out-of-state cells were never eligible as positives OR negatives. The
    # contamination was in the shipped map only.
    inv = []
    dropped = 0
    for f in ("gsi-nlfc_landslides_polygon_arunachal.geojson",
              "bhuvan_ar_slim_2014_gcs_polygon_arunachal.geojson",
              "bhuvan_ar_slim_2017_polygon_arunachal.geojson",
              "bhuvan_ls_arunachal_2023_polygon_arunachal.geojson"):
        p = LABELS / f
        if not p.exists():
            continue
        gg = gpd.read_file(p).to_crs(4326)
        gg = gg[gg.geometry.notna() & ~gg.geometry.is_empty]
        c = gg.geometry.centroid
        # Clip on the CENTROID, not the polygon: a scar straddling the border
        # belongs to whichever state its middle sits in, and testing the
        # polygon would keep a large Assam failure that merely grazes the line.
        keep = c.within(outline)
        dropped += int((~keep).sum())
        src = "GSI" if f.startswith("gsi") else f.split("_")[2][:4]
        inv += [{"y": round(float(y), 4), "x": round(float(x), 4), "s": src}
                for x, y in zip(c[keep].x, c[keep].y)]
    if inv:
        (OUT / "landslides.json").write_text(json.dumps(inv, separators=(",", ":")))
        print(f"  inventory  {len(inv):,} mapped landslides inside the state "
              f"({dropped:,} dropped as outside)  "
              f"{(OUT/'landslides.json').stat().st_size/1e6:.2f} MB")

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
            "crs": "EPSG:4326",
            "west": float(west), "east": float(east),
            "south": float(south), "north": float(north),
            "lon_min": float(west), "lon_max": float(east),
            "lat_min": float(south), "lat_max": float(north),
            "downsample": DOWNSAMPLE, "nodata_u8": 255,
            "class_breaks_pct": [50, 75, 90, 97],
            "class_names": ["Very Low", "Low", "Moderate", "High", "Very High"],
            "class_colors": ["#1a9850", "#a6d96a", "#fee08b", "#f46d43", "#a50026"]}
    (BASE / "grid.json").write_text(json.dumps(grid, indent=2))

    for tag, d in (("base", BASE), ("landslide", OUT)):
        sz = sum(p.stat().st_size for p in d.iterdir() if p.is_file())
        print(f"  {tag:<10} {sz/1e6:5.2f} MB  -> {d}")
    total = sum(p.stat().st_size for d in (BASE, OUT)
                for p in d.iterdir() if p.is_file())
    print(f"\n  bundle total: {total/1e6:.2f} MB")


if __name__ == "__main__":
    main()
