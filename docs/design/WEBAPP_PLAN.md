# Web app build plan — operational landslide forecast

**Goal:** a deployed, free-hosted web app whose headline is a **7-day landslide
forecast for Arunachal Pradesh**, not a static susceptibility map.

**Date:** 2026-08-02

---

## 1. 🚨 The architectural finding that shaped this plan

The obvious design — susceptibility × trigger, with the trigger computed from
live Open-Meteo rainfall against our IMERG-built climatology — **is silently
broken.** Measured on 1,068 matched cell-days over the 2026 monsoon:

| | Open-Meteo | IMERG |
|---|---:|---:|
| mean mm/day | 12.56 | 7.45 |
| p90 | 33.80 | 18.36 |
| p99 | 67.06 | 56.17 |

**Open-Meteo runs 1.68× wetter, and daily correlation is only 0.320** (0.303 on
3-day sums). A day sitting at the 50th percentile of IMERG climatology is
nowhere near the 50th percentile of Open-Meteo's own distribution.

Feeding one source's values into another source's percentile table produces
confident, wrong numbers — and nothing in the output would look wrong.

### The fix: one source end-to-end

Measured: the **Open-Meteo archive (ERA5) and the forecast API's past data are
identical** — mean ratio 1.00, correlation 1.000. Same source chain.

```
climatology  ← Open-Meteo archive API   (2005 → present)
live forecast ← Open-Meteo forecast API  (today + 7 days)
                        ↑ same source, so percentiles are valid
```

**IMERG stays** for the historical/research pipeline and everything already
validated on it. It is simply not on the live path.

## 2. ⚠️ The validation that must pass before the app is worth building

The trigger scored **AUC 0.768** on 72 dated events *using IMERG features*. With
IMERG and Open-Meteo correlating at only 0.32, **that number does not
automatically transfer.**

**V4 — re-validate the trigger on the same events using Open-Meteo features.**

### ✅ RESULT 2026-08-02 — PASS, and the resolution cost is ~zero

| | AUC | n |
|---|---:|---:|
| hindcast — 11 km IMERG | 0.768 ± 0.098 | 72 |
| **live — 33 km Open-Meteo** | **0.764 ± 0.091** | **84** |

**A difference of 0.004, far inside the noise.** Both the source change (1.68×
bias, r=0.32) and the resolution change (11 km → 33 km, median event 15 km from
its query point) were absorbed with no measurable loss.

Operating points are effectively unchanged: at trigger ≥0.90, **8.3% of monsoon
days flagged, 39.3% of events caught, 4.7× lift** (hindcast: 7.5% / 41.7% / 5.6×).

**Why it survived:** the trigger scores a *percentile*, not a millimetre value.
Percentiles are about rank within a place's own history, and both sources rank
wet days similarly even when they disagree on the absolute total. The storms that
trigger widespread landsliding are synoptic-scale — 33 km sampling still sees them.

⚠️ This does **not** mean resolution never matters. It means it does not matter
*for this metric on these 84 events*. A single valley-scale cloudburst is exactly
what 33 km would miss, and 84 events is too few to contain many of those. The
upgrade paths in [RAINFALL_RESOLUTION_LIMITS.md](RAINFALL_RESOLUTION_LIMITS.md)
remain worth taking.

*Bonus:* 84 usable events vs 72, because the Open-Meteo grid covers events that
fell outside an IMERG land cell.

## 3. Build order

| # | Step | Output |
|---|---|---|
| **F1** | Fetch Open-Meteo archive, 892 cells, 2005→present | `data/interim/rainfall_om/` |
| **V4** | 🚨 Re-validate trigger on 72 events with Open-Meteo | pass/fail gate |
| **B1** | Export web bundle | `webapp/assets/` (~5 MB) |
| **B2** | Streamlit forecast app | `webapp/app.py` |
| **B3** | Deploy free + link | public URL |

### F1 sizing — ⚠️ revised after hitting the real limit

First attempt asked for **892 cells × 7,900 days ≈ 7 M location-days** and hit
`"Hourly API request limit exceeded"`. Open-Meteo weights requests by
locations × days, so the original plan was never going to fit.

