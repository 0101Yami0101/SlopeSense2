"""FloodSense pages.

    flood hazard = flood-prone ground (terrain, static)
                 x catchment rain     (routed downstream, daily)

Same structure as SlopeSense, and for the same reason: the product is the
FORECAST, and a forecast is only useful somewhere.

⚠️ The static layer is still UNVALIDATED and small streams are still a watch
rather than a forecast — both real, unchanged. What changed is where that's
said: it no longer runs as a standing caption on every page. Full detail
lives on the "Method & limits" branch below — reachable only from the ℹ️
popover, and shown there disabled until the validation work behind it is
done. The polished write-up still belongs in docs/design/, not repeated
chrome on the forecast screen.
"""
from __future__ import annotations

from datetime import date, datetime

import folium
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import core.geo as G
import core.grid as GR
import core.mapping as M
import core.rainfall as RN
import core.theme as T
import products.flood.model as fm
from core.bundle import load_rain_spine
from core.location import ask_again
from core.settings import map_settings

# Method & limits still exists — the branch at the bottom of this file — but
# is reached only from the ℹ️ popover (see Product.extra_nav in
# products/__init__.py), and shown there disabled: not ready for anyone
# outside the team to see yet.
VIEWS = [("🌊", "Forecast"), ("🗺️", "Flood-prone ground"), ("💧", "Catchments")]

# Catchment-wetness ramp — BLUE, deliberately not the green-to-red hazard ramp.
# "A lot of water is coming" and "this is dangerous" are different statements,
# and one ramp for both would merge them.
WET_NAMES = ["Normal", "Above normal", "Wet", "Very wet", "Exceptional"]
WET_COLORS = ["#0b3a5b", "#1565a8", "#2f9fd8", "#7fd4f0", "#d8f6ff"]
WET_CUTS = np.array([0.50, 0.75, 0.90, 0.97], dtype=np.float32)


