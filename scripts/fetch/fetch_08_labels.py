"""Tier A — Landslide event labels (NASA Global Landslide Catalog / COOLR).

PROVENANCE WARNING
------------------
NASA's own distribution points are not currently reachable:
  * data.nasa.gov Socrata endpoints  -> 404 (platform migrated)
  * maps.nccs.nasa.gov ArcGIS        -> connection refused
  * landslides.nasa.gov/viewer       -> JS app, no documented service URL

The data below therefore comes from a public ArcGIS Online re-host of the
catalogue, not from NASA directly. Treat it as provisional: the contents look
right, but currency and completeness are unverified against the source.
Re-point this script at the official endpoint once one is available.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import geopandas as gpd
import pandas as pd

from common import AOI_BBOX, AOI_NAME, LABELS, http_get, record

SERVICE = ("https://services9.arcgis.com/RrvMEynxDB8hycVO/arcgis/rest/services/"
           "nasa_global_landslide_catalog_point/FeatureServer/0")


def query_aoi() -> dict:
    w, s, e, n = AOI_BBOX
    params = {
        "where": "1=1",
        "geometry": f"{w},{s},{e},{n}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326", "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*", "f": "geojson",
    }
    return http_get(f"{SERVICE}/query", params=params, timeout=180).json()


def main() -> None:
    print("NASA Global Landslide Catalog (via ArcGIS Online re-host)")
    print("  [warn] not an official NASA endpoint — see module docstring")

    data = query_aoi()
    feats = data.get("features", [])
    out = LABELS / f"nasa-glc_landslides_point_{AOI_NAME}.geojson"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data))
    print(f"  [ok]   {out.name} ({len(feats)} events)")

    if not feats:
        return

    gdf = gpd.read_file(out)
    gdf.to_file(LABELS / f"nasa-glc_landslides_point_{AOI_NAME}.gpkg", driver="GPKG")

    # --- what these labels are actually worth -----------------------------
    print("\n  --- label quality ---")
    if "ev_date" in gdf:
        d = pd.to_datetime(gdf["ev_date"], errors="coerce", unit="ms")
        if d.isna().all():
            d = pd.to_datetime(gdf["ev_date"], errors="coerce")
        print(f"  date range     : {d.min()}  ->  {d.max()}")
        print(f"  missing dates  : {int(d.isna().sum())}/{len(gdf)}")
    for col, label in [("loc_accu", "location accuracy"),
                       ("ls_trig", "trigger"),
                       ("ls_cat", "category"),
                       ("ls_size", "size")]:
        if col in gdf:
            vc = gdf[col].fillna("(null)").value_counts()
            print(f"  {label:15}: " + ", ".join(f"{k}={v}" for k, v in vc.head(6).items()))

    record(
        LABELS, source="NASA Global Landslide Catalog (unofficial ArcGIS re-host)",
        url=SERVICE, files=[out],
        license_="NASA data is public domain; re-host terms unverified",
        notes=(f"{len(feats)} events intersecting the AOI. PROVISIONAL — official NASA "
               "endpoints unreachable at fetch time. Location accuracy is coarse "
               "(km-level), so these support validation far better than training."),
    )


if __name__ == "__main__":
    main()
