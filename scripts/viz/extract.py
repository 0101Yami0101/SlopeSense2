"""Turn the fetched data into figures and summary numbers for the viz layer.

Two outputs:
  viz/figures/*.png|jpg   — maps rendered from the real rasters and vectors
  viz/data/summary.json   — every number the HTML page needs

Adding a new dataset means adding one function here and one entry in
`layers.py`. Nothing else changes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LightSource, ListedColormap, BoundaryNorm
from rasterio.enums import Resampling
from rasterio.merge import merge

from common import (AOI_BBOX, AOI_NAME, BOUNDARIES, CONTEXT, EXPOSURE,
                    HYDROLOGY, LABELS, LANDCOVER, RAW, ROOT, SEISMIC,
                    SOIL_GEOLOGY, TERRAIN, WEATHER)

warnings.filterwarnings("ignore")

VIZ = ROOT / "viz"
FIG = VIZ / "figures"
DATA = VIZ / "data"
for d in (FIG, DATA):
    d.mkdir(parents=True, exist_ok=True)

SUMMARY: dict = {}

# Palette (from the dataviz reference instance)
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
YELLOW = "#eda100"
INK = "#0b0b0b"
MUTED = "#898781"

W, S, E, N = AOI_BBOX


# ---------------------------------------------------------------- helpers
def state_gdf():
    import geopandas as gpd
    f = BOUNDARIES / f"gadm_state-boundary_vector_{AOI_NAME}.gpkg"
    return gpd.read_file(f) if f.exists() else None


def figure(w=10, h=5.4):
    fig, ax = plt.subplots(figsize=(w, h), dpi=110)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    return fig, ax


def finish(fig, ax, path: Path, title="", cbar=None, label="", jpg=False):
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    if title:
        ax.set_title(title, fontsize=11, color=INK, pad=8)
    if cbar is not None:
        cb = fig.colorbar(cbar, ax=ax, fraction=0.03, pad=0.02)
        cb.set_label(label, fontsize=9, color=INK)
        cb.ax.tick_params(labelsize=8, colors=INK)
        cb.outline.set_visible(False)
    fig.tight_layout()
    if jpg:
        path = path.with_suffix(".jpg")
        fig.savefig(path, format="jpg", bbox_inches="tight", facecolor="white",
                    pil_kwargs={"quality": 80, "optimize": True})
    else:
        fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)
    print(f"  [fig] {path.name} ({path.stat().st_size / 1e3:.0f} KB)")
    return path


def overlay_state(ax, lw=0.8, color="#00000055"):
    g = state_gdf()
    if g is not None:
        g.boundary.plot(ax=ax, linewidth=lw, edgecolor=color)


def dem_mosaic(step=8):
    """Decimated mosaic of the DEM tiles. step=8 -> ~240 m pixels."""
    tiles = sorted((TERRAIN / "copernicus_dem_30m").glob("*.tif"))
    if not tiles:
        return None, None
    srcs = [rasterio.open(t) for t in tiles]
    arr, tr = merge(srcs, res=[s.res[0] * step for s in srcs[:1]] * 2)
    for s in srcs:
        s.close()
    a = arr[0].astype("float32")
    a[a <= -1000] = np.nan
    return a, tr


# ------------------------------------------------------------------ layers
def do_terrain():
    print("terrain")
    a, tr = dem_mosaic(step=8)
    if a is None:
        return
    ext = [tr.c, tr.c + tr.a * a.shape[1], tr.f + tr.e * a.shape[0], tr.f]

    # elevation + hillshade
    fig, ax = figure()
    ls = LightSource(azdeg=315, altdeg=45)
    shaded = ls.shade(np.nan_to_num(a, nan=0), cmap=plt.cm.terrain,
                      blend_mode="soft", vert_exag=3)
    ax.imshow(shaded, extent=ext)
    im = ax.imshow(a, extent=ext, cmap="terrain", alpha=0)
    overlay_state(ax)
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    finish(fig, ax, FIG / "terrain_elevation.png",
           "Elevation with hillshade — Copernicus DEM 30 m", im, "metres", jpg=True)

    # slope
    px = abs(tr.a) * 111320
    gy, gx = np.gradient(a, px)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    fig, ax = figure()
    im = ax.imshow(slope, extent=ext, cmap="YlOrRd", vmin=0, vmax=45)
    overlay_state(ax)
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    finish(fig, ax, FIG / "terrain_slope.png",
           "Slope steepness — steeper ground fails more easily", im, "degrees", jpg=True)

    v = a[np.isfinite(a)]
    sl = slope[np.isfinite(slope)]
    SUMMARY["terrain"] = {
        "elev_min": float(v.min()), "elev_max": float(v.max()),
        "elev_hist": np.histogram(v, bins=24, range=(0, 7200))[0].tolist(),
        "elev_edges": np.histogram(v, bins=24, range=(0, 7200))[1].tolist(),
        "slope_hist": np.histogram(sl, bins=18, range=(0, 54))[0].tolist(),
        "slope_edges": np.histogram(sl, bins=18, range=(0, 54))[1].tolist(),
        "slope_median": float(np.median(sl)),
        "pct_over_15": float((sl > 15).mean() * 100),
        "pct_over_25": float((sl > 25).mean() * 100),
        "pct_over_35": float((sl > 35).mean() * 100),
    }


def do_landcover():
    print("landcover")
    CLASSES = {10: ("Tree cover", "#006400"), 20: ("Shrubland", "#ffbb22"),
               30: ("Grassland", "#ffff4c"), 40: ("Cropland", "#f096ff"),
               50: ("Built-up", "#fa0000"), 60: ("Bare / sparse", "#b4b4b4"),
               70: ("Snow and ice", "#f0f0f0"), 80: ("Water", "#0064c8"),
               90: ("Wetland", "#0096a0"), 95: ("Mangrove", "#00cf75"),
               100: ("Moss / lichen", "#fae6a0")}
    tiles = sorted((LANDCOVER / "esa_worldcover_10m_2021").glob("*.tif"))
    if not tiles:
        return
    srcs = [rasterio.open(t) for t in tiles]
    arr, tr = merge(srcs, res=[s.res[0] * 40 for s in srcs[:1]] * 2)
    for s in srcs:
        s.close()
    a = arr[0]
    ext = [tr.c, tr.c + tr.a * a.shape[1], tr.f + tr.e * a.shape[0], tr.f]
    codes = sorted(CLASSES)
    cmap = ListedColormap([CLASSES[c][1] for c in codes])
    norm = BoundaryNorm([c - 0.5 for c in codes] + [codes[-1] + 0.5], cmap.N)
    fig, ax = figure()
    ax.imshow(a, extent=ext, cmap=cmap, norm=norm, interpolation="nearest")
    overlay_state(ax, color="#000000aa")
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    finish(fig, ax, FIG / "landcover.png",
           "Land cover — ESA WorldCover 10 m (2021)", jpg=True)

    u, c = np.unique(a, return_counts=True)
    tot = int(c[u != 0].sum())
    SUMMARY["landcover"] = {
        "classes": [{"name": CLASSES[int(k)][0], "color": CLASSES[int(k)][1],
                     "pct": round(100 * int(v) / tot, 2)}
                    for k, v in zip(u.tolist(), c.tolist())
                    if int(k) in CLASSES and v / tot > 0.0005]
    }


def do_soil():
    print("soil")
    out = {}
    panels = [("clay", "Clay content", "BrBG"), ("sand", "Sand content", "YlOrBr"),
              ("soc", "Organic carbon", "Greens")]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6), dpi=110)
    fig.patch.set_alpha(0)
    for ax, (prop, label, cm) in zip(axes, panels):
        f = SOIL_GEOLOGY / "soilgrids_250m" / f"soilgrids_{prop}-0-5cm_250m_{AOI_NAME}.tif"
        if not f.exists():
            continue
        with rasterio.open(f) as ds:
            a = ds.read(1).astype("float32")
            a[a == ds.nodata] = np.nan
            ext = [ds.bounds.left, ds.bounds.right, ds.bounds.bottom, ds.bounds.top]
        a = a / 10.0                      # g/kg -> %
        im = ax.imshow(a, extent=ext, cmap=cm)
        g = state_gdf()
        if g is not None:
            g.boundary.plot(ax=ax, linewidth=0.6, edgecolor="#00000066")
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_title(f"{label} (0–5 cm)", fontsize=10, color=INK)
        cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
        cb.ax.tick_params(labelsize=7, colors=INK)
        cb.outline.set_visible(False)
        v = a[np.isfinite(a)]
        out[prop] = {"min": float(v.min()), "max": float(v.max()),
                     "mean": float(v.mean())}
    fig.tight_layout()
    p = FIG / "soil_properties.jpg"
    fig.savefig(p, format="jpg", bbox_inches="tight", facecolor="white",
                pil_kwargs={"quality": 80, "optimize": True})
    plt.close(fig)
    print(f"  [fig] {p.name} ({p.stat().st_size / 1e3:.0f} KB)")
    SUMMARY["soil"] = out


def do_rivers():
    print("rivers")
    import geopandas as gpd
    f = HYDROLOGY / f"hydrosheds_rivers_vector_{AOI_NAME}.gpkg"
    if not f.exists():
        return
    g = gpd.read_file(f)
    # 50,800 reaches vectorised is a huge PNG; simplify geometry for display
    g["geometry"] = g.geometry.simplify(0.002)
    fig, ax = figure(10, 5.4)
    bands = [(0, 100, "#cde2fb", 0.3), (100, 1000, "#86b6ef", 0.6),
             (1000, 10000, "#2a78d6", 1.1), (10000, 1e9, "#0d366b", 2.0)]
    for lo, hi, col, lw in bands:
        sub = g[(g["UPLAND_SKM"] >= lo) & (g["UPLAND_SKM"] < hi)]
        if len(sub):
            sub.plot(ax=ax, linewidth=lw, color=col)
    overlay_state(ax, color="#00000066")
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    finish(fig, ax, FIG / "rivers.png",
           "River network, thickness by upstream drainage area", jpg=True)

    tot = len(g)
    thresholds = [0, 10, 100, 500, 1000, 5000, 10000, 50000]
    gm = g.to_crs(6933)
    SUMMARY["rivers"] = {
        "total": tot,
        "length_km": float(gm.length.sum() / 1000),
        "bands": [{"threshold": t,
                   "count": int((g["UPLAND_SKM"] > t).sum()),
                   "pct": round(100 * float((g["UPLAND_SKM"] > t).mean()), 2),
                   "length_km": float(gm[(g["UPLAND_SKM"] > t).values].length.sum() / 1000)}
                  for t in thresholds],
    }


def do_seismic():
    print("seismic")
    import geopandas as gpd
    f = SEISMIC / f"usgs_earthquakes_point_{AOI_NAME}-regional_1900-2026.geojson"
    if not f.exists():
        return
    g = gpd.read_file(f)
    g = g[g["mag"].notna()]
    fig, ax = figure()
    sizes = (g["mag"] ** 3.2) / 8
    ax.scatter(g.geometry.x, g.geometry.y, s=sizes, c=ORANGE, alpha=0.45,
               edgecolors="none")
    overlay_state(ax, color="#00000088")
    ax.set_xlim(W - 2, E + 2); ax.set_ylim(S - 2, N + 2)
    finish(fig, ax, FIG / "earthquakes.png",
           "Earthquakes M4.0+ since 1900, sized by magnitude")

    import pandas as pd
    yrs = pd.to_datetime(g["time"], errors="coerce", unit="ms").dt.year
    SUMMARY["seismic"] = {
        "count": int(len(g)),
        "mag_min": float(g["mag"].min()), "mag_max": float(g["mag"].max()),
        "m6plus": int((g["mag"] >= 6).sum()),
        "mag_hist": np.histogram(g["mag"], bins=12, range=(4, 9))[0].tolist(),
        "mag_edges": np.histogram(g["mag"], bins=12, range=(4, 9))[1].tolist(),
        "by_decade": {str(int(d)): int(v) for d, v in
                      (yrs // 10 * 10).value_counts().sort_index().items()
                      if not np.isnan(d)},
    }


def do_labels():
    print("labels")
    import geopandas as gpd
    import pandas as pd
    f = LABELS / f"nasa-glc_landslides_point_{AOI_NAME}.geojson"
    if not f.exists():
        return
    g = gpd.read_file(f)
    fig, ax = figure()
    acc_order = ["exact", "1km", "5km", "10km", "25km", "50km", "unknown"]
    cols = ["#0d366b", "#2a78d6", "#86b6ef", "#eda100", "#eb6834", "#e34948", MUTED]
    for a, c in zip(acc_order, cols):
        sub = g[g["loc_accu"] == a] if "loc_accu" in g else g.iloc[0:0]
        if len(sub):
            ax.scatter(sub.geometry.x, sub.geometry.y, s=44, c=c,
                       edgecolors="white", linewidths=0.8, label=f"{a} ({len(sub)})")
    overlay_state(ax, color="#00000088")
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    ax.legend(fontsize=8, frameon=False, loc="lower left", ncol=2,
              labelcolor=INK, title="Location accuracy",
              title_fontsize=8)
    finish(fig, ax, FIG / "landslide_labels.png",
           "Recorded landslides, coloured by how precisely they are located")

    # ev_date is epoch milliseconds. Without unit="ms" pandas reads the value
    # as nanoseconds and every event collapses onto 1970-01-01.
    d = pd.to_datetime(g["ev_date"], errors="coerce", unit="ms")
    SUMMARY["labels"] = {
        "total": int(len(g)),
        "accuracy": {k: int(v) for k, v in
                     g["loc_accu"].fillna("unknown").value_counts().items()},
        "trigger": {k: int(v) for k, v in
                    g["ls_trig"].fillna("unknown").value_counts().head(8).items()},
        "size": {k: int(v) for k, v in
                 g["ls_size"].fillna("unknown").value_counts().items()},
        "by_year": {str(int(y)): int(v) for y, v in
                    d.dt.year.value_counts().sort_index().items() if y == y},
        "by_month": {str(int(m)): int(v) for m, v in
                     d.dt.month.value_counts().sort_index().items() if m == m},
    }


def do_population():
    print("population")
    import geopandas as gpd
    from rasterio.mask import mask
    f = EXPOSURE / "worldpop_population_100m_india_2020.tif"
    st = state_gdf()
    if not f.exists() or st is None:
        return
    with rasterio.open(f) as ds:
        geoms = [gg.__geo_interface__ for gg in st.to_crs(ds.crs).geometry]
        arr, out_tr = mask(ds, geoms, crop=True, nodata=np.nan, filled=True)
    a = arr[0]
    step = max(1, a.shape[0] // 900)
    a = a[::step, ::step]
    ext = [out_tr.c, out_tr.c + out_tr.a * arr[0].shape[1],
           out_tr.f + out_tr.e * arr[0].shape[0], out_tr.f]
    fig, ax = figure()
    shown = np.where(np.isfinite(a) & (a > 0), a, np.nan)
    im = ax.imshow(np.log10(shown + 1), extent=ext, cmap="magma_r")
    overlay_state(ax, color="#00000066")
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    finish(fig, ax, FIG / "population.png",
           "Where people live — WorldPop 100 m (log scale)", im, "log10(people+1)",
           jpg=True)
    v = arr[0][np.isfinite(arr[0])]
    SUMMARY["population"] = {"total": float(np.nansum(v)),
                             "max_cell": float(np.nanmax(v))}


def do_rainfall():
    print("rainfall")
    import xarray as xr
    files = sorted((WEATHER / "gpm_imerg_daily").glob("*.nc4"))
    if not files:
        return
    season = [f for f in files if "_2024" in f.name]
    stack, dates = [], []
    for f in sorted(season):
        try:
            ds = xr.open_dataset(f)
            stack.append(ds["precipitation"].values[0])
            dates.append(f.stem[-8:])
        except Exception:  # noqa: BLE001
            pass
    if not stack:
        return
    cube = np.stack(stack)                       # (day, lon, lat)
    total = np.nansum(cube, axis=0).T[::-1]      # -> (lat, lon), north up

    fig, ax = figure()
    im = ax.imshow(total, extent=[W, E, S, N], cmap="Blues", aspect="auto")
    overlay_state(ax, color="#00000066")
    finish(fig, ax, FIG / "rainfall_total.png",
           "Total rainfall, monsoon 2024 (Jun–Sep) — GPM IMERG", im, "mm")

    daily_mean = [float(np.nanmean(s)) for s in stack]
    daily_max = [float(np.nanmax(s)) for s in stack]
    SUMMARY["rainfall"] = {
        "days": len(stack), "dates": dates,
        "daily_mean": [round(v, 2) for v in daily_mean],
        "daily_max": [round(v, 1) for v in daily_max],
        "season_total_mean": float(np.nanmean(total)),
        "season_total_max": float(np.nanmax(total)),
    }


def do_discharge():
    print("discharge")
    import xarray as xr
    f = HYDROLOGY / "glofas" / f"glofas_historical_0p05_{AOI_NAME}_2024-monsoon.grib"
    if not f.exists():
        return
    ds = xr.open_dataset(f, engine="cfgrib")
    a = ds["dis24"].values                        # (time, lat, lon)
    peak = np.nanmax(a, axis=0)
    fig, ax = figure()
    im = ax.imshow(np.log10(peak + 1), extent=[W, E, S, N], cmap="Blues",
                   aspect="auto")
    overlay_state(ax, color="#00000066")
    finish(fig, ax, FIG / "discharge_peak.png",
           "Peak river discharge, monsoon 2024 — GloFAS", im, "log10(m³/s)")
    SUMMARY["discharge"] = {
        "days": int(a.shape[0]),
        "max": float(np.nanmax(a)),
        "basin_daily_max": [round(float(np.nanmax(x)), 1) for x in a],
    }


def do_soilmoisture():
    print("soil moisture")
    import glob
    import h5py
    fs = sorted(glob.glob(str(SOIL_GEOLOGY / "smap_soil_moisture" / "*.h5")))
    if not fs:
        return
    with h5py.File(fs[0], "r") as h:
        g = h["Soil_Moisture_Retrieval_Data_AM"]
        sm, lat, lon = g["soil_moisture"][:], g["latitude"][:], g["longitude"][:]
        fill = g["soil_moisture"].attrs.get("_FillValue", -9999.0)
    m = (lat >= S) & (lat <= N) & (lon >= W) & (lon <= E) & (sm != fill)
    fig, ax = figure()
    sc = ax.scatter(lon[m], lat[m], c=sm[m], s=13, cmap="YlGnBu", vmin=0, vmax=0.6)
    overlay_state(ax, color="#00000088")
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    finish(fig, ax, FIG / "soil_moisture.png",
           "Surface soil wetness — SMAP 9 km", sc, "m³/m³")
    SUMMARY["soilmoisture"] = {
        "valid_pct_aoi": float(100 * m.sum() /
                               (((lat >= S) & (lat <= N) &
                                 (lon >= W) & (lon <= E)).sum())),
        "min": float(sm[m].min()), "max": float(sm[m].max()),
        "mean": float(sm[m].mean()),
    }


def do_era5():
    print("era5-land")
    import xarray as xr
    fs = sorted((WEATHER / "era5_land").glob("*.nc"))
    if not fs:
        return
    ds = xr.open_mfdataset(fs, combine="by_coords") if len(fs) > 1 \
        else xr.open_dataset(fs[0])
    sw = ds["swvl1"]                      # volumetric soil water, layer 1
    mean_map = sw.mean(dim="valid_time").values
    lat = ds["latitude"].values

    fig, ax = figure()
    ext = [float(ds.longitude.min()), float(ds.longitude.max()),
           float(lat.min()), float(lat.max())]
    arr = mean_map if lat[0] < lat[-1] else mean_map
    im = ax.imshow(arr, extent=ext, cmap="YlGnBu", aspect="auto",
                   origin="upper" if lat[0] > lat[-1] else "lower")
    overlay_state(ax, color="#00000066")
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    finish(fig, ax, FIG / "era5_soilwater.png",
           "Mean soil water, monsoon 2024 — ERA5-Land", im, "m³/m³")

    t2m = ds["t2m"].mean(dim=["latitude", "longitude"]).values - 273.15
    smlt = ds["smlt"].sum(dim="valid_time").values
    SUMMARY["era5"] = {
        "steps": int(ds.sizes["valid_time"]),
        "variables": list(ds.data_vars),
        "soilwater_mean": float(np.nanmean(mean_map)),
        "soilwater_max": float(np.nanmax(mean_map)),
        "t2m_series": [round(float(v), 2) for v in t2m[::8]],
        "snowmelt_max_m": float(np.nanmax(smlt)),
    }


def do_gfs():
    print("gfs forecast")
    import xarray as xr
    fs = sorted((WEATHER / "noaa_gfs_0p25").glob("*.grib2"))
    if not fs:
        return
    leads, maxima = [], []
    grids = {}
    for f in fs:
        lead = int(f.stem.split("_f")[-1])
        # The file holds APCP (accumulated) and PRATE (instant/avg) together,
        # which cfgrib refuses to merge — ask for the accumulation explicitly.
        ds = None
        for step in ("accum", "instant", "avg"):
            try:
                ds = xr.open_dataset(f, engine="cfgrib", backend_kwargs={
                    "indexpath": "", "filter_by_keys": {"stepType": step}})
                break
            except Exception:  # noqa: BLE001
                continue
        if ds is None or not ds.data_vars:
            continue
        var = "tp" if "tp" in ds.data_vars else list(ds.data_vars)[0]
        a = ds[var].values
        leads.append(lead)
        maxima.append(float(np.nanmax(a)))
        grids[lead] = (a, ds)

    if grids:
        lead = max(grids)
        a, ds = grids[lead]
        lat, lon = ds.latitude.values, ds.longitude.values
        fig, ax = figure(8, 4.4)
        im = ax.imshow(a, extent=[lon.min(), lon.max(), lat.min(), lat.max()],
                       cmap="Blues", aspect="auto",
                       origin="upper" if lat[0] > lat[-1] else "lower")
        overlay_state(ax, color="#00000066")
        ax.set_xlim(W, E); ax.set_ylim(S, N)
        finish(fig, ax, FIG / "gfs_forecast.png",
               f"Forecast rainfall at +{lead} h — NOAA GFS", im, "mm")

    order = np.argsort(leads)
    SUMMARY["gfs"] = {
        "leads": [leads[i] for i in order],
        "maxima": [round(maxima[i], 1) for i in order],
        "files": len(fs),
    }


def do_enso():
    print("enso")
    f = WEATHER / "noaa-cpc_oni_enso_global.txt"
    if not f.exists():
        return
    rows = []
    for line in f.read_text().splitlines()[1:]:
        p = line.split()
        if len(p) >= 4:
            try:
                rows.append((p[0], int(p[1]), float(p[3])))
            except ValueError:
                pass
    recent = rows[-160:]
    SUMMARY["enso"] = {
        "seasons": len(rows),
        "labels": [f"{r[1]}" for r in recent],
        "oni": [r[2] for r in recent],
        "latest": {"season": recent[-1][0], "year": recent[-1][1],
                   "oni": recent[-1][2]},
    }


def do_boundaries():
    print("boundaries")
    import geopandas as gpd
    f = BOUNDARIES / f"gadm_district-boundary_vector_{AOI_NAME}.gpkg"
    st = state_gdf()
    if not f.exists() or st is None:
        return
    d = gpd.read_file(f)
    fig, ax = figure(9, 4.8)
    d.plot(ax=ax, facecolor="#cde2fb", edgecolor="#2a78d6", linewidth=0.7)
    st.boundary.plot(ax=ax, linewidth=1.6, edgecolor="#0d366b")
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    finish(fig, ax, FIG / "boundaries.png",
           "State and district boundaries — GADM 4.1")
    SUMMARY["boundaries"] = {
        "districts": int(len(d)),
        "area_km2": float(st.to_crs(6933).area.sum() / 1e6),
    }


def do_static_counts():
    """Numbers already established that have no raster of their own."""
    import geopandas as gpd
    out = {}
    for name in ("roads", "buildings", "health", "education"):
        f = EXPOSURE / f"osm_{name}_vector_{AOI_NAME}-clipped.gpkg"
        if f.exists():
            g = gpd.read_file(f)
            out[name] = {"count": int(len(g))}
            if name == "roads":
                out[name]["km"] = float(g.to_crs(6933).length.sum() / 1000)
                out[name]["classes"] = {k: int(v) for k, v in
                                        g["highway"].value_counts().head(8).items()}
    SUMMARY["osm"] = out

    j = RAW / "10_context" / f"macrostrat_geology-coverage-test_point_{AOI_NAME}.json"
    if j.exists():
        recs = json.loads(j.read_text())
        from collections import Counter
        liths = Counter((r.get("lith") or "unknown")[:60] for r in recs if r.get("name"))
        SUMMARY["geology"] = {"points": len(recs),
                              "with_data": sum(1 for r in recs if r.get("name")),
                              "lithologies": dict(liths)}

    # Sentinel-2 cloud seasonality — recorded from the catalogue run
    SUMMARY["sentinel2"] = {
        "monsoon": {"n": 309, "median_cloud": 86, "usable": 3},
        "dry": {"n": 310, "median_cloud": 6, "usable": 213},
        "annual": {"n": 1192, "median_cloud": 61, "usable": 342},
    }
    SUMMARY["sentinel1"] = {"scenes_12mo": 2962, "revisit_median_days": 1,
                            "max_gap_days": 3, "ascending": 237, "descending": 278}


def do_geology_state():
    """APSSDI state lithology and lineaments — what replaced the 3-class geology."""
    print("geology (APSSDI)")
    import geopandas as gpd
    from collections import Counter

    lith_f = SOIL_GEOLOGY / f"apssdi_lithology_vector_{AOI_NAME}.geojson"
    lin_f = CONTEXT / f"apssdi_lineaments_vector_{AOI_NAME}.geojson"
    if not lith_f.exists():
        return
    lith = gpd.read_file(lith_f)

    # Rank units by mapped area, not polygon count: a unit can be one huge
    # polygon or two hundred slivers, and area is what a model actually sees.
    lith["_a"] = lith.to_crs(6933).area
    top = lith.groupby("LITH_UNIT")["_a"].sum().sort_values(ascending=False)
    keep = list(top.head(9).index)
    cmap = ["#0d366b", "#2a78d6", "#86b6ef", "#1baf7a", "#7fd4b0",
            "#eda100", "#eb6834", "#e34948", "#8d6bb8"]
    colour = dict(zip(keep, cmap))

    fig, ax = figure()
    lith[~lith["LITH_UNIT"].isin(keep)].plot(ax=ax, color="#d8d5cf", linewidth=0)
    for unit in keep:
        sub = lith[lith["LITH_UNIT"] == unit]
        sub.plot(ax=ax, color=colour[unit], linewidth=0,
                 label=f"{unit} ({len(sub)})")
    if lin_f.exists():
        gpd.read_file(lin_f).plot(ax=ax, color="#00000066", linewidth=0.35)
    overlay_state(ax, color="#00000088")
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    ax.legend(fontsize=7, frameon=False, loc="lower left", ncol=2,
              labelcolor=INK, title="Lithological unit (by mapped area)",
              title_fontsize=8)
    finish(fig, ax, FIG / "geology_state.png",
           "State lithology, with mapped lineaments overlaid")

    out = {
        "polygons": int(len(lith)),
        "lith_units": int(lith["LITH_UNIT"].nunique()),
        "rock_groups": int(lith["ROCK_GR"].nunique()),
        "strat_units": int(lith["LITHO_STRA"].nunique()),
        "by_group": {k: int(v) for k, v in
                     Counter(lith["ROCK_GR"].fillna("unknown")).most_common(9)},
    }
    if lin_f.exists():
        lin = gpd.read_file(lin_f)
        out["lineaments"] = int(len(lin))
        out["lineament_km"] = round(float(lin.to_crs(6933).length.sum() / 1000), 1)
        for col in ("level1_f", "magnitud_1"):
            if col in lin:
                out[col] = {k: int(v) for k, v in
                            Counter(lin[col].fillna("unknown")).most_common(6)}
    SUMMARY["geology_state"] = out


def _read_inventories():
    """Load every landslide inventory we hold, tagged by source."""
    import geopandas as gpd
    frames = []
    for f, src in [
        (LABELS / f"gsi-nlfc_landslides_polygon_{AOI_NAME}.geojson", "GSI polygons"),
        (LABELS / f"bhuvan_ar_slim_2014_gcs_polygon_{AOI_NAME}.geojson", "Bhuvan 2014"),
        (LABELS / f"bhuvan_ar_slim_2017_polygon_{AOI_NAME}.geojson", "Bhuvan 2017"),
        (LABELS / f"bhuvan_ls_arunachal_2023_polygon_{AOI_NAME}.geojson", "Bhuvan 2023"),
    ]:
        if f.exists():
            g = gpd.read_file(f)
            # GSI's tile-based delivery spills over the state line — 246 of its
            # polygons sit in Nagaland or Assam. Counting them would inflate both
            # the inventory and the district list.
            if "STATE" in g.columns:
                keep = g["STATE"].astype(str).str.strip().str.lower() == "arunachal pradesh"
                if keep.any():
                    dropped = int((~keep).sum())
                    if dropped:
                        print(f"  {src}: dropped {dropped} outside Arunachal")
                    g = g[keep].reset_index(drop=True)
            g["_src"] = src
            frames.append(g)
    return frames


def do_landslide_inventory():
    """The real inventory — GSI extents plus Bhuvan's season-tagged polygons."""
    print("landslide inventory")
    import geopandas as gpd
    import pandas as pd
    from collections import Counter

    frames = _read_inventories()
    if not frames:
        return

    fig, ax = figure()
    style = {"GSI polygons": ("#0d366b", 6, 0.55),
             "Bhuvan 2014": ("#1baf7a", 12, 0.85),
             "Bhuvan 2017": ("#eda100", 12, 0.85),
             "Bhuvan 2023": ("#eb6834", 12, 0.85)}
    counts = {}
    for g in frames:
        src = g["_src"].iloc[0]
        c, sz, al = style.get(src, (MUTED, 8, 0.7))
        # Polygons at state scale are sub-pixel, so plot representative points.
        pts = g.geometry.representative_point()
        ax.scatter(pts.x, pts.y, s=sz / 6, c=c, alpha=al, linewidths=0,
                   label=f"{src} ({len(g):,})")
        counts[src] = int(len(g))
    overlay_state(ax, color="#00000088")
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    ax.legend(fontsize=8, frameon=False, loc="lower left", labelcolor=INK,
              title="Inventory source", title_fontsize=8, markerscale=6)
    finish(fig, ax, FIG / "landslide_inventory.png",
           "Mapped landslides — official inventories, by source")

    allg = pd.concat(frames, ignore_index=True)
    out = {"total": int(len(allg)), "by_source": counts}

    # GSI and Bhuvan mapped the state independently, so some physical slides
    # appear in both. Summing the sources overstates the inventory; measure the
    # overlap and report the union, because the sum is the number that would
    # get quoted to a client and then challenged.
    gsi = next((g for g in frames if g["_src"].iloc[0] == "GSI polygons"), None)
    bhu = [g for g in frames if g["_src"].iloc[0].startswith("Bhuvan")]
    if gsi is not None and bhu:
        b = gpd.GeoDataFrame(pd.concat(bhu, ignore_index=True), crs=bhu[0].crs)
        j = gpd.sjoin(b[["geometry"]], gsi[["geometry"]], how="left",
                      predicate="intersects")
        dup = int(j[j.index_right.notna()].index.nunique())
        out["overlap_bhuvan_in_gsi"] = dup
        out["unique_total"] = int(len(allg)) - dup
        out["overlap_pct"] = round(100 * dup / len(b), 1)

    # GSI spells the column DISTRICT, Bhuvan spells it District. Concatenating
    # leaves both, each null where the other source supplied the value, so
    # coalesce instead of picking one — picking one silently buries a whole
    # source in "unknown".
    cols = [c for c in ("DISTRICT", "District") if c in allg]
    if cols:
        d = allg[cols[0]]
        for c in cols[1:]:
            d = d.fillna(allg[c])
        d = d.fillna("unknown").astype(str).str.upper().str.strip()
        # "SHI YOMI" and "SHI-YOMI" are the same district in different sources.
        d = d.str.replace("-", " ", regex=False).str.replace(r"\s+", " ", regex=True)
        out["by_district"] = {k: int(v) for k, v in Counter(d).most_common(12)}
        out["districts_covered"] = int(d[d != "UNKNOWN"].nunique())

    # Size distribution, from whichever layers carry dimensions. The three
    # Bhuvan seasons disagree on both column name and dtype — 2017 delivers
    # areas as strings — so coerce rather than trusting the schema.
    areas = []
    for g in frames:
        for col in ("Area_sq_m", "Area_sqm", "Area_Sqm"):
            if col in g:
                v = pd.to_numeric(g[col], errors="coerce").dropna()
                areas += [float(x) for x in v[v > 0]]
                break
    if areas:
        a = np.array(areas)
        out["area_m2"] = {"n": int(a.size), "median": float(np.median(a)),
                          "p90": float(np.percentile(a, 90)),
                          "max": float(a.max())}

    act = []
    for g in frames:
        if "Activity" in g:
            act += list(g["Activity"].dropna().astype(str))
    if act:
        out["activity"] = {k: int(v) for k, v in Counter(act).most_common(6)}

    SUMMARY["inventory"] = out


