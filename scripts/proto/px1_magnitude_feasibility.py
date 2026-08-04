"""PX1 — can we forecast HOW BIG a landslide will be, not just whether?

The client's question, in their words: "0.99 — small slide, 0.76 — major
slide". That is two completely different questions wearing one sentence, and
they have different answers:

  GATE A  Does the rainfall trigger predict the SIZE of the event it triggers?
          This is the forecastable version — it would let a daily bulletin say
          "today's rain would produce a large failure". Needs events that carry
          BOTH a date and a size. We have 90.

  GATE B  Does the terrain predict the TYPICAL size of failures at a place?
          This is a static map, not a forecast — but it is trainable on 37,788
          measured polygon areas, three orders of magnitude more data.

Run:  .venv/Scripts/python scripts/proto/px1_magnitude_feasibility.py

Both gates are cheap and both are checked against a null, because "we found a
correlation" on 90 points is worth nothing without knowing what noise looks
like at n=90.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from scipy.stats import kruskal, spearmanr

import grid as G
from common import INTERIM, LABELS, ROOT

warnings.filterwarnings("ignore")

SRC = INTERIM / "rainfall"
FEAT = SRC / "features"
TERRAIN = INTERIM / "terrain"
FEATDIR = INTERIM / "features"
REPORTS = ROOT / "reports"

SIZE_ORDER = {"small": 0, "medium": 1, "large": 2, "very_large": 3}
POLYGONS = [
    ("gsi-nlfc_landslides_polygon_arunachal.geojson", "GSI"),
    ("bhuvan_ar_slim_2014_gcs_polygon_arunachal.geojson", "Bhuvan 2014"),
    ("bhuvan_ar_slim_2017_polygon_arunachal.geojson", "Bhuvan 2017"),
    ("bhuvan_ls_arunachal_2023_polygon_arunachal.geojson", "Bhuvan 2023"),
]
SEED = 0
N_PERM = 20_000


# ═══════════════════════ GATE A — rainfall -> event size ════════════════════
def gate_a() -> dict:
    print("\n" + "=" * 74)
    print("GATE A — does the rainfall trigger predict the SIZE of the event?")
    print("=" * 74)

    with rasterio.open(SRC / "imerg_index.tif") as s:
        idx = s.read(1)
    dates = pd.to_datetime(np.load(SRC / "dates.npy").astype("datetime64[D]"))
    dmap = {d: i for i, d in enumerate(dates)}

    g = gpd.read_file(LABELS / "nasa-glc_landslides_point_arunachal.geojson")
    # ⚠️ ArcGIS ships ev_date as epoch MILLISECONDS; a plain parse yields 1970.
    g["dt"] = pd.to_datetime(g.ev_date, unit="ms", errors="coerce")
    g["size"] = g.ls_size.astype(str).str.strip().str.lower().map(SIZE_ORDER)
    n_all = len(g)
    g = g.dropna(subset=["dt", "size"])
    print(f"  {n_all} catalogued events, {len(g)} carry BOTH a date and a size")

    g = g.to_crs(G.CRS)
    r, c = G.xy_to_rowcol(g.geometry.x.to_numpy(), g.geometry.y.to_numpy())
    ok = (r >= 0) & (r < G.NROWS) & (c >= 0) & (c < G.NCOLS)
    g, cell = g[ok], idx[r[ok], c[ok]]
    m = cell >= 0
    g, cell = g[m], cell[m]
    ti = np.array([dmap.get(pd.Timestamp(d.date()), -1) for d in g.dt])
    k = ti >= 0
    g, cell, ti = g[k], cell[k], ti[k]
    size = g["size"].to_numpy().astype(int)
    print(f"  {len(ti)} of those also match a rainfall cell and day")

    # Trigger = mean percentile of the r3 and r7 totals against that cell's own
    # MONSOON climatology. Copied from trigger.py deliberately: comparing an
    # event against the all-year distribution would inflate every percentile,
    # since half the year is dry, and the gate would then be testing a
    # different quantity from the one the app ships.
    mo = dates.month.to_numpy()
    mons = (mo >= 5) & (mo <= 10)
    trig = []
    for f in ("r3", "r7"):
        a = np.load(FEAT / f"{f}.npy", mmap_mode="r")
        clim = np.asarray(a[mons], dtype=np.float32)
        trig.append(np.array([(clim[:, cl] < a[t_, cl]).mean()
                              for t_, cl in zip(ti, cell)]))
    t = np.mean(trig, axis=0)

    names = {v: k for k, v in SIZE_ORDER.items()}
    print(f"\n  {'size':<12}{'n':>5}{'median trigger':>17}{'mean':>8}")
    groups = []
    for s in sorted(set(size)):
        v = t[size == s]
        groups.append(v)
        print(f"  {names[s]:<12}{len(v):>5}{np.median(v):>17.3f}{v.mean():>8.3f}")

    rho, p_rho = spearmanr(t, size)
    print(f"\n  Spearman(trigger, size)     rho = {rho:+.3f}   p = {p_rho:.3f}")
    if len(groups) > 1:
        h, p_kw = kruskal(*[gp for gp in groups if len(gp) > 0])
        print(f"  Kruskal-Wallis across sizes   H = {h:.2f}      p = {p_kw:.3f}")
    else:
        p_kw = 1.0

    # What does pure noise look like at this n? Shuffle the labels.
    rng = np.random.default_rng(SEED)
    null = np.array([abs(spearmanr(t, rng.permutation(size)).statistic)
                     for _ in range(2000)])
    print(f"  Shuffled-label null: |rho| exceeds {abs(rho):.3f} on "
          f"{100 * (null >= abs(rho)).mean():.1f}% of random relabellings")
    print(f"  (95th percentile of noise at n={len(t)} is |rho| = "
          f"{np.percentile(null, 95):.3f})")

    passed = bool(p_rho < 0.05 and abs(rho) >= 0.25)
    print(f"\n  VERDICT: {'PASS' if passed else 'FAIL'} — "
          + ("rainfall carries usable information about event size"
             if passed else
             "rainfall does NOT separate small from large failures here"))
    return {"n_dated_sized": int(len(t)), "rho": float(rho), "p": float(p_rho),
            "p_kruskal": float(p_kw), "passed": passed,
            "by_size": {names[s]: int((size == s).sum()) for s in sorted(set(size))}}


# ═══════════════════════ GATE B — terrain -> typical size ═══════════════════
def _sample(paths: dict[str, Path], xs: np.ndarray, ys: np.ndarray) -> pd.DataFrame:
    out = {}
    for name, p in paths.items():
        with rasterio.open(p) as s:
            v = np.array([x[0] for x in s.sample(zip(xs, ys))], dtype="float64")
            if s.nodata is not None:
                v[v == s.nodata] = np.nan
        out[name] = v
    return pd.DataFrame(out)


def gate_b() -> dict:
    print("\n" + "=" * 74)
    print("GATE B — does the TERRAIN predict the typical size of failures there?")
    print("=" * 74)

    frames = []
    for fn, label in POLYGONS:
        g = gpd.read_file(LABELS / fn).to_crs(G.CRS)
        g = g[g.geometry.notna() & g.geometry.is_valid]
        cen = g.geometry.centroid
        frames.append(pd.DataFrame({"src": label, "area_m2": g.geometry.area.to_numpy(),
                                    "x": cen.x.to_numpy(), "y": cen.y.to_numpy()}))
    df = pd.concat(frames, ignore_index=True)
    df = df[df.area_m2 > 0]
    print(f"  {len(df):,} mapped polygons with a measured area")
    print(f"  area m2:  median {df.area_m2.median():,.0f}   "
          f"p90 {df.area_m2.quantile(.9):,.0f}   max {df.area_m2.max():,.0f}")
    print(f"  spread: the largest is {df.area_m2.max()/df.area_m2.median():,.0f}x "
          f"the median — there IS something to predict")

    paths = {p.stem: p for p in sorted(TERRAIN.glob("*.tif"))
             if not p.stem.startswith("_")}
    paths |= {p.stem: p for p in sorted(FEATDIR.glob("*.tif"))}
    X = _sample(paths, df.x.to_numpy(), df.y.to_numpy())
    df = pd.concat([df.reset_index(drop=True), X], axis=1).dropna(
        subset=[c for c in X.columns if c.startswith("terrain_")])
    print(f"  {len(df):,} polygons sampled against {len(paths)} terrain/soil layers")

    # Spatial blocks, so a model cannot score by memorising one valley. Same
    # 50 km grid the susceptibility model uses.
    block = 50_000
    df["block"] = ((df.x // block).astype(int).astype(str) + "_"
                   + (df.y // block).astype(int).astype(str))
    blocks = df.block.unique()
    rng = np.random.default_rng(SEED)
    rng.shuffle(blocks)
    fold_of = {b: i % 5 for i, b in enumerate(blocks)}
    df["fold"] = df.block.map(fold_of)
    print(f"  {len(blocks)} spatial blocks -> 5 folds")

    import lightgbm as lgb
    feats = [c for c in X.columns]
    y = np.log10(df.area_m2.to_numpy())
    rhos, r2s = [], []
    for f in range(5):
        tr, te = df.fold != f, df.fold == f
        if te.sum() < 50:
            continue
        mdl = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05,
                                num_leaves=63, min_child_samples=40,
                                subsample=0.8, colsample_bytree=0.8,
                                random_state=SEED, verbose=-1)
        mdl.fit(df.loc[tr, feats], y[tr.to_numpy()])
        pred = mdl.predict(df.loc[te, feats])
        yt = y[te.to_numpy()]
        rhos.append(spearmanr(pred, yt).statistic)
        r2s.append(1 - ((yt - pred) ** 2).sum() / ((yt - yt.mean()) ** 2).sum())
    rho, r2 = float(np.mean(rhos)), float(np.mean(r2s))
    print(f"\n  Spatial-CV Spearman(predicted, actual log area) = {rho:+.3f} "
          f"(fold sd {np.std(rhos):.3f})")
    print(f"  Spatial-CV R^2 on log area                       = {r2:+.3f}")

    # Baseline: predict the training mean for everyone. R^2 = 0 by definition,
    # so the honest comparison is how much of the SPREAD we removed.
    resid = np.std(y) * np.sqrt(max(1 - r2, 0))
    print(f"  Typical error: predicting area to within a factor of "
          f"{10**resid:.1f}x (spread of the data itself is a factor of "
          f"{10**np.std(y):.1f}x)")

    # ── the number that settles it ───────────────────────────────────────
    # Before blaming the model, check whether the TARGET is even a physical
    # quantity. Each survey has its own minimum mapping unit and its own habit
    # about splitting or merging adjacent scars.
    grand = np.var(y)
    within = float(df.assign(la=y).groupby("src").la.var().mean())
    survey_frac = float(1 - within / grand)
    print(f"\n  Variance in log area explained by WHICH SURVEY mapped it: "
          f"{survey_frac:.3f}")
    print(f"  Variance explained by all 34 terrain and soil layers:      "
          f"{max(r2, 0):.3f}")
    print("  -> polygon 'size' tracks the mapping team more than the hillside.")
    print(df.assign(la=y).groupby("src").la.agg(["count", "median"]).round(2)
          .to_string().replace("\n", "\n     "))

    passed = bool(rho >= 0.30 and r2 > 0.05)
    print(f"\n  VERDICT: {'PASS' if passed else 'FAIL'} — "
          + ("terrain ranks big-failure ground above small-failure ground"
             if passed else
             "terrain ranks size barely above chance and predicts no magnitude"))
    return {"n_polygons": int(len(df)), "spearman": rho, "r2": r2,
            "factor_error": float(10 ** resid), "passed": passed,
            "variance_from_survey_identity": survey_frac}


def main() -> None:
    print("PX1 — magnitude feasibility: can we say HOW BIG, not just whether?")
    a = gate_a()
    b = gate_b()

    print("\n" + "=" * 74)
    print("WHAT THIS MEANS FOR THE PRODUCT")
    print("=" * 74)
    if not a["passed"] and b["passed"]:
        print("  A daily 'how big will it be' forecast is NOT supported: the")
        print(f"  rainfall trigger does not separate sizes over {a['n_dated_sized']} events.")
        print("  A STATIC 'typical failure size here' map IS supported, from")
        print(f"  {b['n_polygons']:,} measured polygons. It is a map, not a forecast —")
        print("  it must never be labelled as one.")
    elif a["passed"]:
        print("  Both routes open. Build the static size map first (more data),")
        print("  then test whether the trigger shifts it day to day.")
    else:
        print("  Neither gate passes. Report size as a property of the")
        print("  inventory only, with no predictive claim attached.")

    REPORTS.mkdir(exist_ok=True)
    import json
    (REPORTS / "px1_magnitude.json").write_text(
        json.dumps({"gate_a_rainfall_to_size": a,
                    "gate_b_terrain_to_size": b}, indent=2))
    print(f"\n  wrote {REPORTS / 'px1_magnitude.json'}")


if __name__ == "__main__":
    main()
