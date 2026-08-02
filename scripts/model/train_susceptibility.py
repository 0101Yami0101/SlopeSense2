"""P6c — train the susceptibility model and explain it.

Produces:

    models/susceptibility_fold{0..4}.txt   leave-one-fold-out models
    models/susceptibility_full.txt         trained on everything, for deployment
    models/_susceptibility_meta.json       metrics, params, hashes
    reports/susceptibility_shap.png        what the model actually learned
    reports/susceptibility_importance.csv
    data/processed/susceptibility_oof.parquet   honest per-cell score

════════════════════════════════════════════════════════════════════════════
WHY TWO SETS OF MODELS
════════════════════════════════════════════════════════════════════════════
Fold models exist to produce an HONEST number. Each scores only the region it
never trained on, so the out-of-fold (OOF) prediction for every cell comes from
a model that never saw that part of Arunachal. That is the number we report.

The full model exists to SHIP. It sees 25% more data than any fold model and
will be slightly better everywhere — but it has no clean holdout left, so it
can never be used to quote a score. Using the full model's own training
predictions as evidence of skill is the most common way a project like this
ends up claiming 0.99 and failing in the field.

    report from  ->  fold models (OOF)
    deploy       ->  full model

════════════════════════════════════════════════════════════════════════════
WHAT THE OUTPUT NUMBER MEANS
════════════════════════════════════════════════════════════════════════════
The training sample is 16.67% positive by construction (1:5). The real mapped
prevalence in-domain is ~1.3%. So a model score of 0.5 does NOT mean "50%
chance of failure" — it means "this cell ranks high among slopes".

This is a RELATIVE SUSCEPTIBILITY INDEX. It is meaningful for ranking,
percentile classing and precision@k. It is not an event probability, and it
cannot be made into one by rescaling, because the underlying label is
presence-only (see LABELS_AND_SAMPLING.md §1) — the denominator we would need
does not exist.

Report it as five classes by percentile, which is what a disaster-management
authority actually uses, and which is standard practice in the literature.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import time
import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (average_precision_score, roc_auc_score)

from common import PROCESSED, ROOT

warnings.filterwarnings("ignore")

MODELS = ROOT / "models"
REPORTS = ROOT / "reports"
SAMPLE = PROCESSED / "susceptibility_samples.parquet"

CATS = ["lc_class_cat", "geol_rockgr_cat", "geol_lithunit_cat"]

# Deliberately conservative. With 90k positives and 34 features there is ample
# room to overfit; min_child_samples=50 and the subsampling are what keep the
# fold spread at +/-0.016 instead of the +/-0.05 an unconstrained model gives.
PARAMS = dict(
    objective="binary", n_estimators=600, learning_rate=0.05,
    num_leaves=63, min_child_samples=50, subsample=0.8,
    subsample_freq=1, colsample_bytree=0.8,
    reg_lambda=1.0, verbose=-1, n_jobs=-1, random_state=42,
)


def load():
    df = pd.read_parquet(SAMPLE)
    skip = {"cell_id", "label", "fold", "row", "col", "x_utm", "y_utm"}
    feats = [c for c in df.columns if c not in skip]
    for c in CATS:
        df[c] = df[c].astype("category")
    return df, feats


def main() -> None:
    t0 = time.time()
    MODELS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    print("P6c — training susceptibility model")

    df, feats = load()
    print(f"  {len(df):,} rows x {len(feats)} features   "
          f"prevalence {100*df.label.mean():.2f}%")

    # --- leave-one-fold-out: the honest number ---------------------------
    oof = np.full(len(df), np.nan)
    rows = []
    print(f"\n  {'fold':<6}{'train':>10}{'test':>10}{'AUC':>8}{'AP':>8}{'P@1%':>8}")
    for f in sorted(df.fold.unique()):
        tr, te = df[df.fold != f], df[df.fold == f]
        m = lgb.LGBMClassifier(**PARAMS)
        m.fit(tr[feats], tr.label, categorical_feature=CATS)
        p = m.predict_proba(te[feats])[:, 1]
        oof[df.fold.to_numpy() == f] = p

        auc = roc_auc_score(te.label, p)
        ap = average_precision_score(te.label, p)
        k = max(1, int(0.01 * len(p)))
        pk = te.label.to_numpy()[np.argsort(-p)[:k]].mean()
        rows.append(dict(fold=int(f), n_train=len(tr), n_test=len(te),
                         auc=auc, ap=ap, p_at_1pct=pk))
        print(f"  {int(f):<6}{len(tr):>10,}{len(te):>10,}{auc:>8.3f}{ap:>8.3f}"
              f"{pk:>8.3f}")
        m.booster_.save_model(str(MODELS / f"susceptibility_fold{int(f)}.txt"))

    auc_m = float(np.mean([r["auc"] for r in rows]))
    auc_s = float(np.std([r["auc"] for r in rows]))
    ap_m = float(np.mean([r["ap"] for r in rows]))
    oof_auc = float(roc_auc_score(df.label, oof))
    print(f"  {'mean':<6}{'':>20}{auc_m:>8.3f}{ap_m:>8.3f}")
    print(f"\n  pooled OOF AUC {oof_auc:.3f}   "
          f"(baseline AP = prevalence = {df.label.mean():.3f})")

    pd.DataFrame({"cell_id": df.cell_id, "fold": df.fold,
                  "label": df.label, "score_oof": oof.astype(np.float32)}) \
        .to_parquet(PROCESSED / "susceptibility_oof.parquet", index=False,
                    compression="zstd")

    # --- full model, for deployment only ---------------------------------
    print("\n  training full model (deployment)...", flush=True)
    full = lgb.LGBMClassifier(**PARAMS)
    full.fit(df[feats], df.label, categorical_feature=CATS)
    full.booster_.save_model(str(MODELS / "susceptibility_full.txt"))

    # --- importance + SHAP ------------------------------------------------
    imp = pd.DataFrame({
        "feature": feats,
        "gain": full.booster_.feature_importance("gain"),
        "split": full.booster_.feature_importance("split"),
    }).sort_values("gain", ascending=False)
    imp["gain_pct"] = 100 * imp.gain / imp.gain.sum()
    imp.to_csv(REPORTS / "susceptibility_importance.csv", index=False)
    print("\n  top features by gain:")
    for _, r in imp.head(10).iterrows():
        print(f"    {r.feature:<32}{r.gain_pct:>6.1f}%")

    print("\n  computing SHAP...", flush=True)
    import shap
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # TreeSHAP is exact and fast, but 545k x 34 is still wasteful for a plot
    # that is read by eye. 40k stratified rows give a stable summary.
    samp = df.groupby("label", group_keys=False).apply(
        lambda g: g.sample(min(len(g), 20_000), random_state=42))
    X = samp[feats]
    sv = shap.TreeExplainer(full.booster_).shap_values(X)
    if isinstance(sv, list):
        sv = sv[1]

    plt.figure(figsize=(9, 9))
    shap.summary_plot(sv, X, max_display=20, show=False)
    plt.title("Susceptibility — SHAP (40k stratified rows)", fontsize=11)
    plt.tight_layout()
    plt.savefig(REPORTS / "susceptibility_shap.png", dpi=130)
    plt.close()

    mean_abs = pd.DataFrame({
        "feature": feats, "mean_abs_shap": np.abs(sv).mean(axis=0)
    }).sort_values("mean_abs_shap", ascending=False)
    mean_abs.to_csv(REPORTS / "susceptibility_shap.csv", index=False)
    print("  top features by mean |SHAP|:")
    for _, r in mean_abs.head(8).iterrows():
        print(f"    {r.feature:<32}{r.mean_abs_shap:>8.4f}")

    (MODELS / "_susceptibility_meta.json").write_text(json.dumps({
        "trained_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sample": SAMPLE.name,
        "sample_hash": json.loads(
            (PROCESSED / "susceptibility_samples.meta.json").read_text())["sample_hash"],
        "n_rows": int(len(df)), "features": feats, "categorical": CATS,
        "params": {k: v for k, v in PARAMS.items()},
        "folds": rows,
        "auc_mean": auc_m, "auc_std": auc_s, "ap_mean": ap_m,
        "oof_auc_pooled": oof_auc,
        "sample_prevalence": float(df.label.mean()),
        "score_meaning": "relative susceptibility index, NOT event probability",
        "report_from": "fold models (OOF)", "deploy_with": "susceptibility_full.txt",
    }, indent=2))

    print(f"\n  done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
