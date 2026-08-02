# Rainfall resolution — the limit, what it costs, and how to lift it

**Date:** 2026-08-02
**Short version:** the free web app samples rain at ~33 km. The hindcast used
11 km. This is a **hosting/budget limit, not a science limit** — the full-detail
system already exists locally, and every upgrade path below restores it.

---

## 1. Where the limit comes from

Two separate ceilings, and it matters which is which.

| Ceiling | Value | Can we lift it? |
|---|---|---|
| **How much we're allowed to ask for** | Open-Meteo free tier: hourly request cap, weighted by locations × days | ✅ yes — paid tier or another source |
| **How fine the weather model itself is** | global models resolve ~9–25 km over India | ⚠️ partly — only with a national/regional model |

We are currently well *below* both. We sample 97 points at ~33 km spacing when the
underlying model already resolves finer than that. **So the first upgrade is free
detail we are simply not collecting yet.**

### Why we're at 97 points

| Grid | Points | Live API calls per refresh | First-visit wait |
|---|---:|---:|---|
| 0.2° (~22 km) | 219 | 6 | ~20 s |
| **0.3° (~33 km)** ← current | **97** | **3** | **~10 s** |
| 0.4° (~44 km) | 54 | 2 | ~7 s |
| IMERG-native (11 km) | 892 | 23 | **~2 min** ❌ |

The binding constraint was never the download — it was that a public web page
cannot make a visitor wait two minutes.

## 2. What the limit actually costs

**What is lost:** a storm sitting over a single narrow valley can fall between
sample points and be under-represented. In terrain with 3,000 m of relief and
rainfall ranging 799 → 4,167 mm/yr across the state, that is a real gap.

**What is *not* lost — and this is most of the value:**

- The **where** half is untouched. Susceptibility uses terrain, soil, rock and
  land cover — **no rainfall at all**. AUC 0.860 stands.
- **Per-place comparison survives.** We still ask "is this unusual *for here*"
  rather than applying one millimetre threshold statewide. That was always the
  main methodological gain over a fixed-threshold app, and coarser sampling does
  not weaken it.
- **The 7-day horizon is unaffected.**
- The map's fine texture comes from 100 m terrain, which is real detail.

⚠️ **What we do not know yet:** the trigger scored AUC 0.768 on 11 km IMERG. The
V4 gate measures what it scores on the coarser live source. Until that runs, the
size of the accuracy cost is unmeasured — do not assume it is small.

## 3. Upgrade paths

Ordered by effort. Costs are indicative — **verify current pricing before quoting.**

### A. Sample more points on the same free tier — *free, immediate*

Move 0.3° → 0.2° (97 → 219 points, ~22 km). Costs ~6 live calls instead of 3 and
about 10 s more on first load; aggressive caching hides most of it.

**Do this first.** It is free detail we are leaving on the table. The only reason
it is not already done is that the free tier's hourly cap made the initial
climatology fetch slow.

### B. Open-Meteo paid API — *low cost, restores full detail*

Paid tiers lift the request cap and permit commercial use. That allows querying
all **892 points at 11 km**, matching the hindcast exactly — so the live product
would inherit the validated 0.768 rather than an unknown reduction.

Also removes the non-commercial restriction on the free tier, which matters if
this ever ships to a paying client.

### C. Our own IMERG pipeline — *restores 11 km, but only for "now", not "ahead"*

We already hold 26 years of IMERG and a working fetcher. A small scheduled job
could compute the trigger at full 11 km daily.

⚠️ **Critical limit: IMERG is *observed* rainfall with a 3–4 day lag.** It can
power a "conditions right now" product at full resolution, but it **cannot
forecast**. A forecast needs a weather model. So this complements the forecast,
it does not replace it.

### D. Alternative forecast sources — *free, more work*

| Source | Resolution over India | Notes |
|---|---|---|
| **ECMWF open data** | ~0.25° | Generally the strongest global forecast model; open dataset published since 2024 |
| **NOAA GFS** | ~0.25° | Free, keyless via NOMADS, long-established |
| **NCMRWF** (India) | finer over India | India's national modelling centre — regional models beat global ones here |
| **IMD** | finer over India | Official national forecasts; access likely needs a formal agreement |

**For a government deployment, the Indian national sources (C/D) are the real
prize** — regional models resolve Himalayan terrain far better than any global
model, and a state government is exactly the party able to obtain them.

### E. Run it on a real server — *removes the web-page constraint entirely*

The 97-point limit exists because a *visitor* triggers the API call. If a
scheduled job computes the forecast every few hours and writes the result to a
file the page just reads, resolution stops being tied to page-load time. Cheap
hosting (or a free scheduled runner) makes 892 points perfectly viable.

**This is the highest-leverage architectural fix** and does not require paying
for weather data at all.

## 4. Recommendation

| Stage | Action | Cost |
|---|---|---|
| **Now (free MVP)** | ship at 0.3°, state the limit plainly in the UI | free |
| **Quick win** | go to 0.2° (219 points) | free |
| **Best free fix** | precompute on a schedule (E), then 892 points | ~free |
| **If commercial** | Open-Meteo paid tier (B) — removes the licence issue too | low |
| **For the client** | NCMRWF / IMD regional model (D) | an ask |

> ⚠️ Whatever the resolution, the app must keep saying that rainfall is coarse
> and terrain is fine. A viewer sees crisp 100 m detail and will assume the
> weather is that sharp. It is not, at any of these tiers.