def do_susceptibility():
    """GSI's own susceptibility map — the benchmark our output is judged against."""
    print("susceptibility (GSI)")
    f = CONTEXT / f"gsi_landslide-susceptibility_50m_{AOI_NAME}.tif"
    if not f.exists():
        return
    with rasterio.open(f) as src:
        a = src.read(1, out_shape=(src.height // 4, src.width // 4),
                     resampling=Resampling.mode).astype("float32")
    a[a == 0] = np.nan

    cmap = ListedColormap(["#f2e9a0", "#eda100", "#c62f2f"])
    fig, ax = figure()
    im = ax.imshow(a, extent=(W, E, S, N), cmap=cmap,
                   norm=BoundaryNorm([0.5, 1.5, 2.5, 3.5], 3), interpolation="nearest")
    overlay_state(ax, color="#00000088")
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02, ticks=[1, 2, 3])
    cb.ax.set_yticklabels(["Low", "Moderate", "High"], fontsize=8, color=INK)
    cb.outline.set_visible(False)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("GSI national landslide susceptibility (50 m)",
                 fontsize=11, color=INK, pad=8)
    fig.tight_layout()
    p = FIG / "susceptibility.jpg"
    fig.savefig(p, format="jpg", bbox_inches="tight", facecolor="white",
                pil_kwargs={"quality": 80, "optimize": True})
    plt.close(fig)
    print(f"  [fig] {p.name} ({p.stat().st_size / 1e3:.0f} KB)")

    with rasterio.open(f) as src:
        full = src.read(1)
    vals, counts = np.unique(full[full > 0], return_counts=True)
    tot = int(counts.sum())
    names = {1: "Low", 2: "Moderate", 3: "High"}
    SUMMARY["susceptibility"] = {
        "classes": {names.get(int(v), str(v)): int(c) for v, c in zip(vals, counts)},
        "pct": {names.get(int(v), str(v)): round(100 * int(c) / tot, 1)
                for v, c in zip(vals, counts)},
        "resolution_m": 50,
    }


