"""Data Backbone bundle — the catalogue, the statistics, and safe previews.

The pipeline is the asset. This script turns ~9 GB of licensed source data and
40 derived layers into a ~1 MB bundle that lets someone SEE what the platform
is built on without being handed the data itself.

════════════════════════════════════════════════════════════════════════════
THE RULE THIS SCRIPT EXISTS TO ENFORCE
════════════════════════════════════════════════════════════════════════════
Nothing written here may allow a source dataset to be reconstructed. Three
things follow from that, and none of them is optional:

  HISTOGRAMS, NOT VALUES     A layer is described by binned counts. You learn
                             the shape of the distribution; you cannot read a
                             cell.

  THUMBNAILS, NOT RASTERS    Previews are downsampled by ~60x to about 100 px
                             across and quantised to 8 bits. That is a picture
                             of a layer, at roughly 6 km per pixel. It is not
                             a usable elevation model, and it is not
                             georeferenced precisely enough to become one.

  SYNTHETIC ROWS, NOT REAL   Demo records are drawn from each column's OWN
                             marginal distribution, INDEPENDENTLY per column.
                             That deliberately destroys the correlations
                             between columns, so no generated row corresponds
                             to any real cell anywhere in Arunachal. A row that
                             looks plausible is meant to; it is still fiction.

Provenance (source, licence, URL, fetch date, byte counts) IS published in
full, because that is metadata about the data rather than the data — and
because a client is entitled to audit where every layer came from.
"""
import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import rasterio

from common import INTERIM, PROCESSED, RAW, ROOT

OUT = ROOT / "webapp" / "assets" / "backbone"

# Preview geometry. ~60x downsample puts a thumbnail at roughly 6 km per pixel:
# enough to recognise the shape of the state and where a layer has values,
# nowhere near enough to be a usable dataset.
THUMB_W = 98
N_BINS = 28
N_DEMO_ROWS = 6
RNG = np.random.default_rng(20260817)

# Human-readable group titles and what each is FOR. The folder names are
# pipeline plumbing; this is what a reader actually needs.
GROUPS = {
    "01_boundaries": ("Boundaries", "The state and district outlines every "
                                    "layer is clipped to."),
    "02_terrain": ("Terrain", "Elevation, and everything derived from its "
                              "shape — slope, curvature, wetness."),
    "03_soil_geology": ("Soil & geology", "What the slope is made of: soil "
                                          "texture and depth, rock type, "
                                          "fault lines."),
    "04_landcover": ("Land cover", "What is growing on it, or built on it."),
    "05_hydrology": ("Hydrology", "Rivers, catchments and river discharge — "
                                  "the flood module's foundation."),
    "06_weather": ("Weather", "Daily rainfall, the input that makes a "
                              "forecast a forecast rather than a map."),
    "07_seismic": ("Seismic", "Earthquake shaking, a second trigger for "
                              "slope failure."),
    "08_labels": ("Evidence", "Mapped landslides and observed flooding — the "
                              "record every model is fitted and judged on."),
    "09_exposure": ("Exposure", "Roads, settlements and population: what a "
                                "hazard would actually reach."),
    "10_context": ("Context & benchmarks", "Official hazard products we are "
                                           "measured against, not trained on."),
    "11_satellite": ("Satellite", "Radar imagery, held for change detection "
                                  "work that is not in the shipped models."),
}

# Every derived layer, with what it means and the units it is in. Written out
# rather than parsed from filenames: "cfvo" and "bdod" are SoilGrids codes and
# mean nothing to a reader without this table.
LAYERS = [
    # file stem,                group,       title, units, kind
    ("dem_elev_m", "terrain", "Elevation", "m", "num"),
    ("terrain_slope_deg", "terrain", "Slope", "°", "num"),
    ("terrain_slope_max_deg", "terrain", "Slope, local maximum", "°", "num"),
    ("terrain_relief_m", "terrain", "Local relief", "m", "num"),
    ("terrain_curv_plan", "terrain", "Plan curvature", "1/m", "num"),
    ("terrain_curv_prof", "terrain", "Profile curvature", "1/m", "num"),
    ("terrain_northness", "terrain", "Northness", "−1..1", "num"),
    ("terrain_eastness", "terrain", "Eastness", "−1..1", "num"),
    ("hydro_twi", "terrain", "Topographic wetness", "index", "num"),
    ("hydro_flowacc_cells", "terrain", "Flow accumulation", "cells", "num"),
    ("dist_river_m", "terrain", "Distance to river", "m", "num"),
    ("dist_road_m", "terrain", "Distance to road", "m", "num"),
    ("dist_lineament_m", "terrain", "Distance to fault line", "m", "num"),
    ("lc_class_cat", "features", "Land cover class", "class", "cat"),
    ("geol_rockgr_cat", "features", "Rock group", "class", "cat"),
    ("geol_lithunit_cat", "features", "Lithological unit", "class", "cat"),
]
# The 18 SoilGrids layers follow one naming pattern, so generate rather than
# type them out and risk a typo in a units string.
SOIL = {"bdod": ("Bulk density", "cg/cm³"), "cfvo": ("Coarse fragments", "cm³/dm³"),
        "clay": ("Clay", "g/kg"), "sand": ("Sand", "g/kg"),
        "silt": ("Silt", "g/kg"), "soc": ("Soil organic carbon", "dg/kg")}
