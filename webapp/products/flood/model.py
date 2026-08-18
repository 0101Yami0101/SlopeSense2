"""Flood maths — deliberately free of Streamlit so it can be tested directly.

    flood hazard = flood-prone ground (static, from terrain)
                 x catchment rain     (daily, routed downstream)

THE ONE IDEA THAT MAKES THIS DIFFERENT FROM THE LANDSLIDE TRIGGER
A slope fails because of the rain that lands ON it. A river rises because of
the rain that lands ANYWHERE UPSTREAM of it. So the flood signal cannot be read
off the nearest rain gauge — it has to be collected over the whole catchment
and carried downstream. That is what accumulate() does, and it is why the
bundle ships a basin graph at all.

⚠️ The output is an INDEX, not a probability, and not a depth. Nothing here
estimates how deep the water gets or how likely a flood is; see the module's
Method page for exactly what is missing.
"""
from __future__ import annotations

import numpy as np

# Breaks on hazard = index x catchment percentile. Absolute, not percentile
# breaks: on an ordinary day the catchment percentile sits near 0.5, so these
# are roughly the static index's own breaks halved. Percentile breaks would
# force a fifth of the floodplain into "Very High" every single day, including
# days with no rain at all.
HAZARD_BREAKS = np.array([0.04, 0.10, 0.20, 0.33], dtype=np.float32)

CLASS_NAMES = ["Very Low", "Low", "Moderate", "High", "Very High"]

# A catchment this size or larger is a river a global model can resolve; below
# it, we are watching rainfall rather than forecasting a river. The split is
# the single most important honest line in this product.
LARGE_RIVER_KM2 = 2_000.0


def accumulate(values: np.ndarray, sub_area: np.ndarray,
               next_down: np.ndarray, order: np.ndarray) -> np.ndarray:
    """Area-weighted mean of `values` over each basin AND everything upstream.

    One pass in topological order, headwaters first, so by the time a basin is
    read its tributaries have already contributed. `order` comes from the
    bundle, where it was checked against the routing graph — a single
    out-of-order pair would silently drop a catchment's rain from everything
    below it.
    """
    weighted = (values * sub_area).astype(np.float64)
    area = sub_area.astype(np.float64).copy()
    for i in order:
        d = next_down[i]
        if d >= 0:
            weighted[d] += weighted[i]
            area[d] += area[i]
    return (weighted / np.maximum(area, 1e-9)).astype(np.float32), area


def catchment_signal(rain_day: np.ndarray, trig_day: np.ndarray,
                     rain_pt: np.ndarray, sub_area: np.ndarray,
                     next_down: np.ndarray, order: np.ndarray):
    """Per basin: upstream mean rainfall (mm), upstream mean anomaly, and the
    upstream area those two are means over.

    The anomaly is what drives the forecast — millimetres alone would make the
    wet south look dangerous every day of the monsoon, because it IS wet every
    day of the monsoon. The percentile asks the only question that matters:
    is this a lot *for here*.
    """
    mm, area = accumulate(rain_day[rain_pt], sub_area, next_down, order)
    pct, _ = accumulate(trig_day[rain_pt], sub_area, next_down, order)
    return mm, pct, area


# How a catchment's rainfall percentile becomes a forecast multiplier.
#
# ⚠️ NOT the percentile itself. Passing it straight through made an ordinary
# monsoon day read as 34% of the floodplain at High or above, every day, moving
# barely three points across a whole week — because the median day scores 0.50
# and 0.50 is most days by construction. The forecast was really just the
# static map wearing a date.
#
# Rivers rise on rain that is UNUSUAL for their catchment, so the response is
# near zero through the bottom half of the distribution and climbs steeply
# through the top. The floor keeps floodplain visible as Very Low on a calm
# day: "this is floodplain and nothing is coming" and "this is not floodplain"
# are different statements and must not render the same.
PCT_ONSET = 0.35              # below this, upstream rain is doing nothing
PCT_FLOOR = 0.02              # calm floodplain still shows, faintly


def trigger_response(pct: np.ndarray) -> np.ndarray:
    """Catchment rainfall percentile -> 0-1 forecast multiplier."""
    return np.clip((pct - PCT_ONSET) / (1.0 - PCT_ONSET),
                   PCT_FLOOR, 1.0).astype(np.float32)


def hazard_raster(idx: np.ndarray, bid: np.ndarray,
                  basin_pct: np.ndarray) -> np.ndarray:
    """Flood-prone index x its catchment's rainfall anomaly, per cell.

    Cells with no catchment (bid 0) or no flood-prone ground score zero, which
    renders transparent rather than as a low value — "this is not floodplain"
    and "this floodplain is calm today" are different statements.
    """
    out = np.zeros(idx.shape, np.float32)
    ok = (idx > 0) & (bid > 0)
    if not ok.any():
        return out
    # bid is 1-based into the basin arrays; 0 means "outside every catchment".
    resp = trigger_response(basin_pct)
    out[ok] = (idx[ok].astype(np.float32) / 254.0) * resp[bid[ok] - 1]
    return out


def classify(hz: np.ndarray) -> np.ndarray:
    """5 classes, 0 = not flood-prone."""
    out = np.zeros(hz.shape, np.uint8)
    live = hz > 0
    if live.any():
        out[live] = (np.digitize(hz[live], HAZARD_BREAKS) + 1).astype(np.uint8)
    return out


def nearest_flood_cell(idx: np.ndarray, r: int, c: int, max_rings: int = 40):
    """Nearest cell that is flood-prone at all, searched in growing rings.

    A visitor searching a hill town gets "this spot is not floodplain, the
    nearest low ground is 3 km away" instead of silence. Returns
    (row, col, rings) or None.
    """
    h, w = idx.shape
    if idx[r, c] > 0:
        return r, c, 0
    for k in range(1, max_rings + 1):
        r0, r1 = max(r - k, 0), min(r + k + 1, h)
        c0, c1 = max(c - k, 0), min(c + k + 1, w)
        sub = idx[r0:r1, c0:c1]
        hit = np.argwhere(sub > 0)
        if hit.size:
            # Closest within the ring, not merely the first in raster order.
            d = np.hypot(hit[:, 0] + r0 - r, hit[:, 1] + c0 - c)
            j = int(np.argmin(d))
            return int(hit[j, 0] + r0), int(hit[j, 1] + c0), k
    return None
