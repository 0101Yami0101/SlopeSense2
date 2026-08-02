"""Stage 2b — build the susceptibility training sample.

Output: data/processed/susceptibility_samples.parquet

This is the script that decides what the model is actually asked to learn, and
it is the easiest place in the whole project to destroy the result without any
error being raised. Every constraint below is here for a measured reason.

════════════════════════════════════════════════════════════════════════════
THE PROBLEM: WE HAVE NO TRUE NEGATIVES
════════════════════════════════════════════════════════════════════════════
We have 91,610 cells where somebody mapped a landslide. We have ZERO cells
where somebody checked and certified "no landslide here". Absence of a record
is not evidence of absence — most of Arunachal has never been walked by a
surveyor. This is a presence-only problem wearing a presence/absence costume.

Everything below is damage control for that fact. Three consequences we accept
up front rather than discover later:

  1. Predicted probabilities are NOT event probabilities. They are relative
     susceptibility scores. Rank metrics (AUC, precision@k) are meaningful;
     "12% chance of failure" is not, until calibrated against something real.
  2. Some negatives ARE landslides nobody recorded. This puts a ceiling on
     achievable accuracy that no amount of extra data or model capacity lifts.
  3. Reported skill will be optimistic relative to the field. Say so in the
     deliverable.

════════════════════════════════════════════════════════════════════════════
THE MODELLING DOMAIN — applied to BOTH classes, symmetrically
════════════════════════════════════════════════════════════════════════════
    slope > 10 deg          keeps 99.3% of positives, drops 8.7% of the state
    dist to slide > 500 m   negatives only (see buffer note)
    land cover not in       snow/ice, permanent water, moss/lichen
      {70, 80, 100}

Measured land cover, state share vs share of positives:

    snow and ice        1.95% of state    0.00% of positives
    moss and lichen     3.70% of state    0.11% of positives
    permanent water     0.61% of state    0.11% of positives

Glaciers and high-alpine moss have essentially no mapped landslides — partly
physics, mostly that nobody surveys them. So they are OUT OF DOMAIN.

⚠️ MEASURED, AGAINST EXPECTATION: excluding them does NOT improve the score.
See "what this sampling does and does not buy" below before repeating the
usual textbook justification for any of this.

⚠️ CONSEQUENCE FOR DEPLOYMENT: out-of-domain cells must be masked at inference
and reported as "not assessed", NOT scored. A model that never saw glaciers in
training has no business assigning them a number. This is a hard requirement
on the daily run, not a nicety.

⚠️ THE FILTER IS APPLIED TO POSITIVES TOO. Filtering only negatives would leave
positives in regions with no negatives at all, and the model would learn
"land cover 70 => landslide" — the exact inverse of the truth, from a pure
sampling artefact. Symmetry is not optional here.

════════════════════════════════════════════════════════════════════════════
THE 500 m BUFFER
════════════════════════════════════════════════════════════════════════════
A cell 100 m from a mapped landslide is on the same hillside, in the same
rock, under the same rain. Calling it a negative teaches the model to draw a
distinction that does not physically exist, and it is very likely an
unreported positive besides. 500 m is ~5 cells: far enough to leave the
failure's own slope, close enough that we are not restricting negatives to a
different landscape entirely.

════════════════════════════════════════════════════════════════════════════
RATIO AND STRATIFICATION
════════════════════════════════════════════════════════════════════════════
1:5 positive:negative. Trees handle mild imbalance well, and 5x gives the
model a broad view of the landscape without drowning the positives.

Negatives are drawn WITHIN each fold, proportional to that fold's positive
count, so every fold has the same prevalence. Otherwise fold 3's AUC would not
be comparable to fold 1's, and spatial CV would be measuring sampling noise.

Seeded (SAMPLE_SEED) and hashed, exactly like the folds, so the sample is
reproducible and provably predates the results.

════════════════════════════════════════════════════════════════════════════
WHAT THIS SAMPLING DOES AND DOES NOT BUY  (measured 2026-08-02)
════════════════════════════════════════════════════════════════════════════
The standard argument for constrained negatives is that random negatives make
the task trivial and inflate the score. WE TESTED THAT HERE AND IT IS FALSE
FOR ARUNACHAL:

    trained constrained -> hard test set   AUC 0.860 +/- 0.016
    trained NAIVE       -> hard test set   AUC 0.862 +/- 0.016
    slope alone, constrained sample        AUC 0.609
    slope alone, naive sample              AUC 0.639

Identical within noise. The textbook argument assumes mixed terrain with flat
plains available to contaminate the negative pool. Arunachal has almost none:
median slope is 29 deg and 85.7% of the state is already in domain. There are
no easy negatives here to do the damage.

So do NOT defend this sampling on accuracy grounds — the number does not move,
and a reviewer who checks will find that out. It is justified on two grounds
that AUC structurally cannot measure:

  1. LABEL VALIDITY. 15.8% of the naive negative pool lies within 500 m of a
     mapped failure — about 71,600 cells in a 1:5 draw. Those are the cells
     most likely to be unreported positives. Training on them means fitting
     known-bad labels, and AUC is blind to it because the TEST set carries the
     identical corruption. A metric cannot see its own blind spot.
  2. DEPLOYMENT HONESTY. 6.3% of the pool is ice, water or alpine moss
     (~28,700 cells). A model that never trained on glaciers must not emit a
     susceptibility number for one. "We assessed slopes >10 deg excluding
     permanent ice and water" survives review; a glacier with a susceptibility
     score discredits the whole map.

Together those are ~22% of a naive negative draw that is either probably
mislabelled or out of domain. That is the reason. Not the score.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hashlib
import json
import time
import warnings

import numpy as np
import pandas as pd
import rasterio

import grid as G
from common import INTERIM, PROCESSED

warnings.filterwarnings("ignore")

OUT = PROCESSED / "susceptibility_samples.parquet"
META = PROCESSED / "susceptibility_samples.meta.json"

SLOPE_MIN = 10.0        # degrees
BUFFER_M = 500.0        # negatives must be this far from any mapped slide
NEG_PER_POS = 5
SAMPLE_SEED = 1337
LC_EXCLUDE = {70, 80, 100}      # snow/ice, permanent water, moss/lichen


def read(path: Path) -> np.ndarray:
    with rasterio.open(path) as s:
        return s.read(1)


def main() -> None:
    t0 = time.time()
    print("Stage 2b — susceptibility training sample")

    inside = read(INTERIM / "state_mask.tif").astype(bool)
    slope = read(INTERIM / "terrain" / "terrain_slope_deg.tif")
    lc = read(INTERIM / "features" / "lc_class_cat.tif")
    pos = read(INTERIM / "labels" / "label_slide.tif").astype(bool)
    dist = read(INTERIM / "labels" / "label_dist_slide_m.tif")

    n_state = int(inside.sum())

    # --- domain: identical rule for both classes -------------------------
    lc_ok = ~np.isin(lc, list(LC_EXCLUDE))
    with np.errstate(invalid="ignore"):
        domain = inside & lc_ok & (slope > SLOPE_MIN)
    print(f"  state cells          {n_state:>10,}")
    print(f"  in modelling domain  {int(domain.sum()):>10,}  "
          f"({100*domain.sum()/n_state:.1f}%)")

    P = domain & pos
    print(f"  positives in domain  {int(P.sum()):>10,}  "
          f"(of {int((pos & inside).sum()):,} mapped, "
          f"{100*P.sum()/(pos & inside).sum():.1f}% kept)")

    with np.errstate(invalid="ignore"):
        N_pool = domain & ~pos & (dist > BUFFER_M)
    print(f"  eligible negatives   {int(N_pool.sum()):>10,}  "
          f"({100*N_pool.sum()/domain.sum():.1f}% of domain)")

    # --- fold-stratified negative draw ------------------------------------
    folds = pd.read_parquet(INTERIM / "spatial_folds.parquet")
    fmap = dict(zip(folds.block_id.to_numpy(), folds.fold.to_numpy()))

    rng = np.random.default_rng(SAMPLE_SEED)
    rows_p, cols_p = np.nonzero(P)
    fold_p = pd.Series(G.fold_block(rows_p, cols_p)).map(fmap).to_numpy()

    rows_n, cols_n = np.nonzero(N_pool)
    fold_n = pd.Series(G.fold_block(rows_n, cols_n)).map(fmap).to_numpy()

    keep_r, keep_c, keep_y, keep_f = [], [], [], []
    print(f"\n  {'fold':<6}{'pos':>10}{'neg pool':>12}{'neg drawn':>12}{'ratio':>8}")
    for f in sorted(set(fold_p[~pd.isna(fold_p)])):
        pm = fold_p == f
        nm = fold_n == f
        want = int(pm.sum()) * NEG_PER_POS
        avail = int(nm.sum())
        take = min(want, avail)
        idx = rng.choice(avail, size=take, replace=False)

        keep_r.append(rows_p[pm]);  keep_c.append(cols_p[pm])
        keep_y.append(np.ones(pm.sum(), np.int8))
        keep_f.append(np.full(pm.sum(), f, np.int8))

        keep_r.append(rows_n[nm][idx]);  keep_c.append(cols_n[nm][idx])
        keep_y.append(np.zeros(take, np.int8))
        keep_f.append(np.full(take, f, np.int8))

        print(f"  {int(f):<6}{int(pm.sum()):>10,}{avail:>12,}{take:>12,}"
              f"{take/max(pm.sum(),1):>8.1f}")
        if take < want:
            print(f"         ⚠ fold {int(f)} negative pool exhausted")

    rows = np.concatenate(keep_r)
    cols = np.concatenate(keep_c)
    y = np.concatenate(keep_y)
    fold = np.concatenate(keep_f)

    sel = pd.DataFrame({
        "cell_id": G.encode(rows, cols).astype(np.int32),
        "label": y, "fold": fold,
    })
    print(f"\n  sample: {len(sel):,} rows   "
          f"{int(y.sum()):,} pos / {int((y==0).sum()):,} neg   "
          f"prevalence {100*y.mean():.2f}%")

    # --- attach features from the grid table ------------------------------
    print("  joining features...", flush=True)
    frames = []
    for f in sorted(sel.fold.unique()):
        part = pd.read_parquet(INTERIM / "grid_100m" / f"fold={f}" / "part.parquet")
        sub = sel[sel.fold == f]
        merged = sub.merge(part, on="cell_id", how="left", validate="one_to_one")
        frames.append(merged)
    df = pd.concat(frames, ignore_index=True)

    feat_cols = [c for c in df.columns
                 if c not in ("cell_id", "label", "fold", "row", "col",
                              "x_utm", "y_utm")]
    miss = df[feat_cols].isna().any(axis=1)
    if miss.any():
        print(f"  dropping {int(miss.sum()):,} rows with missing features "
              f"({100*miss.mean():.2f}%)")
        df = df[~miss].reset_index(drop=True)

    front = ["cell_id", "label", "fold", "row", "col", "x_utm", "y_utm"]
    df = df[front + [c for c in df.columns if c not in front]]

    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False, compression="zstd")

    # --- freeze: hash the exact membership --------------------------------
    payload = df[["cell_id", "label", "fold"]].sort_values("cell_id") \
        .to_csv(index=False).encode()
    digest = hashlib.sha256(payload).hexdigest()[:16]

    META.write_text(json.dumps({
        "rows": int(len(df)), "features": len(feat_cols),
        "positives": int((df.label == 1).sum()),
        "negatives": int((df.label == 0).sum()),
        "slope_min_deg": SLOPE_MIN, "buffer_m": BUFFER_M,
        "neg_per_pos": NEG_PER_POS, "seed": SAMPLE_SEED,
        "lc_excluded": sorted(LC_EXCLUDE),
        "domain_cells": int(domain.sum()), "state_cells": n_state,
        "sample_hash": digest,
        "feature_columns": feat_cols,
    }, indent=2))

    size = OUT.stat().st_size / 1e6
    print(f"\n  wrote {OUT.name}  {len(df):,} rows x {len(df.columns)} cols "
          f"({size:.0f} MB)")
    print(f"  SAMPLE HASH  {digest}")
    print(f"  done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
