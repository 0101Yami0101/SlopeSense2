"""Tier A — Exposure: who and what is in harm's way.

WorldPop         — modelled population count, 100 m
OpenStreetMap    — roads, buildings, health and education points (via Overpass)
Protected Planet — WDPA protected areas, a constraint layer

The OSM pull doubles as a coverage test: Arunachal is remote and mapping there
is thin, so the counts returned matter as much as the geometry.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zipfile

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point, Polygon

from common import AOI_BBOX, AOI_NAME, EXPOSURE, download, http_get, record

WORLDPOP_URL = ("https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/"
                "2020/BSGM/IND/ind_ppp_2020_constrained.tif")
WDPA_URL = "https://d1gam3xoknrgr2.cloudfront.net/current/WDPA_WDOECM_Jul2026_Public_IND_shp.zip"
OVERPASS = "https://overpass-api.de/api/interpreter"

W, S, E, N = AOI_BBOX
BBOX_OQL = f"{S},{W},{N},{E}"   # Overpass wants south,west,north,east

QUERIES = {
    "roads": f'way["highway"]({BBOX_OQL});',
    "buildings": f'way["building"]({BBOX_OQL});',
    "health": (f'node["amenity"~"^(hospital|clinic|doctors|pharmacy)$"]({BBOX_OQL});'
               f'way["amenity"~"^(hospital|clinic|doctors|pharmacy)$"]({BBOX_OQL});'),
    "education": (f'node["amenity"~"^(school|college|university)$"]({BBOX_OQL});'
                  f'way["amenity"~"^(school|college|university)$"]({BBOX_OQL});'),
}


def overpass_to_gdf(body: str, timeout_s: int = 900) -> gpd.GeoDataFrame | None:
    q = f"[out:json][timeout:{timeout_s}];({body});out geom tags;"
    try:
        data = http_get(OVERPASS, params={"data": q}, timeout=timeout_s + 60, retries=2).json()
    except Exception as exc:  # noqa: BLE001
        print(f"  [fail] overpass: {str(exc)[:140]}")
        return None

    rows = []
    for el in data.get("elements", []):
        tags = el.get("tags", {}) or {}
        if el["type"] == "node" and "lat" in el:
            geom = Point(el["lon"], el["lat"])
        elif el["type"] == "way" and el.get("geometry"):
            pts = [(p["lon"], p["lat"]) for p in el["geometry"]]
            if len(pts) < 2:
                continue
            geom = (Polygon(pts) if len(pts) >= 4 and pts[0] == pts[-1]
                    else LineString(pts))
        else:
            continue
        rows.append({"osm_id": el["id"], "osm_type": el["type"],
                     **{k: v for k, v in tags.items() if len(str(v)) < 200},
                     "geometry": geom})
    if not rows:
        return None
    return gpd.GeoDataFrame(pd.DataFrame(rows), geometry="geometry", crs="EPSG:4326")


def main() -> None:
    written = []

    # ---------------------------------------------------------------- WorldPop
    print("WorldPop — population 100 m (India, constrained 2020)")
    wp = download(WORLDPOP_URL, EXPOSURE / "worldpop_population_100m_india_2020.tif",
                  timeout=1800)
    written.append(wp)

    # ------------------------------------------------------------ OpenStreetMap
    print("OpenStreetMap — via Overpass")
    for name, body in QUERIES.items():
        gdf = overpass_to_gdf(body)
        if gdf is None or gdf.empty:
            print(f"  [warn] {name}: nothing returned")
            continue
        out = EXPOSURE / f"osm_{name}_vector_{AOI_NAME}.gpkg"
        gdf.to_file(out, driver="GPKG")
        written.append(out)
        print(f"  [ok]   {out.name} ({len(gdf)} features)")
        if name == "roads" and "highway" in gdf:
            top = gdf["highway"].value_counts().head(6)
            print("         " + ", ".join(f"{k}={v}" for k, v in top.items()))
            km = gdf.to_crs(6933).length.sum() / 1000
            print(f"         total mapped road length: {km:,.0f} km")

    # ----------------------------------------------------------- ProtectedPlanet
    print("Protected Planet — WDPA (India)")
    try:
        z = download(WDPA_URL, EXPOSURE / "wdpa_india.zip", timeout=600)
        written.append(z)
        ex = EXPOSURE / "wdpa_india"
        with zipfile.ZipFile(z) as zf:
            zf.extractall(ex)
        # WDPA ships nested zips of polygons/points
        for inner in list(ex.rglob("*.zip")):
            with zipfile.ZipFile(inner) as zf:
                zf.extractall(inner.with_suffix(""))
        shp = next((p for p in ex.rglob("*polygons.shp")), None) or next(ex.rglob("*.shp"), None)
        if shp:
            gdf = gpd.read_file(shp, bbox=AOI_BBOX)
            if not gdf.empty:
                out = EXPOSURE / f"wdpa_protected-areas_vector_{AOI_NAME}.gpkg"
                gdf.to_file(out, driver="GPKG")
                written.append(out)
                print(f"  [ok]   {out.name} ({len(gdf)} areas)")
            else:
                print("  [warn] no protected areas inside the AOI")
    except Exception as exc:  # noqa: BLE001
        print(f"  [fail] WDPA: {str(exc)[:140]}")

    record(
        EXPOSURE, source="WorldPop 2020 + OpenStreetMap + WDPA",
        url=f"{WORLDPOP_URL} ; {OVERPASS} ; {WDPA_URL}", files=written,
        license_="WorldPop CC-BY 4.0; OSM ODbL; WDPA non-commercial terms",
        notes="OSM counts are a coverage test as much as a data pull — thin mapping "
              "in Arunachal directly limits any impact/exposure product.",
    )


if __name__ == "__main__":
    main()
