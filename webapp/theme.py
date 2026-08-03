"""Design layer — an operations console, not a dashboard.

Identity: deep ink canvas, cool sky accent, Sora for display type / Inter for
UI. The accent is deliberately COOL because the hazard ramp is warm
(green -> yellow -> red); a warm accent would compete with the very colours
that carry the meaning.

Hazard classes use a green->red ramp because it is the convention emergency
managers already read. The out-of-domain grey is deliberately flat and dull: it
must never be mistaken for "safe".

Kept out of app.py so the layout code stays readable.
"""
from __future__ import annotations

CLASS_NAMES = ["Very Low", "Low", "Moderate", "High", "Very High"]
CLASS_COLORS = ["#1a9850", "#a6d96a", "#fee08b", "#f46d43", "#a50026"]
NOT_ASSESSED = "#3a4351"

# Basemaps. `tiles=None` on the Map plus our own TileLayer is what makes the
# switcher work at all — folium's built-in tiles argument cannot be swapped
# after construction.
CARTO = ('&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> '
         '&copy; <a href="https://carto.com/attributions">CARTO</a>')
BASEMAPS = {
    "Dark": ("https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png", CARTO),
    "Satellite": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/"
                  "MapServer/tile/{z}/{y}/{x}",
                  "Tiles &copy; Esri — Esri, Maxar, Earthstar Geographics"),
    "Terrain": ("https://tile.opentopomap.org/{z}/{x}/{y}.png",
                'Map data &copy; OSM, SRTM · style &copy; '
                '<a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)'),
    "Light": ("https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png", CARTO),
}
LABEL_TILES = {
    "Dark": "https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png",
    "Satellite": "https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png",
    "Terrain": "https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png",
    "Light": "https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png",
}
BOUNDARY_INK = {"Dark": "#38bdf8", "Satellite": "#38bdf8",
                "Terrain": "#1f2937", "Light": "#1f2937"}

MAP_MIN_ZOOM = 6
MAP_H = 560

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Sora:wght@500;600;700&display=swap');

:root{
  --ink:#0b0f14; --panel:#111823; --panel-2:#161f2c; --line:#223044;
  --txt:#e5edf5; --mut:#8fa3ba; --dim:#64798f;
  --accent:#38bdf8; --accent-2:#818cf8;
}
html,body,.stApp,p,li,td,th,label,input,textarea,select,button{
  font-family:'Inter',system-ui,-apple-system,sans-serif;
}
h1,h2,h3,h4,h5,h6,[data-testid="stMetricValue"]{
  font-family:'Sora','Inter',sans-serif!important; letter-spacing:-.015em;
}
.stApp{
  background:
    radial-gradient(1100px 520px at 12% -12%, rgba(56,189,248,.10), transparent 62%),
    radial-gradient(900px 480px at 88% -6%, rgba(129,140,248,.10), transparent 60%),
    var(--ink);
}
.block-container{padding-top:1.7rem; padding-bottom:3rem; max-width:1480px;}

/* Header is made invisible but NOT removed — it reserves the vertical space
   the content sits below. The sidebar's reopen button lives inside the
   toolbar, so hiding the whole toolbar would strand a collapsed sidebar. */
[data-testid="stHeader"]{background:transparent; box-shadow:none;}
[data-testid="stDecoration"],.stAppDeployButton,#MainMenu,footer{display:none;}
[data-testid="stToolbarActions"]{display:none;}
[data-testid="stExpandSidebarButton"]{visibility:visible!important; opacity:1!important;}

/* Map components mount at zero width before their own JS measures the
   container; forcing width at the CSS layer applies first, so that flash
   never paints. */
iframe,[data-testid="stDeckGlJsonChart"],[data-testid="stFullScreenFrame"]{width:100%!important;}
iframe{border-radius:14px; border:1px solid var(--line)!important;}

/* ---- brand ---- */
.brand{display:flex; align-items:center; gap:11px; margin-bottom:6px;}
.brand-logo{
  width:40px;height:40px;border-radius:12px;display:flex;align-items:center;
  justify-content:center;font-size:19px;color:#06121a;
  background:linear-gradient(135deg,var(--accent),var(--accent-2));
  box-shadow:0 4px 14px rgba(56,189,248,.24);
}
.brand-name{font-family:'Sora',sans-serif;font-weight:700;font-size:1.08rem;
  color:var(--txt);line-height:1.15;letter-spacing:-.02em;}
.brand-tag{font-size:.68rem;color:var(--dim);letter-spacing:.02em;}
.side-label{font-size:.66rem;font-weight:700;letter-spacing:.13em;color:var(--dim);
  text-transform:uppercase;margin:10px 0 2px;}

/* ---- alert banner ---- */
.alert-band{
  display:flex;align-items:center;gap:16px;padding:15px 20px;border-radius:16px;
  border:1px solid var(--line);margin-bottom:14px;
  background:linear-gradient(180deg,var(--panel-2),var(--panel));
}
.alert-dot{width:13px;height:13px;border-radius:50%;flex:none;}
.alert-title{font-family:'Sora',sans-serif;font-weight:700;font-size:1.16rem;color:var(--txt);}
.alert-sub{font-size:.82rem;color:var(--mut);margin-top:2px;}
.alert-right{margin-left:auto;text-align:right;}
.alert-num{font-family:'Sora',sans-serif;font-weight:700;font-size:1.5rem;color:var(--txt);}
.alert-lbl{font-size:.63rem;color:var(--dim);text-transform:uppercase;letter-spacing:.09em;}

