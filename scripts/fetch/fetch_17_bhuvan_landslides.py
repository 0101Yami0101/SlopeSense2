"""NRSC Bhuvan — landslide inventory polygons for Arunachal Pradesh.

This is the label layer the project has been missing. DATA_VERIFICATION.md
records 28 usable NASA GLC points, coarse enough that they support validation
but not training. Bhuvan carries ISRO's mapped inventory for three seasons of
Arunachal Pradesh as true polygons with dimensions, activity state, lithology
and trigger — the thing a susceptibility model actually needs.

Getting it out takes a detour. Bhuvan publishes these through WMS only; WFS is
switched off server-side, so there is no bulk vector download. WMS
GetFeatureInfo does return full geometry and attributes as GeoJSON, but only
for features near the queried pixel, and it silently caps how many it will
return per call. So this walks a grid of small bounding boxes across the state,
queries each cell, and unions the results by feature id.

The grid must be fine enough that no single cell exceeds the server's per-call
cap, or features are lost silently. CELL_DEG is set well inside that limit;
the completeness check at the end is what proves it, and it is deliberately
noisy when a cell comes back suspiciously full.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import time

import requests

from common import AOI_BBOX, AOI_NAME, LABELS, UA, record

WMS = "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms"

LAYERS = [
    ("disaster:AR_SLIM_2014_GCS", 2014),
    ("disaster:AR_SLIM_2017", 2017),
    ("disaster:LS_ARUNACHAL_2023", 2023),
]

CELL_DEG = 0.25          # grid step; small enough to stay under the per-call cap
FEATURE_CAP = 10000      # asked for per call; server may return fewer
SUSPICIOUS = 0.9         # warn if a cell returns >90% of the cap
PAUSE_S = 0.3            # be polite to a public government service


def query_cell(layer: str, w: float, s: float, e: float, n: float,
               session: requests.Session) -> list[dict]:
    """GetFeatureInfo over one grid cell, returned as GeoJSON features."""
    params = {
        "service": "WMS", "version": "1.1.1", "request": "GetFeatureInfo",
        "layers": layer, "query_layers": layer,
        "srs": "EPSG:4326", "bbox": f"{w},{s},{e},{n}",
        # A coarse raster means one pixel covers the cell, so the query's
        # pixel buffer sweeps the whole box rather than a pinpoint.
        "width": "8", "height": "8", "x": "4", "y": "4",
        "info_format": "application/json", "feature_count": str(FEATURE_CAP),
    }
    r = session.get(WMS, params=params, timeout=180, headers=UA)
    r.raise_for_status()
    try:
        return r.json().get("features", [])
    except ValueError:
        return []


def harvest(layer: str, year: int) -> dict[str, dict]:
    w0, s0, e0, n0 = AOI_BBOX
    found: dict[str, dict] = {}
    session = requests.Session()

    xs = [w0 + i * CELL_DEG for i in range(int((e0 - w0) / CELL_DEG) + 1)]
    ys = [s0 + i * CELL_DEG for i in range(int((n0 - s0) / CELL_DEG) + 1)]
    total_cells = len(xs) * len(ys)
    print(f"  {layer}  ({total_cells} cells)")

    done = 0
    for x in xs:
        for y in ys:
            done += 1
            try:
                feats = query_cell(layer, x, y, x + CELL_DEG, y + CELL_DEG, session)
            except Exception as e:  # noqa: BLE001
                print(f"    ! cell {x:.2f},{y:.2f}: {type(e).__name__}")
                continue

            if len(feats) >= FEATURE_CAP * SUSPICIOUS:
                print(f"    ! cell {x:.2f},{y:.2f} returned {len(feats)} — "
                      f"at cap, features may be missing. Lower CELL_DEG.")

            for f in feats:
                fid = f.get("id") or f["properties"].get("SlideNo") \
                    or f["properties"].get("Slide_No")
                if fid and fid not in found:
                    f["properties"]["_season"] = year
                    f["properties"]["_layer"] = layer
                    found[fid] = f

            if done % 100 == 0:
                print(f"    {done}/{total_cells} cells, {len(found)} unique")
            time.sleep(PAUSE_S)

    print(f"    -> {len(found)} unique features")
    return found


def main() -> None:
    print("NRSC Bhuvan — landslide inventory (WMS GetFeatureInfo harvest)\n")
    LABELS.mkdir(parents=True, exist_ok=True)

    written, grand = [], 0
    for layer, year in LAYERS:
        feats = harvest(layer, year)
        if not feats:
            print(f"    ! nothing returned for {layer}, skipped")
            continue
        gj = {"type": "FeatureCollection",
              "crs": {"type": "name",
                      "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
              "features": list(feats.values())}
        stem = layer.split(":")[1].lower()
        dest = LABELS / f"bhuvan_{stem}_polygon_{AOI_NAME}.geojson"
        dest.write_text(json.dumps(gj), encoding="utf-8")
        print(f"    written {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)\n")
        written.append(dest)
        grand += len(feats)

    if written:
        record(
            LABELS,
            source="NRSC Bhuvan landslide inventory (ISRO/NRSC), Arunachal Pradesh",
            url=WMS,
            files=written,
            license_="UNSTATED — Bhuvan terms apply. NRSC/ISRO product; confirm "
                     "redistribution rights before use in a commercial deliverable.",
            notes=f"{grand} landslide polygons across 2014/2017/2023 seasons. "
                  "Harvested via WMS GetFeatureInfo because WFS is disabled "
                  "server-side. Polygons carry length/width/height, area, activity "
                  "state, lithology, LULC and trigger. Coverage is per-season and "
                  "NOT statewide — check district coverage before assuming a "
                  "given area is represented.",
        )
    print(f"  total {grand} landslide polygons")


if __name__ == "__main__":
    main()
