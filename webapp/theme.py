"""Visual layer. Colours follow the SlopeSense palette so the two projects read
as a family; the layout does not, because this app is a forecast and that one is
a static map.

Hazard classes use a green→red ramp because it is the convention emergency
managers already read. The out-of-domain grey is deliberately flat and dull: it
must never be mistaken for "safe".
"""

CLASS_NAMES = ["Very Low", "Low", "Moderate", "High", "Very High"]
CLASS_COLORS = ["#1a9850", "#a6d96a", "#fee08b", "#f46d43", "#a50026"]
NOT_ASSESSED = "#3a3f47"

INK = "#e8eaed"
MUTED = "#9aa3ad"
BG = "#12151a"
PANEL = "#1a1e25"
LINE = "#2b313a"
ACCENT = "#4da3ff"

CSS = f"""
<style>
  .stApp {{ background: {BG}; color: {INK}; }}
  #MainMenu, footer, header {{ visibility: hidden; }}
  .block-container {{ padding-top: 1.2rem; max-width: 1500px; }}

  .brand {{ display:flex; align-items:center; gap:.7rem; margin-bottom:.2rem; }}
  .brand-logo {{ font-size:1.7rem; line-height:1; }}
  .brand-name {{ font-size:1.35rem; font-weight:700; letter-spacing:-.02em; }}
  .brand-tag {{ font-size:.66rem; letter-spacing:.16em; color:{MUTED};
                text-transform:uppercase; }}

  .alert-hero {{ border-radius:14px; padding:1.1rem 1.3rem; margin:.6rem 0 1rem;
                 border:1px solid {LINE}; background:{PANEL}; }}
  .alert-level {{ font-size:2.0rem; font-weight:800; letter-spacing:-.03em;
                  line-height:1.1; }}
  .alert-sub {{ color:{MUTED}; font-size:.86rem; margin-top:.25rem; }}

  .kpi {{ background:{PANEL}; border:1px solid {LINE}; border-radius:12px;
          padding:.75rem .9rem; height:100%; }}
  .kpi-num {{ font-size:1.45rem; font-weight:700; letter-spacing:-.02em; }}
  .kpi-lbl {{ font-size:.7rem; color:{MUTED}; text-transform:uppercase;
              letter-spacing:.08em; margin-top:.15rem; }}

  .daycard {{ border:1px solid {LINE}; background:{PANEL}; border-radius:11px;
              padding:.6rem .5rem; text-align:center; }}
  .daycard.sel {{ border-color:{ACCENT}; box-shadow:0 0 0 1px {ACCENT} inset; }}
  .daycard .dow {{ font-size:.68rem; color:{MUTED}; text-transform:uppercase;
                   letter-spacing:.08em; }}
  .daycard .dnum {{ font-size:1.0rem; font-weight:700; margin:.1rem 0; }}
  .daycard .dot {{ height:6px; border-radius:3px; margin-top:.35rem; }}

  .legend {{ display:flex; gap:.45rem; flex-wrap:wrap; align-items:center;
             font-size:.72rem; color:{MUTED}; margin:.4rem 0 .1rem; }}
  .legend i {{ width:13px; height:13px; border-radius:3px; display:inline-block;
               margin-right:.28rem; vertical-align:-2px; }}

  .note {{ font-size:.76rem; color:{MUTED}; line-height:1.5; }}
  .warn {{ border-left:3px solid #f0a020; padding:.5rem .8rem; background:#1e1a12;
           border-radius:0 8px 8px 0; font-size:.78rem; color:#e6d9c0; }}
  .stDataFrame {{ border:1px solid {LINE}; border-radius:10px; }}
  div[data-testid="stMetricValue"] {{ font-size:1.3rem; }}
</style>
"""


def legend_html(include_na: bool = True) -> str:
    parts = [f"<i style='background:{c}'></i>{n}"
             for c, n in zip(CLASS_COLORS, CLASS_NAMES)]
    if include_na:
        parts.append(f"<i style='background:{NOT_ASSESSED}'></i>Not assessed")
    return f"<div class='legend'>{''.join(parts)}</div>"
