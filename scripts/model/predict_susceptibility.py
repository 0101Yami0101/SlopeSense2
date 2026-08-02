"""P6d — score every in-domain cell in Arunachal and write the map.

Produces:

    data/processed/susceptibility.tif        float32 relative index, 0-1
    data/processed/susceptibility_class.tif  uint8, 1..5 Very Low .. Very High
    reports/susceptibility_map.png           visual check
    reports/susceptibility_validation.json   success-rate + independent points

════════════════════════════════════════════════════════════════════════════
⚠️  OUT-OF-DOMAIN CELLS ARE NOT SCORED. THIS IS NOT OPTIONAL.
════════════════════════════════════════════════════════════════════════════
The model was trained only on slopes >10 deg that are not permanent ice, water
or alpine moss (LABELS_AND_SAMPLING.md §5). It has never seen a glacier. A
model asked to score terrain outside its training domain will return a
confident number anyway — that number is meaningless, and a reviewer who finds
a susceptibility value on a glacier is entitled to distrust the whole map.

So: everything outside the domain is written as nodata and must be rendered as
"not assessed", never as "low risk". Those are completely different claims.

════════════════════════════════════════════════════════════════════════════
HOW TO READ THE NUMBER
════════════════════════════════════════════════════════════════════════════
Trained on a 1:5 sample (16.67% positive) against a real mapped prevalence of
~1.3%. A score of 0.5 therefore does NOT mean "50% chance of failure". It is a
RELATIVE SUSCEPTIBILITY INDEX — valid for ranking and classing, not as a
probability. See train_susceptibility.py for why it cannot be rescaled into one.

The five classes are percentile cuts of the in-domain score distribution. They
are validated below by a SUCCESS RATE analysis: what fraction of *known*
landslides falls in each class. A usable map concentrates observed failures in
the top classes — if Very High held only 20% of known slides it would be no
better than drawing the classes at random.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import time
import warnings

import geopandas as gpd
import lightgbm as lgb
import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))
import grid as G
from common import INTERIM, LABELS, PROCESSED, ROOT

warnings.filterwarnings("ignore")

MODELS = ROOT / "models"
REPORTS = ROOT / "reports"

SLOPE_MIN = 10.0
LC_EXCLUDE = {70, 80, 100}
CATS = ["lc_class_cat", "geol_rockgr_cat", "geol_lithunit_cat"]
CLASS_CUTS = [50, 75, 90, 97]     # -> 5 classes; top class = top 3% of slopes
CLASS_NAMES = {1: "Very Low", 2: "Low", 3: "Moderate", 4: "High", 5: "Very High"}


def rd(p):
    with rasterio.open(p) as s:
        return s.read(1)


def main() -> None:
    t0 = time.time()
    REPORTS.mkdir(exist_ok=True)
    print("P6d — statewide susceptibility inference")

    meta = json.loads((MODELS / "_susceptibility_meta.json").read_text())
    feats = meta["features"]
    booster = lgb.Booster(model_file=str(MODELS / "susceptibility_full.txt"))
    print(f"  model: susceptibility_full.txt  ({len(feats)} features)")

    # --- rebuild the domain mask exactly as sample.py defined it ----------
    inside = rd(INTERIM / "state_mask.tif").astype(bool)
    slope = rd(INTERIM / "terrain" / "terrain_slope_deg.tif")
    lc = rd(INTERIM / "features" / "lc_class_cat.tif")
    with np.errstate(invalid="ignore"):
        domain = inside & ~np.isin(lc, list(LC_EXCLUDE)) & (slope > SLOPE_MIN)
    n_dom = int(domain.sum())
    if n_dom != meta_domain(meta):
        print(f"  ⚠ domain {n_dom:,} != sample-time domain — rules drifted")
    print(f"  domain: {n_dom:,} cells ({100*n_dom/inside.sum():.1f}% of state)")

    # --- score, fold partition at a time to bound memory ------------------
    score = np.full(G.SHAPE, np.nan, dtype=np.float32)
    done = 0
    for f in sorted(int(p.name.split("=")[1])
                    for p in (INTERIM / "grid_100m").glob("fold=*")):
        part = pd.read_parquet(INTERIM / "grid_100m" / f"fold={f}" / "part.parquet")
        r, c = part["row"].to_numpy(), part["col"].to_numpy()
        keep = domain[r, c]
        part = part[keep]
        r, c = r[keep], c[keep]
        if not len(part):
            continue
        for cc in CATS:
            part[cc] = part[cc].astype("category")
        p = booster.predict(part[feats], num_iteration=booster.best_iteration)
        score[r, c] = p.astype(np.float32)
        done += len(part)
        print(f"    fold {f}: scored {len(part):>9,}   total {done:>9,}", flush=True)

    v = score[domain]
    v = v[np.isfinite(v)]
    print(f"\n  scored {len(v):,} cells   "
          f"min {v.min():.3f}  med {np.median(v):.3f}  max {v.max():.3f}")

    # --- classes -----------------------------------------------------------
    cuts = np.percentile(v, CLASS_CUTS)
    print(f"  class cuts (percentile {CLASS_CUTS}): "
          + ", ".join(f"{x:.3f}" for x in cuts))
    cls = np.zeros(G.SHAPE, dtype=np.uint8)
    cls[domain] = np.digitize(score[domain], cuts).astype(np.uint8) + 1
    cls[~domain] = 0                     # 0 = not assessed

    prof = dict(driver="GTiff", height=G.NROWS, width=G.NCOLS, count=1,
                crs=G.CRS, transform=G.TRANSFORM, compress="deflate",
                tiled=True, blockxsize=256, blockysize=256)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    with rasterio.open(PROCESSED / "susceptibility.tif", "w",
                       dtype="float32", nodata=np.nan, **prof) as d:
        d.write(score, 1)
    with rasterio.open(PROCESSED / "susceptibility_class.tif", "w",
                       dtype="uint8", nodata=0, **prof) as d:
        d.write(cls, 1)
        d.update_tags(**{str(k): v for k, v in CLASS_NAMES.items()},
                      **{"0": "not assessed (out of domain)"})

    # --- SUCCESS RATE: do known slides concentrate in the top classes? ----
    pos = rd(INTERIM / "labels" / "label_slide.tif").astype(bool) & domain
    print(f"\n  success rate — {int(pos.sum()):,} mapped landslide cells in domain")
    print(f"  {'class':<12}{'% of area':>11}{'% of slides':>13}{'lift':>8}")
    rates = []
    for k in range(1, 6):
        m = cls == k
        area = m[domain].mean()
        hit = (pos & m).sum() / max(pos.sum(), 1)
        rates.append(dict(cls=k, name=CLASS_NAMES[k], area_frac=float(area),
                          slide_frac=float(hit), lift=float(hit / area) if area else 0))
        print(f"  {CLASS_NAMES[k]:<12}{100*area:>10.1f}%{100*hit:>12.1f}%"
              f"{hit/area if area else 0:>8.1f}x")
    top2 = sum(r["slide_frac"] for r in rates[3:])
    print(f"  -> High + Very High = {100*sum(r['area_frac'] for r in rates[3:]):.0f}% "
          f"of area holds {100*top2:.0f}% of known landslides")

    # --- point-inventory checks -------------------------------------------
    # ⚠️ These two are NOT equivalent, despite both being "held-out points".
    # Measured overlap with the training polygons (distance to nearest):
    #
    #     GSI points    84.6% sit EXACTLY on a training polygon  -> NOT independent
    #     NASA GLC       1.4% sit exactly on one, 47.2% >1 km    -> independent
    #
    # GSI points are centroids of the same failures GSI mapped as polygons, so
    # scoring them measures training-set RECALL, not generalisation. Quoting it
    # as independent validation would be circular and a reviewer comparing the
    # two files would catch it. NASA GLC is a genuinely separate inventory and
    # is the only honest external number we have.
    print("\n  point-inventory checks:")
    indep = {}
    OVERLAP = {"gsi-nlfc_landslides_point_arunachal.geojson":
               ("recall check", "NOT independent — 84.6% on training polygons"),
               "nasa-glc_landslides_point_arunachal.geojson":
               ("INDEPENDENT", "1.4% overlap; coarse geolocation attenuates")}
    for fn in ("gsi-nlfc_landslides_point_arunachal.geojson",
               "nasa-glc_landslides_point_arunachal.geojson"):
        p = LABELS / fn
        if not p.exists():
            continue
        g = gpd.read_file(p).to_crs(G.CRS)
        xs, ys = g.geometry.x.to_numpy(), g.geometry.y.to_numpy()
        rr, cc = G.xy_to_rowcol(xs, ys)
        ok = (rr >= 0) & (rr < G.NROWS) & (cc >= 0) & (cc < G.NCOLS)
        rr, cc = rr[ok], cc[ok]
        ind = domain[rr, cc]
        rr, cc = rr[ind], cc[ind]
        if not len(rr):
            continue
        kv = cls[rr, cc]
        hi = float((kv >= 4).mean())
        kind, note = OVERLAP.get(fn, ("?", ""))
        rand = sum(r["area_frac"] for r in rates[3:])
        indep[fn] = dict(points_in_domain=int(len(rr)),
                         frac_high_or_veryhigh=hi, kind=kind, caveat=note,
                         lift_vs_random=float(hi / rand) if rand else 0,
                         median_score=float(np.nanmedian(score[rr, cc])))
        print(f"    {fn.split('_')[0]:<10} [{kind:<11}] {len(rr):>5} pts   "
              f"{100*hi:>5.1f}% in High/Very High   "
              f"{hi/rand if rand else 0:.1f}x random")
        print(f"               {note}")

    (REPORTS / "susceptibility_validation.json").write_text(json.dumps({
        "domain_cells": n_dom, "scored": int(len(v)),
        "class_cuts_percentile": CLASS_CUTS,
        "class_cuts_value": [float(x) for x in cuts],
        "success_rate": rates,
        "independent_points": indep,
        "oof_auc": meta["oof_auc_pooled"],
        "score_meaning": meta["score_meaning"],
    }, indent=2))

    # --- picture -----------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    fig, ax = plt.subplots(1, 2, figsize=(17, 7))
    s = score.copy()
    im = ax[0].imshow(s, cmap="inferno", vmin=0, vmax=1)
    ax[0].set_title("Susceptibility index (relative, not probability)")
    plt.colorbar(im, ax=ax[0], fraction=0.03)
    cm = ListedColormap(["#e8e8e8", "#2c7bb6", "#abd9e9", "#ffffbf",
                         "#fdae61", "#d7191c"])
    c = np.where(domain, cls, 0)
    im2 = ax[1].imshow(c, cmap=cm, vmin=0, vmax=5)
    ax[1].set_title("Class (grey = not assessed: ice/water/flat)")
    cb = plt.colorbar(im2, ax=ax[1], fraction=0.03, ticks=range(6))
    cb.ax.set_yticklabels(["n/a"] + [CLASS_NAMES[k] for k in range(1, 6)])
    for a in ax:
        a.set_xticks([]); a.set_yticks([])
    plt.tight_layout()
    plt.savefig(REPORTS / "susceptibility_map.png", dpi=120)
    plt.close()

    print(f"\n  wrote susceptibility.tif, susceptibility_class.tif, "
          f"susceptibility_map.png")
    print(f"  done in {time.time()-t0:.0f}s")


def meta_domain(meta):
    try:
        return json.loads(
            (PROCESSED / "susceptibility_samples.meta.json").read_text())["domain_cells"]
    except Exception:
        return -1


if __name__ == "__main__":
    main()
