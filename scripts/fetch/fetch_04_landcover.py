"""Tier A — Land cover (ESA WorldCover 10 m, v200 / 2021).

Tiles are 3x3 degrees, named by their south-west corner on a 3-degree grid.
Open S3 bucket, no account required.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import math

from common import AOI_BBOX, LANDCOVER, download, head_size, record

BASE = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
OUT = LANDCOVER / "esa_worldcover_10m_2021"


def tiles_for_bbox(bbox) -> list[str]:
    w, s, e, n = bbox
    lats = range(int(math.floor(s / 3) * 3), int(math.floor(n / 3) * 3) + 1, 3)
    lons = range(int(math.floor(w / 3) * 3), int(math.floor(e / 3) * 3) + 1, 3)
    return [f"N{la:02d}E{lo:03d}" for la in lats for lo in lons]


def main() -> None:
    print("ESA WorldCover 10 m (2021, v200) — land cover")
    tiles = tiles_for_bbox(AOI_BBOX)
    print(f"  AOI needs {len(tiles)} tiles: {', '.join(tiles)}")

    written, total = [], 0
    for t in tiles:
        name = f"ESA_WorldCover_10m_2021_v200_{t}_Map.tif"
        url = f"{BASE}/{name}"
        size = head_size(url, timeout=30)
        if not size:
            print(f"  [miss] {t} — no tile at this grid position")
            continue
        total += size
        written.append(download(url, OUT / name, timeout=900))

    print(f"  {len(written)} tiles, {total / 1e6:,.0f} MB")
    record(
        LANDCOVER, source="ESA WorldCover v200 (2021)", url=BASE, files=written,
        license_="CC-BY 4.0",
        notes="10 m global land cover, 11 classes. Class codes: 10 tree, 20 shrub, "
              "30 grass, 40 crop, 50 built, 60 bare, 70 snow/ice, 80 water, "
              "90 herbaceous wetland, 95 mangrove, 100 moss/lichen.",
    )


if __name__ == "__main__":
    main()
