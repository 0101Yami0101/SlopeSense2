"""Tier A — River network and catchments (HydroSHEDS).

HydroRIVERS  — river reach network with drainage area attributes
HydroBASINS  — nested catchment polygons, levels 1-12

Both are distributed as continent-wide archives; this downloads the Asia
files, then clips to the AOI so downstream work has a small local copy.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zipfile

import geopandas as gpd

from common import AOI_BBOX, AOI_NAME, HYDROLOGY, download, record

RIVERS_URL = "https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_as_shp.zip"
BASINS_URL = "https://data.hydrosheds.org/file/hydrobasins/standard/hybas_as_lev01-12_v1c.zip"
OUT = HYDROLOGY / "hydrosheds"


def unzip(archive: Path, into: Path) -> Path:
    into.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        z.extractall(into)
    return into


def clip_shp(shp: Path, out: Path, label: str) -> Path | None:
    try:
        gdf = gpd.read_file(shp, bbox=AOI_BBOX)
    except Exception as exc:  # noqa: BLE001
        print(f"  [fail] {label}: {exc}")
        return None
    if gdf.empty:
        print(f"  [warn] {label}: nothing inside the AOI")
        return None
    gdf.to_file(out, driver="GPKG")
    print(f"  [ok]   {out.name} ({len(gdf)} features)")
    return out


def main() -> None:
    print("HydroSHEDS — rivers and catchments")
    written = []

    print("  HydroRIVERS (Asia):")
    riv_zip = download(RIVERS_URL, OUT / "HydroRIVERS_v10_as_shp.zip", timeout=900)
    written.append(riv_zip)
    riv_dir = unzip(riv_zip, OUT / "HydroRIVERS_v10_as")
    shp = next(riv_dir.rglob("HydroRIVERS_v10_as.shp"), None)
    if shp:
        out = clip_shp(shp, HYDROLOGY / f"hydrosheds_rivers_vector_{AOI_NAME}.gpkg", "rivers")
        if out:
            written.append(out)
            g = gpd.read_file(out)
            if "UPLAND_SKM" in g:
                for thr in (10, 100, 1000, 10000):
                    print(f"         reaches with upstream area >{thr:>6} km2: "
                          f"{int((g['UPLAND_SKM'] > thr).sum())}")

    print("  HydroBASINS (Asia, levels 1-12):")
    bas_zip = download(BASINS_URL, OUT / "hybas_as_lev01-12_v1c.zip", timeout=1800)
    written.append(bas_zip)
    bas_dir = unzip(bas_zip, OUT / "hybas_as_lev01-12_v1c")
    for lev in ("08", "12"):
        shp = next(bas_dir.rglob(f"hybas_as_lev{lev}_v1c.shp"), None)
        if not shp:
            print(f"  [warn] level {lev} shapefile not found in archive")
            continue
        out = clip_shp(shp, HYDROLOGY / f"hydrosheds_basins-lev{lev}_vector_{AOI_NAME}.gpkg",
                       f"basins L{lev}")
        if out:
            written.append(out)

    record(
        HYDROLOGY, source="HydroSHEDS v1 (HydroRIVERS v10, HydroBASINS v1c)",
        url=f"{RIVERS_URL} ; {BASINS_URL}", files=written,
        license_="Free for non-commercial and commercial use with attribution (WWF)",
        notes="15 arc-second base. Rivers carry UPLAND_SKM (upstream drainage area) — "
              "the field that determines which streams a large-river forecast can reach. "
              "Basin levels 8 and 12 clipped for catchment-scale work.",
    )


if __name__ == "__main__":
    main()
