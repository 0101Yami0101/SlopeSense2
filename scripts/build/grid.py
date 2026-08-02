"""The canonical 100 m grid. Every derived table in this project joins on it.

This module is the single source of truth for the decisions written up in
docs/design/DATA_CONTRACT.md. Nothing downstream should hardcode a CRS, a cell
size or an origin — import them from here, so that if they ever do change there
is exactly one place to change them.

Why these numbers (short version; the doc has the evidence):

  EPSG:32646   Arunachal straddles UTM zones 46/47, but the two disagree by only
               0.4% on the state polygon. We do distance-to-feature everywhere
               and area only at the final aggregation, so UTM beats equal-area.
  100 m        8.2 M cells in-state. This is *terrain* resolution — forecast
               skill is capped by IMERG's ~11 km cell, not by this.
  origin       A round UTM multiple, deliberately NOT derived from the boundary
               file: a bbox-derived origin would shift silently if GADM is ever
               updated, invalidating every derived file without an error.
  cell_id      row*100000+col, so any ID decodes back to a location by
               arithmetic. Sequential IDs hide bad joins; this one exposes them.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from affine import Affine

# --------------------------------------------------------------------------
# Frozen constants — see docs/design/DATA_CONTRACT.md before touching these
# --------------------------------------------------------------------------
CRS = "EPSG:32646"           # WGS 84 / UTM zone 46N
CELL = 100                   # metres
ORIGIN_X = 350_000           # UTM easting of the grid's left edge
ORIGIN_Y = 2_950_000         # UTM northing of the grid's BOTTOM edge
NCOLS = 5_900                # 590 km wide
NROWS = 3_200                # 320 km tall

# cell_id = row * ID_STRIDE + col. 100_000 leaves room for 16x more columns
# than we use, so a future finer grid does not need a new scheme.
ID_STRIDE = 100_000

FOLD_BLOCK = 50_000          # 50 km validation blocks
N_FOLDS = 5
FOLD_SEED = 42               # frozen; see DATA_CONTRACT.md section 6

# Rasterio/affine transform. Note the negative y-step: raster row 0 is the TOP,
# so the transform starts at the top edge and walks down.
TOP_Y = ORIGIN_Y + NROWS * CELL
TRANSFORM = Affine(CELL, 0, ORIGIN_X, 0, -CELL, TOP_Y)

BOUNDS = (ORIGIN_X, ORIGIN_Y, ORIGIN_X + NCOLS * CELL, TOP_Y)  # (W, S, E, N)
SHAPE = (NROWS, NCOLS)


# --------------------------------------------------------------------------
# ID <-> position
# --------------------------------------------------------------------------
def encode(row, col):
    """(row, col) -> cell_id. Accepts scalars or numpy arrays."""
    return np.asarray(row, dtype=np.int32) * ID_STRIDE + np.asarray(col, dtype=np.int32)


def decode(cell_id):
    """cell_id -> (row, col). The inverse of encode()."""
    cid = np.asarray(cell_id, dtype=np.int32)
    return cid // ID_STRIDE, cid % ID_STRIDE


def centre_xy(row, col):
    """(row, col) -> (easting, northing) of the cell centre, in CRS units."""
    row = np.asarray(row)
    col = np.asarray(col)
    return (ORIGIN_X + (col + 0.5) * CELL,
            TOP_Y - (row + 0.5) * CELL)


def xy_to_rowcol(x, y):
    """(easting, northing) -> (row, col). Out-of-grid input is NOT clipped —
    callers should mask, so that a coordinate landing outside is a visible bug
    rather than a silent snap to the edge."""
    col = np.floor((np.asarray(x) - ORIGIN_X) / CELL).astype(np.int32)
    row = np.floor((TOP_Y - np.asarray(y)) / CELL).astype(np.int32)
    return row, col


def fold_block(row, col):
    """(row, col) -> the 50 km validation block it belongs to, as a block id."""
    per = FOLD_BLOCK // CELL                       # cells per block edge
    brow = np.asarray(row) // per
    bcol = np.asarray(col) // per
    return brow * ID_STRIDE + bcol


def summary() -> str:
    w, s, e, n = BOUNDS
    return (f"grid {NROWS} x {NCOLS} @ {CELL} m  ({CRS})\n"
            f"  bbox cells : {NROWS * NCOLS:,}\n"
            f"  extent     : {(e-w)/1000:.0f} km x {(n-s)/1000:.0f} km\n"
            f"  x range    : {w:,} .. {e:,}\n"
            f"  y range    : {s:,} .. {n:,}\n"
            f"  max cell_id: {encode(NROWS-1, NCOLS-1):,} (int32 ok)")


if __name__ == "__main__":
    print(summary())

    # Round-trip check: every corner and the centre must survive
    # rowcol -> id -> rowcol and rowcol -> xy -> rowcol unchanged.
    pts = [(0, 0), (0, NCOLS - 1), (NROWS - 1, 0), (NROWS - 1, NCOLS - 1),
           (NROWS // 2, NCOLS // 2)]
    for r, c in pts:
        r2, c2 = decode(encode(r, c))
        x, y = centre_xy(r, c)
        r3, c3 = xy_to_rowcol(x, y)
        assert (int(r2), int(c2)) == (r, c), f"id round-trip failed at {r},{c}"
        assert (int(r3), int(c3)) == (r, c), f"xy round-trip failed at {r},{c}"
    print("\n  round-trip: OK on all corners + centre")