def render(shell) -> None:
    from products.flood.data import available, load_catchments, load_static

    grid, geo = shell.grid, shell.geo
    PLACES, PLACE_IDX, LOOKUP = shell.places, shell.loc.place_idx, shell.lookup

    if not available():
        st.error("**The flood bundle is missing.** Run "
                 "`python scripts/build/build_flood_layers.py` to build it.")
        return

    FCLS, FIDX, HAND, CHAN_KM2, FRAC, MET = load_static()
    BID, NEXT_DOWN, ORDER, UP_AREA, SUB_AREA, RAIN_PT = load_catchments()
    PTS, QUANT = load_rain_spine()
    fx = RN.load_forecast(tuple(PTS["lat"]), tuple(PTS["lon"]))
    LIVE = fx is not None

    if "fl_view" not in st.session_state:
        st.session_state.fl_view = VIEWS[0][1]
    elif st.session_state.fl_view == "Method & limits":
        # Reachable only through a DISABLED popover entry right now — not
        # ready for anyone outside the team. Guards a session left sitting on
        # it from before that entry was disabled; no live control sets this.
        st.session_state.fl_view = VIEWS[0][1]

    with st.sidebar:
        for icon, label in VIEWS:
            active = st.session_state.fl_view == label
            if st.button(f"{icon}  {label}", key=f"flnav_{label}", width="stretch",
                         type="primary" if active else "secondary"):
                if not active:
                    st.session_state.fl_view = label
                    st.rerun()
        view = st.session_state.fl_view
        st.divider()
        s = map_settings(
            opacity_label="Flood overlay opacity",
            roads_help="Roads crossing floodplain are where a flood cuts access.",
            rivers_help="7,181 mapped stems. The blue line is the channel this "
                        "layer measures height above.")

    # ── daily maths ──────────────────────────────────────────────────────
    if LIVE:
        days, rain = fx
        trig = RN.trigger_series(rain, QUANT)
        fut = RN.forecast_days(days)
    else:
        days, rain, trig, fut = [], None, None, []

    def signal(di: int):
        """Upstream rainfall and anomaly per catchment, for one day."""
        return fm.catchment_signal(rain[di], trig[di], RAIN_PT, SUB_AREA,
                                   NEXT_DOWN, ORDER)

    def day_layers(di: int):
        mm, pct, area = signal(di)
        hz = fm.hazard_raster(FIDX, BID, pct)
        return mm, pct, area, hz, fm.classify(hz)

    @st.cache_data(show_spinner=False)
    def high_share(tag: str) -> list[float]:
        """Share of FLOOD-PRONE ground at High or above, per day.

        ⚠️ A share, never a maximum. The maximum anomaly over 1,680 catchments
        is close to 1.0 on an ordinary day for the same reason the landslide
        strip once read 0.99 everywhere — it is the max of many roughly uniform
        draws, and it carries almost no information about the weather.
        """
        out = []
        prone = FIDX > 0
        n = int(prone.sum())
        for i in fut:
            _, pct, _ = signal(i)
            cl = fm.classify(fm.hazard_raster(FIDX, BID, pct))
            out.append(float((cl[prone] >= 4).sum()) / n if n else 0.0)
        return out

    def location_days(sel):
        """That one place's flood class and score for each of the seven days.

        ⚠️ Mirrors SlopeSense's location_days(), and fixes the same bug it
        once had: the day strip was ALWAYS built from high_share() — the
        statewide share of floodplain — even after a place was selected.
        Clicking the map moved the pin and updated the panel beside it, but
        the strip above kept quoting the whole state's number under a
        specific place's name, silently.

        Returns None when there is no location, the point falls outside the
        mapped grid, or it sits outside every catchment (BID 0 — genuinely
        rare, a sliver at the state edge HydroBASINS does not cover). In
        every one of those the strip falls back to the statewide share.

        ⚠️ Reads FIDX straight off the CLICKED cell — it does NOT snap to the
        nearest flood-prone ground first. An earlier version did snap, to
        match how SlopeSense snaps to the nearest ASSESSED slope — but
        flood-prone ground is only ~5% of the state, so that snap failed for
        most clicks and silently fell back to the statewide number for a
        named place, which is the same bug wearing a disguise: the strip
        would go quiet again the moment someone clicked a hillside instead of
        a riverbank. The honest answer for a hillside is "Not floodplain",
        every day of the week — not the whole state's number — and that is
        what a zero FIDX correctly produces here. This also matches
        place_panel() below exactly: same cell, same reading, so the two
        can never disagree.
        """
        if not sel:
            return None
        px = grid.to_px(sel["lat"], sel["lon"])
        if px is None:
            return None
        r, c = px
        b = int(BID[r, c])
        if b == 0:
            return None
        idx = float(FIDX[r, c]) / 254.0
        hz = np.empty(len(fut), dtype=np.float32)
        for n, i in enumerate(fut):
            _, pct_i, _ = signal(i)
            hz[n] = idx * fm.trigger_response(pct_i[b - 1:b])[0]
        return hz, fm.classify(hz)

    @st.cache_data(show_spinner=False)
    def basin_centres():
        """Mean lat/lon of each catchment's cells, for labelling it with a
        place name. Derived from the raster rather than shipped, so it can
        never disagree with the basin the map actually paints."""
        lon1, lat1 = grid.axes()
        LON, LAT = np.meshgrid(lon1, lat1)
        ok = BID > 0
        lab = BID[ok] - 1
        n = len(SUB_AREA)
        cnt = np.bincount(lab, minlength=n).astype(float)
        la = np.bincount(lab, weights=LAT[ok], minlength=n) / np.maximum(cnt, 1)
        lo = np.bincount(lab, weights=LON[ok], minlength=n) / np.maximum(cnt, 1)
        la[cnt == 0] = np.nan
        lo[cnt == 0] = np.nan
        return np.stack([la, lo], axis=1)

    @st.cache_data(show_spinner=False)
    def basin_has_floodplain() -> np.ndarray:
        """Which catchments contain any flood-prone ground at all."""
        ok = (BID > 0) & (FIDX > 0)
        n = len(SUB_AREA)
        return np.bincount(BID[ok] - 1, minlength=n) > 0

    def wet_raster(pct: np.ndarray) -> np.ndarray:
        """Catchment anomaly painted over the cells of each catchment."""
        out = np.zeros(BID.shape, np.uint8)
        ok = BID > 0
        v = pct[BID[ok] - 1]
        out[ok] = (np.digitize(v, WET_CUTS) + 1).astype(np.uint8)
        return out

    def search_row():
        """Same selection as SlopeSense, and the SAME session key on purpose —
        a place searched in one module is still selected in the other."""
        s1, s2, s3 = st.columns([5, 1.15, 0.95], vertical_alignment="bottom")
        with s2:
            if st.button("📍 My location", width="stretch",
                         help="Ask the browser where you are. Only used if you "
                              "are inside Arunachal Pradesh."):
                ask_again()
                st.rerun()
        with s3:
            if st.button("⌖ Recentre", width="stretch",
                         help="Snap the map back to the selected location."):
                st.session_state.recentre = st.session_state.get("recentre", 0) + 1
                st.rerun()
        with s1:
            options = [G.PROMPT] + [p["label"] for p in PLACES]
            cur = st.session_state.get("search")
            if cur and cur not in PLACE_IDX and cur != G.PROMPT:
                options.insert(1, cur)
            st.selectbox("Location", options, key="search",
                         accept_new_options=True, label_visibility="collapsed",
                         help=f"{len(PLACES):,} towns, villages and districts — "
                              "or type coordinates such as 27.09, 93.61")
        return G.resolve(st.session_state.search, PLACES, LOOKUP)

    def place_panel(sel, cls_day, mm, pct, area):
        """The selected place, beside the map."""
        st.markdown("<div class='map-head' style='padding-top:2px'>"
                    "<div class='mh-dot'></div>"
                    "<div class='mh-title'>Selected location</div></div>",
                    unsafe_allow_html=True)
        box = st.container(height=T.MAP_H - 34, border=False, key="click_shell")
        with box:
            if not sel:
                st.markdown("<div class='insp-empty'>No location chosen.<br><br>"
                            "Search a town above, or click the map, to get its "
                            "height above the nearest river, the size of that "
                            "river, and how much rain is falling upstream."
                            "</div>", unsafe_allow_html=True)
                return
            st.markdown(f"<div class='insp-place'>{sel['label']}</div>",
                        unsafe_allow_html=True)
            px = grid.to_px(sel["lat"], sel["lon"])
            if px is None:
                st.markdown("<div class='insp-empty'><b>Outside the mapped area"
                            "</b><br>This model covers Arunachal Pradesh only."
                            "</div>", unsafe_allow_html=True)
                return
            r, c = px
            # ⚠️ Cast out of the stored dtypes before doing arithmetic. These
            # ship as uint8/uint16 with sentinel nodata, so `100 * FRAC[r, c]`
            # silently overflows uint8 and a missing HAND reads as 65535 m.
            h = int(HAND[r, c])
            km2 = int(CHAN_KM2[r, c])
            b = int(BID[r, c])
            has_h, has_km2 = h != 65535, km2 != 65535
            frac_pct = (100.0 * float(FRAC[r, c]) / 254.0
                        if FRAC[r, c] != 255 else None)

            if FIDX[r, c] == 0:
                near = fm.nearest_flood_cell(FIDX, r, c)
                extra = ""
                if near:
                    d_km = near[2] * grid.cell_km
                    extra = (f"<br><br>Nearest low-lying ground is about "
                             f"<b>{d_km:.1f} km</b> away.")
                st.markdown(
                    "<div class='insp-empty'><b>Not floodplain</b><br>"
                    + (f"This ground sits <b>{h} m</b> above the nearest river "
                       "channel." if has_h else "No drainage nearby.")
                    + " River flooding does not reach it. That says nothing "
                    "about a landslide, or about water running off the slope "
                    "above — see SlopeSense for the first." + extra + "</div>",
                    unsafe_allow_html=True)
                if b > 0:
                    st.markdown(T.row("Upstream catchment", f"{area[b-1]:,.0f} km²")
                                + T.row("Rain upstream, that day", f"{mm[b-1]:.1f} mm")
                                + T.row("Upstream rain vs normal", f"{pct[b-1]:.2f}"),
                                unsafe_allow_html=True)
                return

            k = int(cls_day[r, c])
            st.markdown(
                f"<div style='margin-bottom:9px'>{T.chip(k - 1)}</div>"
                + T.row("Latitude, longitude", f"{sel['lat']:.4f}, {sel['lon']:.4f}")
                + T.row("Height above nearest river", f"{h} m" if has_h else "—")
                + T.row("That river drains", f"{km2:,} km²" if has_km2 else "—")
                + T.row("River class",
                        ("Large river — forecastable" if km2 >= fm.LARGE_RIVER_KM2
                         else "Mountain stream — watch only") if has_km2 else "—")
                + T.row("Low-lying share of this cell",
                        f"{frac_pct:.0f}%" if frac_pct is not None else "—")
                + (T.row("Upstream catchment", f"{area[b-1]:,.0f} km²")
                   + T.row("Rain upstream, that day", f"{mm[b-1]:.1f} mm")
                   + T.row("Upstream rain vs normal", f"{pct[b-1]:.2f}")
                   if b > 0 else ""),
                unsafe_allow_html=True)
            if b > 0 and LIVE:
                st.caption("Next 7 days here")
                vals = []
                for i in fut:
                    _, p, _ = signal(i)
                    # Through the SAME response curve the map uses. Multiplying
                    # by the raw percentile here would draw a chart that
                    # disagreed with the colour under the pin.
                    vals.append(float(FIDX[r, c] / 254.0
                                      * fm.trigger_response(p[b - 1:b])[0]))
                st.bar_chart(pd.DataFrame({
                    "day": [datetime.fromisoformat(days[i]).strftime("%d %b")
                            for i in fut], "flood index": vals}).set_index("day"),
                    height=170, color=T.ACCENT_2)

    # ═════════════════════ FORECAST ══════════════════════════════════════
    if view == "Forecast":
        if not LIVE:
            st.error("**Live rainfall is unavailable right now.** The free "
                     "weather service limits how often it can be queried. The "
                     "flood-prone map still works — open it from the sidebar.")
            st.stop()

        with st.container(border=True):
            M.map_head("Flood forecast", "click anywhere to inspect")
            sel = search_row()
            if sel is None and st.session_state.search != G.PROMPT:
                st.warning(f"Could not read **{st.session_state.search}** as a "
                           "place or a coordinate.")

            # Each button carries the outlook FOR THE SELECTED PLACE once one
            # is chosen — the strip must always say which of the two it is
            # showing, the same rule SlopeSense's strip follows and for the
            # same reason: a number with no place named under it could be
            # anywhere.
            ld = location_days(sel)
            if ld is not None:
                # ⚠️ k CAN be 0 here — unlike SlopeSense, where the lowest
                # hazard still lands in "Very Low", a flood index of exactly
                # 0 (ordinary, non-floodplain ground) classifies to 0, and
                # T.CLASS_NAMES[-1] on that would silently print "Very High"
                # for the SAFEST possible reading — the worst way this could
                # fail, and quietly at that.
                notes = ["Not floodplain" if k == 0 else T.CLASS_NAMES[k - 1]
                         for k in ld[1]]
                strip_label = f"7-day outlook · <b>{sel['label']}</b>"
            else:
                notes = [f"{100*x:.0f}% High+" for x in high_share(days[fut[0]])]
                strip_label = ("7-day outlook · <b>whole state</b> — share of "
                               "floodplain at High or above. Pick a place for "
                               "a local forecast.")
            st.markdown(f"<div class='strip-label'>{strip_label}</div>",
                        unsafe_allow_html=True)
            di = M.day_strip("fl", days, fut, notes)
            sel_day = datetime.fromisoformat(days[di])
            mm, pct, area, hz, cls_day = day_layers(di)

            dfeat = (GR.feature_by(geo.districts["features"], "district",
                                   sel["label"][:-9])
                     if sel and sel["kind"] == "district" else None)
            clip = (GR.polygon_mask(dfeat["geometry"], grid.west, grid.east,
                                    grid.south, grid.north, grid.height,
                                    grid.width) if dfeat else None)
            shown = GR.clip_to(cls_day, clip)

            marker, centre, zoom = None, None, 7
            if sel:
                centre, zoom = (sel["lat"], sel["lon"]), 11
                marker = (sel["lat"], sel["lon"], sel["label"])
            if dfeat:
                pts = np.array([p for ring in G._rings(dfeat["geometry"])
                                for p in ring])
                span = max(float(np.ptp(pts[:, 0])), float(np.ptp(pts[:, 1])), 0.05)
                zoom = float(np.clip(np.log2(360.0 / span) - 1.6, 6, 11))
                marker = None

            cinfo, cmap = st.columns([1, 2.35], gap="medium")
            with cmap:
                shell_box = st.container(height=T.MAP_H + 8, border=False,
                                         key="map_shell")
                m = M.base_map(grid, s)
                img = (None if s.bare
                       else M.rgba_overlay(shown, T.CLASS_COLORS))

                def _sel_district(fg):
                    if dfeat:
                        folium.GeoJson(dfeat, name="Selected district",
                                       style_function=lambda _: {
                                           "color": T.ACCENT, "weight": 2.6,
                                           "fill": False,
                                           "opacity": .95}).add_to(fg)

                fg = M.overlay_group(grid, s, geo, img=img, districts=s.districts,
                                     marker=marker, extra=_sel_district)
                fly_c, fly_z = M.fly_to(sel, zoom)
                with shell_box:
                    out = st_folium(m, height=T.MAP_H, use_container_width=True,
                                    pixelated=True,
                                    returned_objects=["last_clicked"],
                                    feature_group_to_add=fg,
                                    center=fly_c, zoom=fly_z, key="flfmap")
                click = (out or {}).get("last_clicked")
                if click:
                    xy = (round(float(click["lat"]), 5),
                          round(float(click["lng"]), 5))
                    if xy != st.session_state.get("clicked_xy"):
                        st.session_state.clicked_xy = xy
                        st.session_state.pending_place = f"{xy[0]:.4f}, {xy[1]:.4f}"
                        st.rerun()
                if s.bare:
                    M.legend_strip([], [], bare=True)
                else:
                    base = shown if clip is not None else cls_day
                    prone = base > 0
                    shares = [float((base[prone] == i).mean()) if prone.any() else 0
                              for i in range(1, 6)]
                    M.legend_strip(T.CLASS_NAMES, T.CLASS_COLORS, shares,
                                   note=("share of floodplain in "
                                         + sel["label"] if clip is not None else
                                         "share of Arunachal's floodplain · blank "
                                         "ground is not floodplain at all"))
            with cinfo:
                place_panel(sel, cls_day, mm, pct, area)

        # ---- statewide numbers ------------------------------------------ #
        prone = FIDX > 0
        hi = float((cls_day[prone] >= 4).mean()) if prone.any() else 0.0
        k = st.columns(4)
        k[0].metric("Floodplain at High or above", f"{100*hi:.1f}%",
                    help="Share of the state's flood-prone ground, not of the "
                         "state. Most of Arunachal is not flood-prone at all.")
        k[1].metric("Catchments unusually wet", f"{int((pct >= 0.90).sum()):,}",
                    f"of {len(pct):,}",
                    help="Upstream rainfall in the wettest 10% on record for "
                         "that catchment.")
        k[2].metric("Wettest catchment, upstream rain",
                    f"{float(np.nanmax(mm)):.0f} mm")
        ahead = (sel_day.date() - date.today()).days
        k[3].metric("Lead time", "Today" if ahead == 0 else f"+{ahead} d")

        st.markdown("<div class='eyebrow'>Catchments to watch — "
                    f"{sel_day.strftime('%d %b')}</div>", unsafe_allow_html=True)
        # Rank by anomaly, but only among catchments that actually contain
        # flood-prone ground — a wet catchment with nowhere for water to
        # collect is not something to send anyone to look at.
        with_plain = basin_has_floodplain()
        cand = np.where(with_plain)[0]
        big = cand[np.argsort(-pct[cand])][:40]
        cen = basin_centres()
        rows = []
        for b in big:
            lat, lon = cen[b]
            near, dkm = (G.nearest_place(lat, lon, PLACES)
                         if np.isfinite(lat) else (None, 0.0))
            rows.append({
                "Nearest settlement": (f"{near['label']} ({dkm:.0f} km)"
                                       if near else "—"),
                "Upstream catchment (km²)": round(float(area[b])),
                "Rain upstream (mm)": round(float(mm[b]), 1),
                "Vs normal": round(float(pct[b]), 2),
                "River class": ("Large river — forecastable"
                                if area[b] >= fm.LARGE_RIVER_KM2
                                else "Mountain stream — watch only")})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                     height=320,
                     column_config={"Vs normal": st.column_config.ProgressColumn(
                         "Vs normal", min_value=0.0, max_value=1.0, format="%.2f")})
        st.markdown(
            "<div class='caveat'>Read the last column before acting on any row. "
            "On a large river this is a genuine 3-day-ahead statement. On a "
            "mountain stream it is a <b>watch</b>: it says a lot of rain is "
            "falling upstream, not that the stream will rise by any particular "
            "amount at any particular hour.</div>", unsafe_allow_html=True)

    # ═════════════════════ FLOOD-PRONE GROUND ════════════════════════════
    elif view == "Flood-prone ground":
        st.markdown("#### Flood-prone ground — the static half")

        prone = FCLS > 0
        k = st.columns(3)
        k[0].metric("Flood-prone ground", f"{100*prone.mean():.1f}%",
                    "of the mapped state")
        k[1].metric("Channel network",
                    f"{MET['channel_definition']['channel_cells_100m']:,}",
                    f"cells ≥ {MET['channel_definition']['min_upstream_km2']:.0f} km² upstream")
        k[2].metric("Median height above drainage",
                    f"{MET['hand']['median_m_statewide']:.0f} m",
                    "statewide")

        with st.container(border=True):
            M.map_head("Flood-prone ground",
                       "blank means not flood-prone, not missing data")
            box = st.container(height=T.MAP_H + 8, border=False, key="map_shell")
            m = M.base_map(grid, s)
            fg = M.overlay_group(
                grid, s, geo,
                img=None if s.bare else M.rgba_overlay(FCLS, T.CLASS_COLORS),
                districts=s.districts)
            with box:
                st_folium(m, height=T.MAP_H, use_container_width=True,
                          pixelated=True, returned_objects=[],
                          feature_group_to_add=fg, key="flsmap")
            shares = [float((FCLS[prone] == i).mean()) if prone.any() else 0
                      for i in range(1, 6)]
            M.legend_strip(T.CLASS_NAMES, T.CLASS_COLORS, shares,
                           note="share of flood-prone ground · static, no rainfall",
                           bare=s.bare)

        st.markdown("<div class='eyebrow'>How the two ingredients combine</div>",
                    unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([
            {"Ground": "0–5 m above the channel", "Beside a large river":
             "Very High", "Beside a mountain stream": "Low"},
            {"Ground": "5–15 m above the channel", "Beside a large river":
             "High to Moderate", "Beside a mountain stream": "Very Low"},
            {"Ground": "15–25 m above the channel", "Beside a large river":
             "Low", "Beside a mountain stream": "Not flood-prone"},
            {"Ground": "Over 25 m above the channel", "Beside a large river":
             "Not flood-prone", "Beside a mountain stream": "Not flood-prone"},
        ]), width="stretch", hide_index=True)
        st.markdown(
            "<div class='caveat'>A display cell is about 550 m across and "
            "reports its <b>lowest</b> ground, because a floodplain is often "
            "one or two 100 m cells wide and averaging would erase the very "
            "corridor this layer exists to show. The panel on the Forecast page "
            "gives the share of each cell that is actually low-lying.</div>",
            unsafe_allow_html=True)

    # ═════════════════════ CATCHMENTS ════════════════════════════════════
    elif view == "Catchments":
        st.markdown("#### Catchments")

        if not LIVE:
            st.warning("Live rainfall is unavailable, so only the catchment "
                       "boundaries are shown.")
            pct = np.zeros(len(SUB_AREA), np.float32)
            mm = pct.copy()
            area = UP_AREA.copy()
            di = 0
        else:
            notes = [f"{100*x:.0f}% High+" for x in high_share(days[fut[0]])]
            di = M.day_strip("flc", days, fut, notes)
            mm, pct, area = signal(di)

        with st.container(border=True):
            M.map_head("Upstream rain vs normal",
                       "each catchment, including everything draining into it")
            box = st.container(height=T.MAP_H + 8, border=False, key="map_shell")
            m = M.base_map(grid, s)
            fg = M.overlay_group(
                grid, s, geo,
                img=None if s.bare else M.rgba_overlay(wet_raster(pct), WET_COLORS),
                districts=s.districts)
            with box:
                st_folium(m, height=T.MAP_H, use_container_width=True,
                          pixelated=True, returned_objects=[],
                          feature_group_to_add=fg, key="flcmap")
            M.legend_strip(WET_NAMES, WET_COLORS,
                           note="How unusual the upstream rain is — not "
                                "millimetres, and not a river level",
                           bare=s.bare)

        st.markdown("<div class='eyebrow'>What we can and cannot forecast</div>",
                    unsafe_allow_html=True)
        big = area >= fm.LARGE_RIVER_KM2
        k = st.columns(3)
        k[0].metric("Catchments", f"{len(area):,}")
        k[1].metric("Large enough to forecast", f"{int(big.sum()):,}",
                    f"{100*big.mean():.0f}% — over "
                    f"{fm.LARGE_RIVER_KM2:,.0f} km² upstream")
        k[2].metric("Watch only", f"{int((~big).sum()):,}",
                    f"{100*(~big).mean():.0f}%", delta_color="off")
        st.markdown(
            "<div class='caveat'><b>This is the honest headline of the flood "
            "product.</b> Most of Arunachal's rivers are steep mountain streams "
            "below what any global discharge model resolves. For those we can "
            "say a lot of rain is falling upstream — a watch — and no more. "
            "River gauges are the single thing that would turn the watch into a "
            "forecast.</div>", unsafe_allow_html=True)

    # ═════════════════════ METHOD & LIMITS ═══════════════════════════════
    else:
        st.markdown("#### Method & limits")

        st.markdown("##### How the forecast is built")
        st.markdown(
            "- **Where water collects** — every 100 m of ground is measured "
            "against the nearest river channel: how far above it sits, and how "
            "much land drains through that channel. Terrain only, no rainfall.\n"
            "- **How much is coming** — live rainfall at 97 points is pooled "
            f"over {MET['catchments']['n']:,} catchments and carried downstream, "
            "then scored against what is normal *for that catchment*.\n"
            "- **The forecast** — the two multiplied. Near-zero in either term "
            "gives near-zero: dry weather on a floodplain, or a downpour over "
            "ground that water cannot reach, both come out low.")

        v = MET["validation"]
        st.error("**The flood-prone layer is not validated.** "
                 + v["why_rejected"])

        st.markdown("##### We tried, and here is exactly what happened")
        st.dataframe(pd.DataFrame([
            {"Test": "Pixel level — does low ground line up with observed "
                     "flooding?",
             "Result": f"AUC {v['pixel_auc']:.3f}",
             "Reading": "Chance is 0.50. This is chance."},
            {"Test": f"Catchment level — {v['catchment_n']} basins, does a "
                     "flood-prone basin flood more?",
             "Result": f"Spearman {v['catchment_spearman']:+.3f}",
             "Reading": "Zero. No relationship in either direction."},
            {"Test": "Is the reference itself credible?",
             "Result": f"{100*v['reference_on_slope_gt15']:.0f}% of its flooded "
                       f"pixels on slopes over 15°",
             "Reading": "No. Water does not pond on a cliff."},
        ]), width="stretch", hide_index=True)
        st.markdown(
            "<div class='caveat'>Read the third row before the first two. A "
            f"reference that puts {100*v['reference_on_slope_gt25']:.0f}% of its "
            "flooding on slopes steeper than 25° cannot score anything — it is "
            "rendered map tiles, and rendered tiles smear across boundaries. So "
            "the two scores above are evidence about the reference, not about "
            "the terrain. We are showing them rather than quietly dropping a "
            "test that did not go our way.</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='caveat'>What this means in practice: the flood-prone "
            "layer rests on physics that is standard and well understood — "
            "water collects in low ground beside large rivers — and on no "
            "local evidence whatsoever. Treat it as a well-founded hypothesis "
            "about Arunachal, not as a measured fact about it.</div>",
            unsafe_allow_html=True)

        st.markdown("##### What would validate it")
        for w in v["what_would_validate_it"]:
            st.markdown(f"- {w}")

        st.markdown("##### Limits we will not paper over")
        for c in [
            "**No depth, ever.** This says where water collects and when a lot "
            "is coming, not how deep it gets. Depth needs a 2-D hydraulic model "
            "on LiDAR, which is a different project.",
            "**Small streams are a watch, not a forecast.** "
            f"{100*(UP_AREA < fm.LARGE_RIVER_KM2).mean():.0f}% of catchments sit "
            "below the size any global discharge model resolves.",
            "**No dam releases.** Several of these rivers are regulated. A "
            "scheduled release can flood a reach on a dry day and nothing here "
            "would see it coming.",
            "**Rainfall is sampled at ~33 km** and a mountain catchment can be "
            "much smaller than that, so a small basin inherits its neighbour's "
            "weather.",
            "**GloFAS discharge is not in this build.** Two files are on disk "
            "where a climatology needs years of reanalysis. That is a download, "
            "not a permission — and it is the next thing to do.",
        ]:
            st.markdown(f"<div class='caveat'>{c}</div>", unsafe_allow_html=True)

        with st.expander("Data sources"):
            st.markdown(
                "- **Terrain** — Copernicus 30 m DEM, resampled to 100 m\n"
                "- **Drainage and catchments** — HydroSHEDS HydroBASINS v1c, "
                "level 12\n"
                "- **Live rainfall** — Open-Meteo (free tier), 97 points\n"
                "- **Rainfall climatology** — the same Open-Meteo archive, so "
                "live values and history come from one source\n"
                "- **Attempted reference** — Bhuvan aggregated flood extent "
                "2003–2020 (rejected, see above)")

    st.markdown("<div class='app-footer'><b>FloodSense</b>"
                "<span>Flood = flood-prone ground × catchment rain</span></div>",
                unsafe_allow_html=True)
