"""Tier A — Soil properties (SoilGrids 250 m, ISRIC).

Pulls the soil properties that matter for slope stability, at three depths,
clipped to the AOI via the open WCS endpoint. No account required.

Soil depth / permeability / infiltration are not separate products — they are
estimated from texture, bulk density and coarse-fragment content fetched here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from common import AOI_BBOX, AOI_NAME, SOIL_GEOLOGY, UA, record

WCS = "https://maps.isric.org/mapserv"
OUT = SOIL_GEOLOGY / "soilgrids_250m"

# property -> what it tells us about slope stability
PROPERTIES = {
    "clay": "clay % — cohesion, swelling, low permeability",
    "sand": "sand % — friction angle, drainage",
    "silt": "silt % — collapse-prone fraction",
    "bdod": "bulk density — compaction / mass",
    "cfvo": "coarse fragments % — proxy for regolith competence",
    "soc":  "organic carbon — topsoil strength / rooting",
}
DEPTHS = ["0-5cm", "15-30cm", "60-100cm"]


def fetch(prop: str, depth: str, dest: Path) -> Path | None:
    if dest.exists():
        print(f"  [skip] {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest
    w, s, e, n = AOI_BBOX
    params = {
        "map": f"/map/{prop}.map",
        "SERVICE": "WCS", "VERSION": "2.0.1", "REQUEST": "GetCoverage",
        "COVERAGEID": f"{prop}_{depth}_mean",
        "FORMAT": "GEOTIFF_INT16",
        "SUBSET": [f"X({w},{e})", f"Y({s},{n})"],
        "SUBSETTINGCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
        "OUTPUTCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
    }
    try:
        r = requests.get(WCS, params=params, timeout=600, headers=UA)
        r.raise_for_status()
        if "tiff" not in r.headers.get("Content-Type", ""):
            print(f"  [fail] {dest.name}: server returned {r.headers.get('Content-Type')}")
            print(f"         {r.text[:200]}")
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        print(f"  [ok]   {dest.name} ({len(r.content) / 1e6:.1f} MB)")
        return dest
    except Exception as exc:  # noqa: BLE001
        print(f"  [fail] {dest.name}: {exc}")
        return None


def main() -> None:
    print("SoilGrids 250 m — soil properties")
    written = []
    for prop, why in PROPERTIES.items():
        print(f"  {prop}: {why}")
        for depth in DEPTHS:
            name = f"soilgrids_{prop}-{depth}_250m_{AOI_NAME}.tif"
            got = fetch(prop, depth, OUT / name)
            if got:
                written.append(got)

    print(f"\n  {len(written)}/{len(PROPERTIES) * len(DEPTHS)} rasters retrieved")
    record(
        SOIL_GEOLOGY,
        source="SoilGrids 2.0 (ISRIC)",
        url=WCS,
        files=written,
        license_="CC-BY 4.0",
        notes=("250 m soil properties, mean prediction, depths "
               + ", ".join(DEPTHS)
               + ". Values are scaled integers — see ISRIC conversion factors "
                 "(clay/sand/silt g/kg ÷10 = %, bdod cg/cm3 ÷100, soc dg/kg ÷10)."),
    )


if __name__ == "__main__":
    main()
