"""Arunachal Pradesh landslide forecast — 7 days ahead.

The product is the FORECAST. Susceptibility is the layer underneath it, not the
headline: a static map of where slopes are weak never changes, so it cannot tell
anyone what to do this week.

    hazard = susceptibility (where, 100 m, static)
           x trigger        (when, ~33 km, daily)

Reads only webapp/assets/ (0.45 MB) and calls Open-Meteo. No rasterio, no
geopandas, no model files — so it runs on a free 1 GB host.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

import forecast as fc
import theme

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="Arunachal Landslide Forecast",
                   page_icon="⛰️", layout="wide")
st.markdown(theme.CSS, unsafe_allow_html=True)


# ── data ────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_bundle():
    g = json.loads((ASSETS / "grid.json").read_text())
    pts = json.loads((ASSETS / "points.json").read_text())
    met = json.loads((ASSETS / "metrics.json").read_text())
    sus = np.load(ASSETS / "susceptibility.npz")["sus"]
    near = np.load(ASSETS / "nearest_point.npz")["near"]
    q = np.load(ASSETS / "clim_quantiles.npz")
    quant = {k: q[k] for k in q.files}
    districts = json.loads((ASSETS / "districts.geojson").read_text())
    return g, pts, met, sus, near, quant, districts


# Cached for an hour: the forecast only updates a few times a day, and this
# keeps the app to ~3 API calls per hour no matter how many people visit.
@st.cache_data(ttl=3600, show_spinner="Fetching latest rainfall forecast…")
def load_forecast(lats: tuple, lons: tuple):
    return fc.fetch_rain(list(lats), list(lons))


G, PTS, MET, SUS, NEAR, QUANT, DISTRICTS = load_bundle()
H, W = G["height"], G["width"]

st.markdown(
    "<div class='brand'><div class='brand-logo'>⛰️</div><div>"
    "<div class='brand-name'>Arunachal Landslide Forecast</div>"
    "<div class='brand-tag'>Eastern Himalaya · 7-day outlook</div>"
    "</div></div>", unsafe_allow_html=True)

res = load_forecast(tuple(PTS["lat"]), tuple(PTS["lon"]))

if res is None:
    st.markdown(
        "<div class='warn'><b>Live rainfall unavailable.</b> The weather service "
        "did not respond, so no forecast can be shown. The susceptibility layer "
        "below is unaffected — it is static and does not depend on the API."
        "</div>", unsafe_allow_html=True)
    days, rain = None, None
else:
    days, rain = res

# ── forecast → trigger → hazard ─────────────────────────────────────────────
if rain is not None:
    trig = fc.trigger_series(rain, QUANT)          # (n_days, n_points)
    dts = pd.to_datetime(days)
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    # Trailing windows mean the first few rows have no history; keep only days
    # that are both fully computed and today-or-later.
    valid = np.isfinite(trig).all(axis=1)
    fut = np.array([(d >= today) and valid[i] for i, d in enumerate(dts)])
    fidx = np.flatnonzero(fut)[:7]
    if len(fidx) == 0:
        fidx = np.flatnonzero(valid)[-7:]

    # ── today's headline ────────────────────────────────────────────────────
    haz0 = fc.hazard_raster(SUS, NEAR, trig[fidx[0]])
    cls0 = fc.classify(haz0)
    inhi = float(np.mean(cls0[cls0 > 0] >= 4)) if (cls0 > 0).any() else 0.0
    level = ("Very High" if inhi > 0.12 else "High" if inhi > 0.06
             else "Moderate" if inhi > 0.02 else "Low")
    lcol = {"Low": theme.CLASS_COLORS[1], "Moderate": theme.CLASS_COLORS[2],
            "High": theme.CLASS_COLORS[3], "Very High": theme.CLASS_COLORS[4]}[level]

    c1, c2 = st.columns([2.1, 3])
    with c1:
        st.markdown(
            f"<div class='alert-hero'><div class='alert-level' style='color:{lcol}'>"
            f"{level}</div><div class='alert-sub'>Statewide outlook for "
            f"{dts[fidx[0]]:%A %d %B} — <b>{100*inhi:.1f}%</b> of assessed slopes "
            f"in High or Very High hazard</div></div>", unsafe_allow_html=True)
    with c2:
        k = st.columns(4)
        vals = [(f"{MET['susceptibility']['auc']:.3f}", "Where-model accuracy"),
                (f"{MET['trigger']['auc']:.3f}", "When-model accuracy"),
                (f"{MET['labels']['polygons']:,}", "Mapped landslides"),
                ("7", "Days ahead")]
        for col, (n, l) in zip(k, vals):
            col.markdown(f"<div class='kpi'><div class='kpi-num'>{n}</div>"
                         f"<div class='kpi-lbl'>{l}</div></div>",
                         unsafe_allow_html=True)

    # ── day strip ───────────────────────────────────────────────────────────
    st.markdown("#### Pick a day")
    if "day" not in st.session_state:
        st.session_state.day = 0
    cols = st.columns(len(fidx))
    for n, (col, i) in enumerate(zip(cols, fidx)):
        h = fc.hazard_raster(SUS, NEAR, trig[i])
        c = fc.classify(h)
        share = float(np.mean(c[c > 0] >= 4)) if (c > 0).any() else 0.0
        dc = (theme.CLASS_COLORS[4] if share > 0.12 else
              theme.CLASS_COLORS[3] if share > 0.06 else
              theme.CLASS_COLORS[2] if share > 0.02 else theme.CLASS_COLORS[1])
        # Nested same-quotes inside an f-string need Python 3.12+; build the
        # class name outside so this parses on any 3.x the host happens to use.
        sel_cls = "sel" if n == st.session_state.day else ""
        with col:
            st.markdown(
                f"<div class='daycard {sel_cls}'>"
                f"<div class='dow'>{dts[i]:%a}</div>"
                f"<div class='dnum'>{dts[i]:%d %b}</div>"
                f"<div class='dot' style='background:{dc}'></div></div>",
                unsafe_allow_html=True)
            if st.button("select", key=f"d{n}", width='stretch'):
                st.session_state.day = n
                st.rerun()

    sel = fidx[min(st.session_state.day, len(fidx) - 1)]
    lead = (dts[sel] - today).days
    haz = fc.hazard_raster(SUS, NEAR, trig[sel])
    cls = fc.classify(haz)

    if lead >= 4:
        st.markdown(
            f"<div class='warn'><b>Day {lead} — lower confidence.</b> Rainfall "
            "forecasts are reliable about three days out and degrade after that. "
            "Treat this as an outlook, not a prediction.</div>",
            unsafe_allow_html=True)

    # ── map ─────────────────────────────────────────────────────────────────
    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"#### Hazard — {dts[sel]:%A %d %B %Y}")
        rgb = np.zeros((H, W, 3), dtype=np.uint8)
        na = np.array([int(theme.NOT_ASSESSED[i:i+2], 16) for i in (1, 3, 5)])
        rgb[:] = np.array([18, 21, 26])
        rgb[cls == 0] = na
        for k in range(1, 6):
            col = theme.CLASS_COLORS[k - 1]
            rgb[cls == k] = [int(col[i:i+2], 16) for i in (1, 3, 5)]
        st.image(Image.fromarray(rgb), width='stretch')
        st.markdown(theme.legend_html(), unsafe_allow_html=True)
        st.markdown(
            "<div class='note'>Fine detail in this map is <b>terrain</b> at 100 m. "
            "The rainfall driving it is sampled about every 33 km — far coarser "
            "than it looks. Grey areas are ice, open water or ground under 10° "
            "slope: the model was never trained there and does not score them.</div>",
            unsafe_allow_html=True)

    with right:
        st.markdown("#### Where it is worst")
        pl = np.array(PTS["lat"]); po = np.array(PTS["lon"])
        tv = trig[sel]
        order = np.argsort(-tv)[:8]
        st.dataframe(pd.DataFrame({
            "Location": [f"{pl[i]:.2f}°N {po[i]:.2f}°E" for i in order],
            "Rain vs normal": [f"{100*tv[i]:.0f}th pct" for i in order],
        }), hide_index=True, width='stretch')

        st.markdown("#### Rain across the week")
        tot = fc.rolling_totals(rain)["r3"]
        st.dataframe(pd.DataFrame({
            "Day": [f"{dts[i]:%a %d %b}" for i in fidx],
            "3-day rain (avg mm)": [f"{np.nanmean(tot[i]):.0f}" for i in fidx],
            "Trigger": [f"{100*np.nanmean(trig[i]):.0f}th pct" for i in fidx],
        }), hide_index=True, width='stretch')

# ── methodology ─────────────────────────────────────────────────────────────
with st.expander("How this works, and what it cannot do"):
    s, t = MET["susceptibility"], MET["trigger"]
    st.markdown(f"""
**Two questions, answered separately, then multiplied.**

**Where can a slope fail?** Learned from **{MET['labels']['polygons']:,} mapped
landslides** using terrain, soil, rock and land cover — no rainfall at all.
Accuracy **{s['auc']:.3f}** when tested on regions it never saw during training.
The top 3% of terrain contains about 40% of known landslides.

**When might it fail?** Rainfall compared against **what is normal for that exact
place**, using 16 years of local history. Accuracy **{t['auc']:.3f}**, measured
against {t['n_events']} landslides whose dates are known.

Both matter: a steep slope in dry weather does not fail, and heavy rain on flat
stable ground does nothing.

---

**What this cannot do**

- The number is a **relative ranking, not a probability**. We know where landslides
  *did* happen; nobody records where they did *not*, so there is no honest way to
  say "12% chance".
- **Rainfall is coarse.** About 33 km between weather samples. A cloudburst over a
  single narrow valley can be missed.
- Confidence **drops sharply after about three days**.
- Grey areas are **not assessed**, which is not the same as safe.
- **Not for operational safety decisions.**
""")

st.caption("Rainfall: Open-Meteo · Terrain: Copernicus DEM · Landslides: GSI, "
           "NRSC Bhuvan, NASA · Not for operational safety decisions.")
