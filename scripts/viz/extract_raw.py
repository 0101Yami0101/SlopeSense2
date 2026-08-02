"""Open every raw file and record what is actually inside it.

The narrative page tells you what a dataset means. This produces the other
half — the bytes underneath it: which files exist, where they came from, the
real column names, the real dtypes, and a handful of untouched rows or cell
values straight off disk.

    python scripts/viz/extract_raw.py     # -> viz/data/raw.json

Nothing here is interpreted or rounded. If a column is called `Landslde_A`
and holds the string "1200.5", that is what shows up.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import warnings
from datetime import datetime, timezone

import numpy as np

from common import RAW, ROOT

warnings.filterwarnings("ignore")

OUT = ROOT / "viz" / "data" / "raw.json"

SAMPLE_ROWS = 8      # attribute rows shown per vector file
GRID = 6             # raster cell values shown, GRID x GRID from the centre
MAX_COLS = 40

# Which files sit behind each card. Globs are relative to data/raw.
CARD_FILES: dict[str, list[str]] = {
    "boundaries": ["01_boundaries/gadm_*.gpkg"],
    "terrain": ["02_terrain/copernicus_dem_30m/*.tif"],
    "slope": ["02_terrain/copernicus_dem_30m/*.tif"],
    "soil": ["03_soil_geology/soilgrids_250m/*.tif"],
    "geology": [
        "03_soil_geology/apssdi_lithology_vector_arunachal.geojson",
        "10_context/apssdi_geomorphology_vector_arunachal.geojson",
        "10_context/apssdi_litho-geomorphology_vector_arunachal.geojson",
        "10_context/apssdi_lineaments_vector_arunachal.geojson",
        "10_context/apssdi_geology-mining_vector_arunachal.geojson",
        "10_context/apssdi_snow-cover_vector_arunachal.geojson",
    ],
    "landcover": ["04_landcover/esa_worldcover_10m_2021/*.tif"],
    "rivers": [
        "05_hydrology/hydrosheds_rivers_vector_arunachal.gpkg",
        "05_hydrology/hydrosheds_basins-lev08_vector_arunachal.gpkg",
        "05_hydrology/hydrosheds_basins-lev12_vector_arunachal.gpkg",
        "05_hydrology/apssdi_drainage_vector_arunachal.geojson",
    ],
    "discharge": ["05_hydrology/glofas/*.grib"],
    "rainfall": ["06_weather/gpm_imerg_daily/*.nc4"],
    "soilmoisture": ["03_soil_geology/smap_soil_moisture/*.h5"],
    "gfs": ["06_weather/noaa_gfs_0p25/*.grib2"],
    "enso": ["06_weather/noaa-cpc_oni_enso_global.txt"],
    "era5": ["06_weather/era5_land/*.nc"],
    "seismic": [
        "07_seismic/usgs_earthquakes_point_arunachal_1900-2026.geojson",
        "07_seismic/usgs_earthquakes_point_arunachal-regional_1900-2026.geojson",
        "07_seismic/iris_stations_text_arunachal-buffered.txt",
    ],
    "sentinel1": ["11_satellite/*.zip"],
    "inventory": [
        "08_labels/gsi-nlfc_landslides_polygon_arunachal.geojson",
        "08_labels/gsi-nlfc_landslides_point_arunachal.geojson",
        "08_labels/bhuvan_ar_slim_2014_gcs_polygon_arunachal.geojson",
        "08_labels/bhuvan_ar_slim_2017_polygon_arunachal.geojson",
        "08_labels/bhuvan_ls_arunachal_2023_polygon_arunachal.geojson",
    ],
    "susceptibility": ["10_context/gsi_landslide-susceptibility_50m_arunachal.tif"],
    "floodextent": ["08_labels/bhuvan_flood-aggregate-2003-2020_mask_arunachal.tif"],
    "labels": ["08_labels/nasa-glc_landslides_point_arunachal.geojson"],
    "population": [
        "09_exposure/worldpop_population_100m_india_2020.tif",
        "09_exposure/apssdi_settlements_vector_arunachal.geojson",
        "09_exposure/apssdi_admin-circles_vector_arunachal.geojson",
    ],
    "osm": ["09_exposure/osm_*_vector_arunachal-clipped.gpkg"],
    "gap_wdpa": ["09_exposure/wdpa_protected-areas_vector_arunachal.gpkg"],
}

# The script that fetched it, and the machine request it actually issues.
# Kept verbatim so the endpoint can be pasted into a browser and checked.
CARD_FETCH: dict[str, dict[str, str]] = {
    "boundaries": dict(script="fetch_01_boundaries.py",
                       call="GET https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_IND.gpkg"),
    "terrain": dict(script="fetch_02_terrain.py",
                    call="GET https://copernicus-dem-30m.s3.amazonaws.com/"
                         "Copernicus_DSM_COG_10_N{lat}_00_E{lon}_00_DEM/…_DEM.tif  × 28 tiles"),
    "slope": dict(script="derived in scripts/viz/extract.py",
                  call="numpy gradient over the Copernicus DEM — no download"),
    "soil": dict(script="fetch_03_soil.py",
                 call="GET https://maps.isric.org/mapserv?map=/map/{prop}.map"
                      "&SERVICE=WCS&REQUEST=GetCoverage&COVERAGEID={prop}_{depth}_mean"),
    "geology": dict(script="fetch_16_apssdi.py",
                    call="GET https://apssdi.in/geoserver/ows?service=WFS&version=2.0.0"
                         "&request=GetFeature&typeNames={layer}&outputFormat=application/json"
                         "  (no auth; needs the Go Daddy G2 intermediate added to certifi)"),
    "landcover": dict(script="fetch_04_landcover.py",
                      call="GET https://esa-worldcover.s3.eu-central-1.amazonaws.com/"
                           "v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"),
    "rivers": dict(script="fetch_05_hydrology.py",
                   call="GET https://data.hydrosheds.org/file/HydroRIVERS/"
                        "HydroRIVERS_v10_as_shp.zip  → clipped to AOI"),
    "discharge": dict(script="fetch_12_glofas.py",
                      call="cdsapi → ewds.climate.copernicus.eu/api  dataset "
                           "'cems-glofas-forecast' / 'cems-glofas-historical'"),
    "rainfall": dict(script="fetch_11_imerg.py",
                     call="GET https://gpm1.gesdisc.eosdis.nasa.gov/opendap/GPM_L3/"
                          "GPM_3IMERGDL.07/{yyyy}/{mm}/3B-DAY-L.MS.MRG.3IMERG.{date}"
                          "-S000000-E235959.V07B.nc4?precipitation[…]  (Earthdata login)"),
    "soilmoisture": dict(script="fetch_13_smap.py",
                         call="GET https://n5eil01u.ecs.nsidc.org/SMAP/SPL3SMP_E.006/"
                              "{date}/SMAP_L3_SM_P_E_{date}_R19240_00{n}.h5"),
    "gfs": dict(script="fetch_06_weather.py",
                call="GET https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
                     "?file=gfs.t{cycle}z.pgrb2.0p25.f{lead}&var_APCP=on&subregion="
                     "&leftlon=91&rightlon=98&toplat=30&bottomlat=26"),
    "enso": dict(script="fetch_06_weather.py",
                 call="GET https://origin.cpc.ncep.noaa.gov/products/analysis_monitoring/"
                      "ensostuff/detrend.nino34.ascii.txt"),
    "era5": dict(script="fetch_15_era5land.py",
                 call="cdsapi → cds.climate.copernicus.eu/api  dataset "
                      "'reanalysis-era5-land'"),
    "seismic": dict(script="fetch_07_seismic.py",
                    call="GET https://earthquake.usgs.gov/fdsnws/event/1/query"
                         "?format=geojson&starttime=1900-01-01&minmagnitude=4"
                         "&minlatitude=26&maxlatitude=30&minlongitude=91&maxlongitude=98"),
    "sentinel1": dict(script="fetch_14_sentinel.py",
                      call="POST https://identity.dataspace.copernicus.eu/…/token  then "
                           "GET catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter=…"),
    "inventory": dict(script="fetch_17_gsi_landslides.py + fetch_17_bhuvan_landslides.py",
                      call="GSI: ArcGIS FeatureServer /query?where=1=1&outFields=*&f=geojson"
                           "   ·   Bhuvan: GET https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms"
                           "?request=GetFeatureInfo&info_format=application/json"
                           "&width=8&height=8&x=4&y=4  walked over a 0.25° grid "
                           "(WFS is disabled; one big call silently caps and biases)"),
    "susceptibility": dict(script="fetch_18_hazard_products.py",
                           call="GET https://bhusanket.gsi.gov.in/DotNet/proxy.ashx?"
                                "<ImageServer>/exportImage?bbox=…&size=…&format=tiff"
                                "&f=image  — stacked in 2 strips, server maxImageHeight=4100"),
    "floodextent": dict(script="fetch_18_hazard_products.py",
                        call="GET https://bhuvan-app1.nrsc.gov.in/…/wms?request=GetMap"
                             "&layers=agg_ar&width=4000&height=2303&format=image/geotiff"),
    "labels": dict(script="fetch_08_labels.py",
                   call="GET https://maps.nccs.nasa.gov/arcgis/rest/services/"
                        "global_landslide_catalog/…/query?where=1=1&outFields=*&f=geojson"),
    "population": dict(script="fetch_09_exposure.py + fetch_16_apssdi.py",
                       call="GET https://data.worldpop.org/GIS/Population/"
                            "Global_2000_2020/2020/IND/ind_ppp_2020.tif"),
    "osm": dict(script="fetch_09_exposure.py",
                call="Overpass QL → https://overpass-api.de/api/interpreter  "
                     "(way[highway]/(building)/(amenity) in bbox), then clipped to the state"),
    "gap_wdpa": dict(script="fetch_09_exposure.py",
                     call="GET https://d1gam3xoknrgr2.cloudfront.net/current/"
                          "WDPA_WDOECM_{mon}{yyyy}_Public_IND_shp.zip"),
}

VECTOR = {".geojson", ".gpkg", ".shp", ".json"}
RASTER = {".tif", ".tiff"}
GRIDDED = {".nc", ".nc4", ".grib", ".grib2", ".grb"}
TEXT = {".txt", ".csv"}


# --------------------------------------------------------------------------
# per-format readers — each returns a dict describing one file
# --------------------------------------------------------------------------
def _clean(v):
    """Make a value JSON-safe without changing what it says."""
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 6)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    s = str(v)
    return s if len(s) <= 160 else s[:157] + "…"


def read_vector(p: Path) -> dict:
    import pyogrio

    info = pyogrio.read_info(p)
    gdf = pyogrio.read_dataframe(p, max_features=SAMPLE_ROWS)
    cols = [c for c in gdf.columns if c != "geometry"][:MAX_COLS]

    dtypes = dict(zip(info["fields"], [str(d) for d in info["dtypes"]]))
    schema = [{"col": c, "type": dtypes.get(c, str(gdf[c].dtype))} for c in cols]
    rows = [[_clean(gdf.iloc[i][c]) for c in cols] for i in range(len(gdf))]

    geom = gdf.geometry.iloc[0] if len(gdf) and gdf.geometry.notna().any() else None
    wkt = geom.wkt if geom is not None else ""
    gtype = str(info.get("geometry_type", "") or "")
    if gtype in ("", "Unknown", "None") and geom is not None:
        gtype = geom.geom_type            # GeoJSON often declares nothing
    return {
        "kind": "vector",
        "detail": {
            "driver": info.get("driver", ""),
            "geometry": gtype,
            "features": int(info.get("features", 0)),
            "crs": str(info.get("crs", "")),
            "fields": len(info["fields"]),
        },
        "schema": schema,
        "rows": rows,
        "geometry_sample": (wkt[:400] + "…") if len(wkt) > 400 else wkt,
    }


def read_raster(p: Path) -> dict:
    import rasterio
    from rasterio.windows import Window

    with rasterio.open(p) as ds:
        b = ds.bounds
        r, c = ds.height // 2, ds.width // 2
        win = Window(max(0, c - GRID // 2), max(0, r - GRID // 2),
                     min(GRID, ds.width), min(GRID, ds.height))
        arr = ds.read(1, window=win).astype("float64")
        nod = ds.nodata
        valid = arr[np.isfinite(arr)] if nod is None else arr[(arr != nod) & np.isfinite(arr)]
        return {
            "kind": "raster",
            "detail": {
                "driver": ds.driver,
                "size": f"{ds.width} × {ds.height} px",
                "bands": ds.count,
                "dtype": str(ds.dtypes[0]),
                "nodata": _clean(nod),
                "crs": str(ds.crs),
                "cell": f"{abs(ds.transform.a):.6g} × {abs(ds.transform.e):.6g}",
                "bounds": f"{b.left:.4f}, {b.bottom:.4f} → {b.right:.4f}, {b.top:.4f}",
            },
            "grid": {
                "label": f"band 1, {arr.shape[1]}×{arr.shape[0]} cells at the centre "
                         f"(row {r}, col {c})",
                "values": [[_clean(v) for v in row] for row in arr],
                "min": _clean(valid.min()) if valid.size else None,
                "max": _clean(valid.max()) if valid.size else None,
            },
        }


def read_gridded(p: Path) -> dict:
    import xarray as xr

    if p.suffix in (".grib", ".grib2", ".grb"):
        # One GRIB file can hold instantaneous, averaged and accumulated fields
        # under the same key; cfgrib refuses to merge them, so pick one.
        kw = dict(engine="cfgrib", backend_kwargs={"indexpath": ""})
        for flt in ({}, {"stepType": "accum"}, {"stepType": "instant"},
                    {"stepType": "avg"}):
            try:
                if flt:
                    kw["backend_kwargs"]["filter_by_keys"] = flt
                ds = xr.open_dataset(p, **kw)
                break
            except Exception:                                # noqa: BLE001
                ds = None
        if ds is None:
            raise RuntimeError("no stepType filter opened this GRIB")
    else:
        kw = {}
        ds = xr.open_dataset(p)
    try:
        variables = []
        for name, da in list(ds.data_vars.items())[:12]:
            variables.append({
                "col": str(name),
                "type": f"{da.dtype} {tuple(int(s) for s in da.shape)}",
                "note": " · ".join(filter(None, [
                    str(da.attrs.get("units", "")),
                    str(da.attrs.get("long_name", ""))[:60],
                ])),
            })
        dims = ", ".join(f"{k}={v}" for k, v in list(ds.sizes.items())[:8])

        grid = None
        if ds.data_vars:
            da = ds[list(ds.data_vars)[0]]
            flat = da
            while flat.ndim > 2:
                flat = flat.isel({flat.dims[0]: 0})
            if flat.ndim == 2:
                a = np.asarray(flat.values, dtype="float64")
                r, c = a.shape[0] // 2, a.shape[1] // 2
                sub = a[max(0, r - GRID // 2):r + GRID // 2 + 1,
                        max(0, c - GRID // 2):c + GRID // 2 + 1]
                v = sub[np.isfinite(sub)]
                grid = {
                    "label": f"{list(ds.data_vars)[0]} — {sub.shape[1]}×{sub.shape[0]} "
                             f"cells at the centre",
                    "values": [[_clean(x) for x in row] for row in sub],
                    "min": _clean(v.min()) if v.size else None,
                    "max": _clean(v.max()) if v.size else None,
                }
        return {
            "kind": "gridded",
            "detail": {
                "format": "GRIB" if kw else "NetCDF/HDF",
                "dimensions": dims,
                "variables": len(ds.data_vars),
                "coords": ", ".join(list(ds.coords)[:10]),
            },
            "schema": variables,
            "rows": [],
            "grid": grid,
        }
    finally:
        ds.close()


def read_hdf5(p: Path) -> dict:
    import h5py

    found: list[dict] = []
    with h5py.File(p, "r") as f:
        def walk(name, obj):
            if isinstance(obj, h5py.Dataset) and len(found) < 14:
                found.append({
                    "col": name,
                    "type": f"{obj.dtype} {tuple(int(s) for s in obj.shape)}",
                    "note": str(obj.attrs.get("units", b"")).strip("b'\""),
                })
        f.visititems(walk)
        groups = [k for k in f.keys()]
    return {
        "kind": "hdf5",
        "detail": {"format": "HDF5", "top-level groups": ", ".join(groups[:8]),
                   "datasets shown": len(found)},
        "schema": found,
        "rows": [],
    }


def read_text(p: Path) -> dict:
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return {
        "kind": "text",
        "detail": {"lines": len(lines)},
        "text": "\n".join(lines[:14]),
    }


def read_archive(p: Path) -> dict:
    import zipfile

    with zipfile.ZipFile(p) as z:
        names = z.namelist()
    return {
        "kind": "archive",
        "detail": {"format": "ZIP", "entries": len(names)},
        "text": "\n".join(names[:14]),
    }


def describe(p: Path) -> dict:
    ext = p.suffix.lower()
    try:
        if ext in VECTOR:
            body = read_vector(p)
        elif ext in RASTER:
            body = read_raster(p)
        elif ext in GRIDDED:
            body = read_gridded(p)
        elif ext == ".h5":
            body = read_hdf5(p)
        elif ext in TEXT:
            body = read_text(p)
        elif ext == ".zip":
            body = read_archive(p)
        else:
            body = {"kind": "other", "detail": {}}
    except Exception as e:                                   # noqa: BLE001
        body = {"kind": "error", "detail": {"could not open": f"{type(e).__name__}: {e}"}}

    st = p.stat()
    body["path"] = p.relative_to(ROOT).as_posix()
    body["name"] = p.name
    body["bytes"] = st.st_size
    body["modified"] = datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%d")
    return body


# --------------------------------------------------------------------------
def provenance() -> dict[str, list[dict]]:
    """Every _SOURCES.json entry, keyed by the file it covers."""
    by_file: dict[str, list[dict]] = {}
    for f in sorted(RAW.glob("*/_SOURCES.json")):
        try:
            entries = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                    # noqa: BLE001
            continue
        for e in entries if isinstance(entries, list) else [entries]:
            meta = {k: e.get(k, "") for k in
                    ("source", "url", "fetched_utc", "license", "notes")}
            for fl in e.get("files", []):
                by_file.setdefault(fl.get("name", ""), []).append(meta)
    return by_file


def main() -> None:
    prov = provenance()
    cards: dict[str, dict] = {}

    for card, patterns in CARD_FILES.items():
        paths: list[Path] = []
        for pat in patterns:
            paths.extend(sorted(RAW.glob(pat)))
        if not paths:
            print(f"  {card:16} no files matched")
            continue

        # Big uniform collections: describe a few, count the rest.
        shown = paths if len(paths) <= 6 else paths[:4] + paths[-1:]
        files = [describe(p) for p in shown]

        srcs, seen, unrecorded = [], set(), []
        for p in paths:
            # _SOURCES.json records the file as downloaded. Anything we clipped
            # afterwards keeps the provenance of the file it came from.
            hits = prov.get(p.name) or prov.get(p.name.replace("-clipped", "")) or []
            if not hits:
                unrecorded.append(p.name)
            for m in hits:
                key = (m["source"], m["url"])
                if key not in seen:
                    seen.add(key)
                    srcs.append(m)

        cards[card] = {
            "files": files,
            "file_count": len(paths),
            "shown_count": len(files),
            "total_bytes": sum(p.stat().st_size for p in paths),
            "sources": srcs,
            "unrecorded": unrecorded[:6],
            "unrecorded_count": len(unrecorded),
            "fetch": CARD_FETCH.get(card, {}),
        }
        mb = cards[card]["total_bytes"] / 1e6
        print(f"  {card:16} {len(paths):4} files  {mb:9.1f} MB  "
              f"{len(srcs)} source record(s)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cards), encoding="utf-8")
    print(f"\nwrote {OUT}  ({OUT.stat().st_size / 1e3:.0f} kB, {len(cards)} cards)")


if __name__ == "__main__":
    main()