def do_flood_extent():
    """Observed flood footprint, aggregated 2003-2020."""
    print("flood extent (Bhuvan)")
    f = LABELS / f"bhuvan_flood-aggregate-2003-2020_mask_{AOI_NAME}.tif"
    if not f.exists():
        return
    with rasterio.open(f) as src:
        m = src.read(1)

    fig, ax = figure()
    dem, tr = dem_mosaic(step=10)
    if dem is not None:
        ls = LightSource(azdeg=315, altdeg=45)
        ax.imshow(ls.hillshade(np.nan_to_num(dem), vert_exag=0.0006),
                  extent=(W, E, S, N), cmap="gray", alpha=0.45)
    ax.imshow(np.ma.masked_where(m == 0, m), extent=(W, E, S, N),
              cmap=ListedColormap([BLUE]), interpolation="nearest")
    overlay_state(ax, color="#00000088")
    ax.set_xlim(W, E); ax.set_ylim(S, N)
    finish(fig, ax, FIG / "flood_extent.png",
           "Areas observed flooded at least once, 2003–2020")

    SUMMARY["flood_extent"] = {
        "flooded_px": int(m.sum()),
        "pct_of_box": round(100 * float(m.mean()), 2),
        "years": "2003–2020",
    }


def main() -> None:
    print("Extracting visualisation data\n")
    for fn in (do_terrain, do_landcover, do_soil, do_rivers, do_seismic,
               do_labels, do_geology_state, do_landslide_inventory,
               do_susceptibility, do_flood_extent,
               do_population, do_rainfall, do_discharge,
               do_soilmoisture, do_era5, do_gfs, do_enso, do_boundaries,
               do_static_counts):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] {fn.__name__} failed: {type(exc).__name__}: {exc}")

    (DATA / "summary.json").write_text(json.dumps(SUMMARY, indent=1))
    print(f"\nwrote {DATA / 'summary.json'} ({len(json.dumps(SUMMARY)) / 1e3:.0f} KB)")
    print(f"figures in {FIG}")


if __name__ == "__main__":
    main()
