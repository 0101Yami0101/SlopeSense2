"""Visual exit check for Stage 1b.

Flow accumulation is the one layer with an independent ground truth: it should
reproduce the real river network. Panel 2 overlays HydroSHEDS' mapped rivers on
our computed drainage — if they trace the same lines, the routing is right.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, rasterio, geopandas as gpd
import grid as G
from common import INTERIM, HYDROLOGY, AOI_NAME

S = INTERIM / "terrain"; STEP = 3
def rd(n):
    with rasterio.open(S/f"{n}.tif") as s: return s.read(1)[::STEP, ::STEP]

acc, twi = rd("hydro_flowacc_cells"), rd("hydro_twi")
ext = [G.BOUNDS[0], G.BOUNDS[2], G.BOUNDS[1], G.BOUNDS[3]]

fig, ax = plt.subplots(1, 2, figsize=(19, 6))
ax[0].imshow(np.log10(acc+1), cmap="Blues", vmin=0, vmax=4, extent=ext)
ax[0].set_title("Computed drainage — log10(upslope cells)")

ax[1].imshow(np.log10(acc+1), cmap="Greys", vmin=0, vmax=4, extent=ext)
riv = gpd.read_file(HYDROLOGY/f"hydrosheds_rivers_vector_{AOI_NAME}.gpkg").to_crs(G.CRS)
riv.plot(ax=ax[1], color="red", linewidth=0.35, alpha=0.75)
ax[1].set_title("Same, with HydroSHEDS mapped rivers in red")
ax[1].set_xlim(ext[0], ext[1]); ax[1].set_ylim(ext[2], ext[3])
for a in ax: a.set_xticks([]); a.set_yticks([])
fig.tight_layout(); fig.savefig(INTERIM/"terrain"/"_check_hydro.png", dpi=95, bbox_inches="tight")

fig2, ax2 = plt.subplots(figsize=(13, 5))
im = ax2.imshow(twi, cmap="YlGnBu", vmin=4, vmax=14)
ax2.set_title("Topographic Wetness Index — high = converging, wet; low = ridges")
ax2.set_xticks([]); ax2.set_yticks([]); fig2.colorbar(im, ax=ax2, fraction=0.02)
fig2.savefig(INTERIM/"terrain"/"_check_twi.png", dpi=95, bbox_inches="tight")
print("wrote _check_hydro.png and _check_twi.png")

# --- zoomed alignment check -------------------------------------------------
# The full-state overlay is too dense to read. This crops a 60x40 km window so
# the computed drainage and the mapped rivers can actually be compared line by
# line. If routing were wrong (flipped axis, offset origin) they would diverge
# visibly here.
X0, Y0, W, H = 500_000, 3_050_000, 60_000, 40_000
c0 = int((X0 - G.ORIGIN_X) / G.CELL); c1 = c0 + W // G.CELL
r1 = int((G.TOP_Y - Y0) / G.CELL);    r0 = r1 - H // G.CELL

with rasterio.open(S / "hydro_flowacc_cells.tif") as s:
    win = s.read(1)[r0:r1, c0:c1]
zext = [X0, X0 + W, Y0, Y0 + H]

fig3, ax3 = plt.subplots(1, 2, figsize=(18, 6))
for a in ax3:
    a.imshow(np.log10(win + 1), cmap="Greys", vmin=0, vmax=3.5, extent=zext)
    a.set_xlim(X0, X0 + W); a.set_ylim(Y0, Y0 + H)
    a.set_xticks([]); a.set_yticks([])
riv.plot(ax=ax3[1], color="red", linewidth=1.4, alpha=0.9)
ax3[0].set_title("Computed drainage (60 x 40 km, West Kameng area)")
ax3[1].set_title("Same window + HydroSHEDS rivers — lines should coincide")
fig3.tight_layout()
fig3.savefig(INTERIM / "terrain" / "_check_hydro_zoom.png", dpi=110, bbox_inches="tight")
print("wrote _check_hydro_zoom.png")