for _p, (_t, _u) in SOIL.items():
    for _d, _du in (("0-5cm", "0–5 cm"), ("15-30cm", "15–30 cm"),
                    ("60-100cm", "60–100 cm")):
        _suffix = {"bdod": "cgcm3", "cfvo": "cm3dm3", "clay": "gkg",
                   "sand": "gkg", "silt": "gkg", "soc": "dgkg"}[_p]
        LAYERS.append((f"soil_{_p}_{_d}_{_suffix}", "features",
                       f"{_t}, {_du}", _u, "num"))

T0 = time.time()


def tick(m):
    print(f"  [{time.time()-T0:6.1f}s] {m}", flush=True)


def _dir_bytes(p: Path) -> int:
    return sum(f.stat().st_size for f in p.iterdir() if f.is_file()) if p.exists() else 0


def dir_stats(p: Path):
    n = b = 0
    for root, _, fs in os.walk(p):
        for f in fs:
            try:
                b += os.path.getsize(os.path.join(root, f))
                n += 1
            except OSError:
                pass
    return n, b


def build_catalogue() -> dict:
    """Provenance for every source group, straight from the _SOURCES.json the
    fetchers wrote. Published in full — a client auditing a licence needs the
    URL and the fetch date, and neither reveals a single data value."""
    groups = []
    for key in sorted(GROUPS):
        d = RAW / key
        if not d.exists():
            continue
        title, purpose = GROUPS[key]
        n, b = dir_stats(d)
        srcs = []
        sp = d / "_SOURCES.json"
        if sp.exists():
            for s in json.loads(sp.read_text(encoding="utf-8")):
                files = s.get("files", [])
                srcs.append({
                    "source": s.get("source", "—"),
                    "url": s.get("url", ""),
                    "license": s.get("license", "—"),
                    "fetched": (s.get("fetched_utc") or "")[:10],
                    "notes": s.get("notes", ""),
                    "n_files": len(files),
                    "bytes": int(sum(f.get("bytes", 0) for f in files)),
                })
        groups.append({"key": key, "title": title, "purpose": purpose,
                       "n_files": n, "bytes": b, "sources": srcs})
    return {"groups": groups,
            "total_files": sum(g["n_files"] for g in groups),
            "total_bytes": sum(g["bytes"] for g in groups),
            "n_sources": sum(len(g["sources"]) for g in groups)}


