"""The Data Backbone bundle.

⚠️ Everything here is a SUMMARY. There are no source values in this bundle:
histograms instead of cells, ~6 km-per-pixel thumbnails instead of rasters, and
synthetic rows instead of real records. See scripts/build/build_backbone_bundle.py
for the rule and how it is enforced.
"""
from __future__ import annotations

import json

import numpy as np
import streamlit as st

from core.bundle import product_dir

SLUG = "backbone"
DIR = product_dir(SLUG)


def available() -> bool:
    return (DIR / "layers.json").exists()


@st.cache_data(show_spinner=False)
def load_catalogue() -> dict:
    return json.loads((DIR / "catalogue.json").read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load_layers() -> dict:
    return json.loads((DIR / "layers.json").read_text(encoding="utf-8"))


@st.cache_resource(show_spinner=False)
def load_thumbs():
    """cache_resource, not cache_data: these are read-only preview arrays and
    cache_data would deep-copy all 34 of them on every rerun."""
    z = np.load(DIR / "thumbs.npz")
    return {k: z[k] for k in z.files}
