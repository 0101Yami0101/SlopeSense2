"""P11 — operational backtest. What would this system actually have told you?

Output: reports/backtest.json + reports/backtest.png

AUC answers "can it rank days". A disaster manager asks three different
questions, and this script answers those instead:

    1. How many days a year would you have put out an alert?
    2. What share of known landslides happened on an alert day?
    3. Would you have known BEFORE the slope failed, or only the same morning?

Question 3 is the one that decides whether this is a *forecast* or merely a
*report*. It has not been tested until now.

════════════════════════════════════════════════════════════════════════════
⚠️ WHAT CANNOT BE MEASURED HERE, AND WHY
════════════════════════════════════════════════════════════════════════════
**We cannot honestly compute a false-alarm rate.**

An "alert day with no landslide" might mean the system cried wolf — or it might
mean a slope failed in an empty valley and nobody wrote it down. Arunachal has
84 dated landslides across 16 years; the true number is orders of magnitude
higher. Absence of a record is not absence of an event.

So this reports **alert frequency** (how often it fires — a real, measurable
cost) and **capture rate** (share of KNOWN events caught). It does not report
precision, and any such number would be fiction.

Run on the LIVE data path (Open-Meteo), not the IMERG hindcast, so the numbers
describe what the deployed app would have done.
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

from common import INTERIM, LABELS, PROCESSED, ROOT

warnings.filterwarnings("ignore")

OM = INTERIM / "rainfall_om"
MONSOON = (5, 10)
FEATURES = ("r3", "r7")
LEADS = (-5, -4, -3, -2, -1, 0, 1, 2)


def rolling(a: np.ndarray, w: int) -> np.ndarray:
    cs = np.cumsum(np.nan_to_num(a), axis=0, dtype=np.float64)
    out = np.full_like(a, np.nan, dtype=np.float32)
    out[w - 1:] = (cs[w - 1:] -
                   np.vstack([np.zeros((1, a.shape[1])), cs[:-w]])).astype(np.float32)
    return out


def main() -> None:
    print("P11 - operational backtest (live data path)")

    P = np.load(OM / "precip_mm.npy")
    dates = pd.to_datetime(np.load(OM / "dates.npy").astype("datetime64[D]"))
    pts = json.loads((OM / "points.json").read_text())
    plat = np.array(pts["lat"]); plon = np.array(pts["lon"])
    mons = np.asarray((dates.month >= MONSOON[0]) & (dates.month <= MONSOON[1]))

    feat = {f: rolling(P, int(f[1:])) for f in FEATURES}
    clim = {f: {j: feat[f][mons, j][np.isfinite(feat[f][mons, j])]
                for j in range(P.shape[1])} for f in FEATURES}

    def trig_at(t, j):
        vals = []
        for f in FEATURES:
            v = feat[f][t, j]
            if not np.isfinite(v) or not len(clim[f][j]):
                return np.nan
            vals.append((clim[f][j] < v).mean())
        return float(np.mean(vals))

    # full trigger field, every day x every point
    print("  computing trigger for every day and point...")
    T = np.full(P.shape, np.nan, dtype=np.float32)
    for f in FEATURES:
        pc = np.empty_like(feat[f])
        for j in range(P.shape[1]):
            pc[:, j] = np.searchsorted(np.sort(clim[f][j]), feat[f][:, j]) / max(len(clim[f][j]), 1)
        T = pc if np.isnan(T).all() else (T + pc)
    T /= len(FEATURES)
    T = np.clip(T, 0, 1)

    # ── events -> nearest point, plus their susceptibility ───────────────
    import grid as G
    with rasterio.open(PROCESSED / "susceptibility.tif") as s:
        sus = s.read(1)
    g = gpd.read_file(LABELS / "nasa-glc_landslides_point_arunachal.geojson")
    g["evdt"] = pd.to_datetime(g.ev_date, unit="ms", errors="coerce")
    g = g.dropna(subset=["evdt"]).to_crs(4326)
    elat = g.geometry.y.to_numpy(); elon = g.geometry.x.to_numpy()
    d2 = ((elat[:, None] - plat[None, :]) ** 2 +
          ((elon[:, None] - plon[None, :]) * np.cos(np.radians(elat[:, None]))) ** 2)
    ej = np.argmin(d2, axis=1)

    gu = g.to_crs(G.CRS)
    r, c = G.xy_to_rowcol(gu.geometry.x.to_numpy(), gu.geometry.y.to_numpy())
    inb = (r >= 0) & (r < G.NROWS) & (c >= 0) & (c < G.NCOLS)
    esus = np.full(len(g), np.nan)
    esus[inb] = sus[r[inb], c[inb]]

    dmap = {d: i for i, d in enumerate(dates)}
    eti = np.array([dmap.get(pd.Timestamp(x.date()), -1) for x in g.evdt])
    keep = eti >= 0
    eti, ej, esus = eti[keep], ej[keep], esus[keep]
    print(f"  {len(eti)} dated events on the record")

    # ── 1 & 2. alert frequency vs capture ────────────────────────────────
    n_monsoon_days = int(mons.sum())
    n_years = len(np.unique(dates[mons].year))
    ev_trig = np.array([T[t, j] for t, j in zip(eti, ej)])

    print(f"\n  {'alert when trigger >=':<24}{'alert days/yr':>15}"
          f"{'% of known slides caught':>27}")
    rows = []
    for thr in (0.50, 0.75, 0.90, 0.95, 0.99):
        # A statewide alert fires if ANY point crosses the threshold that day.
        fires = (T[mons] >= thr).any(axis=1)
        per_yr = fires.sum() / n_years
        cap = float(np.nanmean(ev_trig >= thr))
        rows.append({"threshold": thr, "alert_days_per_year": float(per_yr),
                     "capture": cap})
        print(f"  {thr:<24.2f}{per_yr:>14.0f}{100*cap:>26.0f}%")

    # localised alerts are the operationally useful version
    print(f"\n  Localised (per rainfall cell, not statewide):")
    print(f"  {'trigger >=':<24}{'% of cell-days alerting':>26}"
          f"{'% slides caught':>18}")
    loc = []
    for thr in (0.75, 0.90, 0.95, 0.99):
        frac = float((T[mons] >= thr).mean())
        cap = float(np.nanmean(ev_trig >= thr))
        loc.append({"threshold": thr, "cell_day_alert_frac": frac, "capture": cap})
        print(f"  {thr:<24.2f}{100*frac:>25.1f}%{100*cap:>17.0f}%")

    # ── 3. lead time — the question that decides forecast vs report ──────
    print(f"\n  == LEAD TIME: is the signal there BEFORE the slope fails? ==")
    print(f"  {'day relative to event':<26}{'median trigger':>16}"
          f"{'% at/above 0.90':>18}")
    lead = []
    base = float(np.nanmedian(T[mons]))
    for L in LEADS:
        tt = eti + L
        ok = (tt >= 0) & (tt < T.shape[0])
        v = np.array([T[t, j] for t, j in zip(tt[ok], ej[ok])])
        med = float(np.nanmedian(v))
        hi = float(np.nanmean(v >= 0.90))
        lead.append({"lead_days": L, "median_trigger": med, "frac_ge_090": hi})
        lbl = ("event day" if L == 0 else
               f"{abs(L)} day{'s' if abs(L) > 1 else ''} "
               f"{'before' if L < 0 else 'after'}")
        mark = "  <-- event" if L == 0 else ""
        print(f"  {lbl:<26}{med:>16.3f}{100*hi:>17.0f}%{mark}")
    print(f"  {'(ordinary monsoon day)':<26}{base:>16.3f}")

    # ── susceptibility of the places that failed ─────────────────────────
    fin = np.isfinite(esus)
    print(f"\n  Susceptibility at the places that failed: median "
          f"{np.nanmedian(esus[fin]):.3f} "
          f"(statewide median {np.nanmedian(sus[np.isfinite(sus)]):.3f})")

    (ROOT / "reports" / "backtest.json").write_text(json.dumps({
        "years": int(n_years), "monsoon_days": n_monsoon_days,
        "n_events": int(len(eti)),
        "statewide_alerts": rows, "localised_alerts": loc,
        "lead_time": lead, "baseline_trigger_median": base,
        "cannot_measure": "False-alarm rate. An alert day with no recorded "
                          "landslide may simply be an unrecorded landslide - "
                          "84 dated events across 16 years is a tiny fraction "
                          "of what actually occurred. Any precision figure "
                          "would be fiction.",
    }, indent=2))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    L = [d["lead_days"] for d in lead]
    ax[0].plot(L, [d["median_trigger"] for d in lead], "o-", color="#d7191c", lw=2)
    ax[0].axhline(base, ls="--", c="#888", lw=1)
    ax[0].axvline(0, ls=":", c="#444")
    ax[0].text(0.1, base + .01, "ordinary monsoon day", fontsize=8, color="#888")
    ax[0].set_xlabel("days relative to the landslide")
    ax[0].set_ylabel("median trigger")
    ax[0].set_title("Is the warning there in advance?", fontsize=10)
    ax[0].grid(alpha=.3)

    t_ = [r["threshold"] for r in loc]
    ax[1].plot(t_, [100 * r["capture"] for r in loc], "o-", color="#2c7bb6",
               lw=2, label="% of known slides caught")
    ax[1].plot(t_, [100 * r["cell_day_alert_frac"] for r in loc], "s--",
               color="#f46d43", lw=2, label="% of cell-days alerting")
    ax[1].set_xlabel("alert threshold"); ax[1].set_ylabel("%")
    ax[1].set_title("Coverage vs how often you'd alert", fontsize=10)
    ax[1].legend(fontsize=8); ax[1].grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(ROOT / "reports" / "backtest.png", dpi=130)
    print("\n  wrote reports/backtest.{json,png}")


if __name__ == "__main__":
    main()
