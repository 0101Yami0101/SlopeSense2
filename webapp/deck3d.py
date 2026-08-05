"""3D terrain view — the hazard surface draped over real relief.

Why this matters for THIS product: landslides are a slope phenomenon, and a
flat map is the one projection that hides slope. Seen in 3D, the red ground
lines up with the gorge walls and the reason for the forecast becomes visible
rather than asserted.

════════════════════════════════════════════════════════════════════════════
HOW IT IS BUILT
════════════════════════════════════════════════════════════════════════════
deck.gl in a self-contained page, via components.html. Three pieces:

  TerrainLayer     Mapzen terrarium tiles decoded to elevation, textured with
                   the same basemap the 2D map uses.
  BitmapLayer      our hazard/trigger/susceptibility raster, carrying
                   `_TerrainExtension` so it is DRAPED onto the mesh instead
                   of lying flat at sea level and being buried by the
                   mountains it is describing.
  GeoJsonLayer     the state edge, also draped.

⚠️ The extension is exported as `deck._TerrainExtension` — with the leading
underscore — in the 8.9 standalone build. Verified against the actual bundle
rather than assumed; the un-prefixed name silently does not exist, and a
missing extension does not raise, it just renders the overlay flat.

⚠️ The overlay is handed over as an HTMLImageElement built from a data URI,
NOT as a URL. deck.gl's URL path goes through loaders.gl, which is what
forced the earlier SlopeSense to write PNGs into a served static directory and
turn on `enableStaticServing`. Decoding the image ourselves first sidesteps
all of that, so this app still needs no server configuration and writes no
files.
"""
from __future__ import annotations

import base64
import io
import json

import numpy as np
from PIL import Image

TERRAIN_TILES = ("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
                 "{z}/{x}/{y}.png")

# Terrarium encodes height as  r*256 + g + b/256 - 32768  metres. Multiplying
# every term by the same factor exaggerates relief without distorting sea
# level. 1.0 is true scale; Arunachal spans ~100 m to 7,000 m, so a little
# lift makes the mid-altitude ridges read without turning the Himalaya into
# spikes.
EXAG = 1.35
DECODER = {"rScaler": 256 * EXAG, "gScaler": 1 * EXAG,
           "bScaler": EXAG / 256, "offset": -32768 * EXAG}

# Tile styles WITH cartography baked in — roads, rivers and place names come
# as part of the texture, so the 3D view needs no separate label layer riding
# above the drape.
TEX = {
    "Dark": ("https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
             "© CARTO · © OpenStreetMap"),
    "Light": ("https://server.arcgisonline.com/ArcGIS/rest/services/"
              "World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
              "© Esri — World Topo Map"),
    "Terrain": ("https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
                "© OpenTopoMap (CC-BY-SA) · © OpenStreetMap"),
    "Satellite": ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                  "World_Imagery/MapServer/tile/{z}/{y}/{x}",
                  "Imagery © Esri, Maxar"),
}

# deck.gl lights the mesh by MULTIPLYING the texture, which drives an already
# dark basemap to near-black. Lift the ambient term per style so the tile's own
# roads and labels survive, while keeping enough diffuse for relief to read.
MATERIAL = {
    "Dark": {"ambient": 1.0, "diffuse": 0.75, "shininess": 3,
             "specularColor": [70, 90, 110]},
    "Light": {"ambient": 0.6, "diffuse": 0.55, "shininess": 1,
              "specularColor": [40, 40, 40]},
    "Terrain": {"ambient": 0.6, "diffuse": 0.55, "shininess": 1,
                "specularColor": [40, 40, 40]},
    "Satellite": {"ambient": 0.55, "diffuse": 0.6, "shininess": 2,
                  "specularColor": [50, 50, 50]},
}


def png_data_uri(rgba: np.ndarray) -> str:
    """RGBA array -> data URI. The class rasters use five colours, so PNG's
    palette makes this ~40 KB even at full grid size."""
    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


