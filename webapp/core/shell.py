"""What every product page is handed.

One object, built once per rerun by app.py, carrying the shared spine: the
grid, the geography drawn under everything, the terrain model and whatever the
platform knows about where the visitor is.

A product reads from this and adds its own data on top. It never loads the
grid or the boundary itself — two products loading the same file twice is how
they end up disagreeing about where Arunachal is.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.bundle import BaseLayers
from core.grid import Grid
from core.location import Locator


@dataclass
class Shell:
    grid: Grid
    geo: BaseLayers
    elev: np.ndarray | None
    loc: Locator
    product: object          # products.Product — untyped to avoid a cycle

    @property
    def places(self):
        return self.loc.places

    @property
    def lookup(self):
        return self.loc.lookup
