"""Road exposure — which stretches of road the forecast puts under threat.

The statewide picture answers "how much of Arunachal is dangerous today". This
answers the question an actual highways engineer asks: **which roads, and how
many kilometres of them.** A slope that fails into an empty valley costs
nothing; the same slope above NH-13 closes the only route into a district.

════════════════════════════════════════════════════════════════════════════
WHY STRETCHES AND NOT NAMED ROUTES
════════════════════════════════════════════════════════════════════════════
The earlier SlopeSense ranked a handful of hand-listed named routes. Our road
layer is OpenStreetMap geometry clipped to the state: 1,231 features, 3,489 km,
and it carries **no names at all** — only a class (trunk / primary /
secondary). Median feature length is 0.8 km, so more than half of them are
fragments; ranking features would rank arbitrary bits of tarmac.

So the unit here is a HOTSPOT STRETCH: a continuous run of road whose forecast
sits at High or above, measured end to end and labelled by the settlement
nearest to it. That is a real object on the ground, it needs no name in the
data, and it is the thing you would send a crew to.

Streamlit-free so it can be tested.
"""
from __future__ import annotations

import numpy as np

# Degrees -> km at Arunachal's latitude. Flat-earth on purpose: over a 5-degree
# state the error is metres, and this runs over every road vertex.
KM_PER_DEG_LAT = 110.6
KM_PER_DEG_LON = 98.9
STEP_KM = 1.0            # chunk length; ~2 display cells, so colour follows terrain


def _parts(geom: dict):
    """Every line in a feature, whatever the geometry type.

    The layer is mostly LineString but carries 6 MultiLineStrings and — from
    the OSM extract — 2 Polygons, which are roundabouts. Ignoring the awkward
    types would silently drop road, so each is flattened to its line(s).
    """
    t, c = geom["type"], geom["coordinates"]
    if t == "LineString":
        return [c]
    if t == "MultiLineString":
        return c
    if t == "Polygon":
        return [ring for ring in c]
    return []


def _seg_km(c: np.ndarray) -> np.ndarray:
    return np.hypot(np.diff(c[:, 0]) * KM_PER_DEG_LON,
                    np.diff(c[:, 1]) * KM_PER_DEG_LAT)


def chunk_roads(features, step_km: float = STEP_KM):
    """Cut the network into ~step_km pieces.

    Returns (chunks, mid_lat, mid_lon, length_km, road_id, highway) where
    `chunks` is a list of [[lon, lat], ...] and `road_id` says which original
    feature each piece came from — needed so hotspot runs never jump between
    two unconnected roads that happen to be adjacent in the file.
    """
    chunks, mlat, mlon, lens, rid, hw = [], [], [], [], [], []
    for i, f in enumerate(features):
        cls = f.get("properties", {}).get("highway", "road")
        for part in _parts(f["geometry"]):
            c = np.asarray(part, dtype=float)
            if len(c) < 2:
                continue
            d = _seg_km(c)
            cum = np.concatenate([[0.0], np.cumsum(d)])
            total = cum[-1]
            if total <= 0:
                continue
            n = max(1, int(round(total / step_km)))
            edges = np.linspace(0.0, total, n + 1)
            # Resample at the cut points, then keep the original vertices in
            # between so a chunk still follows the bend of the road rather
            # than short-cutting it as a straight line.
            for a, b in zip(edges[:-1], edges[1:]):
                lo = np.interp(a, cum, c[:, 0]), np.interp(a, cum, c[:, 1])
                hi = np.interp(b, cum, c[:, 0]), np.interp(b, cum, c[:, 1])
                inner = c[(cum > a) & (cum < b)]
                pts = [list(lo)] + [list(p) for p in inner] + [list(hi)]
                chunks.append(pts)
                mlon.append((lo[0] + hi[0]) / 2)
                mlat.append((lo[1] + hi[1]) / 2)
                lens.append(b - a)
                rid.append(i)
                hw.append(cls)
    return (chunks, np.array(mlat), np.array(mlon), np.array(lens),
            np.array(rid), hw)


