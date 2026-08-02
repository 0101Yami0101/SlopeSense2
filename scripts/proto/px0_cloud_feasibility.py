"""PX0 — can we date a landslide from Sentinel-2 in Arunachal? The veto gate.

Output: reports/px0_cloud_feasibility.{json,png}

════════════════════════════════════════════════════════════════════════════
THE QUESTION
════════════════════════════════════════════════════════════════════════════
PX proposes recovering failure dates for our 37,788 undated polygons by
detecting when each scar first appears in satellite imagery. That only works if
clear imagery exists close in time to the failure.

86% of dated landslides here occur May-October — peak monsoon, peak cloud. **The
imagery we need is exactly the imagery hardest to get.** If the nearest clear
views either side of a failure are six weeks apart, the recovered date reads
"sometime in these six weeks" — and it rained hard throughout. Useless for a
model that must pick a day.

════════════════════════════════════════════════════════════════════════════
THE TEST — validate against answers we already have
════════════════════════════════════════════════════════════════════════════
Take the NASA GLC events whose dates we KNOW. For each, ask the Copernicus
catalogue what Sentinel-2 acquisitions exist nearby in time and how cloudy each
was. The gap between the last clear view BEFORE and the first clear view AFTER
is the date uncertainty PX could actually achieve for that event.

    *If we cannot recover dates we already have, we cannot discover dates we don't.*

Metadata only — no pixels are downloaded. The whole test is catalogue queries.

════════════════════════════════════════════════════════════════════════════
TWO LIMITS ON WHAT THIS PROVES
════════════════════════════════════════════════════════════════════════════
1. Sentinel-2 starts 2015-06 (S2A) / 2017-03 (S2B). Only events from mid-2015
   are testable, which is ~46 of the 90. Earlier events would need Landsat at
   30 m and 16-day revisit — strictly worse, so this is the optimistic case.

2. Cloud cover is reported PER SCENE (~110 km tile), not per pixel. A tile at
   60% cloud may well be clear over our specific slope. So scene-level filtering
   is PESSIMISTIC, and results are reported at several thresholds rather than
   one. A borderline verdict should be re-tested per-pixel before deciding.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import time
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from common import LABELS, ROOT

warnings.filterwarnings("ignore")

ODATA = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
WINDOW_DAYS = 120          # look this far either side of each event
CLOUD_LEVELS = (20, 40, 60, 80)
S2_START = pd.Timestamp("2015-06-23")      # first S2A acquisitions
REPORTS = ROOT / "reports"


def scenes_near(lon: float, lat: float, when: pd.Timestamp,
                session: requests.Session) -> pd.DataFrame:
    """Every Sentinel-2 acquisition over this point within +/- WINDOW_DAYS."""
    t0 = (when - pd.Timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT00:00:00.000Z")
    t1 = (when + pd.Timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT00:00:00.000Z")
    f = (f"Collection/Name eq 'SENTINEL-2' and "
         f"OData.CSC.Intersects(area=geography'SRID=4326;POINT({lon:.4f} {lat:.4f})') and "
         f"ContentDate/Start gt {t0} and ContentDate/Start lt {t1}")
    rows = []
    for attempt in range(3):
        try:
            r = session.get(ODATA, params={"$filter": f, "$top": 1000,
                                           "$expand": "Attributes"}, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(2 ** attempt)
        except Exception:                                   # noqa: BLE001
            time.sleep(2 ** attempt)
    else:
        return pd.DataFrame(columns=["date", "cloud"])

    for p in r.json().get("value", []):
        cc = [a["Value"] for a in p.get("Attributes", [])
              if a["Name"] == "cloudCover"]
        if not cc:
            continue
        rows.append({"date": pd.Timestamp(p["ContentDate"]["Start"][:10]),
                     "cloud": float(cc[0])})
    if not rows:
        return pd.DataFrame(columns=["date", "cloud"])
    df = pd.DataFrame(rows)
    # One acquisition can appear as several tiles and as both L1C and L2A. Keep
    # the CLEAREST record per date — that is the best view actually available.
    return df.groupby("date", as_index=False).cloud.min().sort_values("date")


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    print("PX0 — Sentinel-2 cloud feasibility (the PX veto gate)")

    g = gpd.read_file(LABELS / "nasa-glc_landslides_point_arunachal.geojson")
    g["evdt"] = pd.to_datetime(g.ev_date, unit="ms", errors="coerce")   # epoch ms
    g = g.dropna(subset=["evdt"])
    g = g[g.evdt >= S2_START].to_crs(4326)
    print(f"  {len(g)} of 90 dated events fall in the Sentinel-2 era "
          f"(>= {S2_START:%Y-%m})")
    if not len(g):
        print("  nothing testable"); return

    s = requests.Session()
    s.headers["User-Agent"] = "LandSlideFlood-research/1.0 (PX0 feasibility)"

    recs = []
    for i, (_, row) in enumerate(g.iterrows(), 1):
        df = scenes_near(row.geometry.x, row.geometry.y, row["evdt"], s)
        rec = {"date": row["evdt"], "month": int(row["evdt"].month),
               "lon": row.geometry.x, "lat": row.geometry.y,
               "n_scenes": len(df)}
        for lv in CLOUD_LEVELS:
            clear = df[df.cloud <= lv]
            before = clear[clear.date <= row["evdt"]]
            after = clear[clear.date > row["evdt"]]
            b = (row["evdt"] - before.date.max()).days if len(before) else np.nan
            a = (after.date.min() - row["evdt"]).days if len(after) else np.nan
            rec[f"gap_before_{lv}"] = b
            rec[f"gap_after_{lv}"] = a
            rec[f"window_{lv}"] = b + a if np.isfinite(b) and np.isfinite(a) else np.nan
        recs.append(rec)
        if i % 5 == 0 or i == len(g):
            print(f"    {i}/{len(g)} events queried", flush=True)

    R = pd.DataFrame(recs)
    print(f"\n  scenes found per event: median {R.n_scenes.median():.0f}")

    print(f"\n  {'cloud <=':<10}{'events w/ both sides':>22}{'median window':>16}"
          f"{'<=7d':>8}{'<=14d':>8}")
    summary = {}
    for lv in CLOUD_LEVELS:
        w = R[f"window_{lv}"].dropna()
        frac7 = float((w <= 7).mean()) if len(w) else 0.0
        frac14 = float((w <= 14).mean()) if len(w) else 0.0
        med = float(w.median()) if len(w) else float("nan")
        summary[lv] = {"n_with_both_sides": int(len(w)),
                       "median_window_days": med,
                       "frac_within_7d": frac7, "frac_within_14d": frac14}
        print(f"  {lv:<10}{len(w):>16}/{len(R):<5}{med:>15.0f}d"
              f"{100*frac7:>7.0f}%{100*frac14:>7.0f}%")

    # monsoon vs dry season — the whole risk is that monsoon is unusable
    print(f"\n  by season (cloud <= 40%):")
    for name, m in (("monsoon (May-Oct)", R.month.between(5, 10)),
                    ("dry (Nov-Apr)", ~R.month.between(5, 10))):
        w = R.loc[m, "window_40"].dropna()
        if len(w):
            print(f"    {name:<20} n={len(w):<4} median window {w.median():.0f}d   "
                  f"<=14d: {100*(w<=14).mean():.0f}%")

    best = max(CLOUD_LEVELS, key=lambda lv: summary[lv]["frac_within_14d"])
    verdict = "PASS" if summary[best]["frac_within_14d"] >= 0.30 else "VETO"
    print(f"\n  ==> {verdict}: at cloud<={best}%, "
          f"{100*summary[best]['frac_within_14d']:.0f}% of events could be dated "
          f"to within 14 days")

    (REPORTS / "px0_cloud_feasibility.json").write_text(json.dumps({
        "events_tested": int(len(R)), "events_total_dated": 90,
        "window_days": WINDOW_DAYS, "cloud_levels": list(CLOUD_LEVELS),
        "summary": summary, "verdict": verdict, "best_level": best,
        "caveats": [
            "scene-level cloud over a ~110 km tile, not per-pixel — pessimistic",
            "Sentinel-2 only; pre-2015 events would need Landsat, strictly worse",
        ],
    }, indent=2))
    R.to_csv(REPORTS / "px0_cloud_feasibility.csv", index=False)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    for lv in CLOUD_LEVELS:
        w = R[f"window_{lv}"].dropna().sort_values()
        if len(w):
            ax[0].plot(w.values, np.linspace(0, 1, len(w)), lw=2,
                       label=f"cloud <= {lv}%")
    ax[0].axvline(14, ls="--", c="k", lw=1)
    ax[0].text(15, .05, "14 d", fontsize=8)
    ax[0].set_xlabel("clear-image window around the event (days)")
    ax[0].set_ylabel("fraction of events")
    ax[0].set_title("Achievable date uncertainty", fontsize=10)
    ax[0].set_xscale("log"); ax[0].grid(alpha=.3); ax[0].legend(fontsize=8)

    mm = R.groupby("month")["window_40"].median()
    ax[1].bar(mm.index, mm.values, color=["#d7191c" if 5 <= m <= 10 else "#2c7bb6"
                                          for m in mm.index])
    ax[1].set_xlabel("month of failure"); ax[1].set_ylabel("median window (days)")
    ax[1].set_title("Red = monsoon, when 86% of landslides happen", fontsize=10)
    ax[1].grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(REPORTS / "px0_cloud_feasibility.png", dpi=130)
    print(f"  wrote reports/px0_cloud_feasibility.{{json,csv,png}}")


if __name__ == "__main__":
    main()
