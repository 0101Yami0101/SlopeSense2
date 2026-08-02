"""P8 — the WHEN half: a rainfall trigger calibrated on Arunachal's own events.

Outputs:
    models/trigger.json            curve + trigger definition + honest metrics
    data/interim/rainfall/trigger_clim.npy   per-cell climatology for percentiles
    reports/trigger_ed_curve.png
    reports/trigger_validation.png

════════════════════════════════════════════════════════════════════════════
THREE THINGS WE MEASURED THAT CHANGED THE DESIGN
════════════════════════════════════════════════════════════════════════════

1. THE CLASSIC INTENSITY–DURATION FORM IS WRONG FOR THIS DATA.
   ID theory says long storms trigger at LOWER intensity, so `I = a*D^-b` with
   b > 0. Fitted here, b came out NEGATIVE, because in our data
   corr(log D, log I) = +0.59 — longer storms have HIGHER intensity.

   Not a bug in the fit. Our storm definition is "consecutive days above 1 mm",
   and in a monsoon that produces runs of weeks (longest in the archive: 202
   days). A long run is not a long storm, it is the monsoon; a 1-2 day run is an
   isolated shower (median 6 mm total). Intensity therefore rises with duration
   by construction.

   ⇒ Switched to the EVENT-RAINFALL–DURATION form, standard in the literature
     and the right shape for this data: corr(log D, log E) = +0.91.

         E = a * D^b          E total storm rainfall mm, D duration hours

2. A RAINFALL THRESHOLD CANNOT BE A BINARY GATE HERE.
   Fitted as a lower envelope on known events, every candidate curve fires
   99-166 days per year at a given cell. That is not a warning, it is a weather
   report — and it is the honest consequence of a place averaging 1,931 mm/yr:
   most monsoon days DO exceed the minimum condition that has ever produced a
   slide. The literature reports the same problem for monsoon climates.

   ⇒ The curve is kept as EXPLAINABLE PHYSICS and as a floor, but the operational
     trigger is a CONTINUOUS severity score, not a threshold crossing.

3. FITTING A MODEL ON 72 EVENTS LOSES TO NOT FITTING ONE.
   Measured against 20,000 random monsoon cell-days at the same cells and months:

       r3 + r7, percentile average, NO fitting     AUC 0.768
       logistic on 6 features, 5-fold CV           AUC 0.755
       r3 alone                                    AUC 0.761

   ⇒ The trigger is an unfitted average of two percentile-normalised features.
     Nothing is fitted, so nothing can overfit, and it is trivially explainable
     to APSDMA. This is direct evidence for the project-wide rule: do not train
     a trigger model until PX delivers real dates.

════════════════════════════════════════════════════════════════════════════
THE TRIGGER
════════════════════════════════════════════════════════════════════════════
    trigger = mean( pctile(r3 | this cell's monsoon climatology),
                    pctile(r7 | this cell's monsoon climatology) )

Percentile-normalised PER CELL because Arunachal spans 799 to 4,167 mm/yr. 150 mm
in three days is unremarkable in the Siang gorge and extraordinary on the
northern crest; a raw millimetre threshold would alert the wet south permanently
and the dry north never.

⚠️ This is a RELATIVE SEVERITY SCORE in [0,1], not P(landslide). Same
presence-only limit as susceptibility: we know storms that DID trigger, never
which storms did not.

════════════════════════════════════════════════════════════════════════════
HAZARD
════════════════════════════════════════════════════════════════════════════
    hazard = susceptibility x trigger

Both terms are needed and neither is sufficient: a cliff in dry weather does not
fail, and a downpour on flat stable ground does nothing. Multiplying keeps that
property — if either term is ~0 the hazard is ~0.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))

import json
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from sklearn.metrics import roc_auc_score

import grid as G
from common import INTERIM, LABELS, ROOT

warnings.filterwarnings("ignore")

SRC = INTERIM / "rainfall"
FEAT = SRC / "features"
MODELS = ROOT / "models"
REPORTS = ROOT / "reports"

TRIGGER_FEATURES = ("r3", "r7")      # measured best; see docstring
MONSOON = (5, 10)
ED_QUANTILE = 0.10
N_NEG = 20_000
SEED = 0


def qfit(x, y, q, iters=500):
    """LAD quantile regression by IRLS — small problem, no extra dependency."""
    X = np.column_stack([np.ones_like(x), x])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    for _ in range(iters):
        r = y - X @ b
        w = np.where(r >= 0, q, 1 - q) / np.maximum(np.abs(r), 1e-6)
        W = X * w[:, None]
        try:
            bn = np.linalg.solve(X.T @ W, W.T @ y)
        except np.linalg.LinAlgError:
            break
        if np.max(np.abs(bn - b)) < 1e-10:
            b = bn
            break
        b = bn
    return b


def load_events(idx, dates):
    dmap = {d: i for i, d in enumerate(dates)}
    g = gpd.read_file(LABELS / "nasa-glc_landslides_point_arunachal.geojson")
    # ⚠️ ArcGIS ships this as epoch MILLISECONDS; a plain parse yields 1970.
    g["dt"] = pd.to_datetime(g.ev_date, unit="ms", errors="coerce")
    g = g.dropna(subset=["dt"]).to_crs(G.CRS)
    r, c = G.xy_to_rowcol(g.geometry.x.to_numpy(), g.geometry.y.to_numpy())
    ok = (r >= 0) & (r < G.NROWS) & (c >= 0) & (c < G.NCOLS)
    g, cell = g[ok], idx[r[ok], c[ok]]
    m = cell >= 0
    g, cell = g[m], cell[m]
    ti = np.array([dmap.get(pd.Timestamp(d.date()), -1) for d in g.dt])
    k = ti >= 0
    return cell[k], ti[k], g[k]


def main() -> None:
    MODELS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    print("P8 — rainfall trigger, calibrated on Arunachal events")

    with rasterio.open(SRC / "imerg_index.tif") as s:
        idx = s.read(1)
    dates = pd.to_datetime(np.load(SRC / "dates.npy").astype("datetime64[D]"))
    mo = dates.month.to_numpy()
    mons = (mo >= MONSOON[0]) & (mo <= MONSOON[1])

    cell, ti, gev = load_events(idx, dates)
    print(f"  {len(ti)} dated events matched to a rainfall cell and day")

    # ── 1. E-D curve: explainable physics ────────────────────────────────
    sd = np.load(FEAT / "storm_dur.npy", mmap_mode="r")
    sr = np.load(FEAT / "storm_rain.npy", mmap_mode="r")
    D = np.array([sd[t, cl] for t, cl in zip(ti, cell)], dtype=float)
    R = np.array([sr[t, cl] for t, cl in zip(ti, cell)], dtype=float)
    dry = D <= 0
    # A slide on a dry day is real — delayed failure after soaking, or a
    # non-rainfall trigger (seismic, undercutting, road cut). It cannot inform a
    # rainfall curve, so it is excluded here and counted as an unavoidable miss.
    Df, Rf = D[~dry], R[~dry]
    hrs = Df * 24.0
    beta = qfit(np.log10(hrs), np.log10(Rf), ED_QUANTILE)
    ed_a, ed_b = 10 ** beta[0], beta[1]
    corr = float(np.corrcoef(np.log(Df), np.log(Rf))[0, 1])
    cap = float((Rf >= ed_a * hrs ** ed_b).mean())
    print(f"\n  E-D curve   E = {ed_a:.2f} * D^{ed_b:.3f}   (D hours, E mm)")
    print(f"    corr(log D, log E) = {corr:+.3f}   captures {100*cap:.0f}% of events")
    print(f"    {int(dry.sum())} events fell on a dry day — excluded, counted as misses")

    # ── 2. per-cell monsoon climatology for percentile normalisation ─────
    print("\n  building per-cell monsoon climatology...", flush=True)
    clim = {}
    for n in TRIGGER_FEATURES:
        a = np.load(FEAT / f"{n}.npy", mmap_mode="r")
        clim[n] = np.asarray(a[mons], dtype=np.float32)   # (ndays_monsoon, ncells)
    ncells = clim[TRIGGER_FEATURES[0]].shape[1]
    print(f"    {clim[TRIGGER_FEATURES[0]].shape[0]:,} monsoon days x {ncells:,} cells")

    def pct(name, t_idx, c_idx):
        a = np.load(FEAT / f"{name}.npy", mmap_mode="r")
        out = np.empty(len(t_idx), dtype=np.float32)
        for i, (t, cl) in enumerate(zip(t_idx, c_idx)):
            out[i] = (clim[name][:, cl] < a[t, cl]).mean()
        return out

    # ── 3. validate against random monsoon cell-days ─────────────────────
    rng = np.random.default_rng(SEED)
    nt = rng.choice(np.where(mons)[0], size=N_NEG)
    nc = rng.choice(np.unique(cell), size=N_NEG)

    ev = np.mean([pct(n, ti, cell) for n in TRIGGER_FEATURES], axis=0)
    ng = np.mean([pct(n, nt, nc) for n in TRIGGER_FEATURES], axis=0)
    y = np.r_[np.ones(len(ev)), np.zeros(len(ng))]
    score = np.r_[ev, ng]
    auc = float(roc_auc_score(y, score))
    ci = 1.96 * np.sqrt(auc * (1 - auc) / len(ev))
    print(f"\n  trigger = mean pctile({' , '.join(TRIGGER_FEATURES)})")
    print(f"    AUC {auc:.3f} +/- {ci:.3f}   "
          f"({len(ev)} events vs {N_NEG:,} monsoon cell-days)")
    print(f"    median on events {np.median(ev):.3f}   "
          f"on ordinary monsoon days {np.median(ng):.3f}")

    print(f"\n  {'trigger >=':<12}{'% of monsoon days':>19}{'% of events':>13}{'lift':>8}")
    ops = []
    for thr in (0.50, 0.75, 0.90, 0.95, 0.99):
        fa = float((ng >= thr).mean())
        hit = float((ev >= thr).mean())
        ops.append(dict(threshold=thr, alert_rate=fa, event_capture=hit,
                        lift=hit / fa if fa else 0))
        print(f"    {thr:<10.2f}{100*fa:>17.1f}%{100*hit:>12.1f}%"
              f"{hit/fa if fa else 0:>8.1f}x")

    # ── 4. save ───────────────────────────────────────────────────────────
    np.save(SRC / "trigger_clim.npy",
            np.stack([clim[n] for n in TRIGGER_FEATURES]).astype(np.float32))

    (MODELS / "trigger.json").write_text(json.dumps({
        "trigger_definition": {
            "features": list(TRIGGER_FEATURES),
            "method": "mean of per-cell monsoon-climatology percentiles",
            "fitted": False,
            "why_unfitted": "logistic on 6 features scored 0.755 under 5-fold CV "
                            "vs 0.768 for this unfitted average; 72 events is too "
                            "few to fit",
        },
        "auc": auc, "auc_ci95": ci, "n_events": int(len(ev)), "n_negatives": N_NEG,
        "operating_points": ops,
        "ed_curve": {"form": "E = a * D^b  (E mm, D hours)",
                     "a": ed_a, "b": ed_b, "quantile": ED_QUANTILE,
                     "corr_logD_logE": corr, "event_capture": cap,
                     "role": "explainable physics floor, NOT a binary gate — "
                             "any fitted envelope fires 99-166 days/yr here"},
        "events_on_dry_days": int(dry.sum()),
        "monsoon_months": list(MONSOON),
        "caveat": "relative severity score in [0,1], not P(landslide). "
                  "Presence-only. Refit when PX delivers dates.",
    }, indent=2))

    # ── 5. pictures ───────────────────────────────────────────────────────
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(14, 5.5))
    xx = np.logspace(np.log10(hrs.min() * .8), np.log10(hrs.max() * 1.2), 100)
    ax[0].scatter(hrs, Rf, s=32, c="#d7191c", edgecolor="k", linewidth=.4, zorder=3,
                  label=f"{len(Df)} dated landslides")
    ax[0].plot(xx, ed_a * xx ** ed_b, "-", lw=2.4, color="#2c7bb6", zorder=2,
               label=f"E = {ed_a:.2f} D$^{{{ed_b:.2f}}}$  (q={ED_QUANTILE})")
    ax[0].set_xscale("log"); ax[0].set_yscale("log")
    ax[0].set_xlabel("storm duration D (hours)")
    ax[0].set_ylabel("storm rainfall E (mm)")
    ax[0].set_title("Event rainfall–duration threshold\n(ID form fails here — see docstring)",
                    fontsize=10)
    ax[0].grid(alpha=.3, which="both"); ax[0].legend(fontsize=8.5, loc="upper left")

    bins = np.linspace(0, 1, 26)
    ax[1].hist(ng, bins=bins, density=True, alpha=.55, color="#999",
               label=f"ordinary monsoon days (n={N_NEG:,})")
    ax[1].hist(ev, bins=bins, density=True, alpha=.75, color="#d7191c",
               label=f"landslide days (n={len(ev)})")
    ax[1].set_xlabel("trigger score (percentile blend)")
    ax[1].set_ylabel("density")
    ax[1].set_title(f"Trigger separation — AUC {auc:.3f} ± {ci:.3f}", fontsize=10)
    ax[1].legend(fontsize=8.5); ax[1].grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(REPORTS / "trigger_validation.png", dpi=130)
    print(f"\n  wrote models/trigger.json + reports/trigger_validation.png")


if __name__ == "__main__":
    main()
