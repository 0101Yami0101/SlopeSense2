"""Turn the fetched data into answers, not just file listings.

Four questions the raw files can now settle:

  1. FLOOD REACH  — what fraction of Arunachal's stream network is large
                    enough for a large-river forecast to cover?
  2. TERRAIN      — how steep is the state, and does the DEM cover it fully?
  3. LAND COVER   — what is the surface actually made of?
  4. LABELS       — how many usable landslide records exist per unit area?

Writes logs/key_findings.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings
from datetime import datetime, timezone

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling

from common import (AOI_NAME, BOUNDARIES, HYDROLOGY, LABELS, LANDCOVER, LOGS,
                    ROOT, TERRAIN)

warnings.filterwarnings("ignore")
lines: list[str] = []


def out(s: str = "") -> None:
    print(s)
    lines.append(s)


WORLDCOVER_CLASSES = {
    10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
    50: "Built-up", 60: "Bare / sparse", 70: "Snow and ice", 80: "Water",
    90: "Herbaceous wetland", 95: "Mangrove", 100: "Moss and lichen",
}


def q1_flood_reach() -> None:
    out("\n## 1. Flood reach — how much of the network can a large-river forecast see?\n")
    f = HYDROLOGY / f"hydrosheds_rivers_vector_{AOI_NAME}.gpkg"
    if not f.exists():
        out("_rivers file missing_")
        return
    g = gpd.read_file(f)
    if "UPLAND_SKM" not in g:
        out("_UPLAND_SKM attribute absent_")
        return

    total = len(g)
    length_km = g.to_crs(6933).length.sum() / 1000
    out(f"Total reaches in AOI: **{total:,}**, combined length **{length_km:,.0f} km**\n")
    out("| upstream drainage area | reaches | % of network | length (km) |")
    out("|---|---:|---:|---:|")
    gm = g.to_crs(6933)
    for thr in (0, 10, 100, 500, 1000, 5000, 10000, 50000):
        sel = g["UPLAND_SKM"] > thr
        km = gm[sel.values].length.sum() / 1000
        out(f"| > {thr:,} km² | {int(sel.sum()):,} | {100 * sel.mean():.1f}% | {km:,.0f} |")

    big = int((g["UPLAND_SKM"] > 5000).sum())
    out(f"\n**Reading:** operational large-river forecasting typically needs a drainage "
        f"area in the thousands of km². At a 5,000 km² threshold only **{big:,} of "
        f"{total:,} reaches ({100 * big / total:.1f}%)** qualify — everything else is "
        f"the small-stream network that a consume-only flood product cannot reach.")


def q2_terrain() -> None:
    out("\n## 2. Terrain — coverage and steepness\n")
    tiles = sorted((TERRAIN / "copernicus_dem_30m").glob("*.tif"))
    if not tiles:
        out("_no DEM tiles_")
        return
    out(f"DEM tiles: **{len(tiles)}**, "
        f"{sum(t.stat().st_size for t in tiles) / 1e9:.2f} GB\n")

    elev_min, elev_max, nod, npx = 1e9, -1e9, 0, 0
    slopes = []
    for t in tiles:
        with rasterio.open(t) as ds:
            # decimated read: ~10x coarser, enough for distribution stats
            a = ds.read(1, out_shape=(1, ds.height // 10, ds.width // 10),
                        resampling=Resampling.average).astype("float32")
            if ds.nodata is not None:
                nod += int(np.sum(a == ds.nodata))
                a[a == ds.nodata] = np.nan
            npx += a.size
            if np.isfinite(a).any():
                elev_min = min(elev_min, float(np.nanmin(a)))
                elev_max = max(elev_max, float(np.nanmax(a)))
                px_m = abs(ds.transform.a) * 111320 * 10
                gy, gx = np.gradient(a, px_m)
                slopes.append(np.degrees(np.arctan(np.hypot(gx, gy))).ravel())

    out(f"- Elevation range: **{elev_min:,.0f} m to {elev_max:,.0f} m**")
    out(f"- No-data pixels: **{100 * nod / npx:.3f}%** — DEM coverage is effectively complete")
    if slopes:
        s = np.concatenate(slopes)
        s = s[np.isfinite(s)]
        out(f"- Slope (computed at ~300 m sampling, so these understate true steepness):")
        for p in (50, 75, 90, 99):
            out(f"    - {p}th percentile: **{np.percentile(s, p):.1f}°**")
        for thr in (15, 25, 35):
            out(f"    - terrain steeper than {thr}°: **{100 * np.mean(s > thr):.1f}%**")


def q3_landcover() -> None:
    out("\n## 3. Land cover — what the surface is made of\n")
    tiles = sorted((LANDCOVER / "esa_worldcover_10m_2021").glob("*.tif"))
    if not tiles:
        out("_no land-cover tiles_")
        return
    counts: dict[int, int] = {}
    for t in tiles:
        with rasterio.open(t) as ds:
            a = ds.read(1, out_shape=(1, ds.height // 20, ds.width // 20),
                        resampling=Resampling.nearest)
        u, c = np.unique(a, return_counts=True)
        for k, v in zip(u.tolist(), c.tolist()):
            counts[k] = counts.get(k, 0) + v
    total = sum(v for k, v in counts.items() if k != 0)
    out("_(tiles extend beyond the state border, so shares are indicative)_\n")
    out("| class | share |")
    out("|---|---:|")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        if k == 0 or v / total < 0.001:
            continue
        out(f"| {WORLDCOVER_CLASSES.get(k, f'code {k}')} | {100 * v / total:.1f}% |")


def q4_labels() -> None:
    out("\n## 4. Labels — how much ground truth actually exists\n")
    f = LABELS / f"nasa-glc_landslides_point_{AOI_NAME}.geojson"
    if not f.exists():
        out("_no label file_")
        return
    g = gpd.read_file(f)
    state = BOUNDARIES / f"gadm_state-boundary_vector_{AOI_NAME}.gpkg"
    area = 81995.0
    if state.exists():
        area = float(gpd.read_file(state).to_crs(6933).area.sum() / 1e6)

    inside = g
    if state.exists():
        poly = gpd.read_file(state).union_all()
        inside = g[g.within(poly)]

    out(f"- Events returned for the AOI bbox: **{len(g)}**")
    out(f"- Events inside the state polygon: **{len(inside)}**")
    out(f"- State area: **{area:,.0f} km²**")
    out(f"- Density: **1 event per {area / max(len(inside), 1):,.0f} km²**\n")

    if "loc_accu" in g:
        out("| location accuracy | events |")
        out("|---|---:|")
        for k, v in g["loc_accu"].fillna("(null)").value_counts().items():
            out(f"| {k} | {v} |")
        precise = int(g["loc_accu"].isin(["exact", "1km"]).sum())
        out(f"\n**Usable for slope-scale training (exact or 1 km): {precise} events.** "
            f"Everything coarser can validate a regional pattern but cannot teach a "
            f"model which slope failed.")


def main() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    out("# Key Findings — what the Tier A data actually supports")
    out(f"\nGenerated {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    q1_flood_reach()
    q2_terrain()
    q3_landcover()
    q4_labels()

    dest = LOGS / "key_findings.md"
    dest.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwritten -> {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
