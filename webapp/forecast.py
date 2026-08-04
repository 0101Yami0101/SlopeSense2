"""Forecast logic — deliberately free of Streamlit imports so it can be tested.

    live rainfall (Open-Meteo)  ->  rolling totals  ->  percentile vs local
    climatology  ->  trigger  ->  hazard = susceptibility x trigger

════════════════════════════════════════════════════════════════════════════
WHY PERCENTILES AND NOT MILLIMETRES
════════════════════════════════════════════════════════════════════════════
Arunachal spans 799 to 4,167 mm of rain a year. 30 mm in three days is an
ordinary week in the Siang gorge and a once-a-year soaking on the northern
crest. A single millimetre threshold would alert the wet south permanently and
the dry north never.

So every reading is scored against WHAT IS NORMAL FOR THAT EXACT PLACE, using
16 years of history at each query point. The model learns "unusually wet for
here", which is the thing that actually matters.

════════════════════════════════════════════════════════════════════════════
ONE SOURCE, END TO END — THIS IS NOT OPTIONAL
════════════════════════════════════════════════════════════════════════════
The climatology and the live values must come from the SAME source. Measured on
1,068 matched cell-days, Open-Meteo runs 1.68x wetter than IMERG and correlates
with it at only 0.320 daily. A day at IMERG's 50th percentile is nowhere near
Open-Meteo's 50th.

Mixing them produces confident, wrong numbers with nothing on screen looking
wrong. The shipped quantile tables are built from the Open-Meteo archive, which
is the same source chain the forecast API serves (measured: ratio 1.00,
correlation 1.000).
"""
from __future__ import annotations

import time

import numpy as np
import requests

API = "https://api.open-meteo.com/v1/forecast"
FEATURES = ("r3", "r7")
BATCH = 40                 # locations per call; 100 trips the rate limit
PAST_DAYS = 10             # enough history to fill the 7-day trailing window
FORECAST_DAYS = 8


def fetch_rain(lats, lons, timeout: int = 25, retries: int = 3):
    """Daily rain (mm) per query point. Returns (dates, array[n_days, n_points]).

    Returns None on failure so the app degrades to susceptibility-only rather
    than showing a broken forecast.

    ⚠️ Retries with backoff on purpose. This is a free API with a per-minute
    cap, and a public page can trip it through no fault of the visitor. Without
    retries a single transient 429 loses the entire forecast — observed in
    testing, where the request pattern that failed once succeeded moments later
    unchanged.
    """
    days = None
    cols = []
    for i in range(0, len(lats), BATCH):
        la = lats[i:i + BATCH]
        lo = lons[i:i + BATCH]
        res = None
        for attempt in range(retries):
            try:
                r = requests.get(API, params={
                    "latitude": ",".join(f"{x:.4f}" for x in la),
                    "longitude": ",".join(f"{x:.4f}" for x in lo),
                    "daily": "precipitation_sum",
                    "past_days": PAST_DAYS, "forecast_days": FORECAST_DAYS,
                    "timezone": "UTC"}, timeout=timeout)
                if r.status_code == 429:
                    time.sleep(2 + 3 * attempt)
                    continue
                r.raise_for_status()
                js = r.json()
            except Exception:                                  # noqa: BLE001
                time.sleep(1 + 2 * attempt)
                continue
            cand = js if isinstance(js, list) else [js]
            if len(cand) == len(la) and all(x.get("daily") for x in cand):
                res = cand
                break
        if res is None:
            return None
        for x in res:
            d = x["daily"]
            days = d["time"]
            cols.append([0.0 if v is None else float(v)
                         for v in d["precipitation_sum"]])
    if days is None:
        return None
    return np.array(days), np.array(cols, dtype=np.float32).T


def rolling_totals(rain: np.ndarray) -> dict[str, np.ndarray]:
    """Trailing sums. Row t is the total for the window ENDING on day t."""
    out = {}
    for f in FEATURES:
        w = int(f[1:])
        cs = np.cumsum(rain, axis=0, dtype=np.float64)
        a = np.full_like(rain, np.nan, dtype=np.float32)
        a[w - 1:] = (cs[w - 1:] -
                     np.vstack([np.zeros((1, rain.shape[1])), cs[:-w]])).astype(np.float32)
        out[f] = a
    return out


