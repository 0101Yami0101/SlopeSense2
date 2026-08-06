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

import deck3d as D3
import forecast as fc
import geo as G
import roads as RD
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

# Rain-trigger ramp — BLUE, deliberately not the green-to-red hazard ramp:
# reusing one ramp for both would make "very wet" and "very dangerous" look
# like the same statement.
#
# ⚠️ Kept although the Forecast page no longer draws this layer. The rain
# trigger is getting a page of its own; trigger_classes() below is its
# renderer, and deleting the pair now would only mean writing them again.
TRIG_NAMES = ["Normal", "Above normal", "Wet", "Very wet", "Exceptional"]
TRIG_COLORS = ["#0b3a5b", "#1565a8", "#2f9fd8", "#7fd4f0", "#d8f6ff"]
TRIG_CUTS = np.array([0.50, 0.75, 0.90, 0.97], dtype=np.float32)

# How far from a road the 3D view paints the forecast. Beyond this a
# slope cannot plausibly put debris on the carriageway, and drawing it
# would bury the road in colour that is not about the road.
CORRIDOR_KM = 5.0
ROUTE_CORRIDOR_KM = 4.0   # one route needs less context than the whole net



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
def load_elevation():
    """Metres per cell, on the same lattice as the forecast. None if absent —
    the 3D view degrades to flat rather than failing."""
    p = ASSETS / "elevation.npz"
    if not p.exists():
        return None
    z = np.load(p)["elev"].astype(np.float32)
    z[z == 65535] = np.nan
    return z


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
ELEV = load_elevation()
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
# ⚠️ OPT-IN ONLY. The page never asks where you are on load — the request fires
# solely when the 📍 button sets geo=ask. Asking unprompted throws a browser
# permission prompt at a visitor who only wanted to look at a map, and it made
# the app open on a personal location without anyone choosing it.
#
# Every outcome — allowed, refused, timed out, unsupported — writes a `geo` flag
# into the URL, and that flag is what stops the request repeating.
qp = st.query_params
geo_state = qp.get("geo")
# The session flag is a second guard: if the browser blocks the iframe from
# navigating its parent, the `geo` flag never gets written, and without this
# the request would fire again on every single rerun.
if geo_state == "ask" and not st.session_state.get("geo_asked"):
    st.session_state.geo_asked = True
    components.html(G.GEO_JS, height=0)

user_pt = None
if geo_state == "ok" and "lat" in qp and "lon" in qp:
    try:
        user_pt = (float(qp["lat"]), float(qp["lon"]))
    except ValueError:
        user_pt = None
user_inside = bool(user_pt and G.in_area(user_pt[0], user_pt[1], GRID))


def me_place() -> dict | None:
    """The visitor's own position as a selectable place.

    Only ever built when the browser answered AND the answer lands inside the
    forecast area. Outside Arunachal there is nothing to forecast, so there is
    no place to offer — the app says so rather than quietly snapping to a
    nearby town the visitor never asked for.
    """
    if not user_inside:
        return None
    near, km = G.nearest_place(user_pt[0], user_pt[1], PLACES)
    label = (f"My location — near {near['label']}" if near and km < 25
             else f"My location — {user_pt[0]:.3f}°N, {user_pt[1]:.3f}°E")
    return {"label": label, "lat": user_pt[0], "lon": user_pt[1], "kind": "me"}


ME = me_place()

# Nothing is selected until someone chooses. The forecast is about a place, and
# picking one for the visitor — their own position or a default town — is a
# claim we have no business making before they ask.
if "search" not in st.session_state:
    st.session_state.search = G.PROMPT

# Adopt the located position ONCE. Without the flag the query string, which
# survives every rerun, would keep re-selecting it and undo any later search.
if ME and not st.session_state.get("geo_applied"):
    st.session_state.geo_applied = True
    st.session_state.pending_place = ME["label"]

# ⚠️ A map click selects a place, but the click only comes back AFTER the search
# box has already been built this run — and Streamlit REFUSES to let a widget's
# session_state be written once the widget exists:
#     StreamlitAPIException: `st.session_state.search` cannot be modified after
#     the widget with key `search` is instantiated.
# So a click parks its coordinates here and the next run adopts them, above,
# before the box is created. An earlier "use this point" button wrote `search`
# directly from inside the panel and would have crashed the app on click.
if "pending_place" in st.session_state:
    st.session_state.search = st.session_state.pop("pending_place")

# Two lookups on purpose, and they are NOT interchangeable:
#   PLACE_IDX — the gazetteer alone, which decides whether a label needs adding
#               to the dropdown's option list.
#   LOOKUP    — everything resolvable, gazetteer PLUS "My location — near X".
# Collapsing them broke the single most common path: a visitor standing in
# Arunachal got "could not read that place", because their own position has a
# label no gazetteer contains.
LOOKUP = dict(PLACE_IDX)
if ME:
    LOOKUP[ME["label"]] = ME


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


def base_map():
    """The parts of the map that must NEVER change between reruns.

    ⚠️ This is the whole trick behind the map not snapping back to the start
    every time you touch a control. streamlit_folium identifies a map by
    hashing its generated JavaScript. Same JS -> same component -> the browser
    keeps the live Leaflet instance, with whatever the user panned and zoomed
    to. Different JS -> a brand-new component, mounted fresh at zoom_start.

    So the base map is built from FIXED arguments only — never from the
    selected day, the chosen layer, or a searched location. Everything that
    varies goes through overlay_group() and is pushed in as a feature group,
    which streamlit_folium applies to the existing map without remounting it.

    That also means the constructor's location/zoom are only ever the opening
    view. Moving the map afterwards is done with st_folium(center=, zoom=).
    """
    # Whole-number zoom only. zoomSnap/zoomDelta of 0.5 were tried here as a
    # "finer wheel steps" nicety and removed again: at a half step Leaflet does
    # not redraw, it CSS-scales what it already painted, which puts a second
    # resampling pass on top of the overlay for no real benefit.
    #
    # ⚠️ That was NOT the cause of the smeared overlay — see pixelated=True on
    # the st_folium calls for the actual fix. Recorded here because the two
    # look alike and it is an easy wrong conclusion to reach twice.
    m = folium.Map(location=[(SOUTH + NORTH) / 2, (WEST + EAST) / 2],
                   zoom_start=7, tiles=None, control_scale=True)
    # folium.Map(min_zoom=) is a no-op when tiles=None — it only reaches the
    # default tile layer, which we skip. Leaflet's own option must be set here
    # or scroll-out is unbounded and eventually shows repeated world copies.
    m.options.update(minZoom=T.MAP_MIN_ZOOM,
                     maxBounds=[[SOUTH - 1.5, WEST - 1.5], [NORTH + 1.5, EAST + 1.5]],
                     maxBoundsViscosity=1.0, worldCopyJump=False)
    url, attr = T.BASEMAPS[basemap]
    folium.TileLayer(url, attr=attr, name="Base", control=False,
                     min_zoom=T.MAP_MIN_ZOOM, no_wrap=True).add_to(m)
    # The label pane must exist on the BASE map: panes are Leaflet containers
    # created at map setup, and a feature group cannot conjure one later.
    folium.map.CustomPane("labels", z_index=650).add_to(m)
    if show_labels:
        folium.TileLayer(T.LABEL_TILES[basemap], attr=T.CARTO, name="Labels",
                         pane="labels", control=False,
                         min_zoom=T.MAP_MIN_ZOOM, no_wrap=True).add_to(m)
    Fullscreen(position="topleft").add_to(m)
    if show_minimap:
        MiniMap(toggle_display=True, minimized=True).add_to(m)
    return m