/* ---- day strip ---- */
[class*="st-key-day_"] button{
  border-radius:12px!important;padding:9px 4px!important;font-weight:600!important;
  border:1px solid var(--line)!important;background:var(--panel-2)!important;
  color:#cfe0ef!important;line-height:1.25!important;
}
[class*="st-key-day_"] button:hover{border-color:var(--accent)!important;color:var(--accent)!important;}
[class*="st-key-day_"] button[kind="primary"]{
  background:linear-gradient(135deg,rgba(56,189,248,.16),rgba(129,140,248,.16))!important;
  border-color:var(--accent)!important;color:var(--accent)!important;
}
[class*="st-key-nav_"] button{
  text-align:left;justify-content:flex-start;font-weight:600;padding:8px 12px;border-radius:11px;
}
[class*="st-key-nav_"] div[data-testid="stMarkdownContainer"]{text-align:left;}

/* ---- panels / metrics ---- */
div[data-testid="stVerticalBlockBorderWrapper"]{
  background:linear-gradient(180deg,rgba(22,31,44,.92),rgba(17,24,35,.92));
  border-radius:18px;
}
[data-testid="stMetric"]{
  background:linear-gradient(180deg,var(--panel-2),var(--panel));
  border:1px solid var(--line);border-radius:16px;padding:12px 15px;
}
[data-testid="stMetricLabel"] p{
  font-size:.66rem!important;font-weight:600!important;text-transform:uppercase;
  letter-spacing:.08em;color:var(--dim)!important;
}
[data-testid="stMetricValue"]{font-size:1.42rem;font-weight:700;color:var(--txt);}
div[data-testid="stExpander"] > details{
  background:var(--panel);border:1px solid var(--line);border-radius:14px;
}
[data-testid="stDataFrame"]{border-radius:12px;}
[data-testid="stSidebar"]{background:#0d131b;border-right:1px solid var(--line);}

/* ---- map card ---- */
.map-head{display:flex;align-items:center;gap:10px;padding:0 0 9px;}
.mh-dot{width:8px;height:8px;border-radius:50%;background:var(--accent);
  box-shadow:0 0 0 4px rgba(56,189,248,.15);flex:none;}
.mh-title{font-family:'Sora',sans-serif;font-weight:600;font-size:1rem;color:var(--txt);}
.mh-note{margin-left:auto;font-size:.73rem;color:var(--dim);}
.legend-strip{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;align-items:center;}
.lg{display:inline-flex;align-items:center;gap:7px;background:var(--panel-2);
  border:1px solid var(--line);border-radius:999px;padding:4px 11px;
  font-size:.75rem;color:#c3d3e3;white-space:nowrap;}
.lg i{width:10px;height:10px;border-radius:3px;flex:none;}
.lg b{color:var(--dim);font-weight:600;font-variant-numeric:tabular-nums;}
.lg-note{font-size:.73rem;color:var(--dim);margin-left:auto;}

/* ---- inspector ---- */
.insp-empty{padding:26px 18px;text-align:center;color:var(--dim);font-size:.86rem;
  border:1px dashed var(--line);border-radius:14px;background:rgba(17,24,35,.5);}
.insp-row{display:flex;justify-content:space-between;padding:7px 0;
  border-bottom:1px solid rgba(34,48,68,.6);font-size:.86rem;}
.insp-row:last-child{border-bottom:none;}
.insp-k{color:var(--mut);}
.insp-v{color:var(--txt);font-weight:600;font-variant-numeric:tabular-nums;}
.chip{padding:2px 10px;border-radius:10px;font-weight:700;font-size:.76rem;}

/* ---- misc ---- */
.stDownloadButton button,.stButton button{
  border-radius:10px;font-weight:600;border:1px solid var(--line);
  background:var(--panel-2);color:#cfe0ef;
}
.stDownloadButton button:hover,.stButton button:hover{
  border-color:var(--accent);color:var(--accent);background:rgba(56,189,248,.06);
}
.eyebrow{font-size:.68rem;font-weight:700;letter-spacing:.16em;color:var(--accent);
  text-transform:uppercase;margin-bottom:6px;}
.caveat{font-size:.78rem;color:var(--dim);border-left:2px solid var(--line);
  padding-left:11px;margin:7px 0;}
.stAlert{border-radius:13px;}
</style>
"""


def chip(idx: int) -> str:
    """Coloured class pill. Dark ink on the pale mid-classes, white elsewhere."""
    ink = "#111" if idx in (1, 2) else "#fff"
    return (f"<span class='chip' style='background:{CLASS_COLORS[idx]};color:{ink}'>"
            f"{CLASS_NAMES[idx]}</span>")


def row(k: str, v: str) -> str:
    return (f"<div class='insp-row'><div class='insp-k'>{k}</div>"
            f"<div class='insp-v'>{v}</div></div>")
