"""SlopeSense Forecast — 7-day landslide outlook for Arunachal Pradesh.

The product is the FORECAST, and a forecast is only useful somewhere. So the
Forecast page is built around ONE location: the visitor's own by default,
anything they search for after that. The statewide picture is real but it is a
management view, not a personal one, so it lives on its own page.

    hazard = susceptibility (where, 100 m, static)
           x trigger        (when, ~33 km, daily)

Reads only webapp/assets/ (~3 MB) and calls Open-Meteo. No rasterio, no
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
import streamlit.components.v1 as components
from folium.plugins import FastMarkerCluster, Fullscreen, HeatMap, MiniMap
from folium.raster_layers import ImageOverlay
from streamlit_folium import st_folium

import forecast as fc
import geo as G
import theme as T

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="SlopeSense Forecast · Arunachal Pradesh",
                   page_icon="◭", layout="wide",
                   initial_sidebar_state="expanded",
                   menu_items={"About": "SlopeSense Forecast — 7-day landslide "
                                        "outlook for Arunachal Pradesh. Research "
                                        "prototype, not for operational safety "
                                        "decisions."})
st.markdown(T.CSS, unsafe_allow_html=True)
# Warm the TLS handshake for the tile hosts before the map asks for them.
st.markdown(
    '<link rel="preconnect" href="https://a.basemaps.cartocdn.com">'
    '<link rel="preconnect" href="https://b.basemaps.cartocdn.com">'
    '<link rel="preconnect" href="https://server.arcgisonline.com">'
    '<link rel="preconnect" href="https://tile.opentopomap.org">',
    unsafe_allow_html=True)

# Rain-trigger ramp — BLUE, deliberately not the green-to-red hazard ramp. The
# two layers sit under the same map control, and reusing one ramp for both
# would make "very wet" and "very dangerous" look like the same statement.
TRIG_NAMES = ["Normal", "Above normal", "Wet", "Very wet", "Exceptional"]
TRIG_COLORS = ["#0b3a5b", "#1565a8", "#2f9fd8", "#7fd4f0", "#d8f6ff"]
TRIG_CUTS = np.array([0.50, 0.75, 0.90, 0.97], dtype=np.float32)

HOME = "Itanagar"          # fallback when the browser will not say where we are


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


def _opt(name):
    """Optional bundle file — the app must still run if one is absent."""
    p = ASSETS / name
    return json.loads(p.read_text()) if p.exists() else None


@st.cache_data(show_spinner=False)
def load_extras():
    return (_opt("roads.geojson"), _opt("rivers.geojson"),
            _opt("towns.json"), _opt("landslides.json"),
            _opt("outside_mask.geojson"))


@st.cache_data(show_spinner=False)
def load_places(_towns, _districts):
    """4,648 settlements + 18 districts as one searchable list.

    Cached because it sorts and de-duplicates the whole gazetteer, and it never
    changes within a deployment.
    """
    places = G.build_places(_towns, _districts)
    return places, {p["label"]: p for p in places}


# TTL of 1 h: the underlying forecast only updates a few times a day, and this
# also caps how hard a busy page hits a free API — the cache is shared across
# all visitors, so traffic does not multiply requests.
@st.cache_data(ttl=3600, show_spinner="Fetching live rainfall…")
def load_forecast(lats: tuple, lons: tuple):
    return fc.fetch_rain(list(lats), list(lons))


GRID, SUS, NEAR, QUANT, PTS, MET, DISTRICTS, BOUNDARY = load_bundle()
ROADS, RIVERS, TOWNS, INVENTORY, OUTSIDE = load_extras()
PLACES, PLACE_IDX = load_places(TOWNS, DISTRICTS)
H, W = GRID["height"], GRID["width"]
WEST, EAST, SOUTH, NORTH = GRID["west"], GRID["east"], GRID["south"], GRID["north"]
# Ground width of one display cell (~0.55 km). The export resamples the 100 m
# model raster down for the web overlay, so this is NOT the model resolution —
# it is only used to turn a cell offset into a distance a person can read.
CELL_KM = (EAST - WEST) / W * 111.32 * np.cos(np.radians((SOUTH + NORTH) / 2))

fx = load_forecast(tuple(PTS["lat"]), tuple(PTS["lon"]))
LIVE = fx is not None


# ─────────────────────────── geolocation ─────────────────────────────────────
# Asked once. Every outcome — allowed, refused, timed out, unsupported — writes
# a `geo` flag into the URL, and that flag is what stops the request repeating
# on every rerun. The 📍 button clears it back to "ask" to try again.
qp = st.query_params
geo_state = qp.get("geo")
# The session flag is a second guard: if the browser blocks the iframe from
# navigating its parent, the `geo` flag never gets written, and without this
# the request would fire again on every single rerun.
if geo_state in (None, "ask") and not st.session_state.get("geo_asked"):
    st.session_state.geo_asked = True
    components.html(G.GEO_JS, height=0)

user_pt = None
if geo_state == "ok" and "lat" in qp and "lon" in qp:
    try:
        user_pt = (float(qp["lat"]), float(qp["lon"]))
    except ValueError:
        user_pt = None
user_inside = bool(user_pt and G.in_area(user_pt[0], user_pt[1], GRID))


def home_place() -> dict:
    """Where the Forecast page opens. The visitor's own position when the
    browser gives it and it falls inside the state; otherwise the capital."""
    if user_inside:
        near, km = G.nearest_place(user_pt[0], user_pt[1], PLACES)
        label = (f"My location — near {near['label']}" if near and km < 25
                 else f"My location — {user_pt[0]:.3f}°N, {user_pt[1]:.3f}°E")
        return {"label": label, "lat": user_pt[0], "lon": user_pt[1], "kind": "me"}
    return PLACE_IDX.get(HOME) or PLACES[0]


HOME_PLACE = home_place()
if "search" not in st.session_state:
    st.session_state.search = HOME_PLACE["label"]

# Two lookups on purpose, and they are NOT interchangeable:
#   PLACE_IDX — the gazetteer alone, which decides whether a label needs adding
#               to the dropdown's option list.
#   LOOKUP    — everything resolvable, gazetteer PLUS "My location — near X".
# Collapsing them broke the single most common path: a visitor standing in
# Arunachal got "could not read that place", because their own position has a
# label no gazetteer contains.
LOOKUP = dict(PLACE_IDX)
LOOKUP[HOME_PLACE["label"]] = HOME_PLACE


# ─────────────────────────── helpers ─────────────────────────────────────────
def latlon_to_px(lat: float, lon: float):
    """Bundle is EPSG:4326 on a regular lattice, so this is plain arithmetic —
    which is exactly why the export reprojects instead of shipping UTM."""
    if not (SOUTH <= lat <= NORTH and WEST <= lon <= EAST):
        return None
    c = int((lon - WEST) / (EAST - WEST) * W)
    r = int((NORTH - lat) / (NORTH - SOUTH) * H)
    return min(max(r, 0), H - 1), min(max(c, 0), W - 1)


def rgba_overlay(cls: np.ndarray, colors) -> np.ndarray:
    """Class colours -> RGBA. Not-assessed stays fully TRANSPARENT so the
    basemap shows through — a grey fill would read as a real, low value."""
    out = np.zeros((*cls.shape, 4), dtype=np.uint8)
    for i, hexc in enumerate(colors, start=1):
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


def finish_map(m, districts=False, marker=None):
    """Vector layers, in draw order: mask, rivers, roads, boundaries, marker."""
    if bare:
        Fullscreen(position="topleft").add_to(m)
        return m
    if dim_outside and OUTSIDE:
        # Arunachal pinches to a narrow neck near 95E, so its two boundary
        # lines run close together and read as a stray line through the state.
        # Dimming the outside makes "inside" unmistakable and the neck legible
        # as real geography rather than a rendering fault.
        folium.GeoJson(OUTSIDE, name="Outside state",
                       style_function=lambda _: {"fillColor": "#05070a",
                                                 "color": "#05070a",
                                                 "weight": 0, "fillOpacity": .80}
                       ).add_to(m)
    if show_rivers and RIVERS:
        folium.GeoJson(RIVERS, name="Rivers",
                       style_function=lambda _: {"color": "#1d5fa8", "weight": 1.0,
                                                 "opacity": .7}).add_to(m)
    if show_roads and ROADS:
        ink = T.ROAD_INK[basemap]
        folium.GeoJson(ROADS, name="Major roads",
                       style_function=lambda _: {"color": ink, "weight": 1.3,
                                                 "opacity": .85},
                       tooltip=folium.GeoJsonTooltip(["highway"], aliases=["Road:"])
                       ).add_to(m)
    if districts:
        folium.GeoJson(DISTRICTS, name="Districts",
                       style_function=lambda _: {"color": "#9fb3c8", "weight": .9,
                                                 "fill": False, "opacity": .55},
                       tooltip=folium.GeoJsonTooltip(["district"], aliases=[""])
                       ).add_to(m)
    # Casing first, then the bright edge on top. A single hairline over dark
    # terrain reads as a line drawn ACROSS the map; a cased edge reads as the
    # rim of a solid body, which is what stops Arunachal's Assam-facing border
    # looking like a defect.
    folium.GeoJson(BOUNDARY, name="State edge",
                   style_function=lambda _: {"color": "#020409", "weight": 6,
                                             "opacity": .85, "fill": False}).add_to(m)
    folium.GeoJson(BOUNDARY, name="State",
                   style_function=lambda _: {"color": T.BOUNDARY_INK[basemap],
                                             "weight": 2.2, "fill": False}).add_to(m)
    if inv_mode != "Off" and INVENTORY:
        _add_inventory(m)
    if show_labels:
        # Labels ride in a pane ABOVE the overlay, or place names vanish under it.
        folium.map.CustomPane("labels", z_index=650).add_to(m)
        folium.TileLayer(T.LABEL_TILES[basemap], attr=T.CARTO, name="Labels",
                         pane="labels", control=False,
                         min_zoom=T.MAP_MIN_ZOOM, no_wrap=True).add_to(m)
    if marker:
        # Pulsing halo + pin: at zoom 11 a bare pin is easy to lose against a
        # busy hazard overlay, and this is the one thing on the map the visitor
        # came to find.
        folium.CircleMarker(marker[:2], radius=13, color=T.ACCENT, weight=2,
                            fill=True, fill_color=T.ACCENT, fill_opacity=.16,
                            tooltip=marker[2]).add_to(m)
        folium.Marker(marker[:2], tooltip=marker[2],
                      icon=folium.Icon(color="lightblue", icon="location-dot",
                                       prefix="fa")).add_to(m)
    Fullscreen(position="topleft").add_to(m)
    if show_minimap:
        MiniMap(toggle_display=True, minimized=True).add_to(m)
    return m


def _add_inventory(m):
    """Every mapped landslide inside the state.

    Individual markers would stall the browser at this count, so: a heatmap for
    the density story, or FastMarkerCluster (which buckets client-side) when
    someone wants to drill into individual failures.
    """
    pts = [(d["y"], d["x"]) for d in INVENTORY]
    if inv_mode == "Heatmap":
        HeatMap(pts, radius=8, blur=11, min_opacity=.35,
                gradient={0.2: "#1e3a8a", 0.45: "#38bdf8",
                          0.7: "#fde047", 1.0: "#dc2626"},
                name="Landslide density").add_to(m)
    else:
        FastMarkerCluster(pts, name="Mapped landslides").add_to(m)


def map_head(title: str, note: str = "") -> None:
    st.markdown(f"<div class='map-head'><div class='mh-dot'></div>"
                f"<div class='mh-title'>{title}</div>"
                + (f"<div class='mh-note'>{note}</div>" if note else "")
                + "</div>", unsafe_allow_html=True)


def legend_strip(names, colors, shares=None, note="") -> None:
    if bare:
        st.markdown("<div class='legend-strip'><div class='lg'>🧭 Bare map mode "
                    "— data layers hidden</div><div class='lg-note'>Turn it off "
                    "in the sidebar to bring the analysis back</div></div>",
                    unsafe_allow_html=True)
        return
    chips = "".join(
        f"<div class='lg'><i style='background:{c}'></i>{n}"
        + (f"<b>{100*s:.0f}%</b>" if shares is not None else "")
        + "</div>"
        for n, c, s in zip(names, colors, shares if shares is not None else names))
    tail = f"<div class='lg-note'>{note}</div>" if note else ""
    st.markdown(f"<div class='legend-strip'>{chips}{tail}</div>",
                unsafe_allow_html=True)


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
VIEWS = [("📍", "Forecast"), ("🌐", "Statewide"), ("🗺️", "Susceptibility"),
         ("🧭", "Evidence"), ("📊", "Model & Validation")]
if "view" not in st.session_state:
    st.session_state.view = VIEWS[0][1]

# Derived, never typed in. An earlier build hardcoded "37,788" in three places;
# when the inventory was clipped to the state the app kept quoting the old
# figure while the map drew 494 fewer dots.
N_INV = len(INVENTORY) if INVENTORY else MET["labels"]["polygons"]

STATS = [
    (f"{N_INV:,}", "Landslides mapped"),
    (f"{MET['susceptibility']['auc']:.3f}", "Spatial-CV AUC"),
    (f"{len(PLACES):,}", "Searchable places"),
    ("9,555", "Days of rainfall"),
]

with st.sidebar:
    bcol, icol = st.columns([4.2, 1], vertical_alignment="center")
    with bcol:
        st.markdown("""
        <div class="brand brand-sm">
          <div class="brand-logo">◭</div>
          <div><div class="brand-name">SlopeSense Forecast</div>
               <div class="brand-tag">ARUNACHAL PRADESH · 7-DAY</div></div>
        </div>""", unsafe_allow_html=True)
    with icol:
        with st.popover("ℹ️", use_container_width=True):
            st.markdown("""
