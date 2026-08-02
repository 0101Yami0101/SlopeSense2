"""Assemble the interactive visualisation page.

Combines four inputs into one self-contained HTML file:
  viz/data/web.json      — raster values, vector paths, time-series frames
  viz/data/summary.json  — the numbers behind the charts
  viz/data/raw.json      — what is actually on disk, for the under-the-hood flip
  scripts/viz/layers.py  — the explanatory registry

The browser does all rendering, so the map pans, zooms, switches layers and
reads out values live. No external requests, no build step.

    python scripts/viz/extract.py      # figures + summary numbers
    python scripts/viz/extract_web.py  # interactive layer data
    python scripts/viz/extract_raw.py  # file listings, schemas, sample records
    python scripts/viz/build.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
from datetime import date

from common import ROOT
from layers import LAYERS, SECTIONS

VIZ = ROOT / "viz"
OUT = VIZ / "index.html"

# Which map layer each card highlights, so "Show on map" works
CARD_LAYER = {
    "terrain": "elevation", "slope": "slope", "soil": "soil_clay",
    "landcover": "landcover", "rivers": "rivers", "discharge": "discharge_peak",
    "rainfall": "rain_total", "soilmoisture": "soil_moisture",
    "era5": "era5_swvl1", "seismic": "earthquakes", "labels": "landslides",
    "population": "population", "osm": "roads", "boundaries": "districts",
}

GLOSSARY = [
    ("Susceptibility", "A map of <i>where</i> slopes are capable of failing, based on "
     "permanent properties — steepness, soil, rock, vegetation. Carries no date. "
     "Think of it as a map of loaded guns."),
    ("Trigger", "What pulls the trigger — usually rainfall, sometimes an earthquake. "
     "Changes hour to hour."),
    ("Prediction", "Susceptibility × trigger. A steep, clay-rich, deforested slope plus "
     "200 mm of rain in a day equals a warning. Either one alone does not."),
    ("Hazard vs risk", "Hazard is the physical event. Risk is hazard × who is in the "
     "way. A landslide in empty mountains is a hazard but not a risk."),
    ("DEM", "Digital Elevation Model — a grid of ground heights. Slope, aspect and "
     "curvature are all derived from it, not downloaded separately."),
    ("Aspect", "Which compass direction a slope faces. Controls sun exposure, moisture "
     "retention and snow behaviour."),
    ("Angle of repose", "The steepest angle loose material holds without sliding — "
     "roughly 30–35° for most soils. Above it, a slope is already near failure."),
    ("Pore water pressure", "Water filling gaps between soil grains pushes them apart, "
     "reducing the friction holding a slope together. The actual mechanism behind most "
     "rain-triggered landslides."),
    ("Antecedent rainfall", "How much rain has already fallen over previous days. Often "
     "a better predictor than today's rain, because it sets how saturated the ground is."),
    ("Upstream drainage area", "How much land drains into a point on a river, in km². "
     "Decides whether a river is large enough for a global forecast model to see."),
    ("Discharge", "Volume of water passing a point per second (m³/s). A small stream "
     "runs 1 m³/s; the Brahmaputra in flood exceeds 50,000."),
    ("SAR / radar", "Synthetic Aperture Radar. The satellite emits its own microwave "
     "pulses instead of relying on sunlight, so it works through cloud and at night."),
    ("InSAR", "Comparing the phase of radar waves between two passes to measure ground "
     "movement down to millimetres. Catches slow creep before a slope fails."),
    ("Relative orbit", "The repeating ground track a satellite follows. InSAR needs "
     "images from the same relative orbit or the viewing geometry does not match."),
    ("Reanalysis", "A physics model of the atmosphere run over history with observations "
     "fed in, producing a gap-free record of things nobody measured everywhere."),
    ("Lithology", "What kind of rock lies beneath. Controls how thick the loose surface "
     "layer is and how water moves through it."),
    ("Location accuracy", "How precisely a recorded event is positioned. '5 km' means the "
     "true spot is somewhere in a 5 km circle — hundreds of separate slopes."),
    ("Tier A / B / C", "How hard data is to obtain. A = open, no account. B = free account. "
     "C = human action: a waitlist, a portal, or a formal government request."),
]


def main() -> None:
    web = json.loads((VIZ / "data" / "web.json").read_text())
    summary = json.loads((VIZ / "data" / "summary.json").read_text())
    rawf = VIZ / "data" / "raw.json"
    raw = json.loads(rawf.read_text(encoding="utf-8")) if rawf.exists() else {}
    if not raw:
        print("  note: no raw.json — run scripts/viz/extract_raw.py for the "
              "under-the-hood view")

    payload = {
        "web": web,
        "summary": summary,
        "raw": raw,
        "layers": [dict(l, mapLayer=CARD_LAYER.get(l["id"])) for l in LAYERS],
        "sections": [{"id": i, "title": t, "blurb": b} for i, t, b in SECTIONS],
        "glossary": [{"term": t, "body": b} for t, b in GLOSSARY],
        "built": str(date.today()),
    }
    html = TEMPLATE.replace("/*__PAYLOAD__*/", json.dumps(payload))
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}  ({OUT.stat().st_size / 1e6:.2f} MB)")
    print(f"  cards {len(LAYERS)} · rasters {len(web['rasters'])} "
          f"· vectors {len(web['paths'])} · series {len(web['series'])} "
          f"· raw-backed cards {len(raw)}")


TEMPLATE = r"""<title>Arunachal Landslide &amp; Flood — Data Explorer</title>
<style>
:root{
  --bg:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --line:#e1e0d9; --rule:#c3c2b7; --ring:rgba(11,11,11,.10);
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s8:#e34948;
  --mapbg:#eceae4;
}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme=light])){
  --bg:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --line:#2c2c2a; --rule:#383835; --ring:rgba(255,255,255,.10);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s8:#e66767;
  --mapbg:#131313;
}}
:root[data-theme=dark]{
  --bg:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --line:#2c2c2a; --rule:#383835; --ring:rgba(255,255,255,.10);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s8:#e66767;
  --mapbg:#131313;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 96px}
h1,h2,h3{line-height:1.25;margin:0}
button{font-family:inherit}

header{padding:56px 0 34px;border-bottom:1px solid var(--line)}
h1{font-size:clamp(27px,4.2vw,42px);letter-spacing:-.02em}
.sub{color:var(--ink2);font-size:17px;max-width:66ch;margin-top:13px}
.meta{color:var(--muted);font-size:13px;margin-top:16px}

/* Tier comparison tables. Wide by nature, so they scroll inside their own
   container rather than forcing the page to scroll sideways on a phone. */
.tiertab{display:block;overflow-x:auto;white-space:nowrap;width:100%;
  border-collapse:collapse;margin:14px 0;font-size:13.5px}
.tiertab th,.tiertab td{border:1px solid var(--line);padding:9px 12px;
  text-align:left;vertical-align:top;white-space:normal;min-width:150px}
.tiertab th{background:var(--bg);color:var(--muted);font-weight:600;
  font-size:11.5px;letter-spacing:.06em;text-transform:uppercase}
.tiertab td:first-child{color:var(--ink);font-weight:600;min-width:120px}

.concept{background:var(--surface);border:1px solid var(--ring);border-radius:14px;padding:24px;margin:28px 0}
.eq{display:flex;flex-wrap:wrap;gap:11px;margin-top:16px}
.eq .box{flex:1 1 190px;border:1px solid var(--ring);border-radius:10px;padding:13px 15px;background:var(--bg)}
.eq .op{display:flex;align-items:center;font-size:24px;color:var(--muted)}
.eq b{display:block;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:5px}
.eq span{font-size:13.5px;color:var(--ink2)}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:11px;margin:24px 0}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:15px}
.tile .v{font-size:25px;font-weight:600;letter-spacing:-.02em}
.tile .k{font-size:12.5px;color:var(--muted);margin-top:2px}
.tile .n{font-size:12px;color:var(--ink2);margin-top:6px;line-height:1.45}

/* ================= map explorer ================= */
.explorer{background:var(--surface);border:1px solid var(--ring);border-radius:16px;
  overflow:hidden;margin:30px 0}
.exhead{padding:20px 22px 0}
.exhead h2{font-size:21px;letter-spacing:-.01em}
.exhead p{color:var(--ink2);font-size:14px;margin:7px 0 0;max-width:74ch}
.exbody{display:grid;grid-template-columns:236px 1fr;gap:0;margin-top:18px}
@media(max-width:820px){.exbody{grid-template-columns:1fr}}
.panel{border-right:1px solid var(--line);padding:16px 18px 20px;max-height:640px;overflow-y:auto}
@media(max-width:820px){.panel{border-right:none;border-bottom:1px solid var(--line);max-height:none}}
.plabel{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);
  margin:16px 0 7px}
