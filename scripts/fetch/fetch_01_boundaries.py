"""Tier A — Administrative boundaries (GADM).

Downloads the India boundary package, extracts Arunachal Pradesh at state and
district level, and writes the AOI polygon every other script clips against.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geopandas as gpd

from common import AOI_NAME, BOUNDARIES, download, record

GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_IND.gpkg"
STATE = "Arunachal Pradesh"


def main() -> None:
    print("GADM — administrative boundaries")
    src = download(GADM_URL, BOUNDARIES / "gadm41_IND.gpkg")

    written = [src]
    for level, label in [(1, "state"), (2, "district")]:
        gdf = gpd.read_file(src, layer=f"ADM_ADM_{level}")
        sel = gdf[gdf["NAME_1"] == STATE].copy()
        if sel.empty:
            print(f"  [warn] no features at level {level} for {STATE}")
            continue
        out = BOUNDARIES / f"gadm_{label}-boundary_vector_{AOI_NAME}.gpkg"
        sel.to_file(out, driver="GPKG")
        print(f"  [ok]   {out.name}  ({len(sel)} features)")
        written.append(out)

        if level == 1:
            b = sel.total_bounds
            print(f"  [aoi]  true bbox: {b[0]:.4f}, {b[1]:.4f}, {b[2]:.4f}, {b[3]:.4f}")
            print(f"  [aoi]  area: {sel.to_crs(6933).area.sum() / 1e6:,.0f} km2")
        else:
            print(f"  [info] districts: {', '.join(sorted(sel['NAME_2'])[:5])} ...")

    record(
        BOUNDARIES,
        source="GADM 4.1",
        url=GADM_URL,
        files=written,
        license_="Free for academic/non-commercial use; attribution required",
        notes="State + district polygons for Arunachal Pradesh. Defines the AOI clip.",
    )


if __name__ == "__main__":
    main()