def summarise(path: Path, kind: str):
    """Histogram, headline statistics and a thumbnail — never the values.

    Returns None when the file is absent so the bundle degrades to whatever is
    actually on disk rather than failing the whole build.
    """
    if not path.exists():
        return None
    with rasterio.open(path) as s:
        a = s.read(1)
        h, w = s.height, s.width
    step = max(1, w // THUMB_W)
    thumb = a[::step, ::step].astype(np.float32)

    if a.dtype.kind in "iu":
        valid = a != 0 if kind == "cat" else np.isfinite(a.astype(np.float32))
        vals = a[valid].astype(np.float64)
    else:
        valid = np.isfinite(a)
        vals = a[valid].astype(np.float64)
    cover = float(valid.mean())
    if vals.size == 0:
        return None

    out = {"coverage": cover, "n_valid": int(valid.sum()),
           "shape": [int(h), int(w)]}

    if kind == "cat":
        u, c = np.unique(vals.astype(np.int64), return_counts=True)
        order = np.argsort(-c)[:12]
        out["classes"] = [{"code": int(u[i]), "share": float(c[i] / c.sum())}
                          for i in order]
        # Quantise categories to distinct grey levels for the preview.
        # ⚠️ 0 is RESERVED for "no data" in every thumbnail, so valid values
        # start at 1. Without that, ground at the bottom of a layer's range
        # renders identically to ground outside the state, and a reader cannot
        # tell "lowest" from "not measured".
        tv = thumb.copy()
        tv[~np.isfinite(tv)] = 0
        m = tv.max() or 1
        tq = np.where(tv > 0, 1 + tv / m * 254, 0)
    else:
        # Percentiles describe the SHAPE. They are order statistics of a public
        # dataset, not a means of recovering it.
        qs = np.percentile(vals, [0, 1, 25, 50, 75, 99, 100])
        out["stats"] = {"min": float(qs[0]), "p1": float(qs[1]),
                        "p25": float(qs[2]), "p50": float(qs[3]),
                        "p75": float(qs[4]), "p99": float(qs[5]),
                        "max": float(qs[6]), "mean": float(vals.mean())}
        lo, hi = qs[1], qs[5]
        if hi <= lo:
            lo, hi = qs[0], max(qs[6], qs[0] + 1e-6)
        cnt, edges = np.histogram(np.clip(vals, lo, hi), bins=N_BINS,
                                  range=(lo, hi))
        out["hist"] = {"edges": [float(x) for x in edges],
                       "counts": [int(x) for x in cnt]}
        tv = np.clip(thumb, lo, hi)
        tq = 1.0 + (tv - lo) / (hi - lo) * 254.0     # 0 reserved for no data
        tq[~np.isfinite(thumb)] = 0

    return out, np.clip(np.nan_to_num(tq), 0, 255).astype(np.uint8)


def synth_rows(layers: dict) -> list:
    """Demo records — SYNTHETIC, and deliberately so.

    Each column is drawn from its own histogram INDEPENDENTLY of every other
    column. Real terrain is heavily correlated (steep ground is high ground, and
    clay and sand are near-complements), so breaking those links guarantees no
    generated row is a real place. The result shows a reader the schema, the
    units and the plausible range of every field, and reveals nothing.
    """
    rows = []
    for i in range(N_DEMO_ROWS):
        row = {"cell_id": int(RNG.integers(100_000, 320_000) * 100000
                              + RNG.integers(0, 5900))}
        for name, L in layers.items():
            if "hist" in L:
                e = np.asarray(L["hist"]["edges"], float)
                c = np.asarray(L["hist"]["counts"], float)
                if c.sum() <= 0:
                    row[name] = None
                    continue
                b = RNG.choice(len(c), p=c / c.sum())
                v = RNG.uniform(e[b], e[b + 1])
                row[name] = round(float(v), 3)
            elif "classes" in L and L["classes"]:
                cl = L["classes"]
                p = np.asarray([x["share"] for x in cl], float)
                row[name] = int(cl[int(RNG.choice(len(cl), p=p / p.sum()))]["code"])
        rows.append(row)
    return rows


def privacy_evidence(layers: dict) -> dict:
    """Measure the guarantees the page makes, rather than asserting them.

    A claim like "these rows are synthetic" is worth nothing on its own. The
    check that means something: real terrain is strongly correlated — steep
    ground is high ground, wet ground is flat — and drawing each column from
    its own marginal independently must DESTROY that structure. If it does,
    no generated row can be a real place, because real places obey the
    correlations and these rows do not.
    """
    pairs = [("dem_elev_m", "terrain_slope_deg", "elevation", "slope"),
             ("terrain_slope_deg", "hydro_twi", "slope", "wetness")]
    rng = np.random.default_rng(11)
    out = []
    for ka, kb, na, nb in pairs:
        pa, pb = INTERIM / "terrain" / f"{ka}.tif", INTERIM / "terrain" / f"{kb}.tif"
        if not (pa.exists() and pb.exists() and ka in layers and kb in layers):
            continue
        with rasterio.open(pa) as f:
            a = f.read(1)
        with rasterio.open(pb) as f:
            b = f.read(1)
        ok = np.isfinite(a) & np.isfinite(b)
        idx = rng.choice(np.flatnonzero(ok), min(200_000, int(ok.sum())),
                         replace=False)
        real = float(np.corrcoef(a.ravel()[idx], b.ravel()[idx])[0, 1])

        def draw(name, n):
            h = layers[name]["hist"]
            e = np.asarray(h["edges"], float)
            c = np.asarray(h["counts"], float)
            j = rng.choice(len(c), size=n, p=c / c.sum())
            return rng.uniform(e[j], e[j + 1])

        synth = float(np.corrcoef(draw(ka, 200_000), draw(kb, 200_000))[0, 1])
        out.append({"pair": f"{na} vs {nb}", "real": round(real, 3),
                    "generated": round(synth, 3)})

    # How coarse the published previews actually are.
    ref = layers.get("dem_elev_m")
    thumb_px = max(1, (THUMB_W * THUMB_W * 55) // 100)
    red = km = None
    if ref:
        cells = ref["shape"][0] * ref["shape"][1]
        red = cells / thumb_px
        km = 0.1 * float(np.sqrt(red))     # 100 m cells -> km per preview pixel
    step = None
    if ref and "stats" in ref:
        step = (ref["stats"]["p99"] - ref["stats"]["p1"]) / (2 * N_BINS)
    return {"correlations": out,
            "preview_reduction": None if red is None else round(red),
            "preview_km_per_px": None if km is None else round(km, 1),
            "hist_bins": N_BINS,
            "elev_uncertainty_m": None if step is None else round(step)}


def rainfall_timeline() -> dict:
    """How much rainfall history exists, by year. Counts of days — the single
    number that decides whether a trigger can be fitted at all."""
    p = INTERIM / "rainfall" / "dates.npy"
    if not p.exists():
        return {}
    d = np.load(p, allow_pickle=True)
    years = np.array([str(x)[:4] for x in d])
    months = np.array([int(str(x)[5:7]) for x in d])
    u, c = np.unique(years, return_counts=True)
    mu, mc = np.unique(months, return_counts=True)
    meta = {}
    mp = INTERIM / "rainfall" / "_stack_meta.json"
    if mp.exists():
        meta = json.loads(mp.read_text())
    return {"by_year": [{"year": str(y), "days": int(n)} for y, n in zip(u, c)],
            "by_month": [{"month": int(m), "days": int(n)} for m, n in zip(mu, mc)],
            "n_days": int(len(d)), "first": str(d[0]), "last": str(d[-1]),
            "cell_km": 11, "grid": meta.get("shape"),
            "nan_frac": meta.get("nan_frac"),
            "cells_over_state": meta.get("imerg_cells_over_state")}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Building Data Backbone bundle")

    cat = build_catalogue()
    tick(f"catalogue: {len(cat['groups'])} groups, {cat['n_sources']} sources, "
         f"{cat['total_files']:,} files, {cat['total_bytes']/1e9:.2f} GB")

    legends = {}
    lp = INTERIM / "features" / "_legends.json"
    if lp.exists():
        legends = json.loads(lp.read_text(encoding="utf-8"))

    layers, thumbs = {}, {}
    for stem, sub, title, units, kind in LAYERS:
        path = INTERIM / sub / f"{stem}.tif"
        res = summarise(path, kind)
        if res is None:
            print(f"      [skip] {stem}")
            continue
        info, th = res
        info.update({"title": title, "units": units, "kind": kind,
                     "group": sub, "file": stem})
        if kind == "cat" and stem in legends:
            for c in info["classes"]:
                c["name"] = legends[stem].get(str(c["code"]), f"class {c['code']}")
        layers[stem] = info
        thumbs[stem] = th
    tick(f"summarised {len(layers)} derived layers "
         f"(histograms + {THUMB_W}px previews)")

    # Evidence layers get the same treatment, from the label rasters.
    lab = {}
    lm = INTERIM / "labels" / "_label_meta.json"
    if lm.exists():
        m = json.loads(lm.read_text())
        lab = {"positive_cells": m.get("positive_cells"),
               "state_cells": m.get("state_cells"),
               "prevalence": m.get("prevalence_frac"),
               "sources": [{"name": s.get("name"), "features": s.get("features"),
                            "cells": s.get("cells_in_state")}
                           for s in m.get("sources_used_as_positives", [])]}

    demo = synth_rows(layers)
    evidence = privacy_evidence(layers)
    for c in evidence["correlations"]:
        tick(f"independence: {c['pair']:<22} real r={c['real']:+.3f} -> "
             f"generated r={c['generated']:+.3f}")
    tick(f"generated {len(demo)} synthetic demo rows; previews reduced "
         f"{evidence['preview_reduction']:,}x "
         f"(~{evidence['preview_km_per_px']} km per pixel)")

    tl = rainfall_timeline()
    tick(f"rainfall archive: {tl.get('n_days', 0):,} days "
         f"{tl.get('first', '?')} to {tl.get('last', '?')}")

    # Pipeline stages, with the script count actually on disk behind each.
    def nscripts(sub, pat=""):
        d = ROOT / "scripts" / sub
        return len([f for f in d.glob("*.py") if pat in f.name]) if d.exists() else 0

    grid_schema = {}
    gp = INTERIM / "grid_100m_schema.json"
    if gp.exists():
        grid_schema = json.loads(gp.read_text())

    pipeline = {
        "stages": [
            {"name": "Fetch", "scripts": nscripts("fetch"),
             "what": "Pull from source archives — NASA, Copernicus, ESA, GSI, "
                     "HydroSHEDS, OpenStreetMap and the state portals.",
             "out": f"{cat['total_files']:,} raw files, "
                    f"{cat['total_bytes']/1e9:.1f} GB",
             "note": "Raw files are never edited in place, and every fetch "
                     "writes its source, licence and checksum alongside."},
            {"name": "Align", "scripts": nscripts("build"),
             "what": "Reproject and resample everything onto one 100 m grid "
                     "over Arunachal.",
             "out": f"{grid_schema.get('rows', 0):,} cells",
             "note": "One lattice, EPSG:32646. Every layer lines up cell for "
                     "cell, which is what lets two hazards share a map."},
            {"name": "Feature", "scripts": nscripts("build"),
             "what": "Derive what the models actually read — slope, curvature, "
                     "wetness, distances, rainfall percentiles.",
             "out": f"{len(grid_schema.get('columns', []))} columns",
             "note": "Terrain and soil are static and computed once; rainfall "
                     "is rebuilt every day."},
            {"name": "Model", "scripts": nscripts("model"),
             "what": "Fit where-it-fails on mapped evidence; score how unusual "
                     "today's weather is against each place's own history.",
             "out": f"{tl.get('n_days', 0):,} days of rainfall history",
             "note": "Validated by hiding whole regions during training, so "
                     "scores come from ground the model has never seen."},
            {"name": "Export", "scripts": nscripts("run") + 1,
             "what": "Cut the small web bundles the app actually reads.",
             "out": "",     # measured below, not guessed — see _dir_bytes
             "note": "Small enough for a free host — which is why the live app "
                     "carries no model files and no geospatial stack."},
        ],
        "grid": {"rows": grid_schema.get("rows"),
                 "columns": len(grid_schema.get("columns", [])),
                 "cell_m": 100, "crs": "EPSG:32646"},
    }

    # ── the Export stage reports what actually ships, MEASURED ────────────
    # ⚠️ This used to be the literal string "~4.4 MB", stale the moment any
    # bundle changed size — the exact thing this module's own privacy and
    # provenance rules exist to prevent elsewhere. base/, landslide/ and
    # flood/ are finished by the time this script runs, so they are scanned
    # directly; this bundle (backbone/) is still being assembled, so its
    # pieces are measured in memory — thumbs.npz via an in-memory
    # np.savez_compressed, catalogue.json via its already-final JSON string,
    # layers.json via a provisional serialisation before the true figure is
    # substituted in below. The only imprecision this leaves is layers.json's
    # own few-byte change in the LENGTH of the number being written into
    # itself — negligible against a bundle measured in hundreds of kilobytes.
    catalogue_json = json.dumps(cat, indent=1)
    thumbs_buf = io.BytesIO()
    np.savez_compressed(thumbs_buf, **thumbs)
    thumbs_bytes = thumbs_buf.tell()

    def _layers_json(pipe: dict) -> str:
        return json.dumps(
            {"layers": layers, "labels": lab, "demo_rows": demo,
             "timeline": tl, "pipeline": pipe,
             "generated_utc": datetime.now(timezone.utc).isoformat()[:19],
             "privacy": {
                 "rule": "No source dataset can be reconstructed from this "
                         "bundle.",
                 "histograms": f"{N_BINS} bins per layer — shape only, no "
                               "cell values",
                 "thumbnails": f"~{THUMB_W} px wide, about 6 km per pixel, "
                               "8-bit",
                 "demo_rows": "Synthetic. Each column drawn independently "
                              "from its own marginal, so no row is a real "
                              "location.",
                 "evidence": evidence,
             }}, indent=1)

    backbone_bytes = (len(catalogue_json.encode()) + thumbs_bytes
                      + len(_layers_json(pipeline).encode()))
    other_bundles = sum(_dir_bytes(OUT.parent / n)
                        for n in ("base", "landslide", "flood"))
    ship_mb = (backbone_bytes + other_bundles) / 1e6
    pipeline["stages"][-1]["out"] = f"{ship_mb:.1f} MB"
    layers_json = _layers_json(pipeline)

    (OUT / "catalogue.json").write_text(catalogue_json)
    (OUT / "layers.json").write_text(layers_json)
    (OUT / "thumbs.npz").write_bytes(thumbs_buf.getvalue())

    total = sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())
    tick(f"backbone bundle: {total/1e6:.2f} MB -> {OUT}  "
         f"(all bundles: {ship_mb:.2f} MB)")
    for p in sorted(OUT.iterdir()):
        if p.is_file():
            print(f"      {p.name:<18} {p.stat().st_size/1e3:8.1f} KB")


if __name__ == "__main__":
    main()
