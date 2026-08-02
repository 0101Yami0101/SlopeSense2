"""V4 GATE — does the trigger still work on the data the LIVE app will use?

The 0.768 figure was measured on 11 km IMERG. The deployed app uses Open-Meteo
sampled at ~33 km. Two things changed at once, and both could hurt:

    1. SOURCE   Open-Meteo vs IMERG correlate at only 0.320 daily, and
                Open-Meteo runs 1.68x wetter.
    2. RESOLUTION  ~33 km sampling instead of 11 km, so each event is scored
                from the nearest query point rather than its own cell.

This re-runs the identical validation under BOTH changes at once — deliberately,
because that is what ships. Scoring each event from its nearest query point is
not a shortcut; it is exactly what the app does for every pixel.

    PASS      >= 0.72   ship as-is, quote this number
    MARGINAL  0.60-0.72 ship, but state plainly that live is weaker than hindcast
    FAIL      <  0.60   the forecast product is not defensible; rethink

⚠️ Climatology starts 2010, so the 6 events from 2008-2009 drop out. 66 of 72
remain — noted rather than hidden, because a shrinking denominator is an easy
way to accidentally flatter a result.
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
from sklearn.metrics import roc_auc_score

import grid as G
from common import INTERIM, LABELS, ROOT

warnings.filterwarnings("ignore")

OM = INTERIM / "rainfall_om"
MONSOON = (5, 10)
FEATURES = ("r3", "r7")
N_NEG = 20_000
SEED = 0


def rolling(a: np.ndarray, w: int) -> np.ndarray:
    if w == 1:
        return a.copy()
    cs = np.cumsum(np.nan_to_num(a), axis=0, dtype=np.float64)
    out = np.full_like(a, np.nan, dtype=np.float32)
    out[w - 1:] = (cs[w - 1:] -
                   np.vstack([np.zeros((1, a.shape[1])), cs[:-w]])).astype(np.float32)
    return out


def main() -> None:
    print("V4 GATE - trigger on the LIVE data source")

    P = np.load(OM / "precip_mm.npy")
    dates = pd.to_datetime(np.load(OM / "dates.npy").astype("datetime64[D]"))
    pts = json.loads((OM / "points.json").read_text())
    plat = np.array(pts["lat"], dtype=np.float64)
    plon = np.array(pts["lon"], dtype=np.float64)
    print(f"  climatology: {P.shape[0]:,} days x {P.shape[1]} points "
          f"({dates[0].date()} .. {dates[-1].date()})")

    # ── events -> nearest query point, exactly as the app assigns pixels ──
    g = gpd.read_file(LABELS / "nasa-glc_landslides_point_arunachal.geojson")
    g["evdt"] = pd.to_datetime(g.ev_date, unit="ms", errors="coerce")
    g = g.dropna(subset=["evdt"]).to_crs(4326)
    elat = g.geometry.y.to_numpy()
    elon = g.geometry.x.to_numpy()
    d2 = ((elat[:, None] - plat[None, :]) ** 2 +
          ((elon[:, None] - plon[None, :]) * np.cos(np.radians(elat[:, None]))) ** 2)
    ecell = np.argmin(d2, axis=1)
    dkm = np.sqrt(d2.min(axis=1)) * 111.0

    dmap = {d: i for i, d in enumerate(dates)}
    ti = np.array([dmap.get(pd.Timestamp(x.date()), -1) for x in g.evdt])
    keep = ti >= 0
    ti, ecell, dkm = ti[keep], ecell[keep], dkm[keep]
    print(f"  events usable: {len(ti)} of {len(g)}  "
          f"({int((~keep).sum())} outside the climatology window)")
    print(f"  distance event -> nearest query point: median {np.median(dkm):.0f} km, "
          f"max {dkm.max():.0f} km")

    # ── features + per-point monsoon climatology ─────────────────────────
    mons = np.asarray((dates.month >= MONSOON[0]) & (dates.month <= MONSOON[1]))
    feat = {f: rolling(P, int(f[1:])) for f in FEATURES}
    clim = {f: {j: feat[f][mons, j][np.isfinite(feat[f][mons, j])]
                for j in range(P.shape[1])} for f in FEATURES}

    rng = np.random.default_rng(SEED)
    nt = rng.choice(np.flatnonzero(mons), N_NEG)
    nc = rng.choice(np.unique(ecell), N_NEG)

    def pct(f, tt, cc):
        a = feat[f]
        return np.array([(clim[f][j] < a[t, j]).mean()
                         if np.isfinite(a[t, j]) and len(clim[f][j]) else np.nan
                         for t, j in zip(tt, cc)])

    ev = np.nanmean([pct(f, ti, ecell) for f in FEATURES], axis=0)
    ng = np.nanmean([pct(f, nt, nc) for f in FEATURES], axis=0)
    y = np.r_[np.ones(len(ev)), np.zeros(len(ng))]
    sc = np.r_[ev, ng]
    ok = np.isfinite(sc)
    auc = float(roc_auc_score(y[ok], sc[ok]))
    n = int(np.isfinite(ev).sum())
    ci = 1.96 * np.sqrt(auc * (1 - auc) / n)

    print(f"\n  {'hindcast (11 km IMERG)':<32} AUC 0.768 +/- 0.098   n=72")
    print(f"  {'LIVE (33 km Open-Meteo)':<32} AUC {auc:.3f} +/- {ci:.3f}   n={n}")
    print(f"\n  median trigger on landslide days {np.nanmedian(ev):.3f}")
    print(f"  median on ordinary monsoon days   {np.nanmedian(ng):.3f}")

    print(f"\n  {'trigger >=':<12}{'% monsoon days':>17}{'% events':>11}{'lift':>8}")
    ops = []
    for thr in (0.50, 0.75, 0.90, 0.95):
        fa = float(np.nanmean(ng >= thr))
        hit = float(np.nanmean(ev >= thr))
        ops.append({"threshold": thr, "alert_rate": fa, "capture": hit,
                    "lift": hit / fa if fa else 0})
        print(f"  {thr:<12.2f}{100*fa:>16.1f}%{100*hit:>10.1f}%"
              f"{hit/fa if fa else 0:>8.1f}x")

    verdict = "PASS" if auc >= 0.72 else ("MARGINAL" if auc >= 0.60 else "FAIL")
    print(f"\n  ==> {verdict}")

    (ROOT / "reports" / "live_trigger_validation.json").write_text(json.dumps({
        "hindcast_auc_imerg_11km": 0.768,
        "live_auc_openmeteo_33km": auc, "ci95": ci, "n_events": n,
        "n_query_points": int(P.shape[1]),
        "median_event_to_point_km": float(np.median(dkm)),
        "climatology_start": str(dates[0].date()),
        "operating_points": ops, "verdict": verdict,
        "note": "Both source AND resolution change vs the hindcast. This is the "
                "number the deployed app actually delivers.",
    }, indent=2))
    print("  wrote reports/live_trigger_validation.json")


if __name__ == "__main__":
    main()
