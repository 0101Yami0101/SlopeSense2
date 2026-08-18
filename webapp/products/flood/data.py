"""FloodSense's own bundle.

Terrain-derived layers and the catchment routing graph. The grid, boundary,
rivers, gazetteer and — importantly — the rainfall points and climatology are
NOT here: they are the shared spine, and both hazards read the same ones.
"""
from __future__ import annotations

import json

import numpy as np
import streamlit as st

from core.bundle import product_dir

SLUG = "flood"
DIR = product_dir(SLUG)


def available() -> bool:
    return (DIR / "floodprone.npz").exists()


@st.cache_data(show_spinner=False)
def load_static():
    """Flood-prone classes and index, HAND in metres, the size of the drainage
    each cell sits above, and the share of each display cell that is low."""
    fp = np.load(DIR / "floodprone.npz")
    hd = np.load(DIR / "hand.npz")
    met = json.loads((DIR / "metrics.json").read_text())
    return fp["cls"], fp["idx"], hd["hand"], hd["chan_km2"], hd["frac"], met


@st.cache_data(show_spinner=False)
def load_catchments():
    """Basin id per cell, plus the routing graph the rain is carried along."""
    c = np.load(DIR / "catchments.npz")
    return (c["bid"], c["next_down"], c["order"], c["up_area"],
            c["sub_area"], c["rain_pt"])
