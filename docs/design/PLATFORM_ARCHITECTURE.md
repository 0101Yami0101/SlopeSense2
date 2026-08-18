# Platform architecture — the data backbone, and where it is going

> **Status: the left half is built, the loop is not.**
> Written 2026-08-17. Rendered for visitors on Data Backbone → Pipeline.
> Companion docs: [DATA_CONTRACT.md](DATA_CONTRACT.md) (grid + provenance
> rules), [FLOOD_MODULE.md](FLOOD_MODULE.md), [ROADMAP_LANDSLIDE.md](ROADMAP_LANDSLIDE.md).

## The target

```
  SOURCES              RAW HUB           PROCESSING          PROCESSED HUB          SERVE
┌───────────┐      ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐   ┌─────────────┐
│ external  │─────▶│ raw store   │──▶│ align        │──▶│ analysis-ready   │──▶│ SlopeSense  │
│ archives  │      │ (immutable) │   │ feature      │   │ (grid, features) │   │ FloodSense  │
│ own       │─────▶│ partner     │   │ model        │   │ model outputs    │   │ public API  │
│ sensors   │      │ intake      │   │              │   │ (forecasts)      │   │ other apps  │
└───────────┘      └─────────────┘   └──────────────┘   └──────────────────┘   └─────────────┘
       ▲                                                                              │
       │                                                                              ▼
       └──────────── outcome log ◀──── verification ◀──── forecast archive ────────────┘
                    (what actually happened)
```

Two things distinguish this from the first sketch, and both matter:

1. **The processed hub is two shelves, not one.** Analysis-ready data is
   hazard-agnostic and shared; model outputs are product-specific and derived.
   Different audiences, different update cadence, different licence footing. An
   external consumer wants one or the other, never both.
2. **The return path exists.** More data flowing in makes a forecast *fresher*.
   Only knowing what actually happened makes it *better*. Without the bottom
   lane this is a pipeline, not a loop.

## What is built today — measured, not claimed

| Layer | State | Evidence |
|---|---|---|
| External archives | **built** | 24 sources, 11 groups, 10,572 files, 8.06 GB |
| Raw store | **built** | `data/raw/`, never edited in place; every fetch writes source, licence, URL, fetch date and a checksum to `_SOURCES.json` |
| Align | **built** | one canonical grid: EPSG:32646, 100 m, 8,202,343 in-state cells |
| Feature | **built** | 34 columns per cell (terrain, soil, geology, land cover, hydrology, distances) |
| Model | **built** | LightGBM susceptibility (spatial-CV AUC 0.859) + percentile trigger; 9,555 days of rainfall history |
| Analysis-ready shelf | **built** | `data/interim/grid_100m/` (~966 MB parquet), `interim/terrain`, `interim/features`, `interim/rainfall` |
| Model-output shelf | **built** | `data/processed/` surfaces, `models/`, and the web bundles in `webapp/assets/` (4.60 MB total) |
| SlopeSense | **built** | live |
| FloodSense | **built** | live; static layer unvalidated by design, see FLOOD_MODULE.md |
| **Own sensors** | *planned* | nothing ingested |
| **Partner intake** | *planned* | no write path, no quarantine |
| **Public API** | *planned* | no service boundary at all — the app reads files off disk |
| **Other apps** | *planned* | no external consumers |
| **Forecast archive** | *planned* | **nothing is being recorded** |
| **Outcome log** | *planned* | nothing |
| **Scheduling** | *planned* | pipeline is run by hand, one stage at a time |

The honest summary: **a strong pipeline, not yet a loop.** The flywheel is
drawn but not attached.

## The plan, in the order it should happen

### 1. Forecast archive + outcome log — do this first
Append, once a day: what was forecast, for where, on what day, from which
input version. Then the simplest possible way to record what actually
happened — a district officer's confirmation, a road-block log line, a dated
news report.

**Why first, ahead of everything below:** it is the only item on this list that
is *time-sensitive*. An API can be built in any month. Yesterday's forecast is
gone forever if nobody wrote it down. Every day without this destroys evidence
permanently — and validation is exactly where both products are thinnest
(SlopeSense's timing model rests on ~72 dated events; FloodSense's static layer
has no local validation at all, because the only available reference put 70.5%
of its flooded pixels on slopes over 15°).

It is also the cheapest thing here: a daily snapshot and an append-only file.

### 2. Automate the pipeline run
Scheduled fetch → build → export, with the rainfall step incremental rather
than a full rebuild. **Before the API, not after:** an API serving a hub last
refreshed by hand three weeks ago is worse than no API, because the staleness
is invisible to whoever is consuming it.

### 3. Make every output record its inputs
Each published surface and forecast stamped with the input versions and the
code revision that produced it. Raw is already immutable and checksummed, which
is half the job; this is the other half, and it is what makes "reproduce the
forecast you issued last Tuesday" answerable.

### 4. Read-only public API — two shelves, separately
Analysis-ready and model outputs as distinct products with distinct terms.
Read-only first; auth, rate limits and a versioned contract from day one.

> ⚠️ **Licence gate before this ships externally.** Some inputs carry
> redistribution terms (Open-Meteo's free tier is non-commercial; the GSI
> inventory's terms are unresolved). Redistributing derived data to third
> parties inherits those constraints. This is a commercial blocker on the
> "other apps" path, not a technical one, and it needs answering before the
> path opens — not after a partner has built on it.

### 5. Partner write path, with quarantine
Field reports and confirmations from districts or partners are the highest-value
feed for step 1 — but they must land in a staging area, be validated and carry
their own provenance before joining authoritative data. One bad partner feed
contaminating the layer the forecasts are built on is very hard to undo.

### 6. Sensor ingest
A genuinely different animal from batch archives: continuous, drifting, prone
to dropout, needing calibration tracking. Its own path, not the same door as a
downloaded archive. PAID-tier capability — see the tier notes in the roadmap.

## The rule this architecture keeps

Raw is append-only and immutable. Processing is reproducible from raw. Every
published figure is measured from what actually shipped, never typed in. The
Data Backbone module enforces the last one on itself: its Pipeline tab reads
its numbers from the bundle, and marks anything on this page that is *planned*
as planned rather than drawing it as though it exists.
