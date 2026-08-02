"""Export every dataset in a form the browser can render interactively.

Rather than baking pictures, this writes the underlying values:

  rasters      — resampled onto one common grid, quantised to uint8, base64
  categorical  — class codes preserved (land cover), not quantised
  vectors      — SVG path strings, drawn with Path2D on canvas
  points       — plain coordinate arrays with attributes for hover
  timeseries   — one frame per day, so the monsoon can be scrubbed

The browser then does the colouring, so palettes, opacity and value readout
are all live rather than fixed at render time.

Output: viz/data/web.json
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import base64
import json
import warnings

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.warp import reproject

from common import (AOI_BBOX, AOI_NAME, BOUNDARIES, CONTEXT, EXPOSURE,
                    HYDROLOGY, LABELS, LANDCOVER, RAW, ROOT, SEISMIC,
                    SOIL_GEOLOGY, TERRAIN, WEATHER)

warnings.filterwarnings("ignore")

VIZ = ROOT / "viz"
DATA = VIZ / "data"
DATA.mkdir(parents=True, exist_ok=True)

W, S, E, N = AOI_BBOX
GW, GH = 512, 260                       # common display grid
OUT: dict = {"bbox": [W, S, E, N], "grid": [GW, GH],
             "rasters": {}, "categorical": {}, "paths": {},
             "points": {}, "series": {}}


def common_transform():
    from rasterio.transform import from_bounds
    return from_bounds(W, S, E, N, GW, GH)


def to_grid(src_arr, src_transform, src_crs, nodata=None,
            resampling=Resampling.average):
    """Resample any raster onto the shared display grid."""
    dst = np.full((GH, GW), np.nan, dtype="float32")
    reproject(source=src_arr, destination=dst,
              src_transform=src_transform, src_crs=src_crs,
              dst_transform=common_transform(), dst_crs="EPSG:4326",
              src_nodata=nodata, dst_nodata=np.nan, resampling=resampling)
    return dst


def quantise(a: np.ndarray, name: str, label: str, unit: str,
             palette: str, note: str = "", log: bool = False):
    """uint8 with 0 reserved for no-data; browser rescales using min/max."""
    v = a.astype("float32")
    if log:
        v = np.log10(np.clip(v, 0, None) + 1)
    finite = np.isfinite(v)
    if not finite.any():
        print(f"  [skip] {name}: no valid data")
        return
    lo, hi = float(np.nanmin(v[finite])), float(np.nanpercentile(v[finite], 99.9))
    if hi <= lo:
        hi = lo + 1
    q = np.zeros(v.shape, dtype="uint8")
    scaled = np.clip((v - lo) / (hi - lo), 0, 1)
    q[finite] = (1 + scaled[finite] * 254).astype("uint8")
    OUT["rasters"][name] = {
        "label": label, "unit": unit, "palette": palette, "note": note,
        "min": round(lo, 4), "max": round(hi, 4), "log": log,
        "data": base64.b64encode(q.tobytes()).decode(),
    }
    print(f"  [ras] {name:16} {label:28} {q.nbytes/1e3:6.0f} KB raw")


# ------------------------------------------------------------------ rasters
def dem():
    tiles = sorted((TERRAIN / "copernicus_dem_30m").glob("*.tif"))
    if not tiles:
        return
    srcs = [rasterio.open(t) for t in tiles]
    arr, tr = merge(srcs, res=[s.res[0] * 6 for s in srcs[:1]] * 2)
    crs = srcs[0].crs
    for s in srcs:
        s.close()
    a = arr[0].astype("float32")
    a[a <= -1000] = np.nan
    g = to_grid(a, tr, crs)
    quantise(g, "elevation", "Elevation", "m", "terrain",
             "Height above sea level. Everything else about slopes derives from this.")

    # slope from the same mosaic, at native mosaic resolution for accuracy
    px = abs(tr.a) * 111320
    gy, gx = np.gradient(a, px)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    quantise(to_grid(slope, tr, crs), "slope", "Slope steepness", "°", "heat",
             "Above ~30° loose material struggles to stay put.")

    # aspect — which way the slope faces
    asp = (np.degrees(np.arctan2(-gx, gy)) + 360) % 360
    quantise(to_grid(asp, tr, crs), "aspect", "Aspect (facing direction)", "°", "cyclic",
             "0°=N, 90°=E, 180°=S, 270°=W. Controls sun and moisture.")


def soil():
    for prop, label, unit, note in [
        ("clay", "Clay content", "%", "Holds water; loses strength when saturated."),
        ("sand", "Sand content", "%", "Drains fast, grips by friction."),
        ("silt", "Silt content", "%", "The collapse-prone fraction."),
        ("soc", "Soil organic carbon", "g/kg", "Proxy for roots and topsoil structure."),
        ("bdod", "Bulk density", "cg/cm³", "How compacted the soil is."),
        ("cfvo", "Coarse fragments", "%", "Stoniness — proxy for regolith competence."),
    ]:
        f = SOIL_GEOLOGY / "soilgrids_250m" / f"soilgrids_{prop}-0-5cm_250m_{AOI_NAME}.tif"
        if not f.exists():
            continue
        with rasterio.open(f) as ds:
            a = ds.read(1).astype("float32")
            a[a == ds.nodata] = np.nan
            scale = 10.0 if prop in ("clay", "sand", "silt", "cfvo", "soc") else 1.0
            g = to_grid(a / scale, ds.transform, ds.crs)
        quantise(g, f"soil_{prop}", label, unit, "soil", note)


def landcover():
    tiles = sorted((LANDCOVER / "esa_worldcover_10m_2021").glob("*.tif"))
    if not tiles:
        return
    srcs = [rasterio.open(t) for t in tiles]
    arr, tr = merge(srcs, res=[s.res[0] * 30 for s in srcs[:1]] * 2)
    crs = srcs[0].crs
    for s in srcs:
        s.close()
    g = to_grid(arr[0].astype("float32"), tr, crs, resampling=Resampling.nearest)
    codes = np.nan_to_num(g, nan=0).astype("uint8")
    CLASSES = {10: ("Tree cover", "#137a3d"), 20: ("Shrubland", "#c9a227"),
               30: ("Grassland", "#d6d64c"), 40: ("Cropland", "#d98fd9"),
               50: ("Built-up", "#d03b3b"), 60: ("Bare / sparse", "#a8a8a8"),
               70: ("Snow and ice", "#dfe9f2"), 80: ("Water", "#2a78d6"),
               90: ("Wetland", "#0096a0"), 95: ("Mangrove", "#00cf75"),
               100: ("Moss / lichen", "#cbbf8a")}
    OUT["categorical"]["landcover"] = {
        "label": "Land cover", "note": "What is physically on the surface.",
        "classes": {str(k): {"name": v[0], "color": v[1]} for k, v in CLASSES.items()},
        "data": base64.b64encode(codes.tobytes()).decode(),
    }
    print(f"  [cat] landcover      {codes.nbytes/1e3:6.0f} KB raw")


def rainfall_map():
    import xarray as xr
    files = sorted((WEATHER / "gpm_imerg_daily").glob("*_2024*.nc4"))
    if not files:
        return
    stack, dates = [], []
    for f in files:
        try:
            ds = xr.open_dataset(f)
            stack.append(ds["precipitation"].values[0])
            dates.append(f.stem[-8:])
        except Exception:  # noqa: BLE001
            pass
    if not stack:
        return
    cube = np.stack(stack)                                  # (day, lon, lat)
    total = np.nansum(cube, axis=0).T[::-1]                 # -> (lat, lon)
    from rasterio.transform import from_bounds
    tr = from_bounds(W, S, E, N, total.shape[1], total.shape[0])
    quantise(to_grid(total, tr, "EPSG:4326"), "rain_total",
             "Monsoon rainfall total", "mm", "rain",
             "Summed June–September 2024.")

    # per-day frames for the scrubber, at native IMERG resolution
    frames = np.transpose(cube, (0, 2, 1))[:, ::-1, :]      # (day, lat, lon)
    fmax = float(np.nanpercentile(frames, 99.5))
    # Linear scaling makes a typical day almost invisible next to the season's
    # extreme. Store sqrt-scaled values and undo it in the browser, so light
    # rain is legible while the ordering and the readout stay exact.
    q = np.sqrt(np.clip(frames / max(fmax, 1e-6), 0, 1))
    q8 = (1 + q * 254).astype("uint8")
    OUT["series"]["rainfall"] = {
        "label": "Daily rainfall", "unit": "mm/day", "palette": "rain",
        "w": int(frames.shape[2]), "h": int(frames.shape[1]),
        "min": 0.0, "max": round(fmax, 1), "gamma": 2.0, "dates": dates,
        "daily_mean": [round(float(np.nanmean(f)), 2) for f in frames],
        "daily_max": [round(float(np.nanmax(f)), 1) for f in frames],
        "data": base64.b64encode(q8.tobytes()).decode(),
    }
    print(f"  [ser] rainfall       {len(dates)} frames  {q8.nbytes/1e3:6.0f} KB raw")


def discharge_map():
    import xarray as xr
    f = HYDROLOGY / "glofas" / f"glofas_historical_0p05_{AOI_NAME}_2024-monsoon.grib"
    if not f.exists():
        return
    ds = xr.open_dataset(f, engine="cfgrib", backend_kwargs={"indexpath": ""})
    a = ds["dis24"].values                                   # (time, lat, lon)
    peak = np.nanmax(a, axis=0)
    from rasterio.transform import from_bounds
    tr = from_bounds(W, S, E, N, peak.shape[1], peak.shape[0])
    quantise(to_grid(peak, tr, "EPSG:4326"), "discharge_peak",
             "Peak river discharge", "m³/s", "water",
             "Highest flow reached during monsoon 2024.", log=True)

    step = 2                                                 # halve the payload
    sub = a[::step]
    lg = np.log10(np.clip(sub, 0, None) + 1)
    m = float(np.nanmax(lg))
    q8 = (1 + np.clip(lg / max(m, 1e-6), 0, 1) * 254).astype("uint8")
    OUT["series"]["discharge"] = {
        "label": "River discharge", "unit": "m³/s", "palette": "water",
        "w": int(a.shape[2]), "h": int(a.shape[1]), "log": True,
        "min": 0.0, "max": round(float(10 ** m - 1), 1),
        "dates": [f"day {i*step+1}" for i in range(sub.shape[0])],
        "daily_max": [round(float(np.nanmax(x)), 1) for x in sub],
        "data": base64.b64encode(q8.tobytes()).decode(),
    }
    print(f"  [ser] discharge      {sub.shape[0]} frames  {q8.nbytes/1e3:6.0f} KB raw")


def soilmoisture_map():
    import glob
    import h5py
    fs = sorted(glob.glob(str(SOIL_GEOLOGY / "smap_soil_moisture" / "*.h5")))
    if not fs:
        return
    with h5py.File(fs[0], "r") as h:
        g = h["Soil_Moisture_Retrieval_Data_AM"]
        sm, lat, lon = g["soil_moisture"][:], g["latitude"][:], g["longitude"][:]
        fill = g["soil_moisture"].attrs.get("_FillValue", -9999.0)
    m = (lat >= S) & (lat <= N) & (lon >= W) & (lon <= E) & (sm != fill) & np.isfinite(sm)
    grid = np.full((GH, GW), np.nan, dtype="float32")
    xs = ((lon[m] - W) / (E - W) * (GW - 1)).astype(int)
    ys = ((N - lat[m]) / (N - S) * (GH - 1)).astype(int)
    for x, y, v in zip(xs, ys, sm[m]):
        for dy in (-1, 0, 1):                     # slight dilation: 9 km cells
            for dx in (-1, 0, 1):
                yy, xx = y + dy, x + dx
                if 0 <= yy < GH and 0 <= xx < GW:
                    grid[yy, xx] = v
    quantise(grid, "soil_moisture", "Surface soil wetness", "m³/m³", "wet",
             "How saturated the top few cm already are.")


def era5_map():
    import xarray as xr
    fs = sorted((WEATHER / "era5_land").glob("*.nc"))
    if not fs:
        return
    ds = xr.open_mfdataset(fs, combine="by_coords") if len(fs) > 1 else xr.open_dataset(fs[0])
    for var, label, unit, note in [
        ("swvl1", "Soil water (0–7 cm)", "m³/m³", "Modelled, gap-free, from ERA5-Land."),
        ("smlt", "Snowmelt", "m", "Water released by melting — matters above 3,000 m."),
    ]:
        if var not in ds:
            continue
        a = ds[var]
        arr = (a.sum(dim="valid_time") if var == "smlt"
               else a.mean(dim="valid_time")).values
        lat = ds["latitude"].values
        if lat[0] < lat[-1]:
            arr = arr[::-1]
        from rasterio.transform import from_bounds
        tr = from_bounds(W, S, E, N, arr.shape[1], arr.shape[0])
        quantise(to_grid(arr, tr, "EPSG:4326"), f"era5_{var}", label, unit, "wet", note)


def population_map():
    import geopandas as gpd
    from rasterio.mask import mask
    f = EXPOSURE / "worldpop_population_100m_india_2020.tif"
    st = BOUNDARIES / f"gadm_state-boundary_vector_{AOI_NAME}.gpkg"
    if not f.exists() or not st.exists():
        return
    g = gpd.read_file(st)
    with rasterio.open(f) as ds:
        geoms = [x.__geo_interface__ for x in g.to_crs(ds.crs).geometry]
        arr, tr = mask(ds, geoms, crop=True, nodata=np.nan, filled=True)
        crs = ds.crs
    quantise(to_grid(arr[0], tr, crs, resampling=Resampling.sum), "population",
             "Population density", "people / cell", "pop",
             "Modelled from census plus satellite-detected buildings.", log=True)


# ------------------------------------------------------------------ vectors
def path_from_geom(geom, prec=4) -> str:
    """SVG path in lon/lat — the browser turns it into a Path2D."""
    parts = []

    def ring(coords):
        pts = [f"{round(x, prec)},{round(y, prec)}" for x, y in coords]
        if pts:
            parts.append("M" + pts[0] + "L" + "L".join(pts[1:]))

    gt = geom.geom_type
    if gt == "LineString":
        ring(geom.coords)
    elif gt == "MultiLineString":
        for g in geom.geoms:
            ring(g.coords)
    elif gt == "Polygon":
        ring(geom.exterior.coords)
        for i in geom.interiors:
            ring(i.coords)
    elif gt == "MultiPolygon":
        for g in geom.geoms:
            ring(g.exterior.coords)
            for i in g.interiors:
                ring(i.coords)
    return "".join(parts)


def vectors():
    import geopandas as gpd

    def add(name, gdf, label, color, width, simplify=None):
        if gdf is None or gdf.empty:
            return
        g = gdf.copy()
        if simplify:
            g["geometry"] = g.geometry.simplify(simplify)
        d = "".join(path_from_geom(x) for x in g.geometry if x is not None)
        OUT["paths"][name] = {"label": label, "color": color, "width": width,
                              "d": d, "count": int(len(g))}
        print(f"  [vec] {name:16} {len(g):6} feat  {len(d)/1e3:6.0f} KB")

    f = BOUNDARIES / f"gadm_state-boundary_vector_{AOI_NAME}.gpkg"
    if f.exists():
        add("state", gpd.read_file(f).boundary.to_frame("geometry"),
            "State boundary", "#0b0b0b", 1.8, 0.002)
    f = BOUNDARIES / f"gadm_district-boundary_vector_{AOI_NAME}.gpkg"
    if f.exists():
        add("districts", gpd.read_file(f).boundary.to_frame("geometry"),
            "District boundaries", "#898781", 0.7, 0.003)

    f = HYDROLOGY / f"hydrosheds_rivers_vector_{AOI_NAME}.gpkg"
    if f.exists():
        r = gpd.read_file(f)
        for key, lo, hi, col, wd, simp in [
            ("rivers_small", 10, 500, "#9ec5f4", 0.4, 0.004),
            ("rivers_mid", 500, 5000, "#3987e5", 0.9, 0.003),
            ("rivers_large", 5000, 1e12, "#0d366b", 1.8, 0.002),
        ]:
            sub = r[(r["UPLAND_SKM"] >= lo) & (r["UPLAND_SKM"] < hi)]
            add(key, sub,
                f"Rivers {int(lo):,}–{'∞' if hi > 1e11 else format(int(hi), ',')} km²",
                col, wd, simp)

    f = EXPOSURE / f"osm_roads_vector_{AOI_NAME}-clipped.gpkg"
    if f.exists():
        rd = gpd.read_file(f)
        if "highway" in rd:
            main = rd[rd["highway"].isin(
                ["trunk", "primary", "secondary", "tertiary"])]
            add("roads", main, "Major roads", "#eb6834", 0.8, 0.002)

    f = CONTEXT / f"apssdi_lineaments_vector_{AOI_NAME}.geojson"
    if f.exists():
        lin = gpd.read_file(f)
        # Nearly 5,000 lineaments render as a solid smear at state scale, and
        # the major ones are what carry the predictive signal anyway.
        if "magnitud_1" in lin:
            major = lin[~lin["magnitud_1"].astype(str).str.contains("Minor", na=False)]
            if not major.empty:
                lin = major
        add("lineaments", lin, "Faults and lineaments", "#8d6bb8", 0.5, 0.002)


def points():
    import geopandas as gpd
    import pandas as pd

    f = LABELS / f"nasa-glc_landslides_point_{AOI_NAME}.geojson"
    if f.exists():
        g = gpd.read_file(f)
        d = pd.to_datetime(g["ev_date"], errors="coerce", unit="ms")
        OUT["points"]["landslides"] = {
            "label": "Recorded landslides", "color": "#d03b3b",
            "items": [{"x": round(p.x, 4), "y": round(p.y, 4),
                       "t": (str(dd.date()) if pd.notna(dd) else "date unknown"),
                       "a": (r.loc_accu if isinstance(r.loc_accu, str) else "unknown"),
                       "g": (r.ls_trig if isinstance(r.ls_trig, str) else "unknown"),
                       "s": (r.ls_size if isinstance(r.ls_size, str) else "unknown")}
                      for p, dd, r in zip(g.geometry, d, g.itertuples())],
        }
        print(f"  [pts] landslides     {len(g)} points")

    # Mapped landslide inventory — Bhuvan's three seasons only, because these
    # are the ones carrying a date. Tens of thousands of polygons will not fit
    # in a browser payload, so each becomes a single point and the set is
    # thinned to the largest slides — the ones a reviewer would look for.
    inv = []
    for fn, src in [
        (LABELS / f"bhuvan_ar_slim_2014_gcs_polygon_{AOI_NAME}.geojson", "2014"),
        (LABELS / f"bhuvan_ar_slim_2017_polygon_{AOI_NAME}.geojson", "2017"),
        (LABELS / f"bhuvan_ls_arunachal_2023_polygon_{AOI_NAME}.geojson", "2023"),
    ]:
        if not fn.exists():
            continue
        g = gpd.read_file(fn)
        acol = next((c for c in ("Area_sq_m", "Area_sqm", "Area_Sqm") if c in g), None)
        dcol = next((c for c in ("District", "DISTRICT") if c in g), None)
        # Column names must not start with an underscore: itertuples() renames
        # those to positional _1, _2 and the attribute lookup below breaks.
        g["area_m2"] = pd.to_numeric(g[acol], errors="coerce") if acol else 0.0
        g["dist"] = g[dcol].astype(str) if dcol else "unknown"
        g["season"] = src
        inv.append(g[["geometry", "area_m2", "dist", "season"]])

    if inv:
        allg = pd.concat(inv, ignore_index=True)
        allg = gpd.GeoDataFrame(allg, geometry="geometry", crs=inv[0].crs)
        allg = allg.sort_values("area_m2", ascending=False).head(4000)
        pts = allg.geometry.representative_point()
        OUT["points"]["inventory"] = {
            "label": "Mapped landslides (largest 4,000)", "color": "#0d366b",
            "items": [{"x": round(p.x, 4), "y": round(p.y, 4),
                       "t": r.season, "a": r.dist.title(),
                       "s": (f"{int(r.area_m2):,} m²"
                             if r.area_m2 == r.area_m2 and r.area_m2
                             else "size unknown")}
                      for p, r in zip(pts, allg.itertuples())],
        }
        print(f"  [pts] inventory      {len(allg)} points "
              f"(of {sum(len(x) for x in inv)})")

    f = SEISMIC / f"usgs_earthquakes_point_{AOI_NAME}-regional_1900-2026.geojson"
    if f.exists():
        g = gpd.read_file(f)
        g = g[g["mag"].notna()].sort_values("mag", ascending=False).head(900)
        epoch = pd.Timestamp("1970-01-01")
        OUT["points"]["earthquakes"] = {
            "label": "Earthquakes M4+", "color": "#eb6834",
            "items": [{"x": round(p.x, 3), "y": round(p.y, 3),
                       "m": round(float(r.mag), 1),
                       "t": str((epoch + pd.Timedelta(milliseconds=float(r.time))).date())}
                      for p, r in zip(g.geometry, g.itertuples())],
        }
        print(f"  [pts] earthquakes    {len(g)} points")


def main() -> None:
    print("Exporting interactive layers\n")
    for fn in (dem, soil, landcover, rainfall_map, discharge_map,
               soilmoisture_map, era5_map, population_map, vectors, points):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] {fn.__name__}: {type(exc).__name__}: {exc}")

    p = DATA / "web.json"
    p.write_text(json.dumps(OUT))
    print(f"\nwrote {p}  ({p.stat().st_size / 1e6:.2f} MB)")
    print(f"  rasters {len(OUT['rasters'])} · categorical {len(OUT['categorical'])} "
          f"· paths {len(OUT['paths'])} · points {len(OUT['points'])} "
          f"· series {len(OUT['series'])}")


if __name__ == "__main__":
    main()