Measured limits:

| request | result |
|---|---|
| 25 locations × 1,461 days | 200 OK, 2.3 s |
| 50 locations × 1,461 days | 200 OK, 9.9 s |
| 100 locations | 429 — minutely limit |
| ~40 locs × 6 yr, repeated | 429 — **hourly** limit |

**The live app matters more than the fetch.** A one-time climatology download can
be slow, but 892 points would need ~23 API calls *per refresh* — a two-minute
wait for the first visitor. That is the binding constraint.

**Revised: a ~0.3° query grid (~120 points across the state).**

| | |
|---|---|
| Climatology fetch | 120 pts × 16 yr (2010–2025) ≈ 20 calls — comfortable |
| Live forecast call | **3 calls, ~10 s**, cached — good UX |
| Trade-off | rainfall input at ~33 km spacing, vs 11 km IMERG in the hindcast |

⚠️ **This resolution loss must be stated in the app.** The hindcast (AUC 0.768)
used 11 km IMERG; the live forecast uses ~33 km sampled Open-Meteo. The live
product is therefore expected to be *somewhat weaker* than the hindcast number,
and V4 measures how much.

### B1 bundle contents

| file | content | size |
|---|---|---|
| `susceptibility.npz` | uint8 @ 500 m, 255 = not assessed | ~0.8 MB |
| `imerg_index.npz` | cell id per 500 m pixel | ~1.5 MB |
| `clim_quantiles.npz` | **101 percentile breakpoints per cell** for r3/r7 | ~0.7 MB |
| `cells.json` | lon/lat of each cell — drives the live API call | small |
| `districts.geojson`, `boundary.geojson` | simplified | ~0.1 MB |
| `metrics.json` | the honest numbers | small |

Shipping quantile **breakpoints** rather than raw climatology is what keeps this
at 0.7 MB instead of 17 MB.

## 4. App design — forecast first

```
┌──────────────────────────────────────────────┐
│  TODAY'S ALERT      statewide level + drivers │
├──────────────────────────────────────────────┤
│  ▸ 7-DAY FORECAST   day selector             │
│    map (hazard)  +  district alert table     │
├──────────────────────────────────────────────┤
│  Susceptibility     supporting layer, toggle  │
│  Methodology        honest numbers + limits   │
└──────────────────────────────────────────────┘
```

**Horizon: 7 days.** Open-Meteo offers 16, but rainfall skill degrades sharply
past ~3 days. Days 1–3 are presented as the confident window; 4–7 explicitly
marked lower confidence. Showing 16 would look better and be partly dishonest.

## 5. Taken from SlopeSense — and deliberately not

| Take | Why |
|---|---|
| Colour scheme & CSS design language | real effort went into it; restyling from zero is wasted work |
| Deployment architecture (git-committed bundle + slim deps, no GDAL) | proven on the free tier |
| Open-Meteo call pattern + graceful degradation on API failure | already solved |
| Safety disclaimer, CSV download, tile-host preconnect | small, sensible polish |

| Leave | Why |
|---|---|
| `risk_rules.py` heuristic (`0.6·past3d + next48h`, fixed mm) | superseded by the calibrated trigger; fixed mm thresholds over-alert the wet south and under-alert the dry north |
| Susceptibility-centric information architecture | our product is a forecast that changes daily |
| Equal-quintile class breaks (20% "Very High") | ours concentrates: 3% of area holds 40% of slides |
| Rainfall as a *static* susceptibility feature | keeps WHERE and WHEN cleanly separated |

## 6. Non-negotiables

- **Out-of-domain cells render "not assessed", never "low risk"** — the model never saw glaciers.
- **Score is a relative index, not probability of failure.** Presence-only data; there is no denominator.
- **11 km rainfall must be labelled as such** — the map has 100 m terrain detail and 11 km weather detail, and viewers will assume otherwise.
- **Not for operational safety decisions**, stated in the UI.

---

## 7. Revision — the location-first Forecast page

A forecast is only useful *somewhere*. The first build opened on a statewide
banner ("15.6% of assessed land at High+"), which is a management number: it
describes ground nobody stands on. The page was restructured around one
location, and the statewide picture moved to a view of its own.