def overlay_group(img=None, districts=False, marker=None, inventory=True):
    """Everything that changes — as ONE feature group, swapped in place.

    Draw order matters and is the order things are added here: dimming mask,
    raster overlay, rivers, roads, districts, state edge, inventory, marker.
    """
    fg = folium.FeatureGroup(name="layers")
    if bare:
        return fg
    if dim_outside and OUTSIDE:
        # Arunachal pinches to a narrow neck near 95E, so its two boundary
        # lines run close together and read as a stray line through the state.
        # Dimming the outside makes "inside" unmistakable and the neck legible
        # as real geography rather than a rendering fault.
        folium.GeoJson(OUTSIDE, name="Outside state",
                       style_function=lambda _: {"fillColor": "#05070a",
                                                 "color": "#05070a",
                                                 "weight": 0, "fillOpacity": .80}
                       ).add_to(fg)
    if img is not None:
        ImageOverlay(img, bounds=[[SOUTH, WEST], [NORTH, EAST]],
                     opacity=opacity, name="Overlay").add_to(fg)
    if show_rivers and RIVERS:
        folium.GeoJson(RIVERS, name="Rivers",
                       style_function=lambda _: {"color": "#1d5fa8", "weight": 1.0,
                                                 "opacity": .7}).add_to(fg)
    if show_roads and ROADS:
        ink = T.ROAD_INK[basemap]
        folium.GeoJson(ROADS, name="Major roads",
                       style_function=lambda _: {"color": ink, "weight": 1.3,
                                                 "opacity": .85},
                       tooltip=folium.GeoJsonTooltip(["highway"], aliases=["Road:"])
                       ).add_to(fg)
    if districts:
        folium.GeoJson(DISTRICTS, name="Districts",
                       style_function=lambda _: {"color": "#9fb3c8", "weight": .9,
                                                 "fill": False, "opacity": .55},
                       tooltip=folium.GeoJsonTooltip(["district"], aliases=[""])
                       ).add_to(fg)
    # Casing first, then the bright edge on top. A single hairline over dark
    # terrain reads as a line drawn ACROSS the map; a cased edge reads as the
    # rim of a solid body, which is what stops Arunachal's Assam-facing border
    # looking like a defect.
    folium.GeoJson(BOUNDARY, name="State edge",
                   style_function=lambda _: {"color": "#020409", "weight": 6,
                                             "opacity": .85, "fill": False}).add_to(fg)
    folium.GeoJson(BOUNDARY, name="State",
                   style_function=lambda _: {"color": T.BOUNDARY_INK[basemap],
                                             "weight": 2.2, "fill": False}).add_to(fg)
    if inventory and inv_mode != "Off" and INVENTORY:
        _add_inventory(fg)
    if marker:
        # Halo + pin: at zoom 11 a bare pin is easy to lose against a busy
        # hazard overlay, and this is the one thing on the map the visitor
        # came to find.
        folium.CircleMarker(marker[:2], radius=13, color=T.ACCENT, weight=2,
                            fill=True, fill_color=T.ACCENT, fill_opacity=.16,
                            tooltip=marker[2]).add_to(fg)
        folium.Marker(marker[:2], tooltip=marker[2],
                      icon=folium.Icon(color="lightblue", icon="location-dot",
                                       prefix="fa")).add_to(fg)
    return fg


def _add_inventory(fg):
    """Every mapped landslide inside the state.

    Individual markers would stall the browser at this count, so: a heatmap for
    the density story, or FastMarkerCluster (which buckets client-side) when
    someone wants to drill into individual failures.

    Both plugins carry their own JS. streamlit_folium collects those links by
    walking the map AFTER the feature group has been attached, so they load
    correctly even though the group is not part of the base map — verified
    before relying on it.
    """
    pts = [(d["y"], d["x"]) for d in INVENTORY]
    if inv_mode == "Heatmap":
        HeatMap(pts, radius=8, blur=11, min_opacity=.35,
                gradient={0.2: "#1e3a8a", 0.45: "#38bdf8",
                          0.7: "#fde047", 1.0: "#dc2626"},
                name="Landslide density").add_to(fg)
    else:
        FastMarkerCluster(pts, name="Mapped landslides").add_to(fg)