.plabel:first-child{margin-top:0}
.panel>.legend2:first-child{margin-bottom:2px}
.opt{display:flex;align-items:center;gap:8px;font-size:13px;padding:4px 0;cursor:pointer;color:var(--ink2)}
.opt:hover{color:var(--ink)}
.opt input{accent-color:var(--s1);margin:0;flex:none}
.opt.on{color:var(--ink);font-weight:500}
.swatch{width:10px;height:10px;border-radius:3px;flex:none}
.stage{position:relative;background:var(--mapbg);aspect-ratio:2.05/1;min-height:420px}
canvas{display:block;width:100%;height:100%;cursor:grab;touch-action:none}
canvas.drag{cursor:grabbing}
.readout{position:absolute;left:14px;top:14px;background:color-mix(in srgb,var(--surface) 94%,transparent);
  border:1px solid var(--ring);border-radius:10px;padding:10px 13px;font-size:12.5px;
  pointer-events:none;min-width:190px;backdrop-filter:blur(6px)}
.readout .rv{font-size:19px;font-weight:600;letter-spacing:-.01em}
.readout .rk{color:var(--muted);font-size:11.5px;margin-top:1px}
.readout .rc{color:var(--ink2);font-size:11.5px;margin-top:7px;font-variant-numeric:tabular-nums}
.legend2{border:1px solid var(--ring);border-radius:10px;padding:11px 13px;font-size:11.5px;
  background:var(--bg)}
.ramp{width:100%;height:10px;border-radius:5px;margin:7px 0 4px}
.rlabels{display:flex;justify-content:space-between;color:var(--muted);font-variant-numeric:tabular-nums}
.zoombar{position:absolute;right:14px;top:14px;display:flex;flex-direction:column;gap:6px}
.zoombar button{width:32px;height:32px;border-radius:9px;border:1px solid var(--ring);
  background:color-mix(in srgb,var(--surface) 94%,transparent);color:var(--ink);
  font-size:16px;cursor:pointer;backdrop-filter:blur(6px);line-height:1}
.zoombar button:hover{border-color:var(--rule)}
.zoombar button.sm{font-size:10px}
.tip{position:absolute;background:var(--surface);border:1px solid var(--ring);border-radius:9px;
  padding:8px 11px;font-size:12px;pointer-events:none;opacity:0;transition:opacity .1s;
  max-width:230px;box-shadow:0 4px 14px rgba(0,0,0,.12);z-index:5}
.scrub{display:flex;align-items:center;gap:12px;padding:13px 18px;border-top:1px solid var(--line);
  flex-wrap:wrap}
.scrub button{border:1px solid var(--ring);background:var(--bg);color:var(--ink);border-radius:9px;
  padding:6px 13px;font-size:13px;cursor:pointer}
.scrub button:hover{border-color:var(--rule)}
.scrub input[type=range]{flex:1;min-width:180px;accent-color:var(--s1)}
.scrub .day{font-size:13px;color:var(--ink2);font-variant-numeric:tabular-nums;min-width:150px}
.slider{width:100%;accent-color:var(--s1)}

/* ================= sections ================= */
nav{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 92%,transparent);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:11px 0;
  display:flex;gap:7px;flex-wrap:wrap;margin-top:28px}
nav a{font-size:13px;color:var(--ink2);text-decoration:none;padding:5px 11px;
  border:1px solid var(--ring);border-radius:99px}
nav a:hover{color:var(--ink);border-color:var(--rule)}
section{padding-top:50px}
.sechead{border-left:3px solid var(--s1);padding-left:14px;margin-bottom:6px}
.sechead h2{font-size:23px;letter-spacing:-.01em}
.sechead p{color:var(--ink2);margin:6px 0 0;max-width:70ch;font-size:14.5px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:14px;padding:24px;margin-top:20px}
.chead{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;align-items:baseline}
.chead h3{font-size:19px;letter-spacing:-.01em}
.tier{font-size:11.5px;color:var(--muted);border:1px solid var(--ring);border-radius:99px;
  padding:3px 10px;white-space:nowrap}
.src{font-size:12.5px;color:var(--muted);margin:3px 0 15px}
.prose{font-size:14.5px;color:var(--ink2);max-width:76ch}
.prose h4{font-size:11.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin:17px 0 6px}
.prose ul{margin:8px 0;padding-left:20px}
.prose li{margin:5px 0}
.prose b{color:var(--ink);font-weight:600}
.showmap{margin-top:16px;border:1px solid var(--ring);background:var(--bg);color:var(--s1);
  border-radius:9px;padding:7px 14px;font-size:13px;cursor:pointer}
.showmap:hover{border-color:var(--s1)}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(138px,1fr));gap:9px;margin-top:17px}
.fact{border:1px solid var(--ring);border-radius:9px;padding:10px 12px;background:var(--bg)}
.fact .fv{font-size:16px;font-weight:600}
.fact .fk{font-size:11.5px;color:var(--muted);margin-top:2px}

.chart{margin-top:20px}
.chart .ct{font-size:13.5px;font-weight:600}
.chart .cs{font-size:12.5px;color:var(--muted);margin:2px 0 11px}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.ax{fill:var(--muted);font-size:10.5px}
.vl{fill:var(--ink2);font-size:11px;font-variant-numeric:tabular-nums}
.gl{stroke:var(--line);stroke-width:1}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:9px;font-size:12px;color:var(--ink2)}
.legend i{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:5px;vertical-align:-1px}
.tbtn{margin-top:10px;font-size:12px;color:var(--muted);background:none;border:1px solid var(--ring);
  border-radius:7px;padding:4px 10px;cursor:pointer}
.tbtn:hover{color:var(--ink)}
table.tv{width:100%;border-collapse:collapse;margin-top:9px;font-size:12.5px;font-variant-numeric:tabular-nums}
table.tv th,table.tv td{text-align:left;padding:5px 9px;border-bottom:1px solid var(--line)}
table.tv th{color:var(--muted);font-weight:500}
.scroll{overflow-x:auto}

/* ============ under-the-hood flip ============
   Every card has two faces: the explanation, and the bytes it was written
   from. The switch swaps between them; the global one in the nav does all
   cards at once. */
.flip{display:inline-flex;align-items:center;gap:7px;cursor:pointer;user-select:none;
  font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);
  border:1px solid var(--ring);border-radius:99px;padding:4px 11px 4px 8px;
  background:var(--bg);white-space:nowrap}
.flip:hover{color:var(--ink);border-color:var(--rule)}
.flip .track{width:26px;height:14px;border-radius:99px;background:var(--rule);
  position:relative;flex:none;transition:background .15s}
.flip .track::after{content:"";position:absolute;top:2px;left:2px;width:10px;height:10px;
  border-radius:99px;background:var(--surface);transition:transform .15s}
.flip.on{color:var(--ink);border-color:var(--s1)}
.flip.on .track{background:var(--s1)}
.flip.on .track::after{transform:translateX(12px)}
nav .flip{margin-left:auto}

.rawpane{margin-top:4px}
.rawnote{font-size:12.5px;color:var(--muted);margin-bottom:16px;max-width:74ch}
.rawblk{border:1px solid var(--line);border-radius:11px;margin-top:13px;overflow:hidden}
.rawblk>summary{cursor:pointer;padding:10px 14px;background:var(--bg);font-size:13px;
  display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;list-style:none}
.rawblk>summary::-webkit-details-marker{display:none}
.rawblk>summary::before{content:"▸";color:var(--muted);font-size:11px}
.rawblk[open]>summary::before{content:"▾"}
.rawblk>summary b{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;font-weight:500}
.rawblk>summary .dim{color:var(--muted);font-size:11.5px;margin-left:auto}
.rawbody{padding:13px 14px 15px;border-top:1px solid var(--line)}
.rawcap{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);
  margin:15px 0 6px}
.rawcap:first-child{margin-top:0}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:3px 18px}
.kv div{font-size:12.5px;display:flex;gap:8px;border-bottom:1px solid var(--line);padding:4px 0}
.kv div span:first-child{color:var(--muted);flex:none;min-width:88px}
.kv div span:last-child{font-family:ui-monospace,Menlo,monospace;font-size:12px;
  word-break:break-word}
table.rawt{border-collapse:collapse;font-size:12px;
  font-family:ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums}
table.rawt th,table.rawt td{border:1px solid var(--line);padding:4px 9px;text-align:left;
  white-space:nowrap;max-width:260px;overflow:hidden;text-overflow:ellipsis}
table.rawt th{background:var(--bg);color:var(--muted);font-weight:500;
  position:sticky;top:0}
table.rawt td.num{text-align:right}
table.rawt tr:nth-child(even) td{background:color-mix(in srgb,var(--bg) 45%,transparent)}
.rawpre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:11px 13px;
  overflow-x:auto;font-family:ui-monospace,Menlo,monospace;font-size:11.5px;line-height:1.55;
  margin:0;white-space:pre;color:var(--ink2)}
