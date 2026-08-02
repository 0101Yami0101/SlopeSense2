"""Visual exit check for Stage 1a — render the terrain layers to a PNG.

The numbers in terrain.py's summary can look fine while the geometry is wrong
(flipped north-south, offset origin, wrong CRS). Only a picture catches that.
Compare against any map of Arunachal: the Himalayan crest should run along the
northern border, the Brahmaputra plains sit low in the southwest.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio

from common import INTERIM

SRC = INTERIM / "terrain"
STEP = 4  # downsample for display only

PANELS = [("dem_elev_m", "Elevation (m)", "terrain", None),
          ("terrain_slope_deg", "Mean slope (deg)", "inferno", (0, 60)),
          ("terrain_slope_max_deg", "Steepest 25 m sub-cell (deg)", "inferno", (0, 70)),
          ("terrain_relief_m", "Relief within cell (m)", "magma", (0, 150)),
          ("terrain_northness", "Northness (cos aspect)", "coolwarm", (-1, 1)),
          ("terrain_curv_plan", "Plan curvature", "BrBG", (-0.05, 0.05))]

fig, axes = plt.subplots(3, 2, figsize=(16, 13))
for ax, (name, title, cmap, lim) in zip(axes.ravel(), PANELS):
    with rasterio.open(SRC / f"{name}.tif") as s:
        a = s.read(1)[::STEP, ::STEP]
    kw = dict(cmap=cmap)
    if lim:
        kw.update(vmin=lim[0], vmax=lim[1])
    im = ax.imshow(a, **kw)
    ax.set_title(title, fontsize=11)
    ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im, ax=ax, fraction=0.03)

fig.suptitle("Stage 1a — terrain derivatives on the 100 m canonical grid "
             "(EPSG:32646, Arunachal Pradesh)", fontsize=13)
fig.tight_layout()
out = INTERIM / "terrain" / "_check_terrain.png"
fig.savefig(out, dpi=95, bbox_inches="tight")
print(f"wrote {out}")