def hotspots(cls_per_chunk: np.ndarray, road_id: np.ndarray,
             length_km: np.ndarray, mlat: np.ndarray, mlon: np.ndarray,
             min_class: int = 4, min_km: float = 0.0):
    """Continuous runs at `min_class` or above, along one road at a time.

    ⚠️ The run breaks whenever road_id changes. Chunks are stored in file
    order, so without that check two unrelated roads listed next to each other
    would be welded into one impossibly long "stretch".
    """
    out = []
    n = len(cls_per_chunk)
    i = 0
    while i < n:
        if cls_per_chunk[i] < min_class:
            i += 1
            continue
        j = i
        while (j + 1 < n and road_id[j + 1] == road_id[i]
               and cls_per_chunk[j + 1] >= min_class):
            j += 1
        km = float(length_km[i:j + 1].sum())
        if km >= min_km:
            out.append({"km": km,
                        "peak": int(cls_per_chunk[i:j + 1].max()),
                        "lat": float(np.mean(mlat[i:j + 1])),
                        "lon": float(np.mean(mlon[i:j + 1]))})
        i = j + 1
    out.sort(key=lambda d: (-d["peak"], -d["km"]))
    return out


def exposure(cls_per_chunk: np.ndarray, length_km: np.ndarray,
             n_classes: int = 5) -> list[float]:
    """Kilometres of road in each hazard class. Unassessed chunks (class 0)
    are excluded, not counted as safe."""
    return [float(length_km[cls_per_chunk == k].sum())
            for k in range(1, n_classes + 1)]


# ── routing ──────────────────────────────────────────────────────────────────
# ⚠️ The network is NOT fully connected, and that is mostly real geography, not
# a data fault. Roads are clipped to Arunachal, so any route that legitimately
# runs through Assam — the whole Tirap/Changlang lobe hangs off one — has its
# link cut. Measured on 12 real town pairs: 11 route, Itanagar->Khonsa does not.
#
# Vertices are also snapped before joining, because separate OSM ways that meet
# at a junction rarely share a vertex to the metre. 120 m was picked by
# measurement: it lifts the largest connected component from 35% of nodes to
# 70%, and below it even Bomdila->Tawang fails.
SNAP_M = 120.0


def build_graph(features, snap_m: float = SNAP_M):
    """Undirected road graph. Returns (adjacency, node -> [lon, lat])."""
    q = snap_m / 111_000.0
    adj: dict = {}
    pos: dict = {}

    def key(p):
        return (round(p[1] / q), round(p[0] / q))

    for f in features:
        for line in _parts(f["geometry"]):
            ks = [key(p) for p in line]
            for k, p in zip(ks, line):
                pos[k] = p
            for a, pa, b, pb in zip(ks[:-1], line[:-1], ks[1:], line[1:]):
                if a == b:
                    continue
                d = float(np.hypot((pa[0] - pb[0]) * KM_PER_DEG_LON,
                                   (pa[1] - pb[1]) * KM_PER_DEG_LAT))
                if d < adj.setdefault(a, {}).get(b, 1e18):
                    adj[a][b] = d
                    adj.setdefault(b, {})[a] = d
    return adj, pos


def nearest_node(adj, pos, lat: float, lon: float):
    """Closest graph node, and how far off-network the request was (km)."""
    best, bd = None, 1e18
    for k in adj:
        p = pos[k]
        d = ((p[0] - lon) * KM_PER_DEG_LON) ** 2 + ((p[1] - lat) * KM_PER_DEG_LAT) ** 2
        if d < bd:
            best, bd = k, d
    return best, float(bd ** 0.5)


def shortest_path(adj, pos, src, dst):
    """Dijkstra. Returns ([[lon, lat], ...], km) or (None, 0) if unreachable.

    Plain heapq rather than a graph library: 7,000 nodes runs in milliseconds
    and the app's whole point is that it deploys with no scientific stack.
    """
    import heapq
    if src is None or dst is None or src not in adj or dst not in adj:
        return None, 0.0
    dist = {src: 0.0}
    prev: dict = {}
    seen = set()
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if u in seen:
            continue
        seen.add(u)
        if u == dst:
            break
        for v, w in adj[u].items():
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if dst not in dist:
        return None, 0.0
    out = [dst]
    while out[-1] != src:
        out.append(prev[out[-1]])
    out.reverse()
    return [pos[k] for k in out], float(dist[dst])


def densify(line, step_km: float = 0.5):
    """Resample a polyline to even spacing — one sample per profile point."""
    c = np.asarray(line, dtype=float)
    d = _seg_km(c)
    cum = np.concatenate([[0.0], np.cumsum(d)])
    total = cum[-1]
    if total <= 0:
        return c[:, 0], c[:, 1], np.array([0.0])
    at = np.arange(0.0, total, step_km)
    return (np.interp(at, cum, c[:, 0]), np.interp(at, cum, c[:, 1]), at)
