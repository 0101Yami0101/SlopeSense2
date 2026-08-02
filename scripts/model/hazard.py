"""P8c — hazard = susceptibility x trigger, and the end-to-end validation.

    python scripts/model/hazard.py                 # validate on the 72 events
    python scripts/model/hazard.py 2017-07-11      # map one day

Outputs:
    data/processed/hazard_<date>.tif
    reports/hazard_validation.json + .png

════════════════════════════════════════════════════════════════════════════
WHY MULTIPLY
════════════════════════════════════════════════════════════════════════════
    hazard = susceptibility (WHERE, 100 m, static)
           x trigger        (WHEN,  11 km, daily)

Both are necessary and neither is sufficient: a cliff in dry weather does not
fail, and a downpour on flat stable ground does nothing. Multiplication keeps
that — if either term is near zero the hazard is near zero. Adding them would
let a torrential day raise the hazard of flat ground, which is wrong.

The two terms come from completely different evidence. Susceptibility rests on
37,788 mapped polygons and scores AUC 0.860. The trigger rests on 72 dated
events and scores 0.768 ± 0.098. **The combined product is only as trustworthy
as its weaker half**, and the weaker half is the trigger — which is exactly why
PX (dating our own polygons) is the highest-leverage work remaining.

════════════════════════════════════════════════════════════════════════════
RESOLUTION IS DELIBERATELY MIXED
════════════════════════════════════════════════════════════════════════════
Susceptibility is genuinely 100 m. The trigger is genuinely 11 km and is NOT
downscaled — every 100 m cell inside one IMERG pixel gets the same trigger
value. The output therefore has 100 m spatial detail and 11 km rainfall detail.

⚠️ Say this on the map. A viewer sees crisp 100 m texture and will assume the
rainfall is that sharp too. It is not.

════════════════════════════════════════════════════════════════════════════
OUT-OF-DOMAIN STAYS OUT
════════════════════════════════════════════════════════════════════════════
Cells the susceptibility model never trained on (slope <=10 deg, ice, water,
alpine moss) are nodata here as well — never "low hazard". See
MODEL_SUSCEPTIBILITY.md §9.
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
from common import INTERIM, LABELS, PROCESSED, ROOT

warnings.filterwarnings("ignore")

SRC = INTERIM / "rainfall"
FEAT = SRC / "features"
MODELS = ROOT / "models"
REPORTS = ROOT / "reports"
MONSOON = (5, 10)
N_NEG = 20_000
SEED = 0


def load_ctx():
    cfg = json.loads((MODELS / "trigger.json").read_text())
    feats = cfg["trigger_definition"]["features"]
    with rasterio.open(SRC / "imerg_index.tif") as s:
        idx = s.read(1)
    dates = pd.to_datetime(np.load(SRC / "dates.npy").astype("datetime64[D]"))
    mo = dates.month.to_numpy()
    mons = (mo >= MONSOON[0]) & (mo <= MONSOON[1])
    clim = {n: np.asarray(np.load(FEAT / f"{n}.npy", mmap_mode="r")[mons],
                          dtype=np.float32) for n in feats}
    return cfg, feats, idx, dates, clim


def trigger_for_cells(feats, clim, t_idx, c_idx):
    """Percentile of each feature against that cell's own monsoon climatology."""
    out = []
    for n in feats:
        a = np.load(FEAT / f"{n}.npy", mmap_mode="r")
        out.append(np.array([(clim[n][:, cl] < a[t, cl]).mean()
                             for t, cl in zip(t_idx, c_idx)], dtype=np.float32))
    return np.mean(out, axis=0)


def trigger_grid(feats, clim, t: int) -> np.ndarray:
    """Trigger score for every IMERG cell on day t."""
    out = []
    for n in feats:
        a = np.load(FEAT / f"{n}.npy", mmap_mode="r")
        today = np.asarray(a[t], dtype=np.float32)
        out.append((clim[n] < today[None, :]).mean(axis=0))
    return np.mean(out, axis=0).astype(np.float32)


