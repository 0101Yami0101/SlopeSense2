"""Tier A — Geology coverage test (Macrostrat) and context layers.

There is no clean, open, bulk-downloadable geological map for this region.
The Appendix lists CGMW / OpenGeology, but neither offers a programmatic
download. Macrostrat is the one open API that returns lithology and age for
a coordinate, so this script grid-samples it to answer a single question:

    is any usable free geology available over Arunachal Pradesh, or does
    geology have to come from GSI (Level 2)?

The output is a coverage verdict, not a production layer.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import time
from collections import Counter

import numpy as np

from common import AOI_BBOX, AOI_NAME, CONTEXT, http_get, record

MACROSTRAT = "https://macrostrat.org/api/v2/geologic_units/map"
STEP_DEG = 0.5


def main() -> None:
    print("Macrostrat — free geology coverage test")
    w, s, e, n = AOI_BBOX
    lons = np.arange(w, e + 1e-9, STEP_DEG)
    lats = np.arange(s, n + 1e-9, STEP_DEG)
    pts = [(round(float(la), 3), round(float(lo), 3)) for la in lats for lo in lons]
    print(f"  sampling {len(pts)} points at {STEP_DEG} deg spacing ...")

    results, hits = [], 0
    liths, ages = Counter(), Counter()
    for i, (la, lo) in enumerate(pts, 1):
        try:
            d = http_get(MACROSTRAT, params={"lat": la, "lng": lo},
                         timeout=45, retries=2).json()
            recs = d.get("success", {}).get("data", [])
        except Exception:  # noqa: BLE001
            recs = []
        if recs:
            hits += 1
            r0 = recs[0]
            liths[(r0.get("lith") or "?")[:60]] += 1
            ages[r0.get("b_age_name") or r0.get("age") or "?"] += 1
            results.append({"lat": la, "lng": lo, "name": r0.get("name"),
                            "lith": r0.get("lith"), "age": r0.get("age"),
                            "source_id": r0.get("source_id")})
        else:
            results.append({"lat": la, "lng": lo, "name": None})
        if i % 25 == 0:
            print(f"    {i}/{len(pts)} sampled, {hits} with data")
        time.sleep(0.15)

    out = CONTEXT / f"macrostrat_geology-coverage-test_point_{AOI_NAME}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))

    pct = 100 * hits / len(pts)
    print(f"\n  coverage: {hits}/{len(pts)} points returned a unit ({pct:.0f}%)")
    if liths:
        print("  most common lithologies:")
        for k, v in liths.most_common(5):
            print(f"    {v:3}x  {k}")
    verdict = ("USABLE — broad lithology available" if pct > 70 else
               "PARTIAL — patchy coverage" if pct > 25 else
               "NOT USABLE — geology must come from GSI at Level 2")
    print(f"  verdict: {verdict}")

    record(
        CONTEXT, source="Macrostrat geologic_units/map API", url=MACROSTRAT,
        files=[out],
        license_="CC-BY 4.0 (Macrostrat)",
        notes=f"Coverage test only, {STEP_DEG} deg grid, {pct:.0f}% of points returned "
              f"a unit. Verdict: {verdict}. Not a production geology layer.",
    )


if __name__ == "__main__":
    main()
