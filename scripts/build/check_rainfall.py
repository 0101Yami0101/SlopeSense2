"""P7 exit check — does the rainfall pipeline see real rainfall-driven failures?

Two tests, in order of how much they prove.

════════════════════════════════════════════════════════════════════════════
1. DATED EVENTS — decisive
════════════════════════════════════════════════════════════════════════════
NASA GLC carries 90 dated landslides (2008-2018); 72 land on a rainfall cell.
On those exact days, at those exact cells, every feature should be far above
climatology for the same cells in the same calendar months. It is: the weakest
sits at the 83rd percentile, r7 at the 92nd (160 mm against 37 mm typical).

This is the only test using real failure DATES, so it is the one that actually
validates date parsing, grid orientation and window alignment together.

════════════════════════════════════════════════════════════════════════════
2. BHUVAN SURVEY YEARS — weak, and confounded in a way worth stating
════════════════════════════════════════════════════════════════════════════
The tempting version is "compare 2017 rainfall at landslide sites vs
elsewhere". That proves nothing: landslide terrain is wetter in general, so it
passes even with the dates shuffled. So we hold PLACE fixed and vary TIME —
rank each inventory year against all 25 monsoons at the cells that failed.

⚠️ But Bhuvan's `Year` is the SURVEY year, not a failure date. Every polygon in
the 2014 file reads Year=2014 / Activity='Active', and the 2023 file separates
914 'Reactivated' slides that first failed earlier. These are mapping
campaigns. A mid-pack rank (2014 sits at #12/25) is therefore expected and is
NOT evidence of a broken pipeline — which is exactly why test 1 exists.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

import grid as G
from common import INTERIM, LABELS, ROOT

warnings.filterwarnings("ignore")

SRC = INTERIM / "rainfall"
FEAT = SRC / "features"

INVENTORIES = {
    2014: "bhuvan_ar_slim_2014_gcs_polygon_arunachal.geojson",
    2017: "bhuvan_ar_slim_2017_polygon_arunachal.geojson",
    2023: "bhuvan_ls_arunachal_2023_polygon_arunachal.geojson",
}
MONSOON = (5, 10)


def imerg_cells_for(path: Path, idx: np.ndarray) -> np.ndarray:
    gdf = gpd.read_file(path).to_crs(G.CRS)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    xs = gdf.geometry.centroid.x.to_numpy()
    ys = gdf.geometry.centroid.y.to_numpy()
    r, c = G.xy_to_rowcol(xs, ys)
    ok = (r >= 0) & (r < G.NROWS) & (c >= 0) & (c < G.NCOLS)
    v = idx[r[ok], c[ok]]
    return np.unique(v[v >= 0])


def dated_event_check(idx: np.ndarray, dates: pd.DatetimeIndex) -> None:
    """THE decisive test: on days landslides actually happened, is it raining?

    NASA GLC carries 90 dated events (2008-2018) — the only real event dates we
    have. GSI has none and Bhuvan's `Year` is a SURVEY year, not a failure date
    (see the note in bhuvan_year_check). 72 of the 90 land on a rainfall cell.

    Compared against climatology for the SAME cells in the SAME calendar months,
    so the comparison is not just "monsoon is wetter than winter".

    ⚠️ ev_date arrives from ArcGIS as epoch MILLISECONDS. Parsing it as a plain
    datetime silently yields 1970 for every row and the whole test looks broken.
    """
    print("  == dated-event check (the decisive one) ==")
    g = gpd.read_file(LABELS / "nasa-glc_landslides_point_arunachal.geojson")
    g["dt"] = pd.to_datetime(g.ev_date, unit="ms", errors="coerce")
    g = g.dropna(subset=["dt"]).to_crs(G.CRS)
    r, c = G.xy_to_rowcol(g.geometry.x.to_numpy(), g.geometry.y.to_numpy())
    ok = (r >= 0) & (r < G.NROWS) & (c >= 0) & (c < G.NCOLS)
    g, cell = g[ok], idx[r[ok], c[ok]]
    m = cell >= 0
    g, cell = g[m], cell[m]
    dmap = {d: i for i, d in enumerate(dates)}
    ti = np.array([dmap.get(pd.Timestamp(d.date()), -1) for d in g.dt])
    keep = ti >= 0
    g, cell, ti = g[keep], cell[keep], ti[keep]
    print(f"     {len(ti)} events matched to a rainfall cell and day "
          f"({g.dt.min():%Y} - {g.dt.max():%Y})")

    mo = dates.month.to_numpy()
    sel = np.isin(mo, list(set(pd.DatetimeIndex(g.dt).month)))
    ucell = np.unique(cell)
    print(f"     {'feature':<16}{'on event':>11}{'climatology':>13}{'pctile':>9}")
    worst = 100
    for n in ("r1", "r3", "r7", "r15", "r30", "api",
              "storm_dur", "storm_id_ratio"):
        a = np.load(FEAT / f"{n}.npy", mmap_mode="r")
        ev = np.array([a[t, cl] for t, cl in zip(ti, cell)])
        clim = np.asarray(a[sel][:, ucell])
        clim = clim[np.isfinite(clim)]
        pct = 100 * (clim < np.nanmedian(ev)).mean()
        worst = min(worst, pct)
        print(f"     {n:<16}{np.nanmedian(ev):>11.1f}{np.nanmedian(clim):>13.1f}"
              f"{pct:>8.0f}%")
    print(f"     {'PASS' if worst >= 75 else 'FAIL'}: weakest feature sits at "
          f"the {worst:.0f}th percentile of climatology\n")


def main() -> None:
    print("P7 exit check — does the pipeline see real rainfall-driven failures?\n")

    with rasterio.open(SRC / "imerg_index.tif") as s:
        idx = s.read(1)
    dates = pd.to_datetime(np.load(SRC / "dates.npy").astype("datetime64[D]"))
    dated_event_check(idx, dates)
    r7 = np.load(FEAT / "r7.npy", mmap_mode="r")

    yr = dates.year.to_numpy()
    mo = dates.month.to_numpy()
    monsoon = (mo >= MONSOON[0]) & (mo <= MONSOON[1])
    years = np.array(sorted(set(yr[monsoon])))
    years = years[(years >= 2001) & (years <= 2025)]   # whole monsoons only

    print(f"  comparing {len(years)} monsoons ({years[0]}-{years[-1]})\n")

    for inv_year, fname in INVENTORIES.items():
        p = LABELS / fname
        if not p.exists():
            continue
        cells = imerg_cells_for(p, idx)
        if not len(cells):
            print(f"  {inv_year}: no cells matched"); continue

        # peak 7-day rainfall each monsoon, averaged over the failed cells
        peak = []
        for y in years:
            m = monsoon & (yr == y)
            peak.append(float(np.nanmean(np.nanmax(r7[m][:, cells], axis=0))))
        peak = np.array(peak)

        rank = int((peak > peak[years == inv_year][0]).sum()) + 1
        z = (peak[years == inv_year][0] - peak.mean()) / peak.std()
        top = np.argsort(-peak)[:5]

        print(f"  -- Bhuvan {inv_year} inventory — {len(cells)} IMERG cells failed")
        print(f"     peak 7-day rain at those cells, {inv_year}: "
              f"{peak[years == inv_year][0]:,.0f} mm")
        print(f"     rank among {len(years)} monsoons: #{rank}"
              f"   (z = {z:+.2f})")
        print(f"     wettest years there: "
              + ", ".join(f"{years[i]} ({peak[i]:,.0f})" for i in top))
        verdict = ("inventory year in the top third"
                   if rank <= len(years) / 3 else
                   "inventory year mid-pack — expected, see note below")
        print(f"     {verdict}\n")

    print("  (i) A mid-pack result here is NOT a pipeline fault. Bhuvan's `Year`")
    print("    is the SURVEY year, not a failure date — every polygon in the")
    print("    2014 file reads Year=2014, Activity='Active', and 2023 even")
    print("    separates 914 'Reactivated' slides that failed earlier. These")
    print("    are mapping campaigns, so the survey year need not be the")
    print("    wettest year. Trust the dated-event check above instead.\n")

    # --- sanity: does the seasonal cycle look like a monsoon? -------------
    r1 = np.load(FEAT / "r1.npy", mmap_mode="r")
    print("  seasonal cycle (AOI mean mm/day) — must peak Jun-Aug:")
    for m in range(1, 13):
        v = float(np.nanmean(r1[mo == m]))
        print(f"    {m:>2}  {v:5.2f}  " + "#" * int(v * 3))

    # --- picture -----------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 2, figsize=(14, 8))
    ax = ax.ravel()
    for i, (inv_year, fname) in enumerate(INVENTORIES.items()):
        cells = imerg_cells_for(LABELS / fname, idx)
        peak = [float(np.nanmean(np.nanmax(r7[monsoon & (yr == y)][:, cells],
                                           axis=0))) for y in years]
        cols = ["#d7191c" if y == inv_year else "#bbbbbb" for y in years]
        ax[i].bar(years, peak, color=cols)
        ax[i].set_title(f"Bhuvan {inv_year}: peak 7-day monsoon rain\n"
                        f"at the cells that failed", fontsize=10)
        ax[i].set_ylabel("mm")
        ax[i].tick_params(labelsize=8)

    daily = [float(np.nanmean(r1[mo == m])) for m in range(1, 13)]
    ax[3].plot(range(1, 13), daily, "o-", color="#2c7bb6")
    ax[3].set_title("Seasonal cycle, AOI mean (sanity)", fontsize=10)
    ax[3].set_xlabel("month"); ax[3].set_ylabel("mm/day")
    ax[3].grid(alpha=.3)
    plt.tight_layout()
    (ROOT / "reports").mkdir(exist_ok=True)
    plt.savefig(ROOT / "reports" / "rainfall_check.png", dpi=120)
    print("\n  wrote reports/rainfall_check.png")


if __name__ == "__main__":
    main()
