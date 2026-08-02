"""PX0b — can Sentinel-1 RADAR do what cloud stopped Sentinel-2 doing?

Output: reports/px0b_sar_feasibility.{json,png}

════════════════════════════════════════════════════════════════════════════
WHY RE-OPEN THIS AFTER PX0 FAILED
════════════════════════════════════════════════════════════════════════════
PX0 vetoed optical change detection: monsoon cloud leaves 55-80 day gaps
between clear views, against the <=7 days a daily trigger needs.

Radar does not care about cloud. Sentinel-1 images through the monsoon exactly
as well as through the dry season. So the one thing that killed PX0 simply does
not apply — which is why this deserves its own gate rather than a shrug.

But radar trades one problem for another, and the new one is arguably worse for
us specifically.

════════════════════════════════════════════════════════════════════════════
THE RADAR PROBLEM: SIDE-LOOKING GEOMETRY IN STEEP TERRAIN
════════════════════════════════════════════════════════════════════════════
Radar does not look straight down. Sentinel-1 looks sideways at roughly 39
degrees from vertical. On flat ground that is fine. On a mountainside it fails
in two ways:

    LAYOVER   slope tilted TOWARD the radar, steeper than the look angle.
              The top of the slope reflects before the bottom, so the image
              folds over itself. The pixel is unrecoverable.

    SHADOW    slope tilted AWAY, steep enough that the radar never illuminates
              it at all. No signal, nothing to detect.

⚠️ THE TRAP: both failures happen on STEEP slopes — which is precisely where
landslides are. A radar dataset can be 100% cloud-free and still be blind on
exactly the pixels we need. So "radar sees through cloud" is true and
irrelevant unless the geometry also works.

════════════════════════════════════════════════════════════════════════════
WHAT THIS SCRIPT MEASURES
════════════════════════════════════════════════════════════════════════════
1. TEMPORAL — from the Copernicus catalogue: how often is Arunachal actually
   imaged, ascending and descending, and how has that changed? (S1B failed in
   Dec 2021, halving revisit until S1C arrived.)

2. GEOMETRIC — from OUR OWN DEM: for every mapped landslide cell, is it in
   layover or shadow on the ascending pass? On the descending pass? Ascending
   and descending look at opposite sides, so a slope hidden from one is often
   visible to the other. The question is what fraction of landslide cells have
   AT LEAST ONE usable geometry.

Verdict needs both: frequent enough acquisitions AND a usable view.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))

import json
import time
import warnings

import numpy as np
import pandas as pd
import rasterio
import requests

from common import INTERIM, ROOT

warnings.filterwarnings("ignore")

ODATA = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
REPORTS = ROOT / "reports"

# Sentinel-1 IW: incidence sweeps 29-46 deg across the swath, ~39 mid-swath.
INCIDENCE = 39.0
INCIDENCE_RANGE = (29.0, 46.0)

# Sentinel-1 is RIGHT-looking. Ground-track heading is ~-13 deg from north on
# the ascending pass, so the look direction is heading+90.
LOOK_AZ = {"ascending": 347.0 + 90.0, "descending": 193.0 + 90.0}   # deg from N

# Sample points spanning the state for the catalogue query
PROBES = [(92.0, 27.3), (94.0, 28.0), (96.0, 28.3)]
YEARS = [(2017, 2018), (2019, 2020), (2022, 2023), (2024, 2026)]


def acquisitions(lon, lat, y0, y1, session):
    f = (f"Collection/Name eq 'SENTINEL-1' and "
         f"OData.CSC.Intersects(area=geography'SRID=4326;POINT({lon} {lat})') and "
         f"ContentDate/Start gt {y0}-01-01T00:00:00.000Z and "
         f"ContentDate/Start lt {y1}-12-31T00:00:00.000Z")
    rows = []
    for attempt in range(3):
        try:
            r = session.get(ODATA, params={"$filter": f, "$top": 1000,
                                           "$expand": "Attributes"}, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(2 ** attempt)
        except Exception:                                    # noqa: BLE001
            time.sleep(2 ** attempt)
    else:
        return pd.DataFrame(columns=["date", "orbit"])
    for p in r.json().get("value", []):
        at = {a["Name"]: a["Value"] for a in p.get("Attributes", [])}
        if at.get("productType") in (None, "RAW"):
            continue
        rows.append({"date": pd.Timestamp(p["ContentDate"]["Start"][:10]),
                     "orbit": str(at.get("orbitDirection", "?")).lower()})
    if not rows:
        return pd.DataFrame(columns=["date", "orbit"])
    return pd.DataFrame(rows).drop_duplicates(["date", "orbit"])


def geometry_check():
    """Layover / shadow for every mapped landslide cell, both orbit directions.

    Effective slope in the radar look direction:
        a_eff = atan( tan(slope) * cos(aspect - look_azimuth) )
    positive = tilted toward the radar, negative = tilted away.

        layover  when  a_eff >= incidence
        shadow   when  a_eff <= incidence - 90
    """
    with rasterio.open(INTERIM / "terrain" / "terrain_slope_deg.tif") as s:
        slope = s.read(1)
    with rasterio.open(INTERIM / "terrain" / "terrain_northness.tif") as s:
        north = s.read(1)
    with rasterio.open(INTERIM / "terrain" / "terrain_eastness.tif") as s:
        east = s.read(1)
    with rasterio.open(INTERIM / "labels" / "label_slide.tif") as s:
        pos = s.read(1).astype(bool)
    with rasterio.open(INTERIM / "state_mask.tif") as s:
        inside = s.read(1).astype(bool)

    aspect = np.degrees(np.arctan2(east, north)) % 360.0
    sel = pos & inside & np.isfinite(slope)
    sl, asp = slope[sel], aspect[sel]
    dom = inside & np.isfinite(slope) & (slope > 10)
    sl_d, asp_d = slope[dom], aspect[dom]

    out = {}
    usable = {}
    for name, look in LOOK_AZ.items():
        res = {}
        for label, S, A in (("landslide_cells", sl, asp),
                            ("all_domain", sl_d, asp_d)):
            a_eff = np.degrees(np.arctan(
                np.tan(np.radians(S)) * np.cos(np.radians(A - look))))
            lay = a_eff >= INCIDENCE
            shd = a_eff <= INCIDENCE - 90.0
            res[label] = {"layover": float(lay.mean()),
                          "shadow": float(shd.mean()),
                          "usable": float((~lay & ~shd).mean())}
            if label == "landslide_cells":
                usable[name] = ~lay & ~shd
        out[name] = res
    both = usable["ascending"] | usable["descending"]
    out["either_orbit_usable_landslide_cells"] = float(both.mean())
    out["both_orbits_usable_landslide_cells"] = float(
        (usable["ascending"] & usable["descending"]).mean())
    out["n_landslide_cells"] = int(sel.sum())

    # sensitivity across the swath — near range is worse for layover
    sweep = {}
    for inc in (INCIDENCE_RANGE[0], INCIDENCE, INCIDENCE_RANGE[1]):
        u = []
        for look in LOOK_AZ.values():
            a_eff = np.degrees(np.arctan(
                np.tan(np.radians(sl)) * np.cos(np.radians(asp - look))))
            u.append((a_eff < inc) & (a_eff > inc - 90.0))
        sweep[f"{inc:.0f}deg"] = float((u[0] | u[1]).mean())
    out["either_orbit_by_incidence"] = sweep
    return out


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    print("PX0b — Sentinel-1 SAR feasibility")

    # ── 1. temporal ───────────────────────────────────────────────────────
    print("\n  == acquisition frequency (catalogue) ==")
    s = requests.Session()
    s.headers["User-Agent"] = "LandSlideFlood-research/1.0 (PX0b feasibility)"
    temporal = {}
    print(f"  {'period':<12}{'n acq':>8}{'asc':>7}{'desc':>7}"
          f"{'median gap':>12}{'p90 gap':>10}")
    # ⚠️ Revisit MUST be computed per location and then aggregated. Pooling
    # acquisitions across probe points would count a date imaged over one probe
    # as coverage of another, which inflates the apparent revisit — a single
    # site is what actually matters for dating a single landslide.
    for y0, y1 in YEARS:
        per_probe, tot, na, nd = [], 0, 0, 0
        for lon, lat in PROBES:
            df = acquisitions(lon, lat, y0, y1, s)
            if df.empty:
                continue
            tot += len(df)
            na += int((df.orbit == "ascending").sum())
            nd += int((df.orbit == "descending").sum())
            d = np.sort(df.date.unique())
            if len(d) > 1:
                g = np.diff(d).astype("timedelta64[D]").astype(int)
                per_probe.append((float(np.median(g)),
                                  float(np.percentile(g, 90))))
        if not per_probe:
            continue
        med = float(np.median([p[0] for p in per_probe]))
        p90 = float(np.median([p[1] for p in per_probe]))
        temporal[f"{y0}-{y1}"] = {"n_all_probes": tot, "asc": na, "desc": nd,
                                  "median_gap_d": med, "p90_gap_d": p90,
                                  "n_probes": len(per_probe)}
        print(f"  {f'{y0}-{y1}':<12}{tot:>8}{na:>7}{nd:>7}"
              f"{med:>11.0f}d{p90:>9.0f}d")

    # ── 2. geometry ───────────────────────────────────────────────────────
    print(f"\n  == radar geometry on our own DEM (incidence {INCIDENCE:.0f} deg) ==")
    geo = geometry_check()
    print(f"  {geo['n_landslide_cells']:,} mapped landslide cells\n")
    print(f"  {'orbit':<14}{'layover':>10}{'shadow':>10}{'usable':>10}")
    for name in ("ascending", "descending"):
        r = geo[name]["landslide_cells"]
        print(f"  {name:<14}{100*r['layover']:>9.1f}%{100*r['shadow']:>9.1f}%"
              f"{100*r['usable']:>9.1f}%")
    print(f"\n  usable on EITHER orbit : {100*geo['either_orbit_usable_landslide_cells']:.1f}%")
    print(f"  usable on BOTH orbits  : {100*geo['both_orbits_usable_landslide_cells']:.1f}%")
    print(f"\n  across the swath (either orbit):")
    for k, v in geo["either_orbit_by_incidence"].items():
        print(f"    incidence {k:<8} {100*v:5.1f}% usable")

    # ── 3. verdict ────────────────────────────────────────────────────────
    recent = temporal.get("2024-2026") or list(temporal.values())[-1]
    gap = recent["median_gap_d"]
    cover = geo["either_orbit_usable_landslide_cells"]
    ok_time = gap <= 14
    ok_geom = cover >= 0.60
    verdict = "PASS" if (ok_time and ok_geom) else "VETO"
    print(f"\n  {'temporal':<12} median gap {gap:.0f}d  "
          f"{'OK' if ok_time else 'FAIL'} (need <=14d)")
    print(f"  {'geometric':<12} {100*cover:.0f}% of landslide cells viewable  "
          f"{'OK' if ok_geom else 'FAIL'} (need >=60%)")
    print(f"\n  ==> {verdict}")

    (REPORTS / "px0b_sar_feasibility.json").write_text(json.dumps({
        "incidence_deg": INCIDENCE, "incidence_range": list(INCIDENCE_RANGE),
        "look_azimuth_deg": LOOK_AZ,
        "temporal": temporal, "geometry": geo,
        "verdict": verdict, "temporal_ok": bool(ok_time), "geometric_ok": bool(ok_geom),
        "caveats": [
            "geometry uses nominal mid-swath incidence; true value varies 29-46 deg",
            "catalogue counts acquisitions, not guaranteed usable interferometric pairs",
            "detecting a scar in SAR amplitude is harder than in optical — this gate "
            "tests only whether the data CAN see the slope, not whether a model would",
        ],
    }, indent=2))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    ks = list(temporal)
    ax[0].bar(ks, [temporal[k]["median_gap_d"] for k in ks], color="#2c7bb6")
    ax[0].axhline(14, ls="--", c="#d7191c", lw=1.5)
    ax[0].text(0, 15, "14 d requirement", color="#d7191c", fontsize=8)
    ax[0].set_ylabel("median gap between acquisitions (days)")
    ax[0].set_title("Sentinel-1 revisit over Arunachal", fontsize=10)
    ax[0].grid(alpha=.3)

    lab, lay, shd, use = [], [], [], []
    for n in ("ascending", "descending"):
        r = geo[n]["landslide_cells"]
        lab.append(n[:4]); lay.append(100*r["layover"])
        shd.append(100*r["shadow"]); use.append(100*r["usable"])
    x = np.arange(len(lab))
    ax[1].bar(x-.25, lay, .25, label="layover", color="#d7191c")
    ax[1].bar(x, shd, .25, label="shadow", color="#fdae61")
    ax[1].bar(x+.25, use, .25, label="usable", color="#2c7bb6")
    ax[1].axhline(100*geo["either_orbit_usable_landslide_cells"], ls="--",
                  c="k", lw=1.4)
    ax[1].text(-.4, 100*geo["either_orbit_usable_landslide_cells"]+2,
               "either orbit", fontsize=8)
    ax[1].set_xticks(x); ax[1].set_xticklabels(lab)
    ax[1].set_ylabel("% of landslide cells")
    ax[1].set_title("Radar geometry on mapped landslides", fontsize=10)
    ax[1].legend(fontsize=8); ax[1].grid(alpha=.3)
    plt.tight_layout()
    plt.savefig(REPORTS / "px0b_sar_feasibility.png", dpi=130)
    print(f"  wrote reports/px0b_sar_feasibility.{{json,png}}")


if __name__ == "__main__":
    main()
