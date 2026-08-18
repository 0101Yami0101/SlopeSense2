"""Where the visitor is, and where they asked about.

Shared because a forecast is only useful somewhere, and that is as true of a
flood as of a landslide. The gazetteer, the browser geolocation handshake and
the one-selection rule all belong to the platform, not to either hazard.

⚠️ Order matters and is why this runs from the shell rather than from a page:
every session-state write here must happen BEFORE the search widget is built,
and the search widget lives inside a product page.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st
import streamlit.components.v1 as components

import core.geo as G
from core.grid import Grid


@st.cache_data(show_spinner=False)
def load_places(_towns, _districts):
    """4,648 settlements + 18 districts as one searchable list.

    Cached because it sorts and de-duplicates the whole gazetteer, and it never
    changes within a deployment.
    """
    places = G.build_places(_towns, _districts)
    return places, {p["label"]: p for p in places}


@dataclass
class Locator:
    places: list
    place_idx: dict
    lookup: dict
    me: dict | None
    geo_state: str | None
    user_pt: tuple | None
    user_inside: bool


def resolve_visitor(grid: Grid, towns, districts) -> Locator:
    """Run the whole location handshake, once per rerun, before any widget.

    ⚠️ OPT-IN ONLY. The page never asks where you are on load — the request
    fires solely when the 📍 button sets geo=ask. Asking unprompted throws a
    browser permission prompt at a visitor who only wanted to look at a map,
    and it made the app open on a personal location without anyone choosing it.

    Every outcome — allowed, refused, timed out, unsupported — writes a `geo`
    flag into the URL, and that flag is what stops the request repeating.
    """
    places, place_idx = load_places(towns, districts)

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
    user_inside = bool(user_pt and G.in_area(user_pt[0], user_pt[1],
                                             {"west": grid.west, "east": grid.east,
                                              "south": grid.south, "north": grid.north}))

    me = _me_place(user_pt, user_inside, places)

    # Nothing is selected until someone chooses. The forecast is about a place,
    # and picking one for the visitor — their own position or a default town —
    # is a claim we have no business making before they ask.
    if "search" not in st.session_state:
        st.session_state.search = G.PROMPT

    # Adopt the located position ONCE. Without the flag the query string, which
    # survives every rerun, would keep re-selecting it and undo any later search.
    if me and not st.session_state.get("geo_applied"):
        st.session_state.geo_applied = True
        st.session_state.pending_place = me["label"]

    # ⚠️ A map click selects a place, but the click only comes back AFTER the
    # search box has already been built this run — and Streamlit REFUSES to let
    # a widget's session_state be written once the widget exists:
    #     StreamlitAPIException: `st.session_state.search` cannot be modified
    #     after the widget with key `search` is instantiated.
    # So a click parks its coordinates here and the next run adopts them, above,
    # before the box is created. An earlier "use this point" button wrote
    # `search` directly from inside the panel and would have crashed the app.
    if "pending_place" in st.session_state:
        st.session_state.search = st.session_state.pop("pending_place")

    # Two lookups on purpose, and they are NOT interchangeable:
    #   place_idx — the gazetteer alone, which decides whether a label needs
    #               adding to the dropdown's option list.
    #   lookup    — everything resolvable, gazetteer PLUS "My location — near X".
    # Collapsing them broke the single most common path: a visitor standing in
    # Arunachal got "could not read that place", because their own position has
    # a label no gazetteer contains.
    lookup = dict(place_idx)
    if me:
        lookup[me["label"]] = me

    return Locator(places=places, place_idx=place_idx, lookup=lookup, me=me,
                   geo_state=geo_state, user_pt=user_pt, user_inside=user_inside)


def _me_place(user_pt, user_inside, places) -> dict | None:
    """The visitor's own position as a selectable place.

    Only ever built when the browser answered AND the answer lands inside the
    forecast area. Outside Arunachal there is nothing to forecast, so there is
    no place to offer — the app says so rather than quietly snapping to a
    nearby town the visitor never asked for.
    """
    if not user_inside:
        return None
    near, km = G.nearest_place(user_pt[0], user_pt[1], places)
    label = (f"My location — near {near['label']}" if near and km < 25
             else f"My location — {user_pt[0]:.3f}°N, {user_pt[1]:.3f}°E")
    return {"label": label, "lat": user_pt[0], "lon": user_pt[1], "kind": "me"}


def ask_again() -> None:
    """Clear both guards so a second press of 📍 asks again rather than
    silently reusing the previous answer."""
    st.query_params["geo"] = "ask"
    for k in ("geo_asked", "geo_applied"):
        st.session_state.pop(k, None)