def map_one_day(datestr: str) -> None:
    cfg, feats, idx, dates, clim = load_ctx()
    day = pd.Timestamp(datestr)
    t = int(np.where(dates == day)[0][0])
    print(f"P8c — hazard map for {day:%Y-%m-%d}")

    trig_cells = trigger_grid(feats, clim, t)
    with rasterio.open(PROCESSED / "susceptibility.tif") as s:
        sus = s.read(1)
        prof = s.profile

    trig = np.full(G.SHAPE, np.nan, dtype=np.float32)
    ok = idx >= 0
    trig[ok] = trig_cells[idx[ok]]
    hz = (sus * trig).astype(np.float32)      # nodata propagates via NaN

    prof.update(dtype="float32", nodata=np.nan, compress="deflate")
    out = PROCESSED / f"hazard_{day:%Y%m%d}.tif"
    with rasterio.open(out, "w", **prof) as d:
        d.write(hz, 1)

    v = hz[np.isfinite(hz)]
    print(f"  susceptibility median {np.nanmedian(sus):.3f}")
    print(f"  trigger        median {np.nanmedian(trig):.3f}  "
          f"max {np.nanmax(trig):.3f}")
    print(f"  hazard         median {np.median(v):.4f}  "
          f"p99 {np.percentile(v,99):.4f}  max {v.max():.4f}")
    print(f"  wrote {out.name}")


