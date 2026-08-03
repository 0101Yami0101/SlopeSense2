"""SlopeSense Forecast — 7-day landslide outlook for Arunachal Pradesh.

The product is the FORECAST. Susceptibility is the layer underneath it, not the
headline: a static map of where slopes are weak never changes, so it cannot tell
anyone what to do this week.

    hazard = susceptibility (where, 100 m, static)
           x trigger        (when, ~33 km, daily)

Reads only webapp/assets/ (~0.4 MB) and calls Open-Meteo. No rasterio, no
geopandas, no model files — which is what lets it run on a free 1 GB host.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from folium.plugins import Fullscreen, MiniMap
from folium.raster_layers import ImageOverlay
from streamlit_folium import st_folium

import forecast as fc
import theme as T

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="SlopeSense Forecast · Arunachal Pradesh",
                   page_icon="◭", layout="wide",
                   initial_sidebar_state="expanded")
st.markdown(T.CSS, unsafe_allow_html=True)
# Warm the TLS handshake for the tile hosts before the map asks for them.
st.markdown(
    '<link rel="preconnect" href="https://a.basemaps.cartocdn.com">'
    '<link rel="preconnect" href="https://server.arcgisonline.com">'
    '<link rel="preconnect" href="https://tile.opentopomap.org">',
    unsafe_allow_html=True)


# ─────────────────────────── data ────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_bundle():
    g = json.loads((ASSETS / "grid.json").read_text())
    sus = np.load(ASSETS / "susceptibility.npz")["sus"]
    near = np.load(ASSETS / "nearest_point.npz")["near"]
    qz = np.load(ASSETS / "clim_quantiles.npz")
    quant = {k: qz[k] for k in qz.files}
    pts = json.loads((ASSETS / "points.json").read_text())
    met = json.loads((ASSETS / "metrics.json").read_text())
    dist = json.loads((ASSETS / "districts.geojson").read_text())
    bnd = json.loads((ASSETS / "boundary.geojson").read_text())
    return g, sus, near, quant, pts, met, dist, bnd


# TTL of 1 h: the underlying forecast only updates a few times a day, and this
# also caps how hard a busy page hits a free API — the cache is shared across
# all visitors, so traffic does not multiply requests.
@st.cache_data(ttl=3600, show_spinner="Fetching live rainfall…")
def load_forecast(lats: tuple, lons: tuple):
    return fc.fetch_rain(list(lats), list(lons))


G, SUS, NEAR, QUANT, PTS, MET, DISTRICTS, BOUNDARY = load_bundle()
H, W = G["height"], G["width"]
WEST, EAST, SOUTH, NORTH = G["west"], G["east"], G["south"], G["north"]

fx = load_forecast(tuple(PTS["lat"]), tuple(PTS["lon"]))
LIVE = fx is not None


# ─────────────────────────── helpers ─────────────────────────────────────────
def latlon_to_px(lat: float, lon: float):
    """Bundle is EPSG:4326 on a regular lattice, so this is plain arithmetic —
    which is exactly why the export reprojects instead of shipping UTM."""
    if not (SOUTH <= lat <= NORTH and WEST <= lon <= EAST):
        return None
    c = int((lon - WEST) / (EAST - WEST) * W)
    r = int((NORTH - lat) / (NORTH - SOUTH) * H)
    return min(max(r, 0), H - 1), min(max(c, 0), W - 1)


def rgba_overlay(cls: np.ndarray) -> np.ndarray:
    """Class colours -> RGBA. Not-assessed stays fully TRANSPARENT so the
    basemap shows through — a grey fill would read as a real, low value."""
    out = np.zeros((*cls.shape, 4), dtype=np.uint8)
    for i, hexc in enumerate(T.CLASS_COLORS, start=1):
        m = cls == i
        if m.any():
            out[m, 0] = int(hexc[1:3], 16)
            out[m, 1] = int(hexc[3:5], 16)
            out[m, 2] = int(hexc[5:7], 16)
            out[m, 3] = 205
    return out


def base_map(zoom=7, center=None):
    m = folium.Map(location=center or [(SOUTH + NORTH) / 2, (WEST + EAST) / 2],
                   zoom_start=zoom, tiles=None, control_scale=True)
    # folium.Map(min_zoom=) is a no-op when tiles=None — it only reaches the
    # default tile layer, which we skip. Leaflet's own option must be set here
    # or scroll-out is unbounded and eventually shows repeated world copies.
    m.options.update(minZoom=T.MAP_MIN_ZOOM,
                     maxBounds=[[SOUTH - 1.5, WEST - 1.5], [NORTH + 1.5, EAST + 1.5]],
                     maxBoundsViscosity=1.0, worldCopyJump=False)
    url, attr = T.BASEMAPS[basemap]
    folium.TileLayer(url, attr=attr, name="Base", control=False,
                     min_zoom=T.MAP_MIN_ZOOM, no_wrap=True).add_to(m)
    return m


def finish_map(m, districts=False):
    if districts:
        folium.GeoJson(DISTRICTS, name="Districts",
                       style_function=lambda _: {"color": "#9fb3c8", "weight": .9,
                                                 "fill": False, "opacity": .55},
                       tooltip=folium.GeoJsonTooltip(["district"], aliases=[""])
                       ).add_to(m)
    folium.GeoJson(BOUNDARY, name="State",
                   style_function=lambda _: {"color": T.BOUNDARY_INK[basemap],
                                             "weight": 2.1, "fill": False,
                                             "dashArray": "6 3"}).add_to(m)
    if show_labels:
        # Labels ride in a pane ABOVE the overlay, or place names vanish under it.
        folium.map.CustomPane("labels", z_index=650).add_to(m)
        folium.TileLayer(T.LABEL_TILES[basemap], attr=T.CARTO, name="Labels",
                         pane="labels", control=False,
                         min_zoom=T.MAP_MIN_ZOOM, no_wrap=True).add_to(m)
    Fullscreen(position="topleft").add_to(m)
    if show_minimap:
        MiniMap(toggle_display=True, minimized=True).add_to(m)
    return m


@st.cache_data(show_spinner=False)
def district_table(cls_bytes: bytes, shape: tuple, tag: str):
    """Share of each district in High / Very High."""
    cls = np.frombuffer(cls_bytes, dtype=np.uint8).reshape(shape)
    rows = []
    for feat in DISTRICTS["features"]:
        name = feat["properties"].get("district", "—")
        geom = feat["geometry"]
        polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                 else [geom["coordinates"]])
        lons, lats = [], []
        for poly in polys:
            for x, y in poly[0]:
                lons.append(x); lats.append(y)
        if not lons:
            continue
        a = latlon_to_px(max(lats), min(lons))
        b = latlon_to_px(min(lats), max(lons))
        if a is None or b is None:
            continue
        sub = cls[a[0]:b[0] + 1, a[1]:b[1] + 1]
        sub = sub[sub > 0]
        if sub.size == 0:
            continue
        rows.append({"District": name,
                     "High+ %": round(100 * float((sub >= 4).mean()), 1),
                     "Peak class": T.CLASS_NAMES[int(sub.max()) - 1],
                     "Assessed cells": int(sub.size)})
    return pd.DataFrame(rows).sort_values("High+ %", ascending=False)


# ─────────────────────────── sidebar ─────────────────────────────────────────
VIEWS = [("🌧️", "Forecast"), ("🗺️", "Susceptibility"), ("📊", "Model & Validation")]
if "view" not in st.session_state:
    st.session_state.view = VIEWS[0][1]

with st.sidebar:
    st.markdown("""
    <div class="brand">
      <div class="brand-logo">◭</div>
      <div><div class="brand-name">SlopeSense Forecast</div>
           <div class="brand-tag">ARUNACHAL PRADESH · 7-DAY OUTLOOK</div></div>
    </div>""", unsafe_allow_html=True)

    for icon, label in VIEWS:
        active = st.session_state.view == label
        if st.button(f"{icon}  {label}", key=f"nav_{label}",
                     use_container_width=True,
                     type="primary" if active else "secondary"):
            if not active:
                # Rerun immediately: the other buttons in this same loop were
                # already rendered from pre-click state, so without this the
                # highlight lags a click behind.
                st.session_state.view = label
                st.rerun()
    view = st.session_state.view

    st.divider()
    st.markdown("<div class='side-label'>Map</div>", unsafe_allow_html=True)
    basemap = st.selectbox("Basemap", list(T.BASEMAPS), index=0,
                           label_visibility="collapsed")
    opacity = st.slider("Overlay opacity", 0.0, 1.0, 0.80, 0.05)
    st.markdown("<div class='side-label'>Layers</div>", unsafe_allow_html=True)
    show_districts = st.toggle("District boundaries", value=False)
    show_labels = st.toggle("Place names", value=True)
    show_minimap = st.toggle("Mini-map", value=False)

    st.divider()
    st.caption("⚠️ Not for operational safety decisions. Relative index, "
               "not a probability of failure.")


# ─────────────────────────── forecast maths ──────────────────────────────────
if LIVE:
    days, rain = fx
    trig = fc.trigger_series(rain, QUANT)          # (n_days, n_points)
    today = date.today().isoformat()
    fut = [i for i, d in enumerate(days) if d >= today][:7]
    if not fut:
        fut = list(range(len(days)))[-7:]
else:
    days, rain, trig, fut = [], None, None, []


# ═════════════════════════ VIEW: FORECAST ════════════════════════════════════
if view == "Forecast":
    if not LIVE:
        st.error("**Live rainfall is unavailable right now.** The free weather "
                 "service limits how often it can be queried. The susceptibility "
                 "map still works — open it from the sidebar. Try again shortly.")
        st.stop()

    if "day_i" not in st.session_state or st.session_state.day_i not in fut:
        st.session_state.day_i = fut[0]

    st.markdown("<div class='eyebrow'>7-day outlook</div>", unsafe_allow_html=True)
    cols = st.columns(len(fut))
    for n, (col, i) in enumerate(zip(cols, fut)):
        d = datetime.fromisoformat(days[i])
        peak = float(np.nanmax(trig[i]))
        with col:
            lbl = "Today" if n == 0 else d.strftime("%a")
            if st.button(f"{lbl}\n{d.strftime('%d %b')}\n● {peak:.2f}",
                         key=f"day_{i}", use_container_width=True,
                         type="primary" if i == st.session_state.day_i else "secondary"):
                st.session_state.day_i = i
                st.rerun()

    di = st.session_state.day_i
    sel = datetime.fromisoformat(days[di])
    tri_pts = trig[di]
    hz = fc.hazard_raster(SUS, NEAR, tri_pts)
    cls = fc.classify(hz)
    assessed = cls > 0
    hi = float((cls[assessed] >= 4).mean()) if assessed.any() else 0.0

    lvl = 4 if hi > .12 else 3 if hi > .05 else 2 if hi > .02 else 1
    band = {4: ("Very High", "#a50026"), 3: ("High", "#f46d43"),
            2: ("Moderate", "#fee08b"), 1: ("Low", "#1a9850")}[lvl]
    ahead = (sel.date() - date.today()).days
    when = "today" if ahead == 0 else "tomorrow" if ahead == 1 else f"in {ahead} days"
    conf = "higher confidence" if ahead <= 3 else "lower confidence"
    st.markdown(f"""
    <div class="alert-band">
      <div class="alert-dot" style="background:{band[1]}"></div>
      <div>
        <div class="alert-title">Statewide outlook: {band[0]}</div>
        <div class="alert-sub">{sel.strftime('%A %d %B %Y')} — {when} · {conf}</div>
      </div>
      <div class="alert-right">
        <div class="alert-num">{100*hi:.1f}%</div>
        <div class="alert-lbl">of assessed land at High+</div>
      </div>
    </div>""", unsafe_allow_html=True)

    k = st.columns(4)
    k[0].metric("Peak trigger", f"{np.nanmax(tri_pts):.2f}",
                help="Highest 'unusually wet for here' score anywhere in the state.")
    k[1].metric("Median trigger", f"{np.nanmedian(tri_pts):.2f}")
    k[2].metric("Rain, wettest point", f"{np.nanmax(rain[di]):.0f} mm")
    k[3].metric("Lead time", "Today" if ahead == 0 else f"+{ahead} d")

    left, right = st.columns([3, 1.25])
    with left:
        st.markdown(f"<div class='map-head'><div class='mh-dot'></div>"
                    f"<div class='mh-title'>Hazard — {sel.strftime('%d %b')}</div>"
                    f"<div class='mh-note'>scroll to zoom · click any point to "
                    f"inspect</div></div>", unsafe_allow_html=True)
        m = base_map()
        ImageOverlay(rgba_overlay(cls), bounds=[[SOUTH, WEST], [NORTH, EAST]],
                     opacity=opacity, name="Hazard").add_to(m)
        finish_map(m, districts=show_districts)
        out = st_folium(m, height=T.MAP_H, use_container_width=True,
                        returned_objects=["last_clicked"], key="fmap")

        shares = [float((cls[assessed] == i).mean()) if assessed.any() else 0
                  for i in range(1, 6)]
        chips = "".join(
            f"<div class='lg'><i style='background:{c}'></i>{n}<b>{100*s:.0f}%</b></div>"
            for n, c, s in zip(T.CLASS_NAMES, T.CLASS_COLORS, shares))
        st.markdown(f"<div class='legend-strip'>{chips}<div class='lg-note'>"
                    f"Terrain 100 m · rainfall ~33 km · uncoloured = not assessed"
                    f"</div></div>", unsafe_allow_html=True)

    with right:
        st.markdown("<div class='map-head'><div class='mh-dot'></div>"
                    "<div class='mh-title'>Location inspector</div></div>",
                    unsafe_allow_html=True)
        click = (out or {}).get("last_clicked")
        if not click:
            st.markdown("<div class='insp-empty'>Click anywhere on the map to see "
                        "that location's susceptibility, rainfall and 7-day hazard "
                        "trend.</div>", unsafe_allow_html=True)
        else:
            px = latlon_to_px(click["lat"], click["lng"])
            if px is None:
                st.warning("Outside the mapped area.")
            else:
                r, c = px
                su8, j = int(SUS[r, c]), int(NEAR[r, c])
                if su8 == 255:
                    st.markdown("<div class='insp-empty'><b>Not assessed</b><br>"
                                "Permanent ice, open water, or slope below 10°. "
                                "The model never trained on this terrain, so it "
                                "reports nothing rather than guessing.</div>",
                                unsafe_allow_html=True)
                else:
                    su = su8 / 254.0
                    st.markdown(
                        f"<div style='margin-bottom:9px'>{T.chip(int(cls[r,c])-1)}</div>"
                        + T.row("Latitude, longitude",
                                f"{click['lat']:.4f}, {click['lng']:.4f}")
                        + T.row("Susceptibility", f"{su:.3f}")
                        + T.row("Trigger (rain vs normal)", f"{tri_pts[j]:.2f}")
                        + T.row("Hazard", f"{hz[r, c]:.3f}")
                        + T.row("Rain that day", f"{rain[di, j]:.1f} mm")
                        + T.row("Rain, previous 3 d",
                                f"{rain[max(di-2,0):di+1, j].sum():.1f} mm")
                        + T.row("Rain, previous 7 d",
                                f"{rain[max(di-6,0):di+1, j].sum():.1f} mm"),
                        unsafe_allow_html=True)
                    st.caption("Hazard here over the next 7 days")
                    st.bar_chart(pd.DataFrame({
                        "day": [datetime.fromisoformat(days[i]).strftime("%d %b")
                                for i in fut],
                        "hazard": [float(su * trig[i][j]) for i in fut]}
                    ).set_index("day"), height=160, color="#38bdf8")

    st.divider()
    st.markdown("<div class='eyebrow'>District outlook</div>", unsafe_allow_html=True)
    dt = district_table(cls.tobytes(), cls.shape, days[di])
    st.dataframe(dt, use_container_width=True, hide_index=True, height=320,
                 column_config={"High+ %": st.column_config.ProgressColumn(
                     "High+ %", min_value=0, max_value=100, format="%.1f%%")})
    st.download_button("⬇️  District outlook (CSV)", dt.to_csv(index=False).encode(),
                       f"slopesense_{days[di]}.csv", "text/csv")
    st.caption("District figures are approximate — computed over each district's "
               "bounding box, not an exact polygon clip.")


# ═════════════════════════ VIEW: SUSCEPTIBILITY ══════════════════════════════
elif view == "Susceptibility":
    st.markdown("<div class='eyebrow'>Where slopes can fail</div>",
                unsafe_allow_html=True)
    st.markdown("#### Susceptibility — the static half")
    st.markdown("This layer uses **no rainfall at all**: terrain, soil, rock and "
                "land cover only. It says where a slope *could* fail given a "
                "trigger. The forecast multiplies it by today's rain.")

    su = SUS.astype(np.float32)
    su[SUS == 255] = np.nan
    su /= 254.0
    ok = np.isfinite(su)
    scls = np.zeros(su.shape, np.uint8)
    scls[ok] = (np.digitize(su[ok], np.array([.05, .15, .35, .60],
                                             dtype=np.float32)) + 1).astype(np.uint8)

    st.markdown("<div class='map-head'><div class='mh-dot'></div>"
                "<div class='mh-title'>Susceptibility</div>"
                "<div class='mh-note'>scroll to zoom · drag to pan</div></div>",
                unsafe_allow_html=True)
    m = base_map()
    ImageOverlay(rgba_overlay(scls), bounds=[[SOUTH, WEST], [NORTH, EAST]],
                 opacity=opacity).add_to(m)
    finish_map(m, districts=show_districts)
    st_folium(m, height=T.MAP_H, use_container_width=True,
              returned_objects=[], key="smap")

    sr = MET["susceptibility"].get("success_rate", [])
    if sr:
        st.markdown("<div class='eyebrow'>How well it concentrates risk</div>",
                    unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([{
            "Class": r["name"], "% of land": f"{100*r['area_frac']:.0f}%",
            "% of known landslides": f"{100*r['slide_frac']:.0f}%",
            "Concentration": f"{r['lift']:.1f}×"} for r in sr]),
            use_container_width=True, hide_index=True)
        st.caption("Read the bottom row: the smallest, reddest sliver of the "
                   "state contains a large share of every landslide mapped there.")


# ═════════════════════════ VIEW: MODEL ═══════════════════════════════════════
else:
    st.markdown("<div class='eyebrow'>How good is it, honestly</div>",
                unsafe_allow_html=True)
    st.markdown("#### Model & validation")
    s, t = MET["susceptibility"], MET["trigger"]
    k = st.columns(4)
    k[0].metric("Where — accuracy", f"{s['auc']:.3f}", f"±{s['auc_std']:.3f}")
    k[1].metric("When — accuracy", f"{t['auc']:.3f}", f"±{t['auc_ci95']:.3f}")
    k[2].metric("Landslides mapped", f"{MET['labels']['polygons']:,}")
    k[3].metric("Dated events", f"{t['n_events']}")

    st.markdown("##### What those two numbers mean")
    st.markdown(
        "- **Where (0.860)** — built from 37,788 mapped landslides, and tested by "
        "hiding whole regions during training, so it is scored on ground it has "
        "never seen.\n"
        "- **When (0.768)** — built from only 84 landslides whose *date* is known. "
        "That is why it is a transparent rule rather than a learned model: we "
        "tested a fitted model and it performed **worse**.")

    st.markdown("##### Alert thresholds — the trade-off is yours to set")
    st.dataframe(pd.DataFrame([{
        "Alert when trigger ≥": f"{o['threshold']:.2f}",
        "How often it alerts": f"{100*o['alert_rate']:.1f}% of days",
        "Known landslides caught": f"{100*o['capture']:.0f}%",
        "Better than chance": f"{o['lift']:.1f}×"} for o in t["operating_points"]]),
        use_container_width=True, hide_index=True)
    st.caption("Catching more means alerting more. No setting does both — that is "
               "a policy decision, not a modelling one.")

    st.markdown("##### Limits we will not paper over")
    for c in MET["caveats"]:
        st.markdown(f"<div class='caveat'>{c}</div>", unsafe_allow_html=True)
    st.markdown("<div class='caveat'><b>We cannot give you a false-alarm rate.</b> "
                "An alert day with no reported landslide might mean we were wrong — "
                "or that a slope failed in an empty valley and nobody recorded it. "
                "84 dated landslides across 16 years is a fraction of what actually "
                "happened. Any such number would be invented.</div>",
                unsafe_allow_html=True)

    with st.expander("Data sources"):
        st.markdown(
            "- **Landslide inventory** — Geological Survey of India; NRSC Bhuvan / "
            "APSAC SILAAS post-monsoon surveys\n"
            "- **Terrain** — Copernicus 30 m DEM\n"
            "- **Soil** — SoilGrids · **Land cover** — ESA WorldCover 10 m\n"
            "- **Rainfall history** — NASA GPM IMERG, 2000–2026\n"
            "- **Live forecast** — Open-Meteo (free tier)\n"
            "- **Dated events** — NASA Global Landslide Catalog")

st.markdown("<div style='text-align:center;color:#64798f;font-size:.75rem;"
            "margin-top:26px'>SlopeSense Forecast · research prototype · "
            "not for operational safety decisions</div>", unsafe_allow_html=True)
