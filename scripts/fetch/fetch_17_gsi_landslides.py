"""GSI National Landslide Susceptibility Mapping inventory — the real labels.

DATA_VERIFICATION.md called the GSI inventory "the single highest-value Level 2
ask" because NASA GLC left only 28 events located precisely enough to train on,
and stopped in 2018. That ask is now answered without a data request: the
National Landslide Forecasting Centre (bhusanket.gsi.gov.in) serves the national
inventory from an ArcGIS FeatureServer holding 31,551 landslides, of which 1,322
fall inside the AOI.

Access note: the FeatureServer itself answers "Token Required", but the portal's
own proxy (DotNet/proxy.ashx) forwards queries unauthenticated — it is what the
public web map uses to draw the layer. We go through the same path the site does.
If that proxy is ever closed, this script breaks and the inventory reverts to a
formal request to GSI; it is not a private endpoint, but it is not a documented
API either, so treat availability as unguaranteed.

Known limitation, and it matters: 'date' is null on 1,309 of 1,322 records. This
is a spatial inventory, not an event catalogue. It answers WHERE well and WHEN
almost not at all, so it can train and validate susceptibility but cannot by
itself support rainfall-threshold or forecasting work.

Licence: GSI reports carry "Not to be published in part or full without prior
permission of the Director General, GSI". Confirm redistribution terms before
anything derived from this ships to the client.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import urllib.parse

from common import AOI_BBOX, AOI_NAME, LABELS, http_get, record

BASE = "https://bhusanket.gsi.gov.in/gisserver/rest/services"
PROXY = "https://bhusanket.gsi.gov.in/DotNet/proxy.ashx"
LAYER = f"{BASE}/Hosted/India_All_Landslided/FeatureServer/0/query"
POLY_LAYER = f"{BASE}/GSI/Landslide_Polygon/FeatureServer/0/query"
PAGE = 1000
POLY_PAGE = 2000  # the polygon service's own maxRecordCount


def query(params: dict, layer: str = LAYER) -> dict:
    """Issue an ArcGIS query through the portal's proxy, as the site's map does."""
    return http_get(f"{PROXY}?{layer}?{urllib.parse.urlencode(params)}",
                    timeout=300).json()


def paged(layer: str, page: int, expected: int | None = None) -> list[dict]:
    """Walk a FeatureServer's pagination.

    The polygon service silently truncates a page below the requested size when
    the GeoJSON payload gets large, so a short page does NOT mean the end of the
    data. Only an empty page — or reaching the server's own count — ends the walk.
    """
    w, s, e, n = AOI_BBOX
    feats: list[dict] = []
    while True:
        g = query({"where": "1=1", "geometry": f"{w},{s},{e},{n}",
                   "geometryType": "esriGeometryEnvelope", "inSR": "4326",
                   "outSR": "4326", "spatialRel": "esriSpatialRelIntersects",
                   "outFields": "*", "returnGeometry": "true", "f": "geojson",
                   "resultOffset": str(len(feats)),
                   "resultRecordCount": str(page)}, layer=layer)
        rows = g.get("features", [])
        if not rows:
            break
        feats.extend(rows)
        print(f"    fetched {len(feats)}" + (f"/{expected}" if expected else ""))
        if expected is not None and len(feats) >= expected:
            break

    # Offset paging over a service that truncates pages re-serves some rows at
    # the seams, so the raw walk carries ~200 duplicates. Key on OBJECTID.
    seen: set = set()
    unique = []
    for f in feats:
        oid = f["properties"].get("OBJECTID")
        if oid in seen:
            continue
        seen.add(oid)
        unique.append(f)
    if len(unique) != len(feats):
        print(f"    deduplicated {len(feats)} -> {len(unique)} on OBJECTID")
    return unique


def fetch_polygons() -> None:
    """Mapped landslide extents — the training labels proper, not just centroids."""
    w, s, e, n = AOI_BBOX
    total = query({"where": "1=1", "geometry": f"{w},{s},{e},{n}",
                   "geometryType": "esriGeometryEnvelope", "inSR": "4326",
                   "spatialRel": "esriSpatialRelIntersects",
                   "returnCountOnly": "true", "f": "json"},
                  layer=POLY_LAYER).get("count")
    print(f"\n  landslide polygons intersecting AOI: {total}")

    feats = paged(POLY_LAYER, POLY_PAGE, expected=total)
    if not feats:
        print("  ! no polygons returned")
        return

    dest = LABELS / f"gsi-nlfc_landslides_polygon_{AOI_NAME}.geojson"
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": feats}),
                    encoding="utf-8")
    print(f"  -> {dest.name}  ({dest.stat().st_size / 1e6:.1f} MB, {len(feats)} features)")

    record(
        LABELS,
        source="GSI National Landslide Forecasting Centre — mapped landslide polygons",
        url=POLY_LAYER,
        files=[dest],
        license_="RESTRICTED — GSI asserts 'not to be published in part or full without "
                 "prior permission of the Director General, GSI'. Confirm before shipping.",
        notes=f"{len(feats)} mapped landslide extents in AOI, DATA_TYPE='Mapped as polygon'. "
              f"Attributes: material, movement class, LULC, geomorphology, district, toposheet. "
              f"True failure geometry — supersedes point centroids for training. No dates.",
    )


def main() -> None:
    print("GSI / NLFC national landslide inventory\n")
    w, s, e, n = AOI_BBOX

    total = query({"where": "1=1", "geometry": f"{w},{s},{e},{n}",
                   "geometryType": "esriGeometryEnvelope", "inSR": "4326",
                   "spatialRel": "esriSpatialRelIntersects",
                   "returnCountOnly": "true", "f": "json"}).get("count")
    print(f"  {total} landslides intersect the AOI")

    feats: list[dict] = []
    while True:
        g = query({"where": "1=1", "geometry": f"{w},{s},{e},{n}",
                   "geometryType": "esriGeometryEnvelope", "inSR": "4326",
                   "outSR": "4326", "spatialRel": "esriSpatialRelIntersects",
                   "outFields": "*", "returnGeometry": "true", "f": "geojson",
                   "resultOffset": str(len(feats)),
                   "resultRecordCount": str(PAGE)})
        page = g.get("features", [])
        if not page:
            break
        feats.extend(page)
        print(f"    fetched {len(feats)}/{total}")
        if len(page) < PAGE:
            break

    if not feats:
        print("  ! nothing returned — proxy may have been closed")
        return

    LABELS.mkdir(parents=True, exist_ok=True)
    dest = LABELS / f"gsi-nlfc_landslides_point_{AOI_NAME}.geojson"
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": feats}),
                    encoding="utf-8")
    print(f"\n  -> {dest.name}  ({dest.stat().st_size / 1e6:.1f} MB, {len(feats)} features)")

    dated = sum(1 for f in feats if (f["properties"].get("date") or "").strip())
    print(f"  records carrying a usable date: {dated}/{len(feats)}")

    record(
        LABELS,
        source="GSI National Landslide Forecasting Centre — national landslide inventory",
        url=LAYER,
        files=[dest],
        license_="RESTRICTED — GSI asserts 'not to be published in part or full without "
                 "prior permission of the Director General, GSI'. Confirm before shipping.",
        notes=f"{len(feats)} landslides in AOI (31,551 nationally). Full attribute schema: "
              f"district, material, movement type, trigger, runout, casualties. "
              f"Only {dated} carry a date — spatial inventory, not an event catalogue. "
              f"Retrieved via the portal's own proxy.ashx; undocumented, availability unguaranteed.",
    )

    fetch_polygons()


if __name__ == "__main__":
    main()
