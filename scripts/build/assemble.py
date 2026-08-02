"""Stage 1e — join every layer into the one table everything downstream reads.

Output: data/interim/grid_100m/  (Parquet, partitioned by validation fold)

One row per in-state 100 m cell, one column per thing we know about it. From
here on nothing else opens a GeoTIFF: models, aggregation and the daily run all
query this table.

Partitioned by fold on purpose. Spatial cross-validation reads "everything
except fold 3" constantly, and partitioning turns that from a full scan plus
filter into skipping a directory.

Column order is stable and grouped by prefix (dem_, terrain_, hydro_, dist_,
soil_, lc_, geol_) so a human scanning the schema can find things.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import time
import warnings

import numpy as np
import pandas as pd
import rasterio

import grid as G
from common import INTERIM

warnings.filterwarnings("ignore")

OUT = INTERIM / "grid_100m"
SRC_DIRS = [INTERIM / "terrain", INTERIM / "features"]

# Categorical layers stay integer codes; everything else is float32.
CATEGORICAL = {"lc_class_cat", "geol_rockgr_cat", "geol_lithunit_cat"}


def layer_paths() -> list[Path]:
    paths = []
    for d in SRC_DIRS:
        for p in sorted(d.glob("*.tif")):
            if p.stem.startswith("_"):      # _dem_unmasked_m is a work file
                continue
            paths.append(p)
    # group by prefix for a readable schema, stable across runs
    order = ["dem_", "terrain_", "hydro_", "dist_", "soil_", "lc_", "geol_"]
    return sorted(paths, key=lambda p: (
        next((i for i, o in enumerate(order) if p.stem.startswith(o)), 99),
        p.stem))


def main() -> None:
    t0 = time.time()
    print("Stage 1e — assembling the grid table")

    with rasterio.open(INTERIM / "state_mask.tif") as m:
        inside = m.read(1).astype(bool)
    rows, cols = np.nonzero(inside)
    n = len(rows)
    print(f"  in-state cells: {n:,}")

    # --- keys --------------------------------------------------------------
    df = pd.DataFrame({
        "cell_id": G.encode(rows, cols).astype(np.int32),
        "row": rows.astype(np.int16),
        "col": cols.astype(np.int16),
    })
    x, y = G.centre_xy(rows, cols)
    df["x_utm"] = x.astype(np.float32)
    df["y_utm"] = y.astype(np.float32)

    # --- fold, from the frozen assignment ----------------------------------
    folds = pd.read_parquet(INTERIM / "spatial_folds.parquet")
    fmap = dict(zip(folds.block_id.to_numpy(), folds.fold.to_numpy()))
    blocks = G.fold_block(rows, cols).astype(np.int32)
    df["fold"] = pd.Series(blocks).map(fmap).astype("int8")
    if df.fold.isna().any():
        raise RuntimeError("some cells have no fold — folds file is stale")

    # --- every layer -------------------------------------------------------
    paths = layer_paths()
    print(f"  layers: {len(paths)}")
    for p in paths:
        with rasterio.open(p) as s:
            band = s.read(1)
        vals = band[rows, cols]
        if p.stem in CATEGORICAL:
            df[p.stem] = vals.astype(np.uint8)
        else:
            df[p.stem] = vals.astype(np.float32)
        del band

    mem = df.memory_usage(deep=True).sum() / 1e9
    print(f"  table: {len(df):,} rows x {len(df.columns)} cols  ({mem:.2f} GB)")

    # --- write, partitioned by fold ----------------------------------------
    if OUT.exists():
        for f in OUT.rglob("*"):
            if f.is_file():
                f.unlink()
    OUT.mkdir(parents=True, exist_ok=True)
    for f in sorted(df.fold.unique()):
        sub = df[df.fold == f]
        d = OUT / f"fold={f}"
        d.mkdir(parents=True, exist_ok=True)
        sub.drop(columns=["fold"]).to_parquet(
            d / "part.parquet", index=False, compression="zstd")

    size = sum(p.stat().st_size for p in OUT.rglob("*.parquet")) / 1e6
    print(f"  wrote {OUT}  ({size:.0f} MB on disk)")

    # --- schema + null report ----------------------------------------------
    report = []
    for c in df.columns:
        if c in ("cell_id", "row", "col", "fold", "x_utm", "y_utm"):
            continue
        v = df[c]
        nulls = float(v.isna().mean()) if v.dtype.kind == "f" else \
            float((v == 0).mean())
        report.append((c, str(v.dtype), nulls))

    print(f"\n  {'column':<30}{'dtype':<10}{'missing':>9}")
    for c, d, nulls in report:
        flag = "  <-- gap" if nulls > 0.02 else ""
        print(f"  {c:<30}{d:<10}{100*nulls:>8.2f}%{flag}")

    (INTERIM / "grid_100m_schema.json").write_text(json.dumps({
        "rows": int(len(df)),
        "columns": [{"name": c, "dtype": d, "missing_frac": round(m, 5)}
                    for c, d, m in report],
        "crs": G.CRS, "cell_m": G.CELL,
        "fold_hash_ref": "see spatial_folds.meta.json",
    }, indent=2))
    print(f"\n  done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
