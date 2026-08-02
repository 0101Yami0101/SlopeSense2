"""Tier A — Elevation (Copernicus DEM GLO-30).

Downloads the 1-degree tiles covering the AOI from the open AWS mirror.
No account required. Slope, aspect and curvature are derived from this later —
they are not separate downloads.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import AOI_LAT_TILES, AOI_LON_TILES, TERRAIN, download, head_size, record

BASE = "https://copernicus-dem-30m.s3.amazonaws.com"
OUT = TERRAIN / "copernicus_dem_30m"


def tile_name(lat: int, lon: int) -> str:
    return f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM"


def main() -> None:
    print("Copernicus DEM GLO-30 — elevation")
    tiles = [(la, lo) for la in AOI_LAT_TILES for lo in AOI_LON_TILES]

    print(f"  checking {len(tiles)} tiles ...")
    available, missing, total = [], [], 0
    for la, lo in tiles:
        name = tile_name(la, lo)
        url = f"{BASE}/{name}/{name}.tif"
        size = head_size(url, timeout=30)
        if size:
            available.append((name, url, size))
            total += size
        else:
            missing.append(name)

    print(f"  available: {len(available)} tiles, {total / 1e6:,.0f} MB")
    if missing:
        print(f"  missing:   {len(missing)} tiles (ocean or no-data)")
        for m in missing:
            print(f"             {m}")

    written = []
    for name, url, _ in available:
        written.append(download(url, OUT / f"{name}.tif"))

    record(
        TERRAIN,
        source="Copernicus DEM GLO-30",
        url=BASE,
        files=written,
        license_="Free, worldwide, non-exclusive (ESA/Copernicus). Attribution required.",
        notes=f"{len(written)} one-degree COG tiles covering the AOI. 30 m posting, EGM2008 vertical datum.",
    )


if __name__ == "__main__":
    main()
