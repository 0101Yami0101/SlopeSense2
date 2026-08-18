"""FloodSense static layers — where water collects, and the catchment graph.

    flood hazard = flood-prone ground (where, static, this script)
                 x catchment rain     (when, daily, computed in the app)

the same two-part shape as SlopeSense, because the physics splits the same way.

WHAT THIS BUILDS
    HAND            height above the nearest drainage, in metres
    channel size    upstream area of the drainage each cell sits above
    flood-prone     the two combined into a 5-class index
    catchments      HydroBASINS level 12, rasterised, with the routing graph
                    that lets the app accumulate rain downstream

TWO CHOICES WORTH KNOWING ABOUT

1. HAND is measured to the NEAREST channel in plan view, not along the flow
   path. The flow-path version is the textbook definition and was built and
   measured first: on this DEM only 61% of in-state cells reach a channel,
   because filling the depressions turns them into flats and a flat cell has no
   steepest-descent neighbour. Against observed inundation the proper version
   scored WORSE than the approximation (AUC 0.649 vs 0.666), so the complete,
   simpler layer is the one that ships. In terrain this steep the nearest
   channel is nearly always the one you would flow to.

2. Low ground is only flood-prone if the channel beside it carries water. Two
   metres above the Siang and two metres above a hillside creek are not the
   same statement, so the index multiplies closeness-to-drainage by the size of
   the drainage. Without that, every gully in Arunachal reads as floodplain.

⚠️ THE OUTPUT IS UNVALIDATED, AND THE PIPELINE SAYS SO IN metrics.json.
The only observed flood record obtainable for Arunachal is Bhuvan's aggregated
2003-2020 layer, which is served as RENDERED MAP TILES. Measured against the
terrain: 70.5% of the pixels it marks as flooded sit on slopes steeper than
15 degrees, and 31.3% on slopes steeper than 25. Water does not pond on a
cliff, so those labels are tile smear, not observation. It cannot referee this
map at pixel level (AUC 0.666, barely above chance) and it cannot referee it at
catchment level either (Spearman +0.03 across 712 basins). Reporting an
accuracy number against it would be inventing one.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject
from scipy import ndimage

from common import HYDROLOGY, INTERIM, LABELS, ROOT

TERRAIN = INTERIM / "terrain"
ASSETS = ROOT / "webapp" / "assets"
BASE = ASSETS / "base"
OUT = ASSETS / "flood"

# A cell is "drainage" once 100 km2 drains through it.
#
# ⚠️ This was 10 km2 and it was too generous — measured, not guessed. At that
# threshold 90.7% of the flood-prone ground the layer produced sat beside a
# channel smaller than 2,000 km2, with a MEDIAN catchment of 47 km2, and the
# layer called 10.7% of the state floodplain. That is a hillside rill: it
# carries water for minutes after rain and floods nothing, and marking its
# banks contradicted this module's own headline that mountain streams are a
# watch rather than a forecast.
#
# One definition of "river" is now used end to end: the channel network, the
# height measured above it, and the size weighting below all agree.
CHANNEL_CELLS = 10_000        # x 100 m x 100 m = 100 km2

# Above this many metres over the nearest drainage, nothing is flood-prone at
# any river size. Deliberately generous — the Brahmaputra's tributaries can
# rise many metres in a monsoon night — but finite, so the map stays blank on
# the mountains, which is the honest picture for a flood layer.
HAND_MAX_M = 25.0

# Channel-size scaling. A drainage of 100 km2 scores 0; one of 10,000 km2
# scores 1; in between it is log-scaled, because discharge grows with area far
# more slowly than area does.
ACC_REF_LO = 10_000           # cells = 100 km2
ACC_REF_HI = 1_000_000        # cells = 10,000 km2

# A display cell is ~550 m across and reports its WORST 100 m of ground, which
# is what keeps narrow valley floors on the map. This floor stops that becoming
# a licence to paint a whole hillside because one corner of it clipped a river.
MIN_LOW_FRAC = 0.05

# Index breaks -> 5 classes. ABSOLUTE, not percentiles: percentile breaks would
# force a fifth of the state into each class, and the true answer is that most
# of Arunachal is not flood-prone at all.
INDEX_BREAKS = [0.08, 0.20, 0.40, 0.65]

T0 = time.time()


def tick(msg: str) -> None:
    print(f"  [{time.time()-T0:6.1f}s] {msg}", flush=True)


def _auc(score: np.ndarray, pos: np.ndarray) -> float:
    """Rank AUC — the chance a flooded cell outscores a dry one.

    ⚠️ TIES GET AVERAGE RANKS, and on this layer that is the difference between
    a real number and a flattering one. 93% of cells score exactly 0 (not
    flood-prone at all), so ties are the overwhelming majority of every
    comparison. Breaking them by sort order instead of averaging scored this
    same layer at 0.879 — the tie-corrected answer is far lower. A tie means
    "these two are indistinguishable", which is worth half a point, not a win.
    """
    npos, nneg = int(pos.sum()), int((~pos).sum())
    if npos == 0 or nneg == 0:
        return float("nan")
    _, inv, cnt = np.unique(score, return_inverse=True, return_counts=True)
    end = np.cumsum(cnt)                 # last 1-based rank of each tie group
    avg = (end - cnt + 1 + end) / 2.0    # mean rank within the group
    ranks = avg[inv]
    return float((ranks[pos].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def validate(index, instate, src_tf, src_crs, bid, dst_tf, gh, gw) -> dict:
    """Score the layer against the only observed flood record we could get —
    and measure that record's own credibility at the same time.

    The verdict below is not a modelling result. It is a statement about the
    reference data: Bhuvan's aggregate is served as RENDERED MAP TILES, and
    rendered tiles smear across a boundary. If most of what it calls flooded
    lies on ground too steep to hold water, it cannot referee anything.
    """
    with rasterio.open(TERRAIN / "terrain_slope_deg.tif") as s:
        slope = s.read(1)
    flood = np.zeros(index.shape, np.uint8)
    with rasterio.open(LABELS / "bhuvan_flood-aggregate-2003-2020_"
                                "mask_arunachal.tif") as s:
        reproject(source=rasterio.band(s, 1), destination=flood,
                  src_transform=s.transform, src_crs=s.crs,
                  dst_transform=src_tf, dst_crs=src_crs,
                  resampling=Resampling.max)   # keep thin flooded strips
    y = (flood > 0) & instate
    on_steep = float((slope[y] > 15).mean()) if y.any() else float("nan")
    on_cliff = float((slope[y] > 25).mean()) if y.any() else float("nan")

    ok = instate & np.isfinite(index)
    pix_auc = _auc(index[ok].astype(np.float64), y[ok])

    # Catchment level: does "share of basin that is flood-prone" track "share
    # of basin observed flooding"? Spearman, so only the ordering matters.
    fweb = np.zeros((gh, gw), np.float32)
    reproject(source=y.astype(np.float32), destination=fweb,
              src_transform=src_tf, src_crs=src_crs,
              dst_transform=dst_tf, dst_crs="EPSG:4326",
              resampling=Resampling.average)
    iweb = np.zeros((gh, gw), np.float32)
    reproject(source=np.where(instate, (index > 0).astype(np.float32), np.nan),
              destination=iweb, src_transform=src_tf, src_crs=src_crs,
              dst_transform=dst_tf, dst_crs="EPSG:4326",
              src_nodata=np.nan, dst_nodata=np.nan,
              resampling=Resampling.average)
    m = (bid > 0) & np.isfinite(iweb) & np.isfinite(fweb)
    lab = bid[m].astype(np.int64) - 1
    n = int(lab.max()) + 1 if lab.size else 0
    cnt = np.bincount(lab, minlength=n).astype(float)
    pred = np.bincount(lab, weights=iweb[m], minlength=n) / np.maximum(cnt, 1)
    obs = np.bincount(lab, weights=fweb[m], minlength=n) / np.maximum(cnt, 1)
    keep = cnt >= 20
    if keep.sum() > 2:
        rp = np.argsort(np.argsort(pred[keep])).astype(float)
        ro = np.argsort(np.argsort(obs[keep])).astype(float)
        rho = float(np.corrcoef(rp, ro)[0, 1])
    else:
        rho = float("nan")
    tick(f"validation attempted: pixel AUC {pix_auc:.3f}, "
         f"catchment rho {rho:+.3f}, {100*on_steep:.1f}% of the reference's "
         f"flooded pixels on slopes > 15 deg")
    return {
        "status": "NOT VALIDATED",
        "reference": "Bhuvan aggregated flood extent 2003-2020 (rendered tiles)",
        "why_rejected": (
            f"{100*on_steep:.1f}% of the pixels the reference marks as flooded "
            f"lie on slopes steeper than 15 degrees, and {100*on_cliff:.1f}% on "
            "slopes steeper than 25 degrees. Water does not pond on a cliff, so "
            "those are tile smear rather than observation."),
        "reference_flooded_cells": int(y.sum()),
        "reference_on_slope_gt15": on_steep,
        "reference_on_slope_gt25": on_cliff,
        "pixel_auc": pix_auc,
        "catchment_spearman": rho,
        "catchment_n": int(keep.sum()),
        "what_would_validate_it": [
            "District inundation reports with dates and locations",
            "Sentinel-1 water mapping for named flood events",
            "River gauge stage records at known cross-sections"],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Building FloodSense static layers")

    # ── terrain ──────────────────────────────────────────────────────────
    # Routing runs on the UNMASKED DEM so a valley that leaves Arunachal and
    # comes back is not cut in two; the state mask is applied at the very end.
    with rasterio.open(TERRAIN / "_dem_unmasked_m.tif") as s:
        z = s.read(1).astype(np.float32)
        src_tf, src_crs = s.transform, s.crs
    with rasterio.open(TERRAIN / "dem_elev_m.tif") as s:
        instate = np.isfinite(s.read(1))
    with rasterio.open(TERRAIN / "hydro_flowacc_cells.tif") as s:
        acc = s.read(1)
    H, W = z.shape
    tick(f"terrain {H}x{W}, {instate.sum()/1e6:.2f}M cells in state")

    # ── HAND, and the size of the drainage each cell sits above ──────────
    chan = acc >= CHANNEL_CELLS
    dist, idx = ndimage.distance_transform_edt(
        ~chan, sampling=(100.0, 100.0), return_indices=True)
    hand = (z - z[idx[0], idx[1]]).astype(np.float32)
    # Below its own channel by a hair is a DEM artefact, not a basement.
    np.maximum(hand, 0.0, out=hand)
    chan_acc = acc[idx[0], idx[1]].astype(np.float32)
    chan_km2 = chan_acc / 100.0            # 100 m cells -> km2
    tick(f"HAND built; {int(chan.sum()):,} channel cells, "
         f"median HAND {np.median(hand[instate]):.0f} m")

    # ── the flood-prone index ────────────────────────────────────────────
    near = np.clip(1.0 - hand / HAND_MAX_M, 0.0, 1.0)
    size = np.clip((np.log10(np.maximum(chan_acc, 1.0)) - np.log10(ACC_REF_LO))
                   / (np.log10(ACC_REF_HI) - np.log10(ACC_REF_LO)), 0.0, 1.0)
    index = (near * size).astype(np.float32)
    index[~instate] = np.nan
    live = np.isfinite(index) & (index > 0)
    tick(f"index built; {live.sum()/1e6:.2f}M cells above zero "
         f"({100*live.sum()/instate.sum():.2f}% of the state)")

    # ── to the web grid, exactly the lattice the other bundles use ───────
    grid = json.loads((BASE / "grid.json").read_text())
    gh, gw = grid["height"], grid["width"]
    dst_tf = from_bounds(grid["west"], grid["south"], grid["east"],
                         grid["north"], gw, gh)

    def to_web(src, resampling, nodata=np.nan, dtype=np.float32):
        dst = np.full((gh, gw), nodata, dtype=dtype)
        reproject(source=src, destination=dst,
                  src_transform=src_tf, src_crs=src_crs,
                  dst_transform=dst_tf, dst_crs="EPSG:4326",
                  src_nodata=nodata, dst_nodata=nodata,
                  resampling=resampling)
        return dst

    # ⚠️ MAX, not average. A floodplain is often one or two 100 m cells wide;
    # averaging it into a ~550 m display cell erases the very corridor this
    # layer exists to show. So a display cell reports its WORST ground, and the
    # share of the cell that is actually low is exported beside it so the panel
    # can say "worst 100 m here, over this much of the cell".
    w_index = to_web(index, Resampling.max)
    w_hand = to_web(np.where(instate, hand, np.nan), Resampling.min)
    w_km2 = to_web(np.where(instate, chan_km2, np.nan), Resampling.max)
    w_frac = to_web(np.where(instate, (index > 0).astype(np.float32), np.nan),
                    Resampling.average)
    tick(f"resampled to the {gh}x{gw} web grid")

    # ── classes ──────────────────────────────────────────────────────────
    # 0 means "not flood-prone", and it renders transparent. That is a real
    # statement about most of Arunachal, not missing data.
    cls = np.zeros((gh, gw), np.uint8)
    m = (np.isfinite(w_index) & (w_index > 0)
         & np.isfinite(w_frac) & (w_frac >= MIN_LOW_FRAC))
    cls[m] = (np.digitize(w_index[m], np.array(INDEX_BREAKS, np.float32)) + 1
              ).astype(np.uint8)
    shares = {i: int((cls == i).sum()) for i in range(6)}
    tick(f"classes: {shares}")

    # The CLASS is what the map paints; the INDEX is what the app multiplies by
    # rainfall. Shipping only the class would force the app to invent a value
    # per class, which would quantise the forecast to five levels before the
    # weather ever touched it.
    q = np.zeros((gh, gw), np.uint8)
    q[m] = np.clip(np.round(w_index[m] * 254), 1, 254).astype(np.uint8)
    np.savez_compressed(OUT / "floodprone.npz", cls=cls, idx=q)
    np.savez_compressed(
        OUT / "hand.npz",
        hand=np.where(np.isfinite(w_hand),
                      np.clip(w_hand, 0, 2000), 65535).astype(np.uint16),
        chan_km2=np.where(np.isfinite(w_km2),
                          np.clip(w_km2, 0, 65000), 65535).astype(np.uint16),
        frac=np.where(np.isfinite(w_frac),
                      np.clip(w_frac * 254, 0, 254), 255).astype(np.uint8))

    # ── catchments and the routing graph ─────────────────────────────────
    g = gpd.read_file(HYDROLOGY / "hydrosheds_basins-lev12_vector_arunachal.gpkg")
    g = g.to_crs("EPSG:4326").reset_index(drop=True)
    # Rasterise straight onto the web grid — the app needs basin-per-display-
    # cell, not basin-per-model-cell.
    bid = rasterize(((geom, i + 1) for i, geom in enumerate(g.geometry)),
                    out_shape=(gh, gw), transform=dst_tf, fill=0,
                    dtype=np.int32).astype(np.uint16)
    tick(f"{len(g)} catchments rasterised, "
         f"{int((bid>0).sum())/1e3:.0f}k cells labelled")

    hyb = {int(v): i for i, v in enumerate(g["HYBAS_ID"])}
    next_down = np.array([hyb.get(int(v), -1) for v in g["NEXT_DOWN"]], np.int32)
    up_area = g["UP_AREA"].to_numpy(np.float32)
    sub_area = g["SUB_AREA"].to_numpy(np.float32)

    # Topological order for the downstream sweep. UP_AREA is strictly larger
    # downstream — every basin's area is contained in its receiver's — so
    # sorting by it ascending IS a valid order. Verified below rather than
    # assumed, because a single out-of-order pair would silently drop a
    # catchment's rain from everything below it.
    order = np.argsort(up_area, kind="stable").astype(np.int32)
    pos = np.empty(len(g), np.int32)
    pos[order] = np.arange(len(g), dtype=np.int32)
    has_dn = next_down >= 0
    bad = int((pos[next_down[has_dn]] <= pos[np.where(has_dn)[0]]).sum())
    tick(f"routing order checked: {bad} basins ordered after their receiver "
         f"({'OK' if bad == 0 else 'PROBLEM'})")

    # Which rainfall point speaks for each catchment. The same 97 points the
    # landslide trigger uses — one rainfall spine, two hazards.
    pts = json.loads((BASE / "points.json").read_text())
    plat = np.asarray(pts["lat"], np.float64)
    plon = np.asarray(pts["lon"], np.float64)
    cen = g.geometry.representative_point()
    d2 = ((cen.y.to_numpy()[:, None] - plat[None, :]) ** 2
          + ((cen.x.to_numpy()[:, None] - plon[None, :]) * 0.89) ** 2)
    rain_pt = np.argmin(d2, axis=1).astype(np.int32)
    tick(f"catchments mapped to {len(np.unique(rain_pt))} of {len(plat)} "
         f"rainfall points")

    np.savez_compressed(OUT / "catchments.npz", bid=bid, next_down=next_down,
                        order=order, up_area=up_area, sub_area=sub_area,
                        rain_pt=rain_pt)

    # ── the attempted validation ─────────────────────────────────────────
    # ⚠️ Computed here, every build, never typed into the app. These numbers
    # appear on FloodSense's Method page; if the layer changes and the numbers
    # do not, the page starts lying. That has happened once already in this
    # project — a hardcoded landslide count outlived the clip that changed it.
    val = validate(index, instate, src_tf, src_crs, bid, dst_tf, gh, gw)

    n_state = int(instate.sum())
    metrics = {
        "grid": {"height": gh, "width": gw},
        "channel_definition": {
            "min_upstream_km2": CHANNEL_CELLS / 100.0,
            "channel_cells_100m": int(chan.sum())},
        "hand": {
            "method": "nearest drainage in plan view",
            "max_m_considered": HAND_MAX_M,
            "median_m_statewide": float(np.median(hand[instate]))},
        "flood_prone": {
            "cells_by_class": {str(i): shares[i] for i in range(6)},
            "share_of_state_any_class": float(
                sum(shares[i] for i in range(1, 6))
                / max(sum(shares.values()) - shares[0], 1))},
        "catchments": {"n": int(len(g)),
                       "level": 12,
                       "source": "HydroSHEDS HydroBASINS v1c"},
        "validation": val,
        "state_cells": n_state,
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))

    total = sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())
    tick(f"flood bundle: {total/1e6:.2f} MB -> {OUT}")
    for p in sorted(OUT.iterdir()):
        if p.is_file():
            print(f"      {p.name:<20} {p.stat().st_size/1e3:8.1f} KB")


if __name__ == "__main__":
    main()