.rawurl{word-break:break-all;white-space:pre-wrap}
.gloss{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:13px;margin-top:18px}
.gitem{background:var(--surface);border:1px solid var(--ring);border-radius:11px;padding:15px 17px}
.gitem dt{font-weight:600;font-size:14px;margin-bottom:4px}
.gitem dd{margin:0;font-size:13.5px;color:var(--ink2);line-height:1.55}
footer{margin-top:60px;padding-top:24px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
code{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;background:var(--bg);
  border:1px solid var(--ring);border-radius:5px;padding:1px 5px}
pre{background:var(--bg);border:1px solid var(--ring);border-radius:10px;padding:15px;
  overflow-x:auto;font-size:12.5px;line-height:1.6}
pre code{background:none;border:none;padding:0}
</style>

<div class="wrap">
<header>
  <h1>What data we actually have</h1>
  <p class="sub">An explorable tour of every dataset gathered for the Arunachal Pradesh
  landslide and flood prediction system. Pan and zoom the map, switch layers, hover to
  read real values. No modelling — just the raw material, explained.</p>
  <p class="sub" style="font-size:15px">Every card has two faces. Flip the
  <b>Under the hood</b> switch — in the nav bar, or on any single card — to replace the
  explanation with the bytes it was written from: the files on disk, the request that
  fetched them, the real column names, and untouched rows straight off the file.</p>
  <p class="meta" id="meta"></p>
</header>

<div class="concept">
  <h2 style="font-size:19px">The one idea everything hangs on</h2>
  <p class="prose" style="margin-top:9px">Predicting a landslide takes two separate
  things, and confusing them is the most common mistake in this field. One is permanent
  and answers <b>where</b>. The other changes by the hour and answers <b>when</b>.</p>
  <div class="eq">
    <div class="box"><b>Susceptibility</b><span>Where slopes <i>can</i> fail. Steepness,
    soil, rock, vegetation. No date on it.</span></div>
    <div class="op">×</div>
    <div class="box"><b>Trigger</b><span>What sets it off. Rain, already-saturated
    ground, sometimes an earthquake.</span></div>
    <div class="op">=</div>
    <div class="box"><b>Prediction</b><span>A steep wet clay slope <i>and</i> 200 mm of
    rain today. Either alone is not a warning.</span></div>
  </div>
</div>

<div class="tiles" id="tiles"></div>

<!-- ==================== interactive explorer ==================== -->
<div class="explorer" id="explorer">
  <div class="exhead">
    <h2>Map explorer</h2>
    <p>Every layer below is real data, not a picture — the colours are computed in your
    browser. <b>Drag to pan, scroll to zoom, hover to read the value under the cursor.</b></p>
  </div>
  <div class="exbody">
    <div class="panel">
      <div class="legend2" id="legend2"></div>
      <div class="plabel">Opacity</div>
      <input type="range" class="slider" id="opacity" min="0" max="100" value="100">
      <div class="plabel">Base layer</div>
      <div id="baseOpts"></div>
      <div class="plabel">Overlays</div>
      <div id="overOpts"></div>
    </div>
    <div class="stage" id="stage">
      <canvas id="map"></canvas>
      <div class="readout" id="readout"></div>
      <div class="zoombar">
        <button id="zin" title="Zoom in">+</button>
        <button id="zout" title="Zoom out">−</button>
        <button id="zreset" class="sm" title="Reset view">⤢</button>
      </div>
      <div class="tip" id="tip"></div>
    </div>
  </div>
  <div class="scrub" id="scrub">
    <button id="play">▶ Play monsoon</button>
    <input type="range" id="frame" min="0" max="0" value="0">
    <span class="day" id="dayLabel">Static layer</span>
    <select id="seriesSel" style="font:inherit;font-size:13px;padding:5px 9px;border-radius:8px;
      border:1px solid var(--ring);background:var(--bg);color:var(--ink)"></select>
  </div>
</div>

<nav id="nav"></nav>
<main id="main"></main>

<section id="inventory">
  <div class="sechead"><h2>Complete inventory</h2>
  <p>Every dataset on disk, with the facts that decide whether it is usable.</p></div>
  <div class="card"><div class="scroll"><table class="tv" id="inv"></table></div></div>
</section>

<section id="glossary">
  <div class="sechead"><h2>Glossary</h2>
  <p>The geology and remote-sensing vocabulary the source documents assume you know.</p></div>
  <div class="gloss" id="gloss"></div>
</section>

<section id="extend">
  <div class="sechead"><h2>Adding new data</h2>
  <p>The page is generated. New datasets plug in without touching the layout.</p></div>
  <div class="card"><div class="prose">
    <ul>
      <li><code>scripts/viz/extract_web.py</code> — exports raster values, vector paths and
      time-series frames for the map</li>
      <li><code>scripts/viz/extract.py</code> — chart numbers into <code>summary.json</code></li>
      <li><code>scripts/viz/layers.py</code> — the card registry: title, explanation, facts</li>
      <li><code>scripts/viz/build.py</code> — assembles this file</li>
    </ul>
    <pre><code># add a map layer  (extract_web.py)
quantise(to_grid(arr, transform, crs), "my_layer",
         "My Layer", "unit", "heat", "One line on what it shows.")

# add a card  (layers.py)
dict(id="mydata", section="triggers", title="My new dataset",
     source="Where from", tier="Tier B - free account",
     what="Plain English: what this is.",
     why="Why it matters for landslides or floods.",
     facts=[("Resolution","10 m")], charts=[])

# link card to map layer  (build.py CARD_LAYER)
"mydata": "my_layer"

python scripts/viz/extract_web.py &amp;&amp; python scripts/viz/build.py</code></pre>
    <p>Palettes available: <code>terrain heat soil rain water wet pop cyclic</code>.
    Add more in the <code>PALETTES</code> object in this page's script.</p>
  </div></div>
</section>

<footer>
  <p>All values read from the files in <code>data/raw/</code>. Companion docs:
  <code>docs/data_research/DATA_VERIFICATION.md</code> for source status,
  <code>data/README.md</code> for folder conventions.</p>
</footer>
</div>

<script>
const P = /*__PAYLOAD__*/;
const WEB = P.web, S = P.summary;
const $=(t,a={},...k)=>{const e=document.createElement(t);
  for(const[n,v]of Object.entries(a)){if(n==="html")e.innerHTML=v;else e.setAttribute(n,v);}
  k.flat().forEach(c=>e.append(c));return e;};
const fmt=n=>Math.abs(n)>=1e6?(n/1e6).toFixed(2)+"M":Math.abs(n)>=1000?Math.round(n).toLocaleString()
  :Math.abs(n)>=10?n.toFixed(0):n.toFixed(2);
const b64=s=>{const b=atob(s),a=new Uint8Array(b.length);
  for(let i=0;i<b.length;i++)a[i]=b.charCodeAt(i);return a;};

/* ============================== palettes ============================== */
const PALETTES={
  terrain:[[38,92,64],[104,150,74],[196,192,110],[176,138,88],[140,110,96],[240,240,242]],
  heat:[[255,255,204],[254,217,118],[253,141,60],[227,74,51],[153,0,13]],
  soil:[[247,244,236],[214,196,146],[176,148,92],[126,98,58],[74,54,28]],
  rain:[[247,251,255],[198,219,239],[107,174,214],[33,113,181],[8,48,107]],
  water:[[237,248,251],[179,205,227],[103,169,207],[28,108,177],[8,44,92]],
  wet:[[255,255,229],[199,233,180],[102,194,164],[44,127,127],[13,60,80]],
  pop:[[255,247,243],[252,197,192],[247,104,161],[174,1,126],[73,0,106]],
  cyclic:[[220,80,80],[220,200,80],[80,200,100],[80,160,220],[160,90,220],[220,80,80]]
};
function ramp(name){
  const st=PALETTES[name]||PALETTES.heat, out=new Uint8Array(256*3);
  for(let i=0;i<256;i++){
    const t=i/255*(st.length-1), k=Math.min(Math.floor(t),st.length-2), f=t-k;
    for(let c=0;c<3;c++) out[i*3+c]=st[k][c]+(st[k+1][c]-st[k][c])*f;
  }
  return out;
}
const RAMPS={};for(const k in PALETTES)RAMPS[k]=ramp(k);
function cssRamp(name){
  const st=PALETTES[name]||PALETTES.heat;
  return "linear-gradient(90deg,"+st.map(c=>`rgb(${c[0]},${c[1]},${c[2]})`).join(",")+")";
}

/* ============================ decode layers ============================ */
const [BW,BH]=WEB.grid, [MW,MS,ME,MN]=WEB.bbox;
const RAS={};
for(const [k,v] of Object.entries(WEB.rasters)) RAS[k]={...v,arr:b64(v.data),kind:"ras"};
for(const [k,v] of Object.entries(WEB.categorical)) RAS[k]={...v,arr:b64(v.data),kind:"cat"};
const SERIES={};
for(const [k,v] of Object.entries(WEB.series)){
  const a=b64(v.data), n=v.dates.length, per=v.w*v.h;
  SERIES[k]={...v,frames:Array.from({length:n},(_,i)=>a.subarray(i*per,(i+1)*per))};
}
const PATHS={};
for(const [k,v] of Object.entries(WEB.paths)) PATHS[k]={...v,p2d:new Path2D(v.d)};

/* build an offscreen image for a raster layer */
const imgCache={};
function rasterImage(key,frameIdx){
  const ck=key+"|"+(frameIdx??"-");
  if(imgCache[ck])return imgCache[ck];
  let w,h,arr,lut,classes=null;
  if(SERIES[key]&&frameIdx!=null){
    const s=SERIES[key];w=s.w;h=s.h;arr=s.frames[frameIdx];lut=RAMPS[s.palette]||RAMPS.rain;
  }else{
    const r=RAS[key];if(!r)return null;
    w=BW;h=BH;arr=r.arr;
    if(r.kind==="cat")classes=r.classes; else lut=RAMPS[r.palette]||RAMPS.heat;
  }
  const cv=document.createElement("canvas");cv.width=w;cv.height=h;
  const ctx=cv.getContext("2d"), im=ctx.createImageData(w,h), d=im.data;
  if(classes){
    const map={};for(const c in classes){const h2=classes[c].color;
      map[c]=[parseInt(h2.slice(1,3),16),parseInt(h2.slice(3,5),16),parseInt(h2.slice(5,7),16)];}
    for(let i=0;i<arr.length;i++){const c=map[arr[i]];
      if(c){d[i*4]=c[0];d[i*4+1]=c[1];d[i*4+2]=c[2];d[i*4+3]=255;}else d[i*4+3]=0;}
  }else{
    for(let i=0;i<arr.length;i++){const v=arr[i];
      if(v===0){d[i*4+3]=0;continue;}
      d[i*4]=lut[v*3];d[i*4+1]=lut[v*3+1];d[i*4+2]=lut[v*3+2];d[i*4+3]=255;}
  }
  ctx.putImageData(im,0,0);
  imgCache[ck]=cv;return cv;
}

/* ============================== map state ============================== */
const cv=document.getElementById("map"), ctx=cv.getContext("2d");
const stage=document.getElementById("stage");
const view={zoom:1,cx:(MW+ME)/2,cy:(MS+MN)/2};
let baseLayer="elevation", opacity=1, activeSeries=null, frameIdx=0;
const overlays={state:true,districts:false,rivers_large:true,rivers_mid:false,
  rivers_small:false,roads:false,landslides:false,earthquakes:false};

function sizeCanvas(){
  const r=stage.getBoundingClientRect(), dpr=window.devicePixelRatio||1;
  cv.width=Math.max(1,r.width*dpr);cv.height=Math.max(1,r.height*dpr);
  cv.style.width=r.width+"px";cv.style.height=r.height+"px";
  ctx.setTransform(dpr,0,0,dpr,0,0);draw();
}
function scale(){                      // px per degree
  const r=stage.getBoundingClientRect();
  return Math.min(r.width/(ME-MW), r.height/(MN-MS))*view.zoom;
}
function toScreen(lon,lat){
  const r=stage.getBoundingClientRect(),k=scale();
  return [r.width/2+(lon-view.cx)*k, r.height/2-(lat-view.cy)*k];
}
function toData(px,py){
  const r=stage.getBoundingClientRect(),k=scale();
  return [view.cx+(px-r.width/2)/k, view.cy-(py-r.height/2)/k];
}

function draw(){
  const r=stage.getBoundingClientRect();
  ctx.clearRect(0,0,r.width,r.height);
  const k=scale();
  const [x0,y0]=toScreen(MW,MN), [x1,y1]=toScreen(ME,MS);

  const img=activeSeries?rasterImage(activeSeries,frameIdx):rasterImage(baseLayer,null);
  if(img){
    ctx.globalAlpha=opacity;
    ctx.imageSmoothingEnabled=(k<60);
    ctx.drawImage(img,x0,y0,x1-x0,y1-y0);
    ctx.globalAlpha=1;
  }

  ctx.save();
  ctx.translate(...toScreen(0,0));ctx.scale(k,-k);
  for(const key of ["rivers_small","rivers_mid","rivers_large","roads","districts","state"]){
    if(!overlays[key]||!PATHS[key])continue;
    const L=PATHS[key];
    ctx.strokeStyle=L.color;ctx.lineWidth=L.width/k;ctx.lineJoin="round";ctx.lineCap="round";
    ctx.stroke(L.p2d);
  }
  ctx.restore();

  for(const key of ["earthquakes","landslides"]){
    if(!overlays[key]||!WEB.points[key])continue;
    const L=WEB.points[key];
    ctx.fillStyle=L.color;ctx.strokeStyle="rgba(255,255,255,.85)";ctx.lineWidth=1.2;
    for(const it of L.items){
      const [sx,sy]=toScreen(it.x,it.y);
      if(sx<-20||sy<-20||sx>r.width+20||sy>r.height+20)continue;
      const rad=key==="earthquakes"?Math.max(2,(it.m-3.4)*1.7):4.4;
      ctx.beginPath();ctx.arc(sx,sy,rad,0,6.284);ctx.fill();
      if(key==="landslides")ctx.stroke();
    }
  }
}

/* -------- value readout under the cursor -------- */
const readout=document.getElementById("readout"), tip=document.getElementById("tip");
function valueAt(lon,lat){
  const src=activeSeries?SERIES[activeSeries]:RAS[baseLayer];
  if(!src)return null;
  const w=activeSeries?src.w:BW, h=activeSeries?src.h:BH;
  const arr=activeSeries?src.frames[frameIdx]:src.arr;
  const ix=Math.floor((lon-MW)/(ME-MW)*w), iy=Math.floor((MN-lat)/(MN-MS)*h);
  if(ix<0||iy<0||ix>=w||iy>=h)return null;
  const q=arr[iy*w+ix];
  if(q===0)return {none:true};
  if(!activeSeries&&RAS[baseLayer].kind==="cat"){
    const c=RAS[baseLayer].classes[q];
    return c?{text:c.name,color:c.color}:{none:true};
  }
  let f=(q-1)/254;
  if(src.gamma)f=Math.pow(f,src.gamma);
  let v=src.min+f*(src.max-src.min);
  if(src.log)v=Math.pow(10,v)-1;
  return {value:v,unit:src.unit,label:src.label};
}
function updateReadout(lon,lat){
  const r=valueAt(lon,lat);
  let inner="";
  if(!r||r.none){inner=`<div class="rv" style="color:var(--muted)">no data</div>
    <div class="rk">${activeSeries?SERIES[activeSeries].label:(RAS[baseLayer]?.label||"")}</div>`;}
  else if(r.text){inner=`<div class="rv">${r.text}</div><div class="rk">Land cover class</div>`;}
  else{inner=`<div class="rv">${fmt(r.value)} <span style="font-size:13px;color:var(--muted)">${r.unit||""}</span></div>
    <div class="rk">${r.label}</div>`;}
  inner+=`<div class="rc">${lat.toFixed(3)}°N &nbsp; ${lon.toFixed(3)}°E</div>`;
  readout.innerHTML=inner;
}
function nearestPoint(px,py){
  let best=null,bd=15;
  for(const key of ["landslides","earthquakes"]){
    if(!overlays[key]||!WEB.points[key])continue;
    for(const it of WEB.points[key].items){
      const [sx,sy]=toScreen(it.x,it.y);
      const d=Math.hypot(sx-px,sy-py);
      if(d<bd){bd=d;best={key,it};}
    }
  }
  return best;
}

/* -------- interaction -------- */
let dragging=false,last=null;
cv.addEventListener("mousedown",e=>{dragging=true;last=[e.offsetX,e.offsetY];cv.classList.add("drag");});
window.addEventListener("mouseup",()=>{dragging=false;cv.classList.remove("drag");});
cv.addEventListener("mousemove",e=>{
  const px=e.offsetX,py=e.offsetY;
  if(dragging&&last){
    const k=scale();
    view.cx-=(px-last[0])/k;view.cy+=(py-last[1])/k;last=[px,py];draw();
  }
  const [lon,lat]=toData(px,py);
  updateReadout(lon,lat);
  const np=nearestPoint(px,py);
  if(np){
    const it=np.it;
    tip.innerHTML=np.key==="landslides"
      ? `<b>Landslide</b><br>${it.t}<br>accuracy: ${it.a}<br>trigger: ${it.g}<br>size: ${it.s}`
      : `<b>Earthquake M${it.m}</b><br>${it.t}`;
    tip.style.left=Math.min(px+14,stage.clientWidth-240)+"px";
    tip.style.top=(py+14)+"px";tip.style.opacity=1;
  } else tip.style.opacity=0;
});
cv.addEventListener("mouseleave",()=>{tip.style.opacity=0;});
cv.addEventListener("wheel",e=>{
  e.preventDefault();
  const [lon,lat]=toData(e.offsetX,e.offsetY);
  const f=e.deltaY<0?1.18:1/1.18;
  view.zoom=Math.max(1,Math.min(60,view.zoom*f));
  const [nl,na]=toData(e.offsetX,e.offsetY);
  view.cx+=lon-nl;view.cy+=lat-na;draw();
},{passive:false});
document.getElementById("zin").onclick=()=>{view.zoom=Math.min(60,view.zoom*1.4);draw();};
document.getElementById("zout").onclick=()=>{view.zoom=Math.max(1,view.zoom/1.4);draw();};
document.getElementById("zreset").onclick=()=>{
  view.zoom=1;view.cx=(MW+ME)/2;view.cy=(MS+MN)/2;draw();};

/* -------- legend -------- */
function updateLegend(){
  const el=document.getElementById("legend2");
  if(activeSeries){
    const s=SERIES[activeSeries];
    el.innerHTML=`<div style="font-weight:600">${s.label}</div>
      <div class="ramp" style="background:${cssRamp(s.palette)}"></div>
      <div class="rlabels"><span>0</span><span>${fmt(s.max)} ${s.unit}</span></div>`;
    return;
  }
  const r=RAS[baseLayer];if(!r){el.innerHTML="";return;}
  if(r.kind==="cat"){
    el.innerHTML=`<div style="font-weight:600;margin-bottom:6px">${r.label}</div>`+
      Object.values(r.classes).map(c=>
        `<div style="display:flex;gap:6px;align-items:center;margin:2px 0">
        <span class="swatch" style="background:${c.color}"></span>${c.name}</div>`).join("");
    return;
  }
  el.innerHTML=`<div style="font-weight:600">${r.label}</div>
    <div class="ramp" style="background:${cssRamp(r.palette)}"></div>
    <div class="rlabels"><span>${fmt(r.min)}</span><span>${fmt(r.max)} ${r.unit}</span></div>`;
}

/* -------- controls -------- */
const baseOpts=document.getElementById("baseOpts");
const GROUPS=[["Terrain",["elevation","slope","aspect"]],
  ["Surface",["landcover","population"]],
  ["Soil",["soil_clay","soil_sand","soil_silt","soil_soc","soil_bdod","soil_cfvo"]],
  ["Water & weather",["rain_total","discharge_peak","soil_moisture","era5_swvl1","era5_smlt"]]];
GROUPS.forEach(([title,keys])=>{
  const avail=keys.filter(k=>RAS[k]);if(!avail.length)return;
  baseOpts.append($("div",{class:"plabel"},title));
  avail.forEach(k=>{
    const id="b_"+k;
    const lab=$("label",{class:"opt"+(k===baseLayer?" on":""),id:"lab_"+id});
    const inp=$("input",{type:"radio",name:"base",id});
    if(k===baseLayer)inp.setAttribute("checked","");
    inp.onchange=()=>{baseLayer=k;activeSeries=null;
      document.querySelectorAll("#baseOpts .opt").forEach(o=>o.classList.remove("on"));
      lab.classList.add("on");
      document.getElementById("seriesSel").value="";
      document.getElementById("dayLabel").textContent="Static layer";
      updateLegend();draw();};
    lab.append(inp,document.createTextNode(RAS[k].label));
    baseOpts.append(lab);
  });
});
const overOpts=document.getElementById("overOpts");
[["state","State boundary"],["districts","Districts"],
 ["rivers_large","Rivers > 5,000 km²"],["rivers_mid","Rivers 500–5,000 km²"],
 ["rivers_small","Small streams"],["roads","Major roads"],
 ["landslides","Landslide records"],["earthquakes","Earthquakes M4+"]]
.forEach(([k,label])=>{
  if(!PATHS[k]&&!WEB.points[k])return;
  const lab=$("label",{class:"opt"+(overlays[k]?" on":"")});
  const inp=$("input",{type:"checkbox"});
  if(overlays[k])inp.setAttribute("checked","");
  inp.onchange=()=>{overlays[k]=inp.checked;lab.classList.toggle("on",inp.checked);draw();};
  const col=(PATHS[k]||WEB.points[k]).color;
  lab.append(inp,$("span",{class:"swatch",style:`background:${col}`}),
    document.createTextNode(label));
  overOpts.append(lab);
});
document.getElementById("opacity").oninput=e=>{opacity=e.target.value/100;draw();};

/* -------- time scrubber -------- */
const sel=document.getElementById("seriesSel"), fr=document.getElementById("frame"),
      dayLabel=document.getElementById("dayLabel"), playBtn=document.getElementById("play");
sel.append($("option",{value:""},"— static layers —"));
Object.entries(SERIES).forEach(([k,v])=>sel.append($("option",{value:k},v.label)));
function setSeries(k){
  activeSeries=k||null;
  if(activeSeries){
    const s=SERIES[activeSeries];
    fr.max=s.dates.length-1;fr.value=frameIdx=0;
    dayLabel.textContent=s.dates[0];
    document.querySelectorAll("#baseOpts .opt").forEach(o=>o.classList.remove("on"));
  }else{dayLabel.textContent="Static layer";stopPlay();}
  updateLegend();draw();
}
sel.onchange=()=>setSeries(sel.value);
fr.oninput=()=>{if(!activeSeries)return;frameIdx=+fr.value;
  dayLabel.textContent=SERIES[activeSeries].dates[frameIdx];draw();};
let timer=null;
function stopPlay(){if(timer){clearInterval(timer);timer=null;playBtn.textContent="▶ Play monsoon";}}
playBtn.onclick=()=>{
  if(timer){stopPlay();return;}
  if(!activeSeries){sel.value=Object.keys(SERIES)[0];setSeries(sel.value);}
  playBtn.textContent="⏸ Pause";
  timer=setInterval(()=>{
    const s=SERIES[activeSeries];frameIdx=(frameIdx+1)%s.dates.length;
    fr.value=frameIdx;dayLabel.textContent=s.dates[frameIdx];draw();
  },110);
};

window.addEventListener("resize",sizeCanvas);
readout.innerHTML='<div class="rv" style="font-size:14px;color:var(--muted)">Hover the map</div>'+
  '<div class="rk">to read the value under your cursor</div>';
updateLegend();sizeCanvas();

/* ============================== charts ============================== */
const SVGNS="http://www.w3.org/2000/svg";
const el=(t,a={})=>{const e=document.createElementNS(SVGNS,t);
  for(const[k,v]of Object.entries(a))e.setAttribute(k,v);return e;};
function frame2(title,sub,svg,tableFn){
  const d=$("div",{class:"chart"});
  if(title)d.append($("div",{class:"ct"},title));
  if(sub)d.append($("div",{class:"cs"},sub));
  d.append(svg);
  if(tableFn){
    const btn=$("button",{class:"tbtn"},"Show numbers");
    const wrap=$("div",{class:"scroll"});wrap.style.display="none";wrap.append(tableFn());
    btn.onclick=()=>{const on=wrap.style.display==="none";
      wrap.style.display=on?"block":"none";btn.textContent=on?"Hide numbers":"Show numbers";};
    d.append(btn,wrap);
  }
  return d;
}
function table(head,rows){
  const t=$("table",{class:"tv"});
  t.append($("tr",{},...head.map(h=>$("th",{},h))));
  rows.forEach(r=>t.append($("tr",{},...r.map(c=>$("td",{},String(c))))));
  return t;
}
function hbar(items,{unit="",color="var(--s1)",w=760}={}){
  const rowH=26,padL=Math.min(190,Math.max(...items.map(i=>i.label.length))*7.2+10),padR=70;
  const h=items.length*rowH+6, svg=el("svg",{viewBox:`0 0 ${w} ${h}`,role:"img"});
  const max=Math.max(...items.map(i=>i.value))||1, bw=w-padL-padR;
  items.forEach((it,i)=>{
    const y=i*rowH+4, len=Math.max(2,bw*it.value/max);
    svg.append(el("rect",{x:padL,y:y+4,width:len,height:13,rx:4,fill:it.color||color}));
    const lb=el("text",{x:padL-9,y:y+15,"text-anchor":"end",class:"ax"});lb.textContent=it.label;
    const vl=el("text",{x:padL+len+8,y:y+15,class:"vl"});
    vl.textContent=(it.display!==undefined?it.display:fmt(it.value))+unit;
    svg.append(lb,vl);
  });
  return svg;
}
function histogram(counts,edges,{unit="",color="var(--s1)",w=760,h=190,every=3}={}){
  const padL=52,padB=26,padT=8, svg=el("svg",{viewBox:`0 0 ${w} ${h}`,role:"img"});
  const max=Math.max(...counts)||1, bw=(w-padL-10)/counts.length;
  [0,.5,1].forEach(f=>{const y=padT+(h-padT-padB)*(1-f);
    svg.append(el("line",{x1:padL,x2:w-10,y1:y,y2:y,class:"gl"}));
    const t=el("text",{x:padL-8,y:y+4,"text-anchor":"end",class:"ax"});
    t.textContent=f===0?"0":fmt(max*f);svg.append(t);});
  counts.forEach((c,i)=>{
    const bh=(h-padT-padB)*c/max;
    svg.append(el("rect",{x:padL+i*bw+1,y:h-padB-bh,width:Math.max(1,bw-2),
      height:Math.max(0,bh),rx:3,fill:color}));
    if(i%every===0){const t=el("text",{x:padL+i*bw+bw/2,y:h-padB+15,
      "text-anchor":"middle",class:"ax"});t.textContent=Math.round(edges[i])+unit;svg.append(t);}
  });
  return svg;
}
function line(series,labels,{w=760,h=200,unit="",colors=["var(--s1)"],fill=false}={}){
  const padL=54,padB=26,padT=10,padR=10, svg=el("svg",{viewBox:`0 0 ${w} ${h}`,role:"img"});
  const all=series.flat(), max=Math.max(...all)||1, min=Math.min(0,...all);
  const X=i=>padL+(w-padL-padR)*i/Math.max(1,labels.length-1);
  const Y=v=>padT+(h-padT-padB)*(1-(v-min)/(max-min||1));
  [0,.5,1].forEach(f=>{const y=padT+(h-padT-padB)*(1-f);
    svg.append(el("line",{x1:padL,x2:w-padR,y1:y,y2:y,class:"gl"}));
    const t=el("text",{x:padL-8,y:y+4,"text-anchor":"end",class:"ax"});
    t.textContent=fmt(min+(max-min)*f);svg.append(t);});
  series.forEach((s,si)=>{
    const d=s.map((v,i)=>`${i?"L":"M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join("");
    if(fill)svg.append(el("path",{d:d+`L${X(s.length-1)},${Y(min)}L${X(0)},${Y(min)}Z`,
      fill:colors[si],opacity:.13,stroke:"none"}));
    svg.append(el("path",{d,fill:"none",stroke:colors[si],"stroke-width":2,"stroke-linejoin":"round"}));
  });
  const step=Math.ceil(labels.length/6);
  labels.forEach((lb,i)=>{if(i%step)return;
    const t=el("text",{x:X(i),y:h-padB+15,"text-anchor":"middle",class:"ax"});
    t.textContent=lb;svg.append(t);});
  const vline=el("line",{y1:padT,y2:h-padB,stroke:"var(--rule)","stroke-width":1,opacity:0});
  const dot=el("circle",{r:4,fill:colors[0],stroke:"var(--surface)","stroke-width":2,opacity:0});
  const lbl=el("text",{class:"vl",opacity:0});
  svg.append(vline,dot,lbl);
  const hit=el("rect",{x:padL,y:padT,width:w-padL-padR,height:h-padT-padB,
    fill:"transparent",style:"cursor:crosshair"});
  hit.addEventListener("mousemove",ev=>{
    const bb=svg.getBoundingClientRect(), rel=(ev.clientX-bb.left)/bb.width*w;
    const i=Math.round((rel-padL)/(w-padL-padR)*(labels.length-1));
    if(i<0||i>=labels.length)return;
    vline.setAttribute("x1",X(i));vline.setAttribute("x2",X(i));vline.setAttribute("opacity",1);
    dot.setAttribute("cx",X(i));dot.setAttribute("cy",Y(series[0][i]));dot.setAttribute("opacity",1);
    lbl.setAttribute("x",Math.min(X(i)+8,w-95));
    lbl.setAttribute("y",Math.max(padT+12,Y(series[0][i])-9));lbl.setAttribute("opacity",1);
    lbl.textContent=`${labels[i]}: ${series[0][i]}${unit}`;
  });
  hit.addEventListener("mouseleave",()=>[vline,dot,lbl].forEach(n=>n.setAttribute("opacity",0)));
  svg.append(hit);
  return svg;
}
function legend(items){
  const d=$("div",{class:"legend"});
  items.forEach(it=>{const s=$("span",{});
    s.append($("i",{style:`background:${it.color}`}),document.createTextNode(it.label));d.append(s);});
  return d;
}
const CHARTS={
  elev_hist(){const t=S.terrain;if(!t)return null;
    return frame2("How much land sits at each altitude","Most of the state is low-to-mid, but it reaches 7,140 m.",
      histogram(t.elev_hist,t.elev_edges,{unit:"m",every:4}),
      ()=>table(["Band","Cells"],t.elev_hist.map((c,i)=>[`${Math.round(t.elev_edges[i])}–${Math.round(t.elev_edges[i+1])} m`,fmt(c)])));},
  slope_hist(){const t=S.terrain;if(!t)return null;
    return frame2("Distribution of slope steepness","30–35° is where loose material stops holding naturally.",
      histogram(t.slope_hist,t.slope_edges,{unit:"°",every:2,color:"var(--s2)"}),
      ()=>table(["Band","Cells"],t.slope_hist.map((c,i)=>[`${Math.round(t.slope_edges[i])}–${Math.round(t.slope_edges[i+1])}°`,fmt(c)])));},
  landcover_bar(){const c=S.landcover&&S.landcover.classes;if(!c)return null;
    const items=c.slice().sort((a,b)=>b.pct-a.pct).map(x=>({label:x.name,value:x.pct,display:x.pct.toFixed(1),color:x.color}));
    return frame2("What covers the ground","Share of surface by class.",hbar(items,{unit:"%"}),
      ()=>table(["Class","Share"],items.map(i=>[i.label,i.display+"%"])));},
  geology_lith(){const g=S.geology;if(!g)return null;
    const items=Object.entries(g.lithologies).sort((a,b)=>b[1]-a[1]).map(([k,v])=>({label:k,value:v}));
    return frame2("Every rock type the free data distinguishes","Three categories for 81,995 km².",
      hbar(items,{unit:" pts",color:"var(--s4)"}),()=>table(["Lithology","Points"],items.map(i=>[i.label,i.value])));},
  geology_groups(){const g=S.geology_state;if(!g||!g.by_group)return null;
    const items=Object.entries(g.by_group).map(([k,v])=>({label:k,value:v}));
    return frame2("Rock groups the state map distinguishes",
      `${g.lith_units} lithological units and ${g.strat_units} named formations, against three before.`,
      hbar(items,{unit:" polygons",color:"var(--s4)"}),
      ()=>table(["Rock group","Polygons"],items.map(i=>[i.label,fmt(i.value)])));},
  inventory_source(){const i=S.inventory;if(!i||!i.by_source)return null;
    const items=Object.entries(i.by_source).sort((a,b)=>b[1]-a[1])
      .map(([k,v])=>({label:k,value:v}));
    return frame2("Where the mapped landslides come from",
      `${fmt(i.unique_total||i.total)} unique after removing ${fmt(i.overlap_bhuvan_in_gsi||0)} slides mapped by both. GSI supplies coverage; Bhuvan supplies the dates.`,
      hbar(items,{unit:"",color:"var(--s1)"}),
      ()=>table(["Source","Landslides"],items.map(i=>[i.label,fmt(i.value)])));},
  inventory_district(){const i=S.inventory;if(!i||!i.by_district)return null;
    const items=Object.entries(i.by_district).map(([k,v])=>({label:k,value:v}));
    return frame2("Mapped landslides by district",
      `Top ${items.length} of ${i.districts_covered} districts mapped statewide.`,
      hbar(items,{unit:"",color:"var(--s2)"}),
      ()=>table(["District","Landslides"],items.map(i=>[i.label,fmt(i.value)])));},
  susceptibility_class(){const s=S.susceptibility;if(!s||!s.pct)return null;
    const order=["Low","Moderate","High"];
    const cols={Low:"var(--s3)",Moderate:"var(--s4)",High:"var(--s2)"};
    const items=order.filter(k=>k in s.pct)
      .map(k=>({label:k,value:s.pct[k],display:s.pct[k].toFixed(1),color:cols[k]}));
    return frame2("How GSI classifies the state's slopes",
      "Share of classified land in each susceptibility class, at 50 m.",
      hbar(items,{unit:"%"}),
      ()=>table(["Class","Share","Cells"],
        items.map(i=>[i.label,i.display+"%",fmt(s.classes[i.label])])));},
  river_bands(){const r=S.rivers;if(!r)return null;
    const items=r.bands.filter(b=>b.threshold>0).map(b=>({label:"> "+fmt(b.threshold)+" km²",value:b.pct,display:b.pct.toFixed(1)}));
    return frame2("Share of the network above each drainage threshold","Global flood models need thousands of km². Only 3.0% qualify at 5,000.",
      hbar(items,{unit:"%"}),()=>table(["Area","Reaches","%","Length km"],
        r.bands.map(b=>[">"+fmt(b.threshold),fmt(b.count),b.pct+"%",fmt(b.length_km)])));},
  discharge_series(){const d=S.discharge;if(!d)return null;
    return frame2("Highest river discharge anywhere in the state, each day","Monsoon 2024. Peaks are the Siang/Brahmaputra trunk.",
      line([d.basin_daily_max],d.basin_daily_max.map((_,i)=>"day "+(i+1)),{unit:" m³/s",fill:true}),
      ()=>table(["Day","Peak m³/s"],d.basin_daily_max.map((v,i)=>["day "+(i+1),fmt(v)])));},
  rain_series(){const r=S.rainfall;if(!r)return null;
    const lab=r.dates.map(d=>d.slice(4,6)+"/"+d.slice(6,8));
    const f=frame2("Rainfall across the monsoon, 2024","Blue = state average. Orange = wettest single cell that day.",
      line([r.daily_mean,r.daily_max],lab,{unit:" mm",colors:["var(--s1)","var(--s2)"]}),
      ()=>table(["Date","Mean","Max cell"],r.dates.map((d,i)=>[lab[i],r.daily_mean[i],r.daily_max[i]])));
    f.insertBefore(legend([{label:"State average",color:"var(--s1)"},{label:"Wettest cell",color:"var(--s2)"}]),f.querySelector(".tbtn"));
    return f;},
  era5_temp(){const e=S.era5;if(!e)return null;
    return frame2("Average air temperature through the monsoon","Drives snowmelt at altitude.",
      line([e.t2m_series],e.t2m_series.map((_,i)=>"d"+(i+1)),{unit:" °C",colors:["var(--s2)"]}),
      ()=>table(["Step","°C"],e.t2m_series.map((v,i)=>["d"+(i+1),v])));},
  gfs_leads(){const g=S.gfs;if(!g||!g.leads.length)return null;
    const items=g.leads.map((l,i)=>({label:"+"+l+" h"+(l===168?"  (7 days)":""),value:g.maxima[i],display:g.maxima[i].toFixed(0)}));
    return frame2("Forecast rainfall available at each lead time","Confirms the full 7-day horizon returns real data.",
      hbar(items,{unit:" mm"}),()=>table(["Lead","Wettest cell mm"],g.leads.map((l,i)=>["+"+l+" h",g.maxima[i]])));},
  enso_series(){const e=S.enso;if(!e)return null;
    return frame2("El Niño / La Niña, last 40 years","Above zero = El Niño (often weaker monsoon). Below = La Niña.",
      line([e.oni],e.labels,{colors:["var(--s2)"]}),()=>table(["Year","ONI"],e.oni.map((v,i)=>[e.labels[i],v])));},
  quake_mag(){const q=S.seismic;if(!q)return null;
    return frame2("Earthquakes by magnitude since 1900","Big events are rare but not absent.",
      histogram(q.mag_hist,q.mag_edges,{unit:"M",every:2,color:"var(--s2)"}),
      ()=>table(["Band","Events"],q.mag_hist.map((c,i)=>[`M${q.mag_edges[i].toFixed(1)}–${q.mag_edges[i+1].toFixed(1)}`,c])));},
  s1_orbits(){const s=S.sentinel1;if(!s)return null;
    const items=[{label:"Ascending passes",value:s.ascending},{label:"Descending passes",value:s.descending}];
    return frame2("Satellite passes over the state, last 60 days","Both directions needed — each sees slopes facing a different way.",
      hbar(items,{unit:" scenes"}),()=>table(["Direction","Scenes"],items.map(i=>[i.label,i.value])));},
  s2_cloud(){const s=S.sentinel2;if(!s)return null;
    const items=[{label:"Monsoon (May–Sep)",value:100*s.monsoon.usable/s.monsoon.n,display:(100*s.monsoon.usable/s.monsoon.n).toFixed(0),color:"var(--s8)"},
      {label:"Whole year",value:100*s.annual.usable/s.annual.n,display:(100*s.annual.usable/s.annual.n).toFixed(0),color:"var(--s4)"},
      {label:"Dry (Nov–Mar)",value:100*s.dry.usable/s.dry.n,display:(100*s.dry.usable/s.dry.n).toFixed(0),color:"var(--s3)"}];
    return frame2("Share of optical images clear enough to use",'"Usable" = under 20% cloud. During monsoon almost nothing gets through.',
      hbar(items,{unit:"%"}),()=>table(["Season","Scenes","Median cloud","Usable"],
        [["Monsoon",s.monsoon.n,s.monsoon.median_cloud+"%",s.monsoon.usable],
         ["Dry",s.dry.n,s.dry.median_cloud+"%",s.dry.usable],
         ["Annual",s.annual.n,s.annual.median_cloud+"%",s.annual.usable]]));},
  label_acc(){const l=S.labels;if(!l)return null;
    const order=["exact","1km","5km","10km","25km","50km","unknown"];
    const cols={exact:"var(--s3)","1km":"var(--s3)","5km":"var(--s4)","10km":"var(--s4)",
      "25km":"var(--s8)","50km":"var(--s8)",unknown:"var(--muted)"};
    const items=order.filter(k=>l.accuracy[k]).map(k=>({label:k,value:l.accuracy[k],color:cols[k]}));
    const f=frame2("How precisely each recorded landslide is located","Only the top two bands — 28 events — are precise enough to train on.",
      hbar(items,{unit:" events"}),()=>table(["Accuracy","Events"],items.map(i=>[i.label,i.value])));
    f.insertBefore(legend([{label:"Usable for training",color:"var(--s3)"},{label:"Regional validation only",color:"var(--s4)"},
      {label:"Too coarse to place",color:"var(--s8)"},{label:"No accuracy recorded",color:"var(--muted)"}]),f.querySelector(".tbtn"));
    return f;},
  label_month(){const l=S.labels;if(!l||!l.by_month)return null;
    const M=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const items=M.map((m,i)=>({label:m,value:l.by_month[String(i+1)]||0,color:(i>=4&&i<=8)?"var(--s2)":"var(--s1)"}));
    const f=frame2("When landslides were recorded, by month","Orange = monsoon months. Compare with the rainfall chart.",
      hbar(items,{unit:" events"}),()=>table(["Month","Events"],items.map(i=>[i.label,i.value])));
    f.insertBefore(legend([{label:"Monsoon (May–Sep)",color:"var(--s2)"},{label:"Rest of year",color:"var(--s1)"}]),f.querySelector(".tbtn"));
    return f;},
  osm_bar(){const o=S.osm;if(!o)return null;
    const items=[["roads","Roads"],["buildings","Buildings"],["education","Schools"],["health","Health facilities"]]
      .filter(([k])=>o[k]).map(([k,lab])=>({label:lab,value:o[k].count}));
    return frame2("Everything OpenStreetMap has mapped inside the state","For 1.76 million people. Coverage is a few percent of reality.",
      hbar(items),()=>table(["Layer","Features"],items.map(i=>[i.label,fmt(i.value)])));}
};

/* ============================== render page ============================== */
document.getElementById("meta").textContent =
  `${P.layers.length} datasets · ${Object.keys(RAS).length} map layers · built ${P.built}`;
const TILES=[["1.76 M","people in the state","WorldPop 2020, modelled at 100 m"],
 ["49.6%","of terrain steeper than 15°","Half the state is landslide-capable ground"],
 ["50,800","river reaches mapped","Only 3.0% are big enough for free flood forecasting"],
 ["28","usable landslide records","For 81,995 km². The single biggest gap"],
 ["2 days","rainfall data latency","Fresh enough to drive a live warning"],
 ["1%","of monsoon satellite photos usable","Cloud blocks optical exactly when it matters"]];
const tiles=document.getElementById("tiles");
TILES.forEach(([v,k,n])=>tiles.append($("div",{class:"tile"},
  $("div",{class:"v"},v),$("div",{class:"k"},k),$("div",{class:"n"},n))));

/* ====================== under the hood ======================
   Renders what extract_raw.py found on disk: provenance, the request that
   fetched it, the real schema, and untouched rows or cell values. Nothing
   here is rounded or renamed. */
const RAW=P.raw||{};

function bytes(n){
  if(n>=1e9)return (n/1e9).toFixed(2)+" GB";
  if(n>=1e6)return (n/1e6).toFixed(1)+" MB";
  if(n>=1e3)return (n/1e3).toFixed(0)+" kB";
  return n+" B";
}
function kv(obj){
  const d=$("div",{class:"kv"});
  Object.entries(obj).forEach(([k,v])=>{
    if(v===null||v===undefined||v==="")return;
    d.append($("div",{},$("span",{},k),$("span",{},String(v))));
  });
  return d;
}
function rawTable(head,rows,{numeric=[]}={}){
  const t=$("table",{class:"rawt"});
  t.append($("tr",{},...head.map(h=>$("th",{},h))));
  rows.forEach(r=>t.append($("tr",{},...r.map((c,i)=>
    $("td",{class:numeric.includes(i)?"num":""},
      c===null||c===undefined?"∅":String(c))))));
  return $("div",{class:"scroll"},t);
}
function cap(text){return $("div",{class:"rawcap"},text);}

function fileBlock(f,openFirst){
  const det=$("details",{class:"rawblk"});
  if(openFirst)det.setAttribute("open","");
  det.append($("summary",{},$("b",{},f.name),
    $("span",{class:"dim"},`${f.kind} · ${bytes(f.bytes)} · ${f.modified}`)));
  const body=$("div",{class:"rawbody"});

  body.append(cap("On disk"));
  body.append(kv(Object.assign({path:f.path},f.detail||{})));

  if(f.schema&&f.schema.length){
    body.append(cap(f.kind==="vector"?"Columns, as the file declares them"
      :"Variables inside the file"));
    body.append(rawTable(["field","type",f.schema.some(s=>s.note)?"units / description":""]
      .filter(Boolean),
      f.schema.map(s=>s.note!==undefined?[s.col,s.type,s.note]:[s.col,s.type])));
  }
  if(f.rows&&f.rows.length){
    body.append(cap(`First ${f.rows.length} records, unedited`));
    const cols=f.schema.map(s=>s.col);
    const numeric=f.schema.map((s,i)=>/int|float|double/i.test(s.type)?i:-1)
      .filter(i=>i>=0);
    body.append(rawTable(cols,f.rows,{numeric}));
  }
  if(f.geometry_sample){
    body.append(cap("Geometry of the first record"));
    body.append($("pre",{class:"rawpre rawurl"},f.geometry_sample));
  }
  if(f.grid){
    body.append(cap(f.grid.label));
    const numeric=f.grid.values[0].map((_,i)=>i);
    body.append(rawTable(f.grid.values[0].map((_,i)=>"c"+i),f.grid.values,{numeric}));
    if(f.grid.min!==null)
      body.append($("div",{class:"rawnote",style:"margin:8px 0 0"},
        `range across these cells: ${f.grid.min} → ${f.grid.max}`));
  }
  if(f.text){
    body.append(cap(f.kind==="archive"?"Entries in the archive":"First lines, verbatim"));
    body.append($("pre",{class:"rawpre"},f.text));
  }
  det.append(body);
  return det;
}

function rawPane(id){
  const r=RAW[id];
  const pane=$("div",{class:"rawpane"});
  if(!r){
    pane.append($("div",{class:"rawnote"},
      "Nothing was downloaded for this card — it reports a query result, a "+
      "derived layer, or a source we could not reach. See the explanation side."));
    return pane;
  }
  pane.append($("div",{class:"rawnote"},
    `${r.file_count} file${r.file_count===1?"":"s"} on disk, ${bytes(r.total_bytes)} total`+
    (r.shown_count<r.file_count
      ? ` — ${r.shown_count} opened below, the rest are the same shape.`:".")));

  if(r.fetch&&r.fetch.call){
    pane.append(cap("How it was fetched"));
    pane.append(kv({script:r.fetch.script}));
    pane.append($("pre",{class:"rawpre rawurl",style:"margin-top:8px"},r.fetch.call));
  }
  if(r.sources&&r.sources.length){
    pane.append(cap("Recorded provenance"));
    r.sources.forEach(s=>{
      pane.append(kv({source:s.source,fetched:s.fetched_utc,licence:s.license}));
      if(s.url)pane.append($("pre",{class:"rawpre rawurl",style:"margin:6px 0 0"},s.url));
      if(s.notes)pane.append($("div",{class:"rawnote",style:"margin:7px 0 0"},s.notes));
    });
  }
  if(r.unrecorded_count){
    pane.append(cap("No provenance record"));
    pane.append($("div",{class:"rawnote"},
      `${r.unrecorded_count} file(s) here have no entry in the folder's `+
      `_SOURCES.json, so licence and fetch date are unverified: `+
      r.unrecorded.join(", ")+(r.unrecorded_count>r.unrecorded.length?", …":"")));
  }
  pane.append(cap("The files themselves"));
  r.files.forEach((f,i)=>pane.append(fileBlock(f,i===0)));
  return pane;
}

/* One switch element; `onto` receives the new state. */
function flipSwitch(label,onto){
  const s=$("label",{class:"flip"},$("span",{class:"track"}),$("span",{},label));
  s.onclick=()=>{const on=!s.classList.contains("on");
    s.classList.toggle("on",on);onto(on,s);};
  return s;
}

const nav=document.getElementById("nav");
nav.append($("a",{href:"#explorer"},"Map explorer"));
P.sections.forEach(s=>nav.append($("a",{href:"#"+s.id},s.title)));
["Inventory","Glossary","Extend"].forEach(t=>nav.append($("a",{href:"#"+t.toLowerCase()},t)));

const main=document.getElementById("main");
const CARD_FLIPS=[];          // [setter] — the global switch drives all of these
P.sections.forEach(sec=>{
  const node=$("section",{id:sec.id});
  node.append($("div",{class:"sechead"},$("h2",{},sec.title),$("p",{html:sec.blurb})));
  P.layers.filter(l=>l.section===sec.id).forEach(l=>{
    const card=$("div",{class:"card"});
    const sw=flipSwitch("Raw data",on=>setFace(on));
    card.append($("div",{class:"chead"},$("h3",{},l.title),
      $("span",{class:"tier"},l.tier),sw));
    card.append($("div",{class:"src"},l.source));
    const face=$("div",{});          // the explanation side, hidden when flipped
    const prose=$("div",{class:"prose"});
    prose.append($("h4",{},"What this is"),$("div",{html:l.what}));
    prose.append($("h4",{},"Why it matters"),$("div",{html:l.why}));
    face.append(prose);
    const ml=l.mapLayer;
    if(ml&&(RAS[ml]||PATHS[ml]||WEB.points[ml]||ml==="rivers")){
      const b=$("button",{class:"showmap"},"↗ Show this on the map");
      b.onclick=()=>{
        if(RAS[ml]){const inp=document.getElementById("b_"+ml);
          if(inp){inp.checked=true;inp.onchange();}}
        else{const keys=ml==="rivers"?["rivers_large","rivers_mid","rivers_small"]:[ml];
          keys.forEach(k=>{overlays[k]=true;});
          document.querySelectorAll("#overOpts .opt").forEach(o=>{
            const t=o.textContent.trim();
            const map={"Landslide records":"landslides","Earthquakes M4+":"earthquakes",
              "Major roads":"roads","Districts":"districts"};
            if(keys.includes(map[t])||(ml==="rivers"&&t.startsWith("Rivers"))||
               (ml==="rivers"&&t==="Small streams")){
              o.classList.add("on");o.querySelector("input").checked=true;}});
          draw();}
        document.getElementById("explorer").scrollIntoView({behavior:"smooth",block:"start"});
      };
      face.append(b);
    }
    if(l.facts&&l.facts.length){
      const f=$("div",{class:"facts"});
      l.facts.forEach(([k,v])=>f.append($("div",{class:"fact"},$("div",{class:"fv"},v),$("div",{class:"fk"},k))));
      face.append(f);
    }
    (l.charts||[]).forEach(c=>{try{const ch=CHARTS[c]&&CHARTS[c]();if(ch)face.append(ch);}
      catch(e){console.warn("chart",c,e);}});
    card.append(face);

    // The raw side is built on first flip — 29 cards' worth of tables up front
    // would cost a second of layout nobody asked for.
    let back=null;
    function setFace(on){
      if(on&&!back){back=rawPane(l.id);card.append(back);}
      if(back)back.style.display=on?"block":"none";
      face.style.display=on?"none":"block";
      sw.classList.toggle("on",on);
    }
    CARD_FLIPS.push(setFace);
    node.append(card);
  });
  main.append(node);
});

/* Global switch: flips every card at once. Lives at the end of the sticky nav. */
nav.append(flipSwitch("Under the hood",on=>{
  CARD_FLIPS.forEach(f=>f(on));
}));

const inv=document.getElementById("inv");
inv.append($("tr",{},...["Dataset","Source","Access","Key facts"].map(h=>$("th",{},h))));
P.layers.forEach(l=>inv.append($("tr",{},$("td",{},l.title),$("td",{},l.source),
  $("td",{},l.tier),$("td",{},(l.facts||[]).map(([k,v])=>`${k}: ${v}`).join(" · ")))));

const gl=document.getElementById("gloss");
P.glossary.forEach(g=>gl.append($("dl",{class:"gitem"},$("dt",{},g.term),$("dd",{html:g.body}))));
</script>
"""

if __name__ == "__main__":
    main()