TEMPLATE = """<!doctype html><meta charset="utf-8">
<link rel="preconnect" href="https://unpkg.com">
<link rel="preconnect" href="https://s3.amazonaws.com">
<script src="https://unpkg.com/deck.gl@8.9.36/dist.min.js"></script>
<style>
html,body{margin:0;padding:0;background:transparent;overflow:hidden}
#map{position:absolute;inset:0;border-radius:14px;overflow:hidden;
     border:1px solid #223044;background:#0b0f14}
#attr{position:absolute;right:9px;bottom:7px;z-index:9;font:10px/1.4 sans-serif;
      color:#8fa3ba;background:rgba(11,15,20,.72);padding:2px 7px;
      border-radius:6px;pointer-events:none}
#hint{position:absolute;left:9px;bottom:7px;z-index:9;font:10.5px/1.4 sans-serif;
      color:#8fa3ba;background:rgba(11,15,20,.72);padding:3px 8px;
      border-radius:6px;pointer-events:none}
#spin{position:absolute;inset:0;display:flex;align-items:center;
      justify-content:center;z-index:8}
#spin i{width:30px;height:30px;border-radius:50%;display:block;
        border:3px solid rgba(46,230,214,.18);border-top-color:#2ee6d6;
        animation:s .85s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}
</style>
<div id="map"></div>
<div id="spin"><i></i></div>
<div id="attr">__ATTR__</div>
<div id="hint">drag to pan · right-drag to tilt and rotate · scroll to zoom</div>
<script>
// Right-drag orbits the camera; without this, releasing the right button also
// pops the browser's native context menu on top of the map.
document.addEventListener('contextmenu', e => e.preventDefault());

const cfg = __CFG__;
const clamp = (v, a, b) => Math.min(Math.max(v, a), b);
// _TerrainExtension is the 8.9 export name. Guard rather than assume: without
// it the overlay would render flat at sea level, under the mountains.
const TerrainExt = deck._TerrainExtension || deck.TerrainExtension;

function build(overlayImage) {
  const layers = [
    new deck.TerrainLayer({
      id: 'terrain',
      elevationData: cfg.terrainTiles,
      elevationDecoder: cfg.decoder,
      texture: cfg.texture,
      material: cfg.material,
      maxZoom: 12, minZoom: 2
    })
  ];
  if (overlayImage) layers.push(new deck.BitmapLayer({
    id: 'hazard', image: overlayImage, bounds: cfg.bounds,
    opacity: cfg.opacity,
    extensions: TerrainExt ? [new TerrainExt()] : []
  }));
  if (cfg.boundary) layers.push(new deck.GeoJsonLayer({
    id: 'edge', data: cfg.boundary, stroked: true, filled: false,
    getLineColor: cfg.edgeColor, lineWidthMinPixels: 2,
    extensions: TerrainExt ? [new TerrainExt()] : []
  }));
  // The searched place is a COLUMN, not a dot: a flat marker draped on a
  // ridge is invisible from a low camera angle, and this is the one thing on
  // screen the visitor came to find.
  if (cfg.marker) layers.push(new deck.ColumnLayer({
    id: 'pin', data: [cfg.marker], diskResolution: 12, radius: 700,
    extruded: true, pickable: true, elevationScale: 1,
    getPosition: d => d.pos, getElevation: 9000,
    getFillColor: [46, 230, 214, 170]
  }));
  return layers;
}

function start(overlayImage) {
  document.getElementById('spin').style.display = 'none';
  new deck.DeckGL({
    container: 'map',
    layers: build(overlayImage),
    initialViewState: {
      longitude: cfg.centre[1], latitude: cfg.centre[0], zoom: cfg.zoom,
      pitch: 55, bearing: 0
    },
    controller: {maxPitch: 75, touchRotate: true, dragRotate: true},
    getTooltip: ({object}) => object && object.tip,
    onViewStateChange: ({viewState}) => {
      viewState.longitude = clamp(viewState.longitude, cfg.lock[0], cfg.lock[2]);
      viewState.latitude = clamp(viewState.latitude, cfg.lock[1], cfg.lock[3]);
      viewState.zoom = clamp(viewState.zoom, 5.6, 13.5);
      return viewState;
    }
  });
}

if (cfg.overlay) {
  // Decode the image ourselves, then hand deck.gl the element. See module
  // docstring: this is what avoids needing a served static file.
  const im = new Image();
  im.onload = () => start(im);
  im.onerror = () => start(null);
  im.src = cfg.overlay;
} else {
  start(null);
}
</script>"""


def html(*, basemap: str, overlay: str | None, bounds: list[float],
         centre: tuple[float, float], zoom: float, opacity: float,
         boundary: dict | None, marker: dict | None,
         edge_color: list[int]) -> str:
    tex, attr = TEX.get(basemap, TEX["Dark"])
    cfg = {
        "terrainTiles": TERRAIN_TILES,
        "decoder": DECODER,
        "texture": tex,
        "material": MATERIAL.get(basemap, MATERIAL["Dark"]),
        "overlay": overlay,
        "bounds": bounds,                       # [W, S, E, N]
        "opacity": opacity,
        "boundary": boundary,
        "edgeColor": edge_color,
        "marker": marker,
        "centre": [centre[0], centre[1]],
        "zoom": zoom,
        # Keep the camera over the region; deck.gl has no maxBounds of its own.
        "lock": [bounds[0] - 1.2, bounds[1] - 1.2, bounds[2] + 1.2, bounds[3] + 1.2],
    }
    return (TEMPLATE.replace("__CFG__", json.dumps(cfg))
            .replace("__ATTR__", attr + " · elevation © Mapzen/Tilezen"))