def to_percentile(vals: np.ndarray, breaks: np.ndarray) -> np.ndarray:
    """Where each value sits in its own point's climatology, 0-1.

    `breaks` is (101, n_points): the 0th..100th percentile of that point's
    monsoon history. Shipping breakpoints instead of raw history is what keeps
    the bundle at ~0.1 MB instead of ~17 MB, at 1% resolution.
    """
    n = vals.shape[-1]
    out = np.empty_like(vals, dtype=np.float32)
    for j in range(n):
        out[..., j] = np.searchsorted(breaks[:, j], vals[..., j]) / (breaks.shape[0] - 1)
    return np.clip(out, 0.0, 1.0)


def trigger_series(rain: np.ndarray, quantiles: dict) -> np.ndarray:
    """Trigger score per day per point: the mean of the r3 and r7 percentiles."""
    tot = rolling_totals(rain)
    return np.nanmean([to_percentile(tot[f], quantiles[f]) for f in FEATURES],
                      axis=0).astype(np.float32)


def hazard_raster(susceptibility_u8: np.ndarray, nearest: np.ndarray,
                  trigger_pts: np.ndarray) -> np.ndarray:
    """hazard = susceptibility x trigger, as float32 with NaN outside the domain.

    Both terms are needed and neither is enough on its own: a cliff in dry
    weather does not fail, and a downpour on flat stable ground does nothing.
    Multiplying keeps that — near-zero in either term gives near-zero hazard.

    ⚠️ 255 means "not assessed" (ice, open water, slope <= 10 deg). Those cells
    stay NaN and must render as grey, never as "low risk" — the model never saw
    that terrain and has no business scoring it.
    """
    sus = susceptibility_u8.astype(np.float32)
    sus[susceptibility_u8 == 255] = np.nan
    sus /= 254.0
    return sus * trigger_pts[nearest]


def nearest_assessed(sus: np.ndarray, r: int, c: int, max_cells: int = 10):
    """Nearest cell the model actually scored. (row, col, distance_in_cells).

    ⚠️ 12% of Arunachal's 4,648 settlements sit on a cell scored 255 — valley
    floors, riverbanks, anything flatter than 10 degrees. Those are exactly the
    towns people search for, and returning "not assessed" is a dead end that is
    also physically misleading: what threatens a valley town is the slope ABOVE
    it, not the flat ground it is built on.

    So the search snaps to the closest scored cell — and the caller must SAY it
    snapped, with the distance. Silently moving someone's location would be the
    dishonest version of this.

    Returns None if nothing is assessed within max_cells, which is the right
    answer for the middle of a large river or a high snowfield.
    """
    if sus[r, c] != 255:
        return r, c, 0.0
    h, w = sus.shape
    r0, r1 = max(r - max_cells, 0), min(r + max_cells + 1, h)
    c0, c1 = max(c - max_cells, 0), min(c + max_cells + 1, w)
    ok = np.argwhere(sus[r0:r1, c0:c1] != 255)
    if ok.size == 0:
        return None
    d = (ok[:, 0] + r0 - r) ** 2 + (ok[:, 1] + c0 - c) ** 2
    i = int(np.argmin(d))
    return int(ok[i, 0] + r0), int(ok[i, 1] + c0), float(np.sqrt(d[i]))


def classify(h: np.ndarray, breaks_pct=(50, 75, 90, 97)) -> np.ndarray:
    """1..5 by fixed hazard cuts; 0 = not assessed.

    Cuts are deliberately top-heavy rather than equal fifths: Very High is ~3%
    of the state, which is what makes the map actionable instead of colouring a
    fifth of Arunachal red.
    """
    cuts = np.array([0.02, 0.06, 0.15, 0.30], dtype=np.float32)
    out = np.zeros(h.shape, dtype=np.uint8)
    ok = np.isfinite(h)
    out[ok] = (np.digitize(h[ok], cuts) + 1).astype(np.uint8)
    return out