def validate() -> None:
    cfg, feats, idx, dates, clim = load_ctx()
    print("P8c — end-to-end validation: does hazard beat either half alone?")

    dmap = {d: i for i, d in enumerate(dates)}
    g = gpd.read_file(LABELS / "nasa-glc_landslides_point_arunachal.geojson")
    g["dt"] = pd.to_datetime(g.ev_date, unit="ms", errors="coerce")
    g = g.dropna(subset=["dt"]).to_crs(G.CRS)
    r, c = G.xy_to_rowcol(g.geometry.x.to_numpy(), g.geometry.y.to_numpy())
    ok = (r >= 0) & (r < G.NROWS) & (c >= 0) & (c < G.NCOLS)
    g, r, c = g[ok], r[ok], c[ok]

    with rasterio.open(PROCESSED / "susceptibility.tif") as s:
        sus = s.read(1)
    cell = idx[r, c]
    ti = np.array([dmap.get(pd.Timestamp(d.date()), -1) for d in g.dt])
    keep = (cell >= 0) & (ti >= 0) & np.isfinite(sus[r, c])
    r, c, cell, ti = r[keep], c[keep], cell[keep], ti[keep]
    g = g[keep]                      # keep loc_accu aligned with the events
    print(f"  {len(ti)} events with BOTH a susceptibility score and rainfall")

    mo = dates.month.to_numpy()
    mons = (mo >= MONSOON[0]) & (mo <= MONSOON[1])
    rng = np.random.default_rng(SEED)

    # Negatives: random IN-DOMAIN cells on random monsoon days. Drawn from the
    # scored domain only, so we never compare against terrain the susceptibility
    # model was never asked about.
    dom_r, dom_c = np.nonzero(np.isfinite(sus))
    pick = rng.choice(len(dom_r), size=N_NEG)
    nr, nc_ = dom_r[pick], dom_c[pick]
    ncell = idx[nr, nc_]
    good = ncell >= 0
    nr, nc_, ncell = nr[good], nc_[good], ncell[good]
    nt = rng.choice(np.where(mons)[0], size=len(nr))

    sus_e, sus_n = sus[r, c], sus[nr, nc_]
    trg_e = trigger_for_cells(feats, clim, ti, cell)
    trg_n = trigger_for_cells(feats, clim, nt, ncell)

    y = np.r_[np.ones(len(sus_e)), np.zeros(len(sus_n))]
    res = {}
    print(f"\n  {'model':<28}{'AUC':>8}{'95% CI':>10}")
    for name, ev, ng in (
        ("susceptibility only (WHERE)", sus_e, sus_n),
        ("trigger only (WHEN)", trg_e, trg_n),
        ("HAZARD = sus x trigger", sus_e * trg_e, sus_n * trg_n),
    ):
        sc = np.r_[ev, ng]
        m = np.isfinite(sc)
        a = float(roc_auc_score(y[m], sc[m]))
        ci = 1.96 * np.sqrt(a * (1 - a) / len(ev))
        res[name] = dict(auc=a, ci95=float(ci))
        print(f"  {name:<28}{a:>8.3f}{ci:>9.3f}")

    # ── why the product does not beat the trigger here ───────────────────
    # ⚠️ This comparison is STRUCTURALLY UNFAIR to susceptibility and must not
    # be read as "susceptibility does not help". NASA GLC is the only dated
    # inventory and its location accuracy is km-level. A point off by 5 km lands
    # in the wrong 100 m susceptibility cell but usually the SAME 11 km rainfall
    # pixel — so geolocation error destroys the fine-resolution term while
    # barely touching the coarse one. Measured below.
    acc = g.loc_accu.to_numpy()
    print(f"\n  susceptibility AUC by label location accuracy:")
    by_acc = {}
    for label, keys in (("exact + 1km", ["exact", "1km"]),
                        ("5km + 10km", ["5km", "10km"]),
                        ("25km + 50km", ["25km", "50km"])):
        sub = sus_e[np.isin(acc, keys)]
        if len(sub) < 3:
            continue
        yy = np.r_[np.ones(len(sub)), np.zeros(len(sus_n))]
        a = float(roc_auc_score(yy, np.r_[sub, sus_n]))
        by_acc[label] = dict(n=int(len(sub)), auc=a)
        print(f"    {label:<14}n={len(sub):<4} AUC {a:.3f}")
    print("    ^ skill tracks label precision — the validation labels, not the")
    print("      model, are the limit. P6 measured 0.860 on precise polygons.")

    hz_e, hz_n = sus_e * trg_e, sus_n * trg_n
    print(f"\n  {'hazard >= pctile':<20}{'% of cell-days':>16}{'% of events':>13}{'lift':>8}")
    ops = []
    for q in (50, 75, 90, 95, 99):
        thr = np.percentile(hz_n, q)
        fa = float((hz_n >= thr).mean())
        hit = float((hz_e >= thr).mean())
        ops.append(dict(pctile=q, threshold=float(thr), alert_rate=fa,
                        capture=hit, lift=hit / fa if fa else 0))
        print(f"    p{q:<18}{100*fa:>15.1f}%{100*hit:>12.1f}%"
              f"{hit/fa if fa else 0:>8.1f}x")

    (REPORTS / "hazard_validation.json").write_text(json.dumps({
        "n_events": int(len(sus_e)), "n_negatives": int(len(sus_n)),
        "models": res, "operating_points": ops,
        "susceptibility_auc_by_label_accuracy": by_acc,
        "READ_THIS_FIRST":
            "These AUCs UNDERSTATE the system. The only dated inventory (NASA "
            "GLC) has km-level location error, which cripples a 100 m layer but "
            "barely touches an 11 km one — so the product scores below the "
            "trigger alone here. That is an artefact of the validation labels, "
            "not evidence that susceptibility is unhelpful: P6 measured 0.860 on "
            "precise polygons, and susceptibility AUC here rises from 0.601 on "
            "25-50 km labels to 0.776 on exact/1 km labels. The combined system "
            "cannot be honestly scored until PX supplies well-located dated "
            "events.",
    }, indent=2))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    for i, (t, ev, ng) in enumerate((
            ("Susceptibility (WHERE)", sus_e, sus_n),
            ("Trigger (WHEN)", trg_e, trg_n),
            ("Hazard = product", hz_e, hz_n))):
        b = np.linspace(0, max(np.nanmax(ng), np.nanmax(ev)), 30)
        ax[i].hist(ng, bins=b, density=True, alpha=.55, color="#999", label="random")
        ax[i].hist(ev, bins=b, density=True, alpha=.75, color="#d7191c", label="events")
        a = list(res.values())[i]["auc"]
        ax[i].set_title(f"{t}\nAUC {a:.3f}", fontsize=10)
        ax[i].legend(fontsize=8); ax[i].grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(REPORTS / "hazard_validation.png", dpi=130)
    print("\n  wrote reports/hazard_validation.{json,png}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        map_one_day(sys.argv[1])
    else:
        validate()
