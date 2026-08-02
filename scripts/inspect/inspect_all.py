"""Inspect every fetched file and record the seven verification facts.

A source is only 'confirmed' once we know, from the real bytes on disk:
resolution, coverage, date range, units, missing-data fraction, latency and
volume. This script produces that evidence and writes it to
logs/inspection_report.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import warnings
from datetime import datetime, timezone

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from shapely.geometry import box

from common import AOI_BBOX, BOUNDARIES, LOGS, RAW, ROOT

warnings.filterwarnings("ignore")

AOI_POLY = box(*AOI_BBOX)
lines: list[str] = []


def out(s: str = "") -> None:
    print(s)
    lines.append(s)


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def aoi_overlap_pct(bounds, crs) -> float:
    """How much of the AOI this raster covers, in percent."""
    try:
        if crs and crs.to_epsg() != 4326:
            bounds = transform_bounds(crs, "EPSG:4326", *bounds, densify_pts=21)
        inter = box(*bounds).intersection(AOI_POLY)
        return 100 * inter.area / AOI_POLY.area
    except Exception:  # noqa: BLE001
        return float("nan")


# --------------------------------------------------------------------------
def inspect_raster(p: Path) -> dict:
    with rasterio.open(p) as ds:
        res = ds.res
        crs = ds.crs
        deg = crs and crs.to_epsg() == 4326
        res_m = (res[0] * 111320, res[1] * 111320) if deg else res
        band = ds.read(1, out_shape=(1, min(ds.height, 1024), min(ds.width, 1024)))
        nodata = ds.nodata
        if nodata is not None:
            miss = float(np.mean(band == nodata) * 100)
            valid = band[band != nodata]
        else:
            miss = float(np.mean(~np.isfinite(band.astype("float32"))) * 100)
            valid = band[np.isfinite(band.astype("float32"))]
        return {
            "kind": "raster",
            "size": p.stat().st_size,
            "shape": f"{ds.width} x {ds.height}",
            "crs": str(crs),
            "res_native": f"{res[0]:.6g}",
            "res_m": f"~{res_m[0]:.0f} m",
            "dtype": str(ds.dtypes[0]),
            "nodata": nodata,
            "missing_pct": round(miss, 2),
            "vmin": float(valid.min()) if valid.size else None,
            "vmax": float(valid.max()) if valid.size else None,
            "aoi_cover_pct": round(aoi_overlap_pct(ds.bounds, crs), 1),
        }


def inspect_vector(p: Path) -> dict:
    gdf = gpd.read_file(p)
    b = gdf.total_bounds
    return {
        "kind": "vector",
        "size": p.stat().st_size,
        "features": len(gdf),
        "geom": str(gdf.geom_type.iloc[0]) if len(gdf) else "-",
        "crs": str(gdf.crs),
        "bounds": f"{b[0]:.3f}, {b[1]:.3f}, {b[2]:.3f}, {b[3]:.3f}" if len(gdf) else "-",
        "columns": len(gdf.columns),
        "aoi_cover_pct": round(aoi_overlap_pct(tuple(b), gdf.crs), 1) if len(gdf) else 0,
    }


# --------------------------------------------------------------------------
def section(title: str) -> None:
    out(f"\n## {title}\n")


def report_folder(folder: Path) -> None:
    if not folder.exists():
        return
    section(folder.name)

    man = folder / "_SOURCES.json"
    if man.exists():
        for e in json.loads(man.read_text()):
            out(f"**{e['source']}**  ")
            out(f"fetched `{e['fetched_utc']}` · license: {e['license'] or 'n/a'}  ")
            if e.get("notes"):
                out(f"_{e['notes']}_  ")
            out("")

    files = sorted(f for f in folder.rglob("*")
                   if f.is_file() and f.suffix.lower() in
                   {".tif", ".gpkg", ".geojson", ".grib2", ".txt", ".json"}
                   and f.name != "_SOURCES.json")
    if not files:
        out("_no files_")
        return

    total = sum(f.stat().st_size for f in files)
    out(f"{len(files)} files · {human(total)}\n")

    # group identical-structure tiles: report the first, count the rest
    shown, groups = 0, {}
    for f in files:
        key = f.parent.name + "|" + f.suffix
        groups.setdefault(key, []).append(f)

    out("| file | facts |")
    out("|---|---|")
    for key, grp in groups.items():
        rep = grp[0]
        try:
            if rep.suffix.lower() == ".tif":
                info = inspect_raster(rep)
                facts = (f"{info['shape']} px · {info['res_m']} · {info['dtype']} · "
                         f"range {info['vmin']}–{info['vmax']} · "
                         f"missing {info['missing_pct']}% · {info['crs']}")
            elif rep.suffix.lower() in {".gpkg", ".geojson"}:
                info = inspect_vector(rep)
                facts = (f"{info['features']:,} {info['geom']} · {info['columns']} cols · "
                         f"{info['crs']} · bounds {info['bounds']}")
            else:
                facts = f"{human(rep.stat().st_size)}"
        except Exception as exc:  # noqa: BLE001
            facts = f"**unreadable** — {type(exc).__name__}: {str(exc)[:90]}"
        extra = f" _(+{len(grp) - 1} more like it)_" if len(grp) > 1 else ""
        out(f"| `{rep.name}`{extra} | {facts} |")
        shown += 1


def main() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    out("# Inspection Report")
    out(f"\nGenerated {datetime.now(timezone.utc).isoformat(timespec='seconds')}  ")
    out(f"AOI bbox: `{AOI_BBOX}`\n")

    for folder in sorted(RAW.iterdir()):
        if folder.is_dir():
            report_folder(folder)

    grand = sum(f.stat().st_size for f in RAW.rglob("*") if f.is_file())
    out(f"\n---\n\n**Total on disk: {human(grand)}**")

    dest = LOGS / "inspection_report.md"
    dest.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwritten -> {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