def fly_to(sel, zoom):
    """center/zoom for st_folium — but ONLY when the target actually changed.

    Passing the selected location every rerun would drag the map back the
    instant someone panned away and then clicked a day button. Returning
    (None, None) leaves the live map exactly where the user put it.
    """
    if not sel:
        return None, None
    sig = f"{sel['lat']:.4f},{sel['lon']:.4f},{zoom},{st.session_state.get('recentre', 0)}"
    if sig == st.session_state.get("map_target"):
        return None, None
    st.session_state.map_target = sig
    return (sel["lat"], sel["lon"]), zoom


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
VIEWS = [("📍", "Forecast"), ("🛣️", "Roads"), ("🗺️", "Susceptibility"),
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
        with st.popover("ℹ️", width="stretch"):
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
                     width="stretch",
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
            if st.button(text, key=f"day_{key}_{i}", width="stretch",
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


@st.cache_resource(show_spinner=False)
def road_chunks():
    """The network cut into ~1 km pieces. Cached: geometry never changes, and
    only the colour on top of it does. cache_resource for the same reason as
    road_graph — 3,995 pieces are not worth re-copying on every rerun."""
    return RD.chunk_roads(ROADS["features"])


def sample_classes(cls: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Hazard class under each road piece. Vectorised — 3,995 pieces per day.

    Out-of-grid pieces return 0 ("not assessed") rather than being dropped, so
    the kilometre totals below always add up to the network length.
    """
    r = ((NORTH - lat) / (NORTH - SOUTH) * H).astype(int)
    c = ((lon - WEST) / (EAST - WEST) * W).astype(int)
    ok = (r >= 0) & (r < H) & (c >= 0) & (c < W)
    out = np.zeros(len(lat), dtype=np.uint8)
    out[ok] = cls[r[ok], c[ok]]
    return out


@st.cache_data(show_spinner=False)
def road_high_km(tag: str) -> list[float]:
    """Kilometres of road at High or above, for each forecast day — the number
    on the day buttons of this view."""
    _, la, lo, km, _, _ = road_chunks()
    out = []
    for i in fut:
        c = sample_classes(fc.classify(fc.hazard_raster(SUS, NEAR, trig[i])), la, lo)
        out.append(float(km[c >= 4].sum()))
    return out


@st.cache_resource(show_spinner=False)
def road_graph():
    """Routable graph over the mapped network. Built once, ~0.03 s.

    ⚠️ cache_resource, not cache_data: cache_data deep-copies what it returns on
    every access, and this is a 6,843-node dict of dicts fetched on every rerun.
    Nothing mutates it, so sharing one object is both correct and far cheaper.
    """
    return RD.build_graph(ROADS["features"])


@st.cache_data(show_spinner=False)
def route_between(a_lat, a_lon, b_lat, b_lon):
    """Shortest mapped road between two points, as ([[lon, lat], ...], km).

    Cached on the coordinates: the same pair is re-requested on every day
    button, layer toggle and opacity nudge.
    """
    adj, pos = road_graph()
    na, da = RD.nearest_node(adj, pos, a_lat, a_lon)
    nb, db = RD.nearest_node(adj, pos, b_lat, b_lon)
    line, km = RD.shortest_path(adj, pos, na, nb)
    return line, km, da, db


def route_geojson(line, cls: np.ndarray, step_km: float = 0.6) -> dict:
    """The route cut into short pieces, each coloured by its own forecast."""
    lo, la, at = RD.densify(line, step_km)
    k = sample_classes(cls, la, lo)
    feats = []
    for i in range(len(at) - 1):
        feats.append({"type": "Feature",
                      "geometry": {"type": "LineString",
                                   "coordinates": [[float(lo[i]), float(la[i])],
                                                   [float(lo[i + 1]), float(la[i + 1])]]},
                      "properties": {"c": int(k[i]),
                                     "cls": T.CLASS_NAMES[k[i] - 1] if k[i]
                                            else "Not assessed",
                                     "km": round(float(at[i]), 1)}})
    return {"type": "FeatureCollection", "features": feats}, lo, la, at, k


@st.cache_data(show_spinner=False)
def route_corridor_mask(lons: tuple, lats: tuple, half_km: float) -> np.ndarray:
    """Cells within `half_km` of one route. Same disc-stamping trick as the
    network-wide mask — cached on the rounded polyline, so panning the day
    strip does not rebuild it."""
    km_per_row = (NORTH - SOUTH) / H * 111.0
    km_per_col = (EAST - WEST) / W * 98.9
    rr = max(int(round(half_km / km_per_row)), 1)
    cc = max(int(round(half_km / km_per_col)), 1)
    dr, dc = np.mgrid[-rr:rr + 1, -cc:cc + 1]
    disc = ((dr * km_per_row) ** 2 + (dc * km_per_col) ** 2) <= half_km ** 2
    m = np.zeros((H, W), dtype=bool)
    rows = ((NORTH - np.asarray(lats)) / (NORTH - SOUTH) * H).astype(int)
    cols = ((np.asarray(lons) - WEST) / (EAST - WEST) * W).astype(int)
    for r, c in zip(rows, cols):
        r0, r1 = max(r - rr, 0), min(r + rr + 1, H)
        c0, c1 = max(c - cc, 0), min(c + cc + 1, W)
        if r1 <= r0 or c1 <= c0:
            continue
        m[r0:r1, c0:c1] |= disc[r0 - (r - rr):r1 - (r - rr),
                                c0 - (c - cc):c1 - (c - cc)]
    return m


def route_elevation(lons, lats):
    """Ground height at each profile sample, in metres. NaN off-grid."""
    out = np.full(len(lons), np.nan)
    if ELEV is None:
        return out
    for i, (lo, la) in enumerate(zip(lons, lats)):
        px = latlon_to_px(la, lo)
        if px is not None and np.isfinite(ELEV[px]):
            out[i] = float(ELEV[px])
    return out


def route_paths_3d(lons, lats, r_cls, run: int = 6):
    """The route as short 3-D paths, coloured by forecast.

    Grouped into runs of `run` samples so the 3D view carries a few hundred
    path segments rather than one per half-kilometre.
    """
    z = route_elevation(lons, lats)
    z = np.nan_to_num(z, nan=800.0)
    out = []
    for i in range(0, len(lons) - 1, run):
        j = min(i + run, len(lons) - 1)
        k = int(np.max(r_cls[i:j + 1])) if j > i else int(r_cls[i])
        col = T.CLASS_COLORS[k - 1] if k else T.NOT_ASSESSED
        out.append({
            "p": [[float(lons[t]), float(lats[t]), (float(z[t]) + 110.0) * D3.EXAG]
                  for t in range(i, j + 1)],
            "c": [int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)],
            "tip": T.CLASS_NAMES[k - 1] if k else "Not assessed"})
    return out


def road_geojson(chunks, c_cls, c_km) -> dict:
    """One FeatureCollection of coloured pieces.

    Pieces rather than whole roads on purpose: the longest single road feature
    runs 49 km, and colouring all of it by one value would paint a safe valley
    stretch the same red as the gorge it climbs into.
    """
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "geometry": {"type": "LineString", "coordinates": ch},
         "properties": {"c": int(k),
                        "cls": T.CLASS_NAMES[k - 1] if k else "Not assessed",
                        "km": round(float(d), 2)}}
        for ch, k, d in zip(chunks, c_cls, c_km)]}


@st.cache_data(show_spinner=False)
def cell_lonlat():
    """Centre lon/lat of every grid cell, as 2-D arrays. Built once."""
    lon = WEST + (np.arange(W) + 0.5) * (EAST - WEST) / W
    lat = NORTH - (np.arange(H) + 0.5) * (NORTH - SOUTH) / H
    return np.meshgrid(lon, lat)


def district_feature(label: str):
    """The GeoJSON feature behind a "<name> district" search result."""
    name = label[:-9] if label.endswith(" district") else label
    for f in DISTRICTS["features"]:
        if f["properties"].get("district") == name:
            return f
    return None


@st.cache_data(show_spinner=False)
def district_mask(name: str) -> np.ndarray:
    """Cells inside one district, as a boolean grid.

    ⚠️ The real polygon, not a bounding box. Arunachal's districts interlock
    along river valleys, so a box around Upper Siang contains large parts of
    three neighbours — clipping to it would show a visitor another district's
    forecast under their own district's name.
    """
    feat = district_feature(name)
    if feat is None:
        return np.ones((H, W), dtype=bool)
    lon = WEST + (np.arange(W) + 0.5) * (EAST - WEST) / W
    lat = NORTH - (np.arange(H) + 0.5) * (NORTH - SOUTH) / H
    return G.rasterize_polygon(feat["geometry"], lon, lat)


def clip_to(cls: np.ndarray, mask) -> np.ndarray:
    """Blank everything outside `mask`. Class 0 renders transparent, so the
    basemap shows through rather than the neighbouring district's forecast."""
    if mask is None:
        return cls
    out = np.zeros_like(cls)
    out[mask] = cls[mask]
    return out


@st.cache_data(show_spinner=False)
def road_corridor_mask(half_km: float = 6.0) -> np.ndarray:
    """Cells within `half_km` of a road, as a boolean grid.

    Stamps a disc around each of the ~4,000 road pieces rather than measuring
    every cell against every road: the direct version is 288,000 x 4,000
    distance calculations and takes minutes.
    """
    _, la, lo, _, _, _ = road_chunks()
    km_per_row = (NORTH - SOUTH) / H * 111.0
    km_per_col = (EAST - WEST) / W * 98.9
    rr = int(round(half_km / km_per_row))
    cc = int(round(half_km / km_per_col))
    dr, dc = np.mgrid[-rr:rr + 1, -cc:cc + 1]
    disc = ((dr * km_per_row) ** 2 + (dc * km_per_col) ** 2) <= half_km ** 2
    m = np.zeros((H, W), dtype=bool)
    rows = ((NORTH - la) / (NORTH - SOUTH) * H).astype(int)
    cols = ((lo - WEST) / (EAST - WEST) * W).astype(int)
    for r, c in zip(rows, cols):
        r0, r1 = max(r - rr, 0), min(r + rr + 1, H)
        c0, c1 = max(c - cc, 0), min(c + cc + 1, W)
        if r1 <= r0 or c1 <= c0:
            continue
        m[r0:r1, c0:c1] |= disc[r0 - (r - rr):r1 - (r - rr),
                                c0 - (c - cc):c1 - (c - cc)]
    return m


# Cell size in degrees, straight off the grid. Everything 3D derives its
# geometry from these, so the blocks are exactly the squares the 2D map paints.
DLON = (EAST - WEST) / W
DLAT = (NORTH - SOUTH) / H


def forecast_cells(cls: np.ndarray, stride: int = 2,
                   mask: np.ndarray | None = None, alpha: float = 205):
    """Every assessed cell as a flat coloured patch lying on the terrain.

    `stride` thins the grid: statewide at stride 1 is ~288,000 patches, a
    multi-megabyte payload rebuilt on every redraw, for detail the camera
    cannot resolve at that height anyway.

    ⚠️ Patch size follows the stride AND is deliberately larger than it.
    Thinning without widening is what turned the surface into polka dots. The
    OVERLAP factor is what makes it read as one skin instead of loose tiles:
    a patch wider than the step to its neighbour covers the drop between them,
    which is the job an extruded block used to do — badly, by showing its walls
    on every slope.
    """
    LON, LAT = cell_lonlat()
    keep = cls > 0
    if mask is not None:
        keep &= mask
    thin = np.zeros_like(keep)
    thin[::stride, ::stride] = True
    keep &= thin
    if not keep.any():
        return "", "", 0, 700.0
    z = ELEV[keep] if ELEV is not None else np.full(int(keep.sum()), 800.0)
    z = np.nan_to_num(z, nan=800.0)
    k = cls[keep].astype(int) - 1
    rgb = np.array([[int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)]
                    for h in T.CLASS_COLORS], dtype=np.uint8)[k]

    # Match SlopeSense v1's proportions: it draws 400 m marks on a 278 m grid.
    OVERLAP = 1.44
    step_lon_m = DLON * stride * 98_900
    step_lat_m = DLAT * stride * 111_000
    cell_m = max(step_lon_m, step_lat_m) * OVERLAP
    # Back to degrees per axis for the corner offset — a square in metres is
    # not a square in degrees, and the offset has to be in the units the
    # coordinates are actually in.
    pb, cb, n = D3.pack_cells(LON[keep], LAT[keep], z, rgb,
                              cell_m / 98_900, cell_m / 111_000, alpha)
    return pb, cb, n, cell_m


def road_paths_3d(chunks, c_cls, every: int = 1):
    """Road pieces as 3-D paths, coloured by their own forecast."""
    if ELEV is None:
        return []
    out = []
    for ch, k in zip(chunks[::every], c_cls[::every]):
        pts = []
        for lon, lat in ch:
            px = latlon_to_px(lat, lon)
            z = 800.0 if px is None or not np.isfinite(ELEV[px]) else float(ELEV[px])
            # 5 dp is ~1 m, far finer than a 490 m cell, and trims about a
            # third off the JSON — this whole page is already ~1.9 MB.
            pts.append([round(lon, 5), round(lat, 5),
                        round((z + 90.0) * D3.EXAG, 1)])
        col = (T.CLASS_COLORS[int(k) - 1] if k else T.NOT_ASSESSED)
        out.append({"p": pts,
                    "c": [int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)],
                    "tip": T.CLASS_NAMES[int(k) - 1] if k else "Not assessed"})
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


def place_panel(sel, cls, hz, tri_pts, di, note: str = "") -> None:
    """The SELECTED place, beside the map rather than below it.

    This used to be a separate "clicked point" readout, which meant the map
    could show a pin on one place while the panel described another. There is
    now one selection: searching sets it, and clicking the map sets it too.
    Whatever the pin is on is what this panel is about.

    Height-locked to the map so long content scrolls inside the panel instead
    of stretching the row and leaving dead space beside the map.
    """
    st.markdown("<div class='map-head' style='padding-top:2px'>"
                "<div class='mh-dot'></div>"
                "<div class='mh-title'>Selected location</div></div>",
                unsafe_allow_html=True)
    box = st.container(height=T.MAP_H - 34, border=False, key="click_shell")
    with box:
        if not sel:
            st.markdown("<div class='insp-empty'>No location chosen.<br><br>"
                        "Search a town above, or click anywhere on the map, to "
                        "get that spot's slope susceptibility, how unusual the "
                        "rain is there, and its next seven days.</div>",
                        unsafe_allow_html=True)
            return
        st.markdown(f"<div class='insp-place'>{sel['label']}</div>",
                    unsafe_allow_html=True)
        if note:
            st.markdown(f"<div class='caveat'>{note}</div>",
                        unsafe_allow_html=True)
        px = latlon_to_px(sel["lat"], sel["lon"])
        if px is None:
            st.markdown("<div class='insp-empty'><b>Outside the mapped area</b>"
                        "<br>This model covers Arunachal Pradesh only.</div>",
                        unsafe_allow_html=True)
            return
        r, c = px
        su8, j = int(SUS[r, c]), int(NEAR[r, c])
        if su8 == 255:
            st.markdown("<div class='insp-empty'><b>Not assessed</b><br>"
                        "Permanent ice, open water, or ground flatter than 10°. "
                        "The model never trained on this terrain, so it reports "
                        "nothing rather than guessing.</div>",
                        unsafe_allow_html=True)
            return
        su = su8 / 254.0
        near, km = G.nearest_place(sel["lat"], sel["lon"], PLACES)
        st.markdown(
            f"<div style='margin-bottom:9px'>{T.chip(int(cls[r, c]) - 1)}</div>"
            + T.row("Latitude, longitude",
                    f"{sel['lat']:.4f}, {sel['lon']:.4f}")
            + T.row("Nearest settlement",
                    f"{near['label']} · {km:.0f} km" if near else "—")
            + T.row("Susceptibility", f"{su:.3f}")
            + T.row("Trigger (rain vs normal)", f"{tri_pts[j]:.2f}")
            + T.row("Hazard", f"{hz[r, c]:.3f}")
            + T.row("Rain that day", f"{rain[di, j]:.1f} mm"),
            unsafe_allow_html=True)
        st.caption("Next 7 days here")
        st.bar_chart(pd.DataFrame({
            "day": [datetime.fromisoformat(days[i]).strftime("%d %b")
                    for i in fut],
            "hazard": [float(su * trig[i][j]) for i in fut]}
        ).set_index("day"), height=170, color=T.ACCENT_2)


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
        # This page is the landslide forecast and nothing else. Susceptibility
        # is the static half and has its own tab; the rain trigger is an input
        # to the forecast, not a competing view of it, and is planned for a
        # page of its own. A layer switch with one option is not a choice.
        h1, h3 = st.columns([2.2, 0.42], vertical_alignment="center")
        with h3:
            dims = ["2D", "3D"]
            dim = st.segmented_control("View", dims, default=dims[0],
                                       label_visibility="collapsed",
                                       help="3D drapes the same surface over "
                                            "real terrain — landslides are a "
                                            "slope phenomenon, and a flat map "
                                            "is the one view that hides slope.")
            dim = dim or dims[0]

        # Search row. `accept_new_options` is what lets a visitor type raw
        # coordinates — the gazetteer has 4,648 names but the state has far
        # more places than that, and someone standing on a road cut needs the
        # forecast for exactly where they are.
        s1, s2, s3 = st.columns([5, 1.15, 0.95], vertical_alignment="bottom")
        with s2:
            if st.button("📍 My location", width="stretch",
                         help="Ask the browser where you are. Only used if you "
                              "are inside Arunachal Pradesh."):
                # Clear both guards so a second press asks again rather than
                # silently reusing the previous answer.
                st.query_params["geo"] = "ask"
                for k in ("geo_asked", "geo_applied"):
                    st.session_state.pop(k, None)
                st.rerun()
        with s3:
            # The map is deliberately left wherever the user panned it, so this
            # is the only way back to the selected place without re-picking it.
            if st.button("⌖ Recentre", width="stretch",
                         help="Snap the map back to the selected location."):
                st.session_state.recentre = st.session_state.get("recentre", 0) + 1
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
            map_head("Landslide forecast",
                     "" if dim == "3D" else "click anywhere to inspect")

        # Each button carries the outlook FOR THE SELECTED PLACE, so the number
        # beside a date is about somewhere a person actually is.
        #
        # ⚠️ The strip must ALWAYS say which of the two it is showing. It used
        # to fall back to the statewide share in silence, so the buttons read
        # "11% High+" with nothing on screen naming a place — and there was no
        # way to tell whether that was your town or the whole of Arunachal.
        ld = location_days(sel)
        if ld is not None:
            notes = [T.CLASS_NAMES[k - 1] for k in ld[1]]
            strip_label = f"7-day outlook · <b>{sel['label']}</b>"
        else:
            notes = [f"{100 * s:.0f}% High+" for s in statewide_high_share(days[fut[0]])]
            strip_label = ("7-day outlook · <b>whole state</b> — share of land at "
                           "High or above. Pick a place for a local forecast.")
        st.markdown(f"<div class='strip-label'>{strip_label}</div>",
                    unsafe_allow_html=True)
        di = day_strip("fc", notes)
        sel_day = datetime.fromisoformat(days[di])
        tri_pts, hz, cls = hazard_layers(di)

        # A district is CLIPPED to its own polygon — in 2D and 3D alike. The
        # 3D view used to window to a square box around the centre while 2D
        # showed the whole state, so the same search gave two different
        # answers about what you were looking at.
        dfeat = district_feature(sel["label"]) if sel and sel["kind"] == "district" else None
        clip = district_mask(sel["label"]) if dfeat else None

        marker = None
        centre, zoom = None, 7
        if sel:
            centre = (sel["lat"], sel["lon"])
            zoom = 11
            marker = (sel["lat"], sel["lon"], sel["label"])
        if dfeat:
            # Frame the district by its own size — they range from Namsai at
            # 1,582 cells to West Siang at 29,159, so one fixed zoom either
            # cropped the big ones or lost the small ones in white space.
            pts = np.array([p for ring in G._rings(dfeat["geometry"]) for p in ring])
            # np.ptp(), not ndarray.ptp() — the method was removed in NumPy 2.
            span = max(float(np.ptp(pts[:, 0])), float(np.ptp(pts[:, 1])), 0.05)
            centre = (float(pts[:, 1].mean()), float(pts[:, 0].mean()))
            zoom = float(np.clip(np.log2(360.0 / span) - 1.6, 6, 11))
            marker = None      # the outline says where it is; a pin adds nothing

        # Inspector LEFT, map RIGHT, side by side inside the same card.
        #
        # ⚠️ The map is rendered FIRST even though it sits second on screen:
        # `out` does not exist until st_folium has run, and the inspector needs
        # it. Streamlit places output by which column context it is written
        # into, not by execution order, so writing the map into `cmap` before
        # the panel into `cinfo` still draws the panel on the left.
        cinfo, cmap = st.columns([1, 2.35], gap="medium")

        with cmap:
            out = None
            img = None
            shown = clip_to(cls, clip)
            if not bare:
                img = rgba_overlay(shown, T.CLASS_COLORS)

            # Height-locked shell: switching layer must not collapse the card
            # and bounce the panels below it up for a frame.
            shell = st.container(height=T.MAP_H + 8, border=False, key="map_shell")
            if dim == "3D":
                # Zoomed in on one place we can afford every cell; statewide we
                # cannot. Measured: stride 1 statewide is 288,000 points and a
                # 6.1 MB payload rebuilt on every redraw, for detail no camera
                # at that height can resolve. Stride 3 is 32,000 and 0.7 MB.
                stride = 1 if sel else 3
                sub = clip
                if sub is None and sel:
                    # No polygon to clip to (a town or a coordinate), so the
                    # window is purely a payload limit — say so in the caption
                    # below rather than dressing it up as a boundary.
                    sub = np.zeros((H, W), bool)
                    px = latlon_to_px(sel["lat"], sel["lon"])
                    if px is not None:
                        rad = 90                      # ~45 km of context
                        r0, r1 = max(px[0] - rad, 0), min(px[0] + rad, H)
                        c0, c1 = max(px[1] - rad, 0), min(px[1] + rad, W)
                        sub[r0:r1, c0:c1] = True
                    else:
                        sub = None
                pb, cb, npt, cell_m = (
                    ("", "", 0, 700.0) if bare else forecast_cells(
                        shown, stride=stride, mask=sub,
                        # The sidebar slider governs 3D too — it used to be
                        # silently ignored the moment you switched from 2D.
                        alpha=255 * opacity))
                with shell:
                    components.html(D3.html(
                        basemap=basemap, bounds=[WEST, SOUTH, EAST, NORTH],
                        centre=centre or ((SOUTH + NORTH) / 2, (WEST + EAST) / 2),
                        zoom=(zoom - 1.5) if sel else 6.4,
                        pos_b64=pb, col_b64=cb, n_points=npt,
                        cell_m=cell_m,
                        marker=({"pos": [sel["lon"], sel["lat"]],
                                 "tip": sel["label"]} if sel else None),
                    ), height=T.MAP_H)
                if dfeat:
                    st.caption(f"Clipped to {sel['label']} — the real boundary, "
                               f"not a box around it.")
                elif sel:
                    st.caption("3D draws a ~45 km window around the selected "
                               "point to keep the page light. That window is a "
                               "performance limit, not a boundary — pick a "
                               "district to clip to a real one.")
                if not sel:
                    st.caption(f"Statewide 3D is thinned to ~{cell_m:,.0f} m "
                               f"blocks so the page stays light. Search a place "
                               f"— or click one on the 2D map — for the full "
                               f"{DLAT * 111_000:.0f} m detail the 2D map shows.")
            else:
                m = base_map()
                fg = overlay_group(img, districts=show_districts, marker=marker)
                if dfeat:
                    folium.GeoJson(dfeat, name="Selected district",
                                   style_function=lambda _: {
                                       "color": T.ACCENT, "weight": 2.6,
                                       "fill": False, "opacity": .95}).add_to(fg)
                fly_c, fly_z = fly_to(sel, zoom)
                with shell:
                    # ⚠️ Stable key. Keying on the layer would rebuild the
                    # component on every layer switch, which is exactly the
                    # reset we are avoiding — the layer now travels in the
                    # feature group instead.
                    out = st_folium(m, height=T.MAP_H, use_container_width=True, pixelated=True,
                                    returned_objects=["last_clicked"],
                                    feature_group_to_add=fg,
                                    center=fly_c, zoom=fly_z, key="fmap")
                # A click IS a selection: it moves the pin, redraws the day
                # strip and repoints the panel. Guarded on the coordinates so
                # the rerun happens once per new click and does not loop.
                click = (out or {}).get("last_clicked")
                if click:
                    xy = (round(float(click["lat"]), 5),
                          round(float(click["lng"]), 5))
                    if xy != st.session_state.get("clicked_xy"):
                        st.session_state.clicked_xy = xy
                        st.session_state.pending_place = f"{xy[0]:.4f}, {xy[1]:.4f}"
                        st.rerun()
            if bare:
                legend_strip([], [])
            else:
                # Shares are of whatever is on screen: the district when one is
                # clipped, the state otherwise. Quoting statewide shares under
                # a district's name would be a different number to the map.
                base = shown if clip is not None else cls
                assessed = base > 0
                shares = [float((base[assessed] == i).mean()) if assessed.any() else 0
                          for i in range(1, 6)]
                legend_strip(T.CLASS_NAMES, T.CLASS_COLORS, shares,
                             note=("share of " + sel["label"] if clip is not None
                                   else "Terrain 100 m · rainfall ~33 km · "
                                        "shaded = outside Arunachal"))

        with cinfo:
            place_panel(sel, cls, hz, tri_pts, di,
                        note=("Clicking to select works on the 2D map."
                              if dim == "3D" else ""))

    # ---- the located forecast -------------------------------------------- #
    if geo_state == "ok" and user_pt and not user_inside:
        st.info(f"You appear to be at {user_pt[0]:.2f}°N, {user_pt[1]:.2f}°E — "
                "**outside Arunachal Pradesh**. This forecast covers Arunachal "
                "only, so nothing has been selected. Search a place above, or "
                "click anywhere on the map.")
    elif geo_state == "denied":
        st.caption("Location sharing was declined. Search a place above, click "
                   "the map, or press 📍 to try again.")

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
                        width="stretch", hide_index=True, height=280)

    # ---- statewide summary ------------------------------------------------ #
    # The dedicated Statewide tab was removed: this page already shows the whole
    # state on the map, so a second page repeating it was a nav item earning
    # nothing. Its NUMBERS were worth keeping though, so they live here, folded
    # away — the district table and its CSV are the only export an operations
    # office actually asked for.
    assessed = cls > 0
    hi = float((cls[assessed] >= 4).mean()) if assessed.any() else 0.0
    with st.expander(f"Statewide summary — {100 * hi:.1f}% of assessed land at "
                     f"High or above on {sel_day.strftime('%d %b')}"):
        n_wet = int((tri_pts >= 0.90).sum())
        k = st.columns(3)
        k[0].metric("Unusually wet points", f"{n_wet} of {len(tri_pts)}",
                    help="Weather points whose 3- and 7-day rain sits in the "
                         "wettest 10% of everything that point has recorded "
                         "since 2010.")
        k[1].metric("Median trigger", f"{np.nanmedian(tri_pts):.2f}",
                    help="The typical point's rainfall percentile — 0.50 is an "
                         "ordinary monsoon day for that place.")
        k[2].metric("Rain, wettest point", f"{np.nanmax(rain[di]):.0f} mm")
        st.caption("The trigger is a percentile, not a probability: 0.90 means "
                   "*wetter than 90% of days on record here*, not a 90% chance "
                   "of a landslide. Nothing in this app estimates a probability "
                   "of failure — see **Model & Validation** for why.")

        st.markdown("<div class='eyebrow'>District outlook</div>",
                    unsafe_allow_html=True)
        dt = district_table(cls.tobytes(), cls.shape, days[di])
        st.dataframe(dt, width="stretch", hide_index=True, height=340,
                     column_config={"High+ %": st.column_config.ProgressColumn(
                         "High+ %", min_value=0, max_value=100, format="%.1f%%")})
        st.download_button("⬇️  District outlook (CSV)",
                           dt.to_csv(index=False).encode(),
                           f"slopesense_{days[di]}.csv", "text/csv")
        st.caption("District figures are approximate — computed over each "
                   "district's bounding box, not an exact polygon clip.")