<div class="hero-eyebrow">Eastern Himalaya · Arunachal Pradesh</div>

A daily landslide outlook: where slopes are weak, learned from mapped
failures, multiplied by how unusual this week's rain is for that exact place.
""" + "<div class='about-stats'>" + "".join(
                f"<div><span class='as-num'>{n}</span>"
                f"<span class='as-lbl'>{l}</span></div>" for n, l in STATS)
                + "</div>", unsafe_allow_html=True)

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
    st.markdown("<div class='side-label'>Map settings</div>", unsafe_allow_html=True)
    basemap = st.radio("Basemap", list(T.BASEMAPS), horizontal=True, index=0,
                       label_visibility="collapsed")
    bare = st.toggle("🧭 Bare map", value=False,
                     help="Hide every data layer — just the basemap.")
    opacity = st.slider("Hazard overlay opacity", 0.0, 1.0, 0.80, 0.05,
                        disabled=bare)

    st.markdown("<div class='side-label'>Layers</div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        show_roads = st.toggle("Roads", value=True, disabled=bare,
                               help="5,536 major roads. Road cuts over-steepen "
                                    "slopes — the strongest proximity signal in "
                                    "our inventory.")
        show_districts = st.toggle("Districts", value=False, disabled=bare)
        dim_outside = st.toggle("Dim outside", value=True, disabled=bare,
                                help="Shade everything beyond Arunachal, so the "
                                     "state's narrow waist near 95°E reads as "
                                     "geography rather than a stray line.")
    with c2:
        show_rivers = st.toggle("Rivers", value=False, disabled=bare,
                                help="7,181 main stems. Rivers undercut slope "
                                     "toes, removing what holds them up.")
        show_labels = st.toggle("Names", value=True, disabled=bare)
        show_minimap = st.toggle("Mini-map", value=False, disabled=bare)

    st.markdown("<div class='side-label'>Landslide inventory</div>",
                unsafe_allow_html=True)
    inv_mode = st.radio("Inventory", ["Off", "Heatmap", "Clusters"],
                        horizontal=True, index=0, label_visibility="collapsed",
                        disabled=bare,
                        help=f"{N_INV:,} landslides mapped by GSI, NRSC Bhuvan "
                             "and APSAC, clipped to the state — the evidence "
                             "the model is built on.")
    if bare:
        opacity = 0.0
        show_roads = show_rivers = show_districts = show_minimap = False
        dim_outside = show_labels = False
        inv_mode = "Off"

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


def day_strip(key: str, notes: list[str] | None = None):
    """Seven buttons, one per forecast day.

    ⚠️ `notes` must be a number that MEANS something at the scale it is shown
    next to. This strip used to print the statewide MAXIMUM trigger, which was
    a bug worth spelling out: the trigger is a percentile against each point's
    own history, so the maximum over 97 points is the maximum of 97 roughly
    uniform draws. Its expected value is 97/98 = 0.99 on a completely ORDINARY
    day. It read as "99% chance of a landslide" and in fact carried almost no
    information about the weather at all.

    Callers now pass something scale-appropriate: the selected location's own
    outlook on the Forecast page, the share of the state at High+ on Statewide.
    """
    if "day_i" not in st.session_state or st.session_state.day_i not in fut:
        st.session_state.day_i = fut[0]
    cols = st.columns(len(fut))
    for n, (col, i) in enumerate(zip(cols, fut)):
        d = datetime.fromisoformat(days[i])
        with col:
            lbl = "Today" if n == 0 else d.strftime("%a")
            text = f"{lbl}\n{d.strftime('%d %b')}"
            if notes:
                text += f"\n{notes[n]}"
            if st.button(text, key=f"day_{key}_{i}", use_container_width=True,
                         type="primary" if i == st.session_state.day_i else "secondary"):
                st.session_state.day_i = i
                st.rerun()
    return st.session_state.day_i


def location_days(sel: dict | None):
    """That one place's hazard class and score for each of the seven days.

    Returns None when there is no location, or when the location sits on ground
    the model never assessed — in both cases the strip falls back to a
    statewide figure rather than inventing a local one.

    ⚠️ Snaps to the nearest assessed cell via the SAME helper the detail panel
    below uses. Reading SUS[r, c] directly here instead would let the strip say
    "not assessed" while the panel underneath it reported High for a slope
    2 km away — two numbers for one place, on one screen.
    """
    if not sel:
        return None
    px = latlon_to_px(sel["lat"], sel["lon"])
    if px is None:
        return None
    snap = fc.nearest_assessed(SUS, *px)
    if snap is None:
        return None
    r, c, _ = snap
    su = float(SUS[r, c]) / 254.0
    j = int(NEAR[r, c])
    hz = np.array([su * float(trig[i][j]) for i in fut], dtype=np.float32)
    return hz, fc.classify(hz)


@st.cache_data(show_spinner=False)
def statewide_high_share(tag: str) -> list[float]:
    """Share of assessed land at High or Very High, for each forecast day.

    This is the honest statewide headline: it varies across the week (16% today
    to 7% next Monday in testing), it is a share of land rather than a
    probability, and no arithmetic pins it near any particular value.
    """
    out = []
    for i in fut:
        cl = fc.classify(fc.hazard_raster(SUS, NEAR, trig[i]))
        a = cl > 0
        out.append(float((cl[a] >= 4).mean()) if a.any() else 0.0)
    return out


def hazard_layers(di: int):
    """Everything the map layers need for one forecast day."""
    tri_pts = trig[di]
    hz = fc.hazard_raster(SUS, NEAR, tri_pts)
    cls = fc.classify(hz)
    return tri_pts, hz, cls


def trigger_classes(tri_pts: np.ndarray) -> np.ndarray:
    """Rain-trigger raster, painted from each cell's nearest weather point.

    ⚠️ Masked to the SAME domain as susceptibility. Rain exists everywhere, but
    showing it on ice and open water invites the reading that those cells are
    part of the assessment — they are not.
    """
    t = tri_pts[NEAR]
    out = np.zeros(t.shape, np.uint8)
    ok = SUS != 255
    out[ok] = (np.digitize(t[ok], TRIG_CUTS) + 1).astype(np.uint8)
    return out


@st.cache_data(show_spinner=False)
def susceptibility_classes():
    su = SUS.astype(np.float32)
    su[SUS == 255] = np.nan
    su /= 254.0
    ok = np.isfinite(su)
    out = np.zeros(su.shape, np.uint8)
    out[ok] = (np.digitize(su[ok], np.array([.05, .15, .35, .60],
                                            dtype=np.float32)) + 1).astype(np.uint8)
    return out


# ═════════════════════════ VIEW: FORECAST ════════════════════════════════════
if view == "Forecast":
    if not LIVE:
        st.error("**Live rainfall is unavailable right now.** The free weather "
                 "service limits how often it can be queried. The susceptibility "
                 "map still works — open it from the sidebar. Try again shortly.")
        st.stop()

    # ---- the map card, at the very top, exactly as SlopeSense v1 ---------- #
    with st.container(border=True):
        h1, h2 = st.columns([1.15, 1], vertical_alignment="center")
        with h2:
            LAYERS = ["🗺️ Hazard", "🌧️ Rain trigger", "⛰️ Susceptibility"]
            layer = st.segmented_control("Layer", LAYERS, default=LAYERS[0],
                                         label_visibility="collapsed")
            layer = layer or LAYERS[0]

        # Search row. `accept_new_options` is what lets a visitor type raw
        # coordinates — the gazetteer has 4,648 names but the state has far
        # more places than that, and someone standing on a road cut needs the
        # forecast for exactly where they are.
        s1, s2 = st.columns([5, 1.15], vertical_alignment="bottom")
        with s2:
            if st.button("📍 My location", use_container_width=True,
                         help="Ask the browser where you are."):
                st.query_params["geo"] = "ask"
                st.session_state.pop("search", None)
                st.rerun()
        with s1:
            options = [G.PROMPT] + [p["label"] for p in PLACES]
            # Whatever is currently selected must exist in `options`, or
            # Streamlit rejects the session-state value outright. That covers
            # "My location — near X" and any coordinate the visitor typed or
            # picked off the map, none of which are in the gazetteer.
            cur = st.session_state.get("search")
            if cur and cur not in PLACE_IDX and cur != G.PROMPT:
                options.insert(1, cur)
            st.selectbox("Location", options, key="search",
                         accept_new_options=True, label_visibility="collapsed",
                         help=f"{len(PLACES):,} towns, villages and districts — "
                              "or type coordinates such as 27.09, 93.61")

        sel = G.resolve(st.session_state.search, PLACES, LOOKUP)
        if sel is None and st.session_state.search != G.PROMPT:
            st.warning(f"Could not read **{st.session_state.search}** as a place "
                       "or a coordinate. Try a name from the list, or "
                       "`27.09, 93.61`.")

        with h1:
            title = {"🗺️ Hazard": "Hazard forecast", "🌧️ Rain trigger": "Rain vs normal",
                     "⛰️ Susceptibility": "Slope susceptibility"}[layer]
            map_head(title, "scroll to zoom · click anywhere to inspect")

        # Each button carries the outlook FOR THE SELECTED PLACE, so the number
        # beside a date is about somewhere a person actually is.
        ld = location_days(sel)
        if ld is not None:
            notes = [T.CLASS_NAMES[k - 1] for k in ld[1]]
        else:
            notes = [f"{100 * s:.0f}% High+" for s in statewide_high_share(days[fut[0]])]
        di = day_strip("fc", notes)
        sel_day = datetime.fromisoformat(days[di])
        tri_pts, hz, cls = hazard_layers(di)

        marker = None
        centre, zoom = None, 7
        if sel:
            centre = (sel["lat"], sel["lon"])
            zoom = 8 if sel["kind"] == "district" else 11
            marker = (sel["lat"], sel["lon"], sel["label"])

        # Height-locked shell: switching layer must not collapse the card and
        # bounce the panels below it up for a frame.
        shell = st.container(height=T.MAP_H + 8, border=False, key="map_shell")
        m = base_map(zoom=zoom, center=centre)
        if not bare:
            if layer == LAYERS[0]:
                img, names, colors = rgba_overlay(cls, T.CLASS_COLORS), T.CLASS_NAMES, T.CLASS_COLORS
            elif layer == LAYERS[1]:
                img, names, colors = (rgba_overlay(trigger_classes(tri_pts), TRIG_COLORS),
                                      TRIG_NAMES, TRIG_COLORS)
            else:
                img, names, colors = (rgba_overlay(susceptibility_classes(), T.CLASS_COLORS),
                                      T.CLASS_NAMES, T.CLASS_COLORS)
            ImageOverlay(img, bounds=[[SOUTH, WEST], [NORTH, EAST]],
                         opacity=opacity, name=layer).add_to(m)
        finish_map(m, districts=show_districts, marker=marker)
        with shell:
            out = st_folium(m, height=T.MAP_H, use_container_width=True,
                            returned_objects=["last_clicked"],
                            key=f"fmap_{layer}")
        if bare:
            legend_strip([], [])
        elif layer == LAYERS[1]:
            legend_strip(TRIG_NAMES, TRIG_COLORS,
                         note=f"How unusual {sel_day.strftime('%d %b')}'s rain is "
                              f"for each place — not millimetres")
        else:
            assessed = cls > 0
            shares = [float((cls[assessed] == i).mean()) if assessed.any() else 0
                      for i in range(1, 6)]
            legend_strip(T.CLASS_NAMES, T.CLASS_COLORS,
                         shares if layer == LAYERS[0] else None,
                         note="Terrain 100 m · rainfall ~33 km · shaded = outside Arunachal")

    # ---- the located forecast -------------------------------------------- #
    if geo_state == "ok" and user_pt and not user_inside:
        st.info(f"You appear to be at {user_pt[0]:.2f}°N, {user_pt[1]:.2f}°E, "
                f"outside Arunachal Pradesh — so the forecast opened on "
                f"**{HOME}** instead. Search any place above.")
    elif geo_state == "denied":
        st.caption("Location sharing was declined — showing "
                   f"**{HOME_PLACE['label']}**. Search any place above, or press "
                   "📍 to try again.")

    if sel is None:
        st.markdown("<div class='insp-empty'>Search a town, a district, or a "
                    "coordinate above to get that location's 7-day outlook."
                    "</div>", unsafe_allow_html=True)
    else:
        px = latlon_to_px(sel["lat"], sel["lon"])
        if px is None:
            st.warning(f"**{sel['label']}** is outside the forecast area. "
                       "This model covers Arunachal Pradesh only.")
        else:
            snap = fc.nearest_assessed(SUS, *px)
            if snap is None:
                st.markdown(
                    "<div class='insp-empty'><b>Not assessed here</b><br>"
                    "Permanent ice, open water, or ground flatter than 10° for "
                    "several kilometres in every direction. The model never "
                    "trained on this terrain, so it reports nothing rather than "
                    "guessing. Try a nearby settlement.</div>",
                    unsafe_allow_html=True)
            else:
                r, c, dcells = snap
                su8, j = int(SUS[r, c]), int(NEAR[r, c])
                su = su8 / 254.0
                series = np.array([su * trig[i][j] for i in fut], dtype=np.float32)
                dcls = fc.classify(series)
                here = float(su * tri_pts[j])
                hcls = int(fc.classify(np.array([here]))[0])
                worst = int(np.argmax(series))
                ahead = (sel_day.date() - date.today()).days
                when = ("today" if ahead == 0 else "tomorrow" if ahead == 1
                        else f"in {ahead} days")
                conf = "higher confidence" if ahead <= 3 else "lower confidence"
                st.markdown(f"""
                <div class="loc-head">
                  <div class="loc-pin">📍</div>
                  <div>
                    <div class="loc-name">{sel['label']}</div>
                    <div class="loc-sub">{sel_day.strftime('%A %d %B %Y')} — {when}
                      · {conf} · {sel['lat']:.4f}°N, {sel['lon']:.4f}°E</div>
                  </div>
                  <div class="loc-right">
                    <div class="loc-cls" style="color:{T.CLASS_COLORS[hcls-1]}">
                      {T.CLASS_NAMES[hcls-1]}</div>
                    <div class="loc-lbl">landslide outlook here</div>
                  </div>
                </div>""", unsafe_allow_html=True)

                if dcells > 0:
                    st.markdown(
                        f"<div class='caveat'>The point itself is flat ground, "
                        f"open water or ice, which this model does not score. "
                        f"Shown here is the nearest slope it does assess, "
                        f"<b>{dcells * CELL_KM:.1f} km</b> away — which is the "
                        f"slope that would reach the town, not the ground the "
                        f"town stands on.</div>", unsafe_allow_html=True)

                k = st.columns(4)
                k[0].metric("Rain that day", f"{rain[di, j]:.0f} mm")
                k[1].metric("Rain, previous 7 days",
                            f"{rain[max(di-6, 0):di+1, j].sum():.0f} mm")
                k[2].metric("Trigger — rain vs normal", f"{tri_pts[j]:.2f}",
                            help="0.90 means wetter than 90% of days on record "
                                 "at this exact spot.")
                k[3].metric("Slope susceptibility", f"{su:.2f}",
                            help="Static. Terrain, soil, rock and land cover — "
                                 "no rainfall at all.")

                left, right = st.columns([1.6, 1])
                with left:
                    map_head("Next 7 days here")
                    st.bar_chart(pd.DataFrame({
                        "day": [datetime.fromisoformat(days[i]).strftime("%a %d")
                                for i in fut],
                        "hazard": series}).set_index("day"),
                        height=210, color=T.ACCENT)
                    peak_day = datetime.fromisoformat(days[fut[worst]])
                    st.markdown(
                        f"<div class='caveat'>Worst day in this window: "
                        f"<b>{peak_day.strftime('%A %d %b')}</b> — "
                        f"{T.CLASS_NAMES[int(dcls[worst])-1]}, "
                        f"hazard {series[worst]:.3f}.</div>",
                        unsafe_allow_html=True)
                with right:
                    map_head("Day by day")
                    st.dataframe(pd.DataFrame({
                        "Day": [datetime.fromisoformat(days[i]).strftime("%a %d %b")
                                for i in fut],
                        "Rain": [f"{rain[i, j]:.0f} mm" for i in fut],
                        "Trigger": [f"{trig[i][j]:.2f}" for i in fut],
                        "Outlook": [T.CLASS_NAMES[int(x) - 1] for x in dcls]}),
                        use_container_width=True, hide_index=True, height=280)

    # ---- click inspector -------------------------------------------------- #
    click = (out or {}).get("last_clicked")
    if click:
        st.divider()
        st.markdown("<div class='eyebrow'>Clicked point</div>",
                    unsafe_allow_html=True)
        px = latlon_to_px(click["lat"], click["lng"])
        cA, cB = st.columns([1, 1.4])
        if px is None:
            cA.warning("Outside the mapped area.")
        else:
            r, c = px
            su8, j = int(SUS[r, c]), int(NEAR[r, c])
            if su8 == 255:
                cA.markdown("<div class='insp-empty'><b>Not assessed</b><br>"
                            "Ice, open water, or slope below 10°.</div>",
                            unsafe_allow_html=True)
            else:
                su = su8 / 254.0
                near, km = G.nearest_place(click["lat"], click["lng"], PLACES)
                cA.markdown(
                    f"<div style='margin-bottom:9px'>{T.chip(int(cls[r,c])-1)}</div>"
                    + T.row("Latitude, longitude",
                            f"{click['lat']:.4f}, {click['lng']:.4f}")
                    + T.row("Nearest settlement",
                            f"{near['label']} · {km:.0f} km" if near else "—")
                    + T.row("Susceptibility", f"{su:.3f}")
                    + T.row("Trigger (rain vs normal)", f"{tri_pts[j]:.2f}")
                    + T.row("Hazard", f"{hz[r, c]:.3f}")
                    + T.row("Rain that day", f"{rain[di, j]:.1f} mm"),
                    unsafe_allow_html=True)
                cB.caption("Hazard at the clicked point over the next 7 days")
                cB.bar_chart(pd.DataFrame({
                    "day": [datetime.fromisoformat(days[i]).strftime("%d %b")
                            for i in fut],
                    "hazard": [float(su * trig[i][j]) for i in fut]}
                ).set_index("day"), height=200, color=T.ACCENT_2)
                if st.button("Use this point as my location", key="use_click"):
                    st.session_state.search = (f"{click['lat']:.4f}, "
                                               f"{click['lng']:.4f}")
                    st.rerun()


# ═════════════════════════ VIEW: STATEWIDE ═══════════════════════════════════
elif view == "Statewide":
    if not LIVE:
        st.error("**Live rainfall is unavailable right now.** Try again shortly.")
        st.stop()

    st.markdown("<div class='eyebrow'>The management view</div>",
                unsafe_allow_html=True)
    hi_share = statewide_high_share(days[fut[0]])
    di = day_strip("sw", [f"{100 * s:.0f}% High+" for s in hi_share])
    sel_day = datetime.fromisoformat(days[di])
    tri_pts, hz, cls = hazard_layers(di)
    assessed = cls > 0
    hi = float((cls[assessed] >= 4).mean()) if assessed.any() else 0.0

    lvl = 4 if hi > .12 else 3 if hi > .05 else 2 if hi > .02 else 1
    band = {4: ("Very High", "#a50026"), 3: ("High", "#f46d43"),
            2: ("Moderate", "#fee08b"), 1: ("Low", "#1a9850")}[lvl]
    ahead = (sel_day.date() - date.today()).days
    when = "today" if ahead == 0 else "tomorrow" if ahead == 1 else f"in {ahead} days"
    conf = "higher confidence" if ahead <= 3 else "lower confidence"
    st.markdown(f"""
    <div class="alert-band">
      <div class="alert-dot" style="background:{band[1]}"></div>
      <div>
        <div class="alert-title">Statewide outlook: {band[0]}</div>
        <div class="alert-sub">{sel_day.strftime('%A %d %B %Y')} — {when} · {conf}</div>
      </div>
      <div class="alert-right">
        <div class="alert-num">{100*hi:.1f}%</div>
        <div class="alert-lbl">of assessed land at High+</div>
      </div>
    </div>""", unsafe_allow_html=True)

    # ⚠️ Deliberately NOT the peak trigger. The trigger is a percentile against
    # each point's own history, so the maximum across 97 points sits near 0.99
    # on an ordinary day purely as arithmetic — a headline that never moves and
    # invites being read as a probability. A COUNT of unusually wet points says
    # the same thing truthfully and does move: 3 of 97 today, 0 by next Monday.
    n_wet = int((tri_pts >= 0.90).sum())
    k = st.columns(4)
    k[0].metric("Unusually wet points", f"{n_wet} of {len(tri_pts)}",
                help="Weather points whose 3- and 7-day rain sits in the wettest "
                     "10% of everything that point has recorded since 2010.")
    k[1].metric("Median trigger", f"{np.nanmedian(tri_pts):.2f}",
                help="The typical point's rainfall percentile — 0.50 is an "
                     "ordinary monsoon day for that place.")
    k[2].metric("Rain, wettest point", f"{np.nanmax(rain[di]):.0f} mm")
    k[3].metric("Lead time", "Today" if ahead == 0 else f"+{ahead} d")
    st.caption("The trigger is a percentile, not a probability: 0.90 means "
               "*wetter than 90% of days on record here*, not a 90% chance of a "
               "landslide. Nothing in this app estimates a probability of "
               "failure — see **Model & Validation** for why.")

    with st.container(border=True):
        map_head(f"Statewide hazard — {sel_day.strftime('%d %b')}",
                 "scroll to zoom · drag to pan")
        shell = st.container(height=T.MAP_H + 8, border=False, key="map_shell")
        m = base_map(zoom=7)
        if not bare:
            ImageOverlay(rgba_overlay(cls, T.CLASS_COLORS),
                         bounds=[[SOUTH, WEST], [NORTH, EAST]],
                         opacity=opacity, name="Hazard").add_to(m)
        finish_map(m, districts=show_districts)
        with shell:
            st_folium(m, height=T.MAP_H, use_container_width=True,
                      returned_objects=[], key="swmap")
        shares = [float((cls[assessed] == i).mean()) if assessed.any() else 0
                  for i in range(1, 6)]
        legend_strip(T.CLASS_NAMES, T.CLASS_COLORS, shares,
                     note="Terrain 100 m · rainfall ~33 km · shaded = outside Arunachal")

    st.markdown("<div class='eyebrow'>District outlook</div>", unsafe_allow_html=True)
    dt = district_table(cls.tobytes(), cls.shape, days[di])
    st.dataframe(dt, use_container_width=True, hide_index=True, height=340,
                 column_config={"High+ %": st.column_config.ProgressColumn(
                     "High+ %", min_value=0, max_value=100, format="%.1f%%")})
    st.download_button("⬇️  District outlook (CSV)", dt.to_csv(index=False).encode(),
                       f"slopesense_{days[di]}.csv", "text/csv")
    st.caption("District figures are approximate — computed over each district's "
               "bounding box, not an exact polygon clip.")
    st.markdown("<div class='caveat'>Arunachal wraps around the top of the Assam "
                "valley, so its southern border runs across the middle of the map "
                "and the Tirap–Changlang districts sit below it as a separate "
                "lobe. The shaded ground between them is Assam, not a gap in the "
                "data.</div>", unsafe_allow_html=True)


# ═════════════════════════ VIEW: SUSCEPTIBILITY ══════════════════════════════
elif view == "Susceptibility":
    st.markdown("<div class='eyebrow'>Where slopes can fail</div>",
                unsafe_allow_html=True)
    st.markdown("#### Susceptibility — the static half")
    st.markdown("This layer uses **no rainfall at all**: terrain, soil, rock and "
                "land cover only. It says where a slope *could* fail given a "
                "trigger. The forecast multiplies it by today's rain.")

    with st.container(border=True):
        map_head("Statewide susceptibility surface", "scroll to zoom · drag to pan")
        shell = st.container(height=T.MAP_H + 8, border=False, key="map_shell")
        m = base_map(zoom=7)
        if not bare:
            ImageOverlay(rgba_overlay(susceptibility_classes(), T.CLASS_COLORS),
                         bounds=[[SOUTH, WEST], [NORTH, EAST]],
                         opacity=opacity).add_to(m)
        finish_map(m, districts=show_districts)
        with shell:
            st_folium(m, height=T.MAP_H, use_container_width=True,
                      returned_objects=[], key="smap")
        legend_strip(T.CLASS_NAMES, T.CLASS_COLORS,
                     note="Static — no rainfall in this layer")

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


# ═════════════════════════ VIEW: EVIDENCE ════════════════════════════════════
elif view == "Evidence":
    st.markdown("<div class='eyebrow'>What this is built on</div>",
                unsafe_allow_html=True)
    st.markdown("#### The evidence base")
    st.markdown("Every number in this app traces back to observed data. This is "
                "what that data actually is.")

    k = st.columns(4)
    k[0].metric("Landslides mapped", f"{len(INVENTORY):,}" if INVENTORY else "—")
    k[1].metric("Days of rainfall", "9,555", "26 years, no gaps")
    k[2].metric("Terrain cells", "8.2 M", "100 m resolution")
    k[3].metric("Model inputs", f"{MET['susceptibility']['n_features']}")

    if INVENTORY:
        with st.container(border=True):
            map_head("Where the landslides are",
                     "each point is a surveyed failure, not a model output")
            shell = st.container(height=T.MAP_H + 8, border=False, key="map_shell")
            m = base_map(zoom=7)
            HeatMap([(d["y"], d["x"]) for d in INVENTORY], radius=8, blur=11,
                    min_opacity=.35,
                    gradient={0.2: "#1e3a8a", 0.45: "#38bdf8",
                              0.7: "#fde047", 1.0: "#dc2626"}).add_to(m)
            finish_map(m, districts=show_districts)
            with shell:
                st_folium(m, height=T.MAP_H, use_container_width=True,
                          returned_objects=[], key="emap")
        st.caption("Turn on **Roads** in the sidebar — the clustering along the "
                   "road network is real, and it is partly physical (road cuts "
                   "over-steepen slopes) and partly a survey artefact (surveyors "
                   "reach roadsides more easily). We keep the feature, but never "
                   "read its importance as pure physics.")

    src = pd.DataFrame([
        {"Dataset": "GSI National Landslide Inventory", "What": "Mapped failure outlines",
         "Scale": "26,459 polygons", "Used for": "Where slopes fail"},
        {"Dataset": "NRSC Bhuvan / APSAC SILAAS", "What": "Post-monsoon surveys 2014/17/23",
         "Scale": "11,329 polygons", "Used for": "Where slopes fail"},
        {"Dataset": "NASA Global Landslide Catalog", "What": "Landslides with a known date",
         "Scale": "84 events", "Used for": "When they fail"},
        {"Dataset": "NASA GPM IMERG", "What": "Daily rainfall 2000–2026",
         "Scale": "9,555 days", "Used for": "Rainfall history"},
        {"Dataset": "Open-Meteo", "What": "Live + forecast rainfall",
         "Scale": "97 points, 7 days", "Used for": "The live forecast"},
        {"Dataset": "Copernicus DEM", "What": "Elevation",
         "Scale": "30 m", "Used for": "Slope, aspect, curvature, wetness"},
        {"Dataset": "SoilGrids", "What": "Soil properties",
         "Scale": "18 layers", "Used for": "Where slopes fail"},
        {"Dataset": "ESA WorldCover", "What": "Land cover",
         "Scale": "10 m", "Used for": "Where slopes fail"},
        {"Dataset": "APSSDI", "What": "Lithology + fault lines",
         "Scale": "4,777 lineaments", "Used for": "Where slopes fail"},
        {"Dataset": "OpenStreetMap", "What": "Road network",
         "Scale": "107,302 ways", "Used for": "Where slopes fail"},
        {"Dataset": "HydroSHEDS", "What": "River network",
         "Scale": "50,800 reaches", "Used for": "Where slopes fail"},
        {"Dataset": "Settlement gazetteer", "What": "Named places for search",
         "Scale": f"{len(PLACES):,} entries", "Used for": "Location forecasts"},
    ])
    st.markdown("<div class='eyebrow'>Every source</div>", unsafe_allow_html=True)
    st.dataframe(src, use_container_width=True, hide_index=True, height=440)

    st.markdown("<div class='eyebrow'>The imbalance that shapes everything</div>",
                unsafe_allow_html=True)
    a, b = st.columns(2)
    a.markdown("##### Where — abundant\n"
               f"**{len(INVENTORY):,}** mapped landslides.\n\n"
               "Enough to train a proper model, test it on regions it has never "
               "seen, and still have data left over. This half is strong.")
    b.markdown("##### When — scarce\n"
               f"**{MET['trigger']['n_events']}** landslides with a usable date.\n\n"
               "Three orders of magnitude fewer. This is why the timing half is a "
               "transparent rule rather than a learned model — and it is the single "
               "biggest limit on the whole system.")
    st.markdown("<div class='caveat'>We tried five separate routes to find more "
                "dated landslides — including reading dates off satellite imagery "
                "and radar. Four failed, and we documented why. The honest position "
                "is that this is a data problem, not a modelling one.</div>",
                unsafe_allow_html=True)


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
    # Read from metrics.json, never typed in. An earlier version hardcoded the
    # event count as 84 while the metric card beside it read 72 — 84 is how many
    # dated events the catalogue holds, 72 is how many survive the filters and
    # actually train the trigger. The page must show the number it used.
    st.markdown(
        f"- **Where ({s['auc']:.3f})** — built from {MET['labels']['polygons']:,} "
        "mapped landslides, and tested by hiding whole regions during training, "
        "so it is scored on ground it has never seen.\n"
        f"- **When ({t['auc']:.3f})** — built from only **{t['n_events']}** "
        "landslides whose *date* is known. That is why it is a transparent rule "
        "rather than a learned model: we tested a fitted model and it performed "
        "**worse**.")

    st.markdown("##### Alert thresholds — the trade-off is yours to set")
    st.dataframe(pd.DataFrame([{
        "Alert when trigger ≥": f"{o['threshold']:.2f}",
        "How often it alerts": f"{100*o['alert_rate']:.1f}% of days",
        "Known landslides caught": f"{100*o['event_capture']:.0f}%",
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
                f"{t['n_events']} dated landslides across 16 years is a fraction of what actually "
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

st.markdown("<div class='app-footer'><b>SlopeSense Forecast</b>"
            "<span>Research prototype — not for operational safety decisions</span>"
            "<span>Hazard = susceptibility × rainfall trigger</span></div>",
            unsafe_allow_html=True)
