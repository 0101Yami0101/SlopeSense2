"""Exposure reality check — how much is actually mapped, and who lives there.

OSM feature counts in a remote state are a data-quality finding in their own
right: a thin road or building layer caps what any impact product can claim.
WorldPop is clipped to the state before summing, since the source raster
covers all of India.
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
from rasterio.mask import mask

from common import AOI_NAME, BOUNDARIES, EXPOSURE, LOGS, ROOT

warnings.filterwarnings("ignore")
lines: list[str] = []


def out(s: str = "") -> None:
    print(s)
    lines.append(s)


def state_polygon():
    f = BOUNDARIES / f"gadm_state-boundary_vector_{AOI_NAME}.gpkg"
    return gpd.read_file(f) if f.exists() else None


def main() -> None:
    out("# Exposure — what is mapped and who is exposed")
    out(f"\nGenerated {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    state = state_polygon()
    area_km2 = float(state.to_crs(6933).area.sum() / 1e6) if state is not None else 81995.0

    # ------------------------------------------------------------------ OSM
    out("\n## OpenStreetMap coverage\n")
    out("_Fetched on the AOI bounding box, which overlaps densely-mapped Assam._")
    out("_Counts are therefore reported both as fetched and clipped to the state._\n")
    poly = state.union_all() if state is not None else None
    out("| layer | in bbox | inside state | note |")
    out("|---|---:|---:|---|")
    for layer in ("roads", "buildings", "health", "education"):
        f = EXPOSURE / f"osm_{layer}_vector_{AOI_NAME}.gpkg"
        if not f.exists():
            out(f"| {layer} | – | – | file missing |")
            continue
        g = gpd.read_file(f)
        n_bbox = len(g)
        g_in = g[g.intersects(poly)] if poly is not None else g
        # persist the corrected, state-clipped layer for downstream use
        if poly is not None and not g_in.empty:
            g_in.to_file(EXPOSURE / f"osm_{layer}_vector_{AOI_NAME}-clipped.gpkg",
                         driver="GPKG")
        if layer == "roads":
            km = g_in.to_crs(6933).length.sum() / 1000
            note = f"{km:,.0f} km · {km / area_km2 * 100:.1f} km per 100 km²"
        elif layer == "buildings":
            note = f"1 per {area_km2 / max(len(g_in), 1):.2f} km²"
        else:
            note = f"1 per {area_km2 / max(len(g_in), 1):,.0f} km²"
        out(f"| {layer} | {n_bbox:,} | {len(g_in):,} | {note} |")

    f = EXPOSURE / f"osm_roads_vector_{AOI_NAME}-clipped.gpkg"
    if f.exists():
        g = gpd.read_file(f)
        if "highway" in g:
            out(f"\n**Road classes inside the state:** " + ", ".join(
                f"{k} ({v:,})" for k, v in g["highway"].value_counts().head(8).items()))

    # ------------------------------------------------------------- WorldPop
    out("\n## Population (WorldPop 2020, clipped to the state)\n")
    wp = EXPOSURE / "worldpop_population_100m_india_2020.tif"
    if wp.exists() and state is not None:
        with rasterio.open(wp) as ds:
            geoms = [g.__geo_interface__ for g in state.to_crs(ds.crs).geometry]
            arr, _ = mask(ds, geoms, crop=True, nodata=np.nan, filled=True)
            a = arr[0].astype("float64")
            valid = a[np.isfinite(a)]
            total = float(np.nansum(valid))
            out(f"- Total population in state: **{total:,.0f}**")
            out(f"- Populated cells: **{int((valid > 0).sum()):,}** "
                f"of {valid.size:,} inside the boundary "
                f"({100 * (valid > 0).mean():.1f}%)")
            out(f"- Mean density where populated: "
                f"**{float(valid[valid > 0].mean()):.1f} people per 100 m cell**")
            out(f"- Max cell: **{float(valid.max()):,.0f} people**")
            out(f"\n_Census 2011 recorded ~1.38 million for Arunachal Pradesh — "
                f"compare against that as a sanity check._")
    else:
        out("_WorldPop raster or state boundary missing_")

    # ----------------------------------------------------------------- WDPA
    # WDPA ships as three split shapefiles; reading only the first one silently
    # drops most protected areas, so every polygon part is read and combined.
    out("\n## Protected areas (WDPA)\n")
    parts = sorted((EXPOSURE / "wdpa_india").rglob("*polygons.shp"))
    if parts:
        frames = []
        for p in parts:
            try:
                frames.append(gpd.read_file(p, bbox=tuple(state.total_bounds)))
            except Exception as exc:  # noqa: BLE001
                out(f"- _could not read {p.name}: {type(exc).__name__}_")
        if frames:
            import pandas as pd
            g = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True),
                                 crs=frames[0].crs)
            g = g[g.intersects(poly)] if poly is not None else g
            out(f"- Shapefile parts read: **{len(parts)}**")
            allpa = gpd.GeoDataFrame(pd.concat(
                [gpd.read_file(p) for p in parts], ignore_index=True), crs=frames[0].crs)
            out(f"- Total protected areas in the India download: **{len(allpa)}**")
            if "DESIG_ENG" in allpa:
                out("- Designations present: " + ", ".join(
                    f"{k} ({v})" for k, v in allpa["DESIG_ENG"].value_counts().items()))
            if g.empty:
                out("\n- **No protected areas fall inside Arunachal Pradesh.**")
                out("- Diagnosis: the public WDPA release for India carries only "
                    "*internationally* designated sites (Ramsar, World Heritage, "
                    "UNESCO-MAB). National parks and wildlife sanctuaries are not "
                    "published, so Namdapha, Pakke, Mouling and Mehao are absent. "
                    "This is a limitation of the source, not of the fetch — a "
                    "protected-area constraint layer must come from the State Forest "
                    "Department instead.")
            else:
                g = g.drop_duplicates(subset=[c for c in ("WDPAID",) if c in g])
                clipped = g.clip(poly) if poly is not None else g
                pa_km2 = clipped.to_crs(6933).area.sum() / 1e6
                out(f"- Protected areas inside the state: **{len(g)}**")
                out(f"- Combined area within the state: **{pa_km2:,.0f} km²** "
                    f"({100 * pa_km2 / area_km2:.1f}% of state area)")
                if "NAME" in g:
                    big = g.assign(a=g.to_crs(6933).area).nlargest(5, "a")
                    out("- Largest: " + ", ".join(
                        f"{r.NAME} ({r.a / 1e6:,.0f} km²)" for r in big.itertuples()))
                out_f = EXPOSURE / f"wdpa_protected-areas_vector_{AOI_NAME}.gpkg"
                g.to_file(out_f, driver="GPKG")
                out(f"- Corrected layer written: `{out_f.name}`")
    else:
        out("_no WDPA polygon shapefiles found_")

    dest = LOGS / "exposure_findings.md"
    dest.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwritten -> {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