# ═════════════════════════ VIEW: ROADS ═══════════════════════════════════════
elif view == "Roads":
    if not LIVE:
        st.error("**Live rainfall is unavailable right now.** Try again shortly.")
        st.stop()
    if not ROADS:
        st.warning("No road layer in the bundle.")
        st.stop()

    st.markdown("<div class='eyebrow'>What the forecast means for the network</div>",
                unsafe_allow_html=True)
    st.markdown("#### Road exposure")
    st.markdown("A slope that fails into an empty valley costs nothing. The same "
                "slope above a highway closes the only route into a district. "
                "This is the forecast measured **in kilometres of road**.")

    chunks, c_lat, c_lon, c_km, c_rid, c_hw = road_chunks()

    # ---- pick a route (optional) ------------------------------------------ #
    # Empty by default on purpose: the whole-network view is the one that
    # answers "where do I look today", and it should not need two choices
    # before it shows anything.
    NONE = "—"
    labels = [NONE] + [p["label"] for p in PLACES]
    r1, r2, r3 = st.columns([1, 1, 0.42], vertical_alignment="bottom")
    with r1:
        st.selectbox("From", labels, key="rd_from",
                     help="Leave both empty for the whole network.")
    with r2:
        st.selectbox("To", labels, key="rd_to")
    with r3:
        if st.button("Clear route", width="stretch"):
            st.session_state.rd_from = NONE
            st.session_state.rd_to = NONE
            st.rerun()
    p_from = LOOKUP.get(st.session_state.get("rd_from", NONE))
    p_to = LOOKUP.get(st.session_state.get("rd_to", NONE))

    di = day_strip("rd", [f"{k:.0f} km" for k in road_high_km(days[fut[0]])])
    sel_day = datetime.fromisoformat(days[di])
    tri_pts, hz, cls = hazard_layers(di)
    c_cls = sample_classes(cls, c_lat, c_lon)

    route, route_km, snap_a, snap_b = (None, 0.0, 0.0, 0.0)
    if p_from and p_to:
        route, route_km, snap_a, snap_b = route_between(
            p_from["lat"], p_from["lon"], p_to["lat"], p_to["lon"])
        if route is None:
            st.warning(
                f"**No mapped road connects {p_from['label']} to "
                f"{p_to['label']}.** The road layer is clipped to Arunachal, so "
                "any route that legitimately runs through Assam is cut — the "
                "Tirap and Changlang lobe hangs off one of those. Showing the "
                "whole network instead.")

    ahead = (sel_day.date() - date.today()).days

    if route:
        # ---- ONE ROUTE ---------------------------------------------------- #
        r_gj, r_lo, r_la, r_at, r_cls = route_geojson(route, cls)
        step = r_at[1] - r_at[0] if len(r_at) > 1 else 0.6
        r_km_by_class = [float((r_cls == c).sum() * step) for c in range(1, 6)]
        r_high = r_km_by_class[3] + r_km_by_class[4]
        r_assessed = float(sum(r_km_by_class))
        worst_i = int(np.argmax(r_cls))

        k = st.columns(4)
        k[0].metric("Route length", f"{route_km:,.0f} km")
        k[1].metric("At High or above", f"{r_high:,.0f} km",
                    f"{100*r_high/r_assessed:.0f}% of the route"
                    if r_assessed else "—")
        k[2].metric("Worst point",
                    T.CLASS_NAMES[int(r_cls[worst_i]) - 1] if r_cls[worst_i] else "—",
                    f"km {r_at[worst_i]:.0f}")
        k[3].metric("Lead time", "Today" if ahead == 0 else f"+{ahead} d")
        if max(snap_a, snap_b) > 3:
            st.caption(f"Nearest mapped road is {snap_a:.1f} km from "
                       f"{p_from['label']} and {snap_b:.1f} km from "
                       f"{p_to['label']}; the route starts and ends there.")
    else:
        km_by_class = RD.exposure(c_cls, c_km)
        total_km = float(c_km.sum())
        assessed_km = float(sum(km_by_class))
        high_km = km_by_class[3] + km_by_class[4]
        spots = RD.hotspots(c_cls, c_rid, c_km, c_lat, c_lon)

        k = st.columns(4)
        k[0].metric("Road at High or above", f"{high_km:,.0f} km",
                    f"{100*high_km/assessed_km:.0f}% of assessed network"
                    if assessed_km else "—")
        k[1].metric("Hotspot stretches", f"{len(spots):,}",
                    help="Continuous runs of road at High or above. This is the "
                         "unit you would send a crew to.")
        k[2].metric("Longest stretch", f"{spots[0]['km']:.1f} km" if spots else "—")
        k[3].metric("Lead time", "Today" if ahead == 0 else f"+{ahead} d")

    with st.container(border=True):
        hh1, hh2 = st.columns([2.2, 0.62], vertical_alignment="center")
        with hh2:
            rdim = st.segmented_control("View", ["2D", "3D"], default="2D",
                                        key="rd_dim", label_visibility="collapsed",
                                        help="3D shows the terrain the road is "
                                             "cut into, with the forecast on "
                                             "the ground around it.")
            rdim = rdim or "2D"
        with hh1:
            map_head(f"Roads by forecast — {sel_day.strftime('%d %b')}",
                     "each ~1 km of road coloured by its own forecast")

        # Where the 3D camera opens. On a chosen route, its worst point; on the
        # whole network, today's worst stretch — in both cases the place
        # somebody actually has to make a decision about.
        if route:
            focus, zoom3d = (float(r_la[worst_i]), float(r_lo[worst_i])), 9.6
        elif spots:
            focus, zoom3d = (spots[0]["lat"], spots[0]["lon"]), 10.2
        else:
            focus, zoom3d = ((SOUTH + NORTH) / 2, (WEST + EAST) / 2), 8.0
        if rdim == "3D":
            # A chosen route gets a tight corridor around ITSELF; the network
            # view gets the corridor around every road.
            corr = (route_corridor_mask(tuple(np.round(r_lo, 4)),
                                        tuple(np.round(r_la, 4)),
                                        ROUTE_CORRIDOR_KM) if route
                    else road_corridor_mask(CORRIDOR_KM))
            pb, cb, npt, cell_m = forecast_cells(cls, stride=1, mask=corr,
                                                 alpha=255 * opacity)
            shell = st.container(height=T.MAP_H + 8, border=False, key="map_shell")
            with shell:
                components.html(D3.html(
                    basemap=basemap, bounds=[WEST, SOUTH, EAST, NORTH],
                    centre=focus, zoom=10.2, pitch=60,
                    pos_b64=pb, col_b64=cb, n_points=npt,
                    cell_m=cell_m,
                    paths=(route_paths_3d(r_lo, r_la, r_cls) if route
                           else road_paths_3d(chunks, c_cls)),
                    marker={"pos": [focus[1], focus[0]],
                            "tip": ("Worst point on the route" if route
                                    else "Worst stretch today")},
                    pin_height=2500,
                ), height=T.MAP_H)
            band = ROUTE_CORRIDOR_KM if route else CORRIDOR_KM
            st.caption(f"Forecast shown only within {band:.0f} km of the "
                       f"{'route' if route else 'road network'} — the ground "
                       f"that can actually reach it. Opens on the worst point; "
                       f"drag to fly along it.")
            legend_strip(T.CLASS_NAMES, T.CLASS_COLORS, None,
                         note="Relief exaggerated 1.25x so mid-altitude ridges read")
        else:
            shell = st.container(height=T.MAP_H + 8, border=False, key="map_shell")
            m = base_map()
            # Roads ride in their OWN feature group, drawn without the hazard
            # raster: painting both would put a red road on red ground and lose
            # the very thing this view exists to show.
            fg = overlay_group(None, districts=show_districts, inventory=False)
            if route:
                # The rest of the network stays but faint: a route drawn with
                # no context around it could be anywhere in the state.
                folium.GeoJson(road_geojson(chunks, c_cls, c_km),
                               style_function=lambda f: {
                                   "color": "#5b6b7d", "weight": 1.0,
                                   "opacity": 0.32}).add_to(fg)
                folium.GeoJson(r_gj, name="Route casing",
                               style_function=lambda f: {
                                   "color": "#05070a", "weight": 7,
                                   "opacity": 0.85}).add_to(fg)
                folium.GeoJson(
                    r_gj, name="Route by forecast",
                    style_function=lambda f: {
                        "color": T.CLASS_COLORS[f["properties"]["c"] - 1]
                                 if f["properties"]["c"] else T.NOT_ASSESSED,
                        "weight": 4.5, "opacity": 1.0},
                    tooltip=folium.GeoJsonTooltip(["cls", "km"],
                                                  aliases=["Outlook:", "At km:"])
                ).add_to(fg)
                for pt, lbl in ((p_from, "From"), (p_to, "To")):
                    folium.Marker([pt["lat"], pt["lon"]],
                                  tooltip=f"{lbl}: {pt['label']}",
                                  icon=folium.Icon(color="lightblue",
                                                   icon="location-dot",
                                                   prefix="fa")).add_to(fg)
                fly_c = ((min(r_la) + max(r_la)) / 2, (min(r_lo) + max(r_lo)) / 2)
                span = max(max(r_la) - min(r_la), max(r_lo) - min(r_lo), 0.05)
                fly_z = float(np.clip(np.log2(360.0 / span) - 1.4, 6, 12))
            else:
                folium.GeoJson(
                    road_geojson(chunks, c_cls, c_km),
                    name="Roads by forecast",
                    style_function=lambda f: {
                        "color": T.CLASS_COLORS[f["properties"]["c"] - 1]
                                 if f["properties"]["c"] else T.NOT_ASSESSED,
                        "weight": 3.5 if f["properties"]["c"] >= 4 else 2.0,
                        "opacity": 0.95},
                    tooltip=folium.GeoJsonTooltip(["cls", "km"],
                                                  aliases=["Outlook:", "Length (km):"])
                ).add_to(fg)
                fly_c, fly_z = None, None
            with shell:
                st_folium(m, height=T.MAP_H, use_container_width=True,
                          pixelated=True, returned_objects=[],
                          feature_group_to_add=fg,
                          center=fly_c, zoom=fly_z, key="rdmap")
            if route:
                shares = [x / r_assessed if r_assessed else 0
                          for x in r_km_by_class]
                legend_strip(T.CLASS_NAMES, T.CLASS_COLORS, shares,
                             note=f"share of the {route_km:,.0f} km route")
            else:
                shares = [x / assessed_km if assessed_km else 0
                          for x in km_by_class]
                legend_strip(T.CLASS_NAMES, T.CLASS_COLORS, shares,
                             note=f"{assessed_km:,.0f} km assessed of "
                                  f"{total_km:,.0f} km mapped")

    if route:
        st.markdown("<div class='eyebrow'>Along the route</div>",
                    unsafe_allow_html=True)
        prof = pd.DataFrame({
            "km": np.round(r_at, 2),
            "Elevation (m)": route_elevation(r_lo, r_la),
            "Outlook (1-5)": [int(c) if c else np.nan for c in r_cls],
        }).set_index("km")
        pc1, pc2 = st.columns(2)
        with pc1:
            st.caption("Elevation along the route")
            st.line_chart(prof[["Elevation (m)"]], height=200, color=T.ACCENT_2)
        with pc2:
            st.caption("Forecast along the route — 5 is Very High")
            st.bar_chart(prof[["Outlook (1-5)"]], height=200, color=T.ACCENT)
        st.download_button(
            f"⬇️  Route profile, {days[di]} (CSV)",
            prof.reset_index().to_csv(index=False).encode(),
            f"route_profile_{days[di]}.csv", "text/csv")
        st.markdown(
            "<div class='caveat'>This is the shortest path over the "
            "<b>mapped</b> network, not a navigation instruction. Where "
            "OpenStreetMap coverage is patchy it can detour, and it knows "
            "nothing about one-way streets, closures or surface quality.</div>",
            unsafe_allow_html=True)
        st.stop()

    st.markdown("<div class='eyebrow'>Worst stretches</div>", unsafe_allow_html=True)
    if not spots:
        st.success(f"No road stretch reaches High on {sel_day.strftime('%d %b')}.")
    else:
        rows = []
        for h in spots[:60]:
            near, dkm = G.nearest_place(h["lat"], h["lon"], PLACES)
            rows.append({"Nearest settlement":
                             f"{near['label']} ({dkm:.0f} km)" if near else "—",
                         "Outlook": T.CLASS_NAMES[h["peak"] - 1],
                         "Length (km)": round(h["km"], 1),
                         "Latitude": round(h["lat"], 4),
                         "Longitude": round(h["lon"], 4)})
        rdf = pd.DataFrame(rows)
        st.dataframe(rdf, width="stretch", hide_index=True, height=340,
                     column_config={"Length (km)": st.column_config.ProgressColumn(
                         "Length (km)", min_value=0,
                         max_value=float(max(r["Length (km)"] for r in rows)),
                         format="%.1f km")})
        st.download_button(f"⬇️  Road hotspots, {days[di]} (CSV)",
                           pd.DataFrame([
                               {"nearest_settlement": r["Nearest settlement"],
                                "outlook": r["Outlook"], "length_km": r["Length (km)"],
                                "lat": r["Latitude"], "lon": r["Longitude"]}
                               for r in [dict(zip(rdf.columns, v))
                                         for v in rdf.values]]).to_csv(index=False).encode(),
                           f"road_hotspots_{days[di]}.csv", "text/csv")
        st.caption("Ranked by severity then length, showing the top 60. "
                   "Coordinates are the midpoint of the stretch.")

    st.markdown("<div class='caveat'><b>The road layer has no names.</b> "
                "OpenStreetMap gives us 3,489 km of trunk, primary and secondary "
                "road for Arunachal, but no route numbers, so a stretch is "
                "identified by the settlement nearest to it rather than by "
                "\"NH-13, km 47\". Matching to PWD chainage would fix that, and "
                "is the same ask that would unlock the timing model.</div>",
                unsafe_allow_html=True)
    st.markdown("<div class='caveat'>Exposure is the forecast on the ground the "
                "road crosses. It does not model the slope above the carriageway, "
                "which is what actually lands on it — that needs road-cut "
                "geometry we do not have.</div>", unsafe_allow_html=True)


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
        m = base_map()
        fg = overlay_group(None if bare else
                           rgba_overlay(susceptibility_classes(), T.CLASS_COLORS),
                           districts=show_districts)
        with shell:
            st_folium(m, height=T.MAP_H, use_container_width=True, pixelated=True,
                      returned_objects=[], feature_group_to_add=fg, key="smap")
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
            width="stretch", hide_index=True)
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
            m = base_map()
            # This map IS the inventory, so it always draws the heatmap —
            # independent of the sidebar's inventory control.
            fg = overlay_group(None, districts=show_districts, inventory=False)
            HeatMap([(d["y"], d["x"]) for d in INVENTORY], radius=8, blur=11,
                    min_opacity=.35,
                    gradient={0.2: "#1e3a8a", 0.45: "#38bdf8",
                              0.7: "#fde047", 1.0: "#dc2626"}).add_to(fg)
            with shell:
                st_folium(m, height=T.MAP_H, use_container_width=True, pixelated=True,
                          returned_objects=[], feature_group_to_add=fg, key="emap")
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
    st.dataframe(src, width="stretch", hide_index=True, height=440)

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
        width="stretch", hide_index=True)
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
