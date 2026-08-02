"""P7b — turn the raw rainfall stack into the features a trigger model reads.

Outputs one (ndays, ncells) float32 array per feature into
`data/interim/rainfall/features/`, plus a per-date table of the things that
vary in time but not in space (season, ENSO).

    r1 r3 r7 r15 r30      trailing rainfall totals, mm
    rmax_30               wettest single day in the last 30
    wetdays_30            days >1 mm in the last 30
    api                   antecedent precipitation index, exponential decay
    storm_dur             length of the wet spell in progress, days
    storm_rain            rain accumulated in that spell, mm
    storm_id_ratio        ID-threshold exceedance for the spell (physics)

🔗 SPINE — flood reuses this stage unchanged. Nothing here is landslide-specific.

════════════════════════════════════════════════════════════════════════════
WHY BOTH SHORT AND LONG WINDOWS
════════════════════════════════════════════════════════════════════════════
Two different mechanisms, and a model given only one of them cannot separate:

    r1, r3     the burst that actually breaks the slope
    r15, r30   the antecedent wetting that decided whether the burst was enough

The same 100 mm day is unremarkable on dry ground and lethal on ground already
saturated by three wet weeks. `api` compresses that history into one number by
decaying each past day by 0.92^age, which weights recent rain more heavily than
a flat 30-day sum does.

════════════════════════════════════════════════════════════════════════════
THE ID THRESHOLD — physics enters here, as a feature
════════════════════════════════════════════════════════════════════════════
Rainfall-triggered landsliding follows an intensity–duration relationship:
short bursts need high intensity, long soakings need less. The classic form is

    I = a * D^(-b)          I mean intensity mm/hr, D duration hr

`storm_id_ratio` is the actual intensity of the wet spell in progress divided
by that threshold. Above 1.0 means the storm exceeded the curve.

⚠️ **Applied to STORM EVENTS, not rolling windows.** Doing it on rolling windows
was measured to collapse into a rescaled 30-day total (r=0.973) — see the
inline note at the computation. Duration here means "how long has it been
raining", which is what the ID relationship is actually about.

We use two published GLOBAL thresholds:

    Caine (1980)      I = 14.82 * D^-0.39
    Guzzetti (2008)   I = 2.20  * D^-0.44

⚠️ NEITHER IS CALIBRATED FOR ARUNACHAL, and it matters: this is one of the
wettest places on earth (2,000-4,000+ mm/yr against a global land mean nearer
800). A global threshold will be exceeded routinely here, so `id_ratio` must be
read as a RELATIVE severity index, not as "a landslide is expected above 1.0".

Local calibration needs dated events, which we do not yet have — GSI carries no
dates and Bhuvan only season-years. That is PX (label factory) work. Until then
this feature earns its place by ranking storms sensibly, not by being a
decision threshold. The `a`/`b` constants are module-level so recalibration is
a one-line change, not a rewrite.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import time
import warnings

import numpy as np
import pandas as pd

from common import INTERIM, WEATHER

warnings.filterwarnings("ignore")

SRC = INTERIM / "rainfall"
OUT = SRC / "features"

WINDOWS = (1, 3, 7, 15, 30)
API_DECAY = 0.92
WET_MM = 1.0

# I = A * D^-B, I in mm/hr, D in hours. See module docstring — provisional.
THRESHOLDS = {"caine1980": (14.82, 0.39), "guzzetti2008": (2.20, 0.44)}
ID_USE = "guzzetti2008"      # the lower, more conservative curve


def rolling_sum(x: np.ndarray, w: int) -> np.ndarray:
    """Trailing sum over w days, inclusive of today. Days before a full window
    exists are NaN — our archive starts 2000-06-01, so the first 30 days
    genuinely have no antecedent history and must not pretend to."""
    if w == 1:
        return x.copy()
    cs = np.cumsum(np.nan_to_num(x, nan=0.0), axis=0, dtype=np.float64)
    out = np.empty_like(x, dtype=np.float32)
    out[w - 1:] = (cs[w - 1:] - np.vstack([np.zeros((1, x.shape[1])),
                                           cs[:-w]])).astype(np.float32)
    out[:w - 1] = np.nan
    return out


def main() -> None:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    print("P7b — rainfall features")

    stack = np.load(SRC / "precip_mm.npy")             # (ndays, nlat, nlon)
    dates = np.load(SRC / "dates.npy")
    nd, nlat, nlon = stack.shape
    x = stack.reshape(nd, nlat * nlon)
    print(f"  stack {stack.shape} -> {x.shape}   "
          f"{dates[0]} .. {dates[-1]}")

    feats: dict[str, np.ndarray] = {}

    # --- trailing totals ---------------------------------------------------
    for w in WINDOWS:
        feats[f"r{w}"] = rolling_sum(x, w)
        v = feats[f"r{w}"]
        print(f"    r{w:<3} mean {np.nanmean(v):7.1f} mm   "
              f"p99 {np.nanpercentile(v, 99):7.1f}   max {np.nanmax(v):7.1f}")

    # --- wettest day and wet-day count in the last 30 ---------------------
    print("  rolling max / wet days...", flush=True)
    rmax = np.full_like(x, np.nan)
    wet = np.full_like(x, np.nan)
    xz = np.nan_to_num(x, nan=0.0)
    wetbin = (xz > WET_MM).astype(np.float32)
    cw = np.cumsum(wetbin, axis=0, dtype=np.float64)
    for t in range(29, nd):
        rmax[t] = xz[t - 29:t + 1].max(axis=0)
    wet[29:] = (cw[29:] - np.vstack([np.zeros((1, x.shape[1])),
                                     cw[:-30]])).astype(np.float32)
    feats["rmax_30"] = rmax
    feats["wetdays_30"] = wet
    print(f"    rmax_30    mean {np.nanmean(rmax):7.1f} mm   "
          f"max {np.nanmax(rmax):7.1f}")
    print(f"    wetdays_30 mean {np.nanmean(wet):7.1f} d")

    # --- antecedent precipitation index -----------------------------------
    # api[t] = rain[t] + decay * api[t-1]. One pass, no window to choose.
    print("  API...", flush=True)
    api = np.empty_like(x, dtype=np.float32)
    acc = np.zeros(x.shape[1], dtype=np.float32)
    for t in range(nd):
        acc = xz[t] + API_DECAY * acc
        api[t] = acc
    api[:29] = np.nan               # spin-up, same reasoning as the windows
    feats["api"] = api
    print(f"    api        mean {np.nanmean(api):7.1f}   "
          f"p99 {np.nanpercentile(api, 99):7.1f}")

    # --- storm events, then the ID threshold on THEM ----------------------
    # ⚠️ An earlier version applied the ID curve to the rolling windows and took
    # the worst exceedance. MEASURED: that collapsed to r30 (correlation 0.973)
    # and added nothing. The reason is conceptual, not a coding slip — during a
    # monsoon it rains near-continuously, so a rolling 30-day window is not a
    # storm duration, it is just a window, and cumulative rain grows faster with
    # D than the threshold curve decays. The longest window therefore always won
    # (67% of the time), making the feature a rescaled 30-day total.
    #
    # The ID relationship describes DISCRETE EVENTS. So identify actual storms:
    # a maximal run of consecutive days above WET_MM. Duration is how long the
    # current run has lasted, intensity is its mean rate. Dry days score 0.
    print("  storm events + ID exceedance...", flush=True)
    A, B = THRESHOLDS[ID_USE]
    wetday = xz > WET_MM
    sdur = np.zeros_like(x, dtype=np.float32)
    srain = np.zeros_like(x, dtype=np.float32)
    for t in range(1, nd):
        sdur[t] = np.where(wetday[t], sdur[t - 1] + 1.0, 0.0)
        srain[t] = np.where(wetday[t], srain[t - 1] + xz[t], 0.0)
    sdur[0] = wetday[0]
    srain[0] = np.where(wetday[0], xz[0], 0.0)

    hrs = np.maximum(sdur, 1.0) * 24.0
    with np.errstate(invalid="ignore", divide="ignore"):
        inten = srain / hrs                          # mm/hr
        ratio = inten / (A * hrs ** (-B))
    ratio = np.where(sdur > 0, ratio, 0.0).astype(np.float32)

    feats["storm_dur"] = sdur
    feats["storm_rain"] = srain
    feats["storm_id_ratio"] = ratio

    ex = float(np.mean(ratio > 1.0))
    live = sdur > 0
    print(f"    storm_dur       mean {sdur[live].mean():5.2f} d   "
          f"max {sdur.max():.0f} d   ({100*live.mean():.0f}% of days in a storm)")
    print(f"    storm_rain      mean {srain[live].mean():6.1f} mm   "
          f"max {srain.max():.0f} mm")
    print(f"    storm_id_ratio  mean {ratio[live].mean():5.2f}   "
          f"p99 {np.percentile(ratio, 99):5.2f}")
    print(f"    days over the curve: {100*ex:.1f}%")

    # --- write -------------------------------------------------------------
    for k, v in feats.items():
        np.save(OUT / f"{k}.npy", v.astype(np.float32))
    print(f"\n  wrote {len(feats)} feature arrays "
          f"({sum(v.nbytes for v in feats.values())/1e6:.0f} MB)")

    # --- per-date table: season + ENSO ------------------------------------
    d = pd.to_datetime(dates.astype("datetime64[D]"))
    tab = pd.DataFrame({"date": d, "year": d.year, "month": d.month,
                        "doy": d.dayofyear})
    tab["monsoon"] = tab.month.between(5, 10).astype("int8")
    tab["doy_sin"] = np.sin(2 * np.pi * tab.doy / 365.25).astype(np.float32)
    tab["doy_cos"] = np.cos(2 * np.pi * tab.doy / 365.25).astype(np.float32)
    tab["oni"] = load_oni(tab)
    miss = float(tab.oni.isna().mean())
    print(f"  ENSO ONI joined  ({100*(1-miss):.1f}% of days matched)")
    tab.to_parquet(SRC / "date_features.parquet", index=False)

    (OUT / "_features_meta.json").write_text(json.dumps({
        "features": sorted(feats), "shape": [int(nd), int(nlat * nlon)],
        "windows": list(WINDOWS), "api_decay": API_DECAY,
        "id_threshold": ID_USE, "id_constants": {"a": A, "b": B},
        "id_exceedance_frac": round(ex, 4),
        "date_min": str(dates[0]), "date_max": str(dates[-1]),
        "nan_note": "first 29 days NaN — incomplete antecedent window",
        "caveat": "id_ratio is a relative severity index; global curve is not "
                  "calibrated for Arunachal. Recalibrate when dated events exist.",
    }, indent=2))
    print(f"\n  done in {time.time()-t0:.0f}s")


def load_oni(tab: pd.DataFrame) -> pd.Series:
    """NOAA CPC ONI: overlapping 3-month seasons, each centred on its middle
    month. DJF is centred on January, so month M maps to the M-th season."""
    p = WEATHER / "noaa-cpc_oni_enso_global.txt"
    if not p.exists():
        return pd.Series(np.nan, index=tab.index)
    rows = []
    for line in p.read_text().splitlines()[1:]:
        f = line.split()
        if len(f) == 4:
            rows.append((f[0], int(f[1]), float(f[3])))
    seas = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ",
            "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
    order = {s: i + 1 for i, s in enumerate(seas)}
    o = pd.DataFrame(rows, columns=["seas", "year", "oni"])
    o["month"] = o.seas.map(order)
    o = o.dropna(subset=["month"])
    return tab.merge(o[["year", "month", "oni"]], on=["year", "month"],
                     how="left")["oni"].astype("float32")


if __name__ == "__main__":
    main()
