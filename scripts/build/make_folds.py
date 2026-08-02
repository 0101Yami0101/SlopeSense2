"""Build the in-state cell mask and FREEZE the spatial validation folds.

Run this once, before any model is trained. See docs/design/DATA_CONTRACT.md §6.

Why folds are frozen up front: neighbouring 100 m cells are near-identical, so a
random train/test split leaks the answer and produces an excellent, meaningless
score. Blocked splits fix that. But if you choose the blocks *after* seeing
results, you will unconsciously prefer the arrangement that flatters the model
and you will not notice. Writing them first, with a content hash, is what lets a
reviewer prove the folds predate the numbers.

Outputs
    data/interim/state_mask.tif        uint8, 1 = inside Arunachal
    data/interim/spatial_folds.parquet block_id -> fold, plus the hash
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hashlib
import json
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize

import grid as G
from common import AOI_NAME, BOUNDARIES, INTERIM

warnings.filterwarnings("ignore")


def build_mask() -> np.ndarray:
    """Rasterise the state polygon onto the canonical grid."""
    src = BOUNDARIES / f"gadm_state-boundary_vector_{AOI_NAME}.gpkg"
    gdf = gpd.read_file(src).to_crs(G.CRS)
    mask = rasterize(
        [(geom, 1) for geom in gdf.geometry],
        out_shape=G.SHAPE,
        transform=G.TRANSFORM,
        fill=0,
        dtype="uint8",
        all_touched=False,       # centre-in-polygon: no inflated edge cells
    )
    INTERIM.mkdir(parents=True, exist_ok=True)
    out = INTERIM / "state_mask.tif"
    with rasterio.open(
        out, "w", driver="GTiff", height=G.NROWS, width=G.NCOLS, count=1,
        dtype="uint8", crs=G.CRS, transform=G.TRANSFORM,
        compress="deflate", tiled=True,
    ) as dst:
        dst.write(mask, 1)
    return mask


def main() -> None:
    print("Building canonical grid artefacts")
    print(G.summary())

    mask = build_mask()
    n_in = int(mask.sum())
    print(f"\n  in-state cells : {n_in:,} "
          f"({100 * n_in / mask.size:.1f}% of the bbox)")
    print(f"  implied area   : {n_in * G.CELL**2 / 1e6:,.0f} km2")

    # --- which 50 km blocks actually contain state territory ---------------
    rows, cols = np.nonzero(mask)
    blocks = G.fold_block(rows, cols)
    uniq, counts = np.unique(blocks, return_counts=True)

    # A block clipped to a sliver by the state boundary is a bad test set —
    # too few cells to give a stable metric. Fold it into a neighbour instead.
    MIN_CELLS = 5_000                       # 50 km2 of real land
    keep = counts >= MIN_CELLS
    print(f"  50 km blocks   : {len(uniq)} touched, "
          f"{int(keep.sum())} with >= {MIN_CELLS:,} cells")

    # --- assign blocks to folds, fixed seed --------------------------------
    rng = np.random.default_rng(G.FOLD_SEED)
    main_blocks = uniq[keep]
    order = rng.permutation(len(main_blocks))
    folds = np.empty(len(main_blocks), dtype=np.int8)
    for i, pos in enumerate(order):
        folds[pos] = i % G.N_FOLDS

    # Slivers join the nearest kept block's fold, so no cell is unassigned.
    small = uniq[~keep]
    brow_m, bcol_m = main_blocks // G.ID_STRIDE, main_blocks % G.ID_STRIDE
    sliver_folds = []
    for b in small:
        br, bc = b // G.ID_STRIDE, b % G.ID_STRIDE
        d = (brow_m - br) ** 2 + (bcol_m - bc) ** 2
        sliver_folds.append(folds[int(np.argmin(d))])

    df = pd.DataFrame({
        "block_id": np.concatenate([main_blocks, small]).astype(np.int32),
        "fold": np.concatenate([folds, np.array(sliver_folds, dtype=np.int8)]),
        "n_cells": np.concatenate([counts[keep], counts[~keep]]).astype(np.int32),
        "is_sliver": np.concatenate([np.zeros(len(main_blocks), bool),
                                     np.ones(len(small), bool)]),
    }).sort_values("block_id").reset_index(drop=True)

    print(f"\n  {'fold':<6}{'blocks':>8}{'cells':>12}{'share':>8}")
    for f in range(G.N_FOLDS):
        sub = df[df.fold == f]
        print(f"  {f:<6}{len(sub):>8}{sub.n_cells.sum():>12,}"
              f"{100*sub.n_cells.sum()/n_in:>7.1f}%")

    # --- freeze: content hash over the assignment itself --------------------
    payload = df[["block_id", "fold"]].to_csv(index=False).encode()
    digest = hashlib.sha256(payload).hexdigest()[:16]

    out = INTERIM / "spatial_folds.parquet"
    df.to_parquet(out, index=False, compression="zstd")
    (INTERIM / "spatial_folds.meta.json").write_text(json.dumps({
        "sha256_16": digest,
        "seed": G.FOLD_SEED,
        "n_folds": G.N_FOLDS,
        "block_metres": G.FOLD_BLOCK,
        "min_cells_per_block": MIN_CELLS,
        "crs": G.CRS,
        "cell_m": G.CELL,
        "in_state_cells": n_in,
        "note": "FROZEN before any model training. Changing this voids every "
                "previously reported metric — see docs/design/DATA_CONTRACT.md",
    }, indent=2))

    print(f"\n  wrote {out.name} and state_mask.tif")
    print(f"  FOLD HASH: {digest}   <- quote this alongside any reported metric")


if __name__ == "__main__":
    main()