### 7.1 Information architecture

| View | Question it answers | Audience |
|---|---|---|
| **Forecast** | What is the outlook *where I am*? | anyone |
| **Statewide** | Which districts need resources this week? | APSDMA operations |
| Susceptibility | Where are slopes weak, regardless of weather? | planning |
| Evidence | What is this built on? | procurement |
| Model & Validation | How good is it, honestly? | technical review |

The statewide alert band, the four trigger KPIs and the district table moved
wholesale to **Statewide**. Nothing was deleted.

### 7.2 The search index

One box replaces the old "Jump to" town dropdown, and accepts three kinds of
input:

| Input | Count | Source |
|---|---:|---|
| Districts | 18 | `districts.geojson` |
| Settlements | 4,648 | APSSDI settlements layer |
| Named anchors | 18 added | hand-entered, see below |
| Raw coordinates | ∞ | `st.selectbox(accept_new_options=True)` |

**The gazetteer has a hole at the top.** APSSDI's settlements layer is a village
register: excellent at village level, and missing **Itanagar** — the state
capital — along with Yingkiong, Yupia, Koloriang, Longding, Roing town and Ziro
town (it carries only "Old Ziro" and "Ziro Point"). A search box that cannot
find the capital is broken, so `geo.ANCHORS` names the capital and the district
headquarters explicitly.

An anchor is suppressed only when the gazetteer already holds a same-named place
**within 12 km**. Matching on name alone was the first attempt and it was wrong:
three unrelated villages called *Roing* hid the district headquarters 100 km
away. 18 of 22 anchors survive that test; the other four (Dirang, Deomali,
Jairampur, Yupia) were already present.

Name collisions are resolved rather than dropped — 180 names are shared by two
or more villages, so duplicates carry their coordinates in the label, and the
six pairs that also round to the same 2 dp get a numeric suffix. Every one of
the 4,648 gazetteer rows stays reachable.

### 7.3 Snapping to assessed ground

**12.1% of settlements (565 of 4,648) sit on a cell scored 255** — valley floors,
riverbanks, anything flatter than 10°. Pasighat, Along, Roing and Miao are all
among them. Returning "not assessed" for those searches is a dead end, and it is
also physically misleading: what threatens a valley town is the slope *above*
it, not the flat ground it stands on.

So a searched location snaps to the nearest scored cell within ~5.5 km, and the
UI **says so, with the distance**. Silently relocating someone's forecast would
be the dishonest version of this. The click inspector deliberately does *not*
snap — a click on a river should say "not assessed", because that is what the
user asked about. Where nothing is assessed within range (mid-river, high
snowfield), the answer is still "not assessed".

### 7.4 Geolocation without a dependency

The page asks the browser for the visitor's position on first load. This is
**not** a Python package: a small script writes the answer into the page's query
string and reloads, so the deploy stays at seven pure-Python requirements.

Every outcome — allowed, refused, timed out, unsupported — writes a `geo` flag,
and that flag is what stops the request repeating on every rerun; a session
flag backs it up in case the browser blocks the iframe from navigating. A
visitor outside Arunachal is told so plainly and the page opens on Itanagar,
rather than silently forecasting the nearest edge pixel.

### 7.5 Map layers

The map moved back to the top of the card, SlopeSense-style, with a segmented
control over three genuine layers of the same surface:

- **Hazard** — susceptibility × trigger, green→red
- **Rain trigger** — how unusual the rain is for each place, **blue** ramp
- **Susceptibility** — the static half, green→red

The rain ramp is deliberately blue. The two layers sit under one control, and
reusing the hazard ramp for both would make "very wet" and "very dangerous" look
like the same statement.

### 7.6 Bug found while rebuilding

`Model & Validation` was reading `operating_points[i]['capture']`; the key
written by `trigger.py` is `event_capture`. **The page had been raising
`KeyError` on every load.** Its prose also hardcoded "84 dated landslides" while
the metric card beside it read `n_events = 72` — 84 is what the catalogue holds,
72 is what survives the filters and actually trains the trigger. Both now read
from `metrics.json`, so they cannot drift apart again.
