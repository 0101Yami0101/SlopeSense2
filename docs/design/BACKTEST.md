# P11 — Operational backtest: what the system would actually have said

**Date:** 2026-08-03 · **Script:** [backtest.py](../../scripts/model/backtest.py) ·
**Data:** `reports/backtest.{json,png}`

Run on the **live data path** (Open-Meteo, 97 points, 2010–2026), not the IMERG
hindcast — so these numbers describe what the deployed app would have done, not
what a lab version could have done.

---

## 1. The finding that matters most — the warning arrives early

AUC says the system can rank days. It does not say whether the signal exists
*before* the slope fails. That had never been tested. It has now.

Median trigger score around the 84 dated landslides:

| when | median trigger | share at/above 0.90 |
|---|---:|---:|
| 5 days before | 0.754 | 21% |
| 4 days before | 0.728 | 25% |
| 3 days before | 0.713 | 20% |
| 2 days before | 0.775 | 24% |
| **1 day before** | **0.843** | 36% |
| **event day** | **0.863** | 39% |
| 1 day after | 0.842 | 39% |
| *ordinary monsoon day* | *0.499* | — |

**Even five days out, conditions at the failure site are already far above a
normal monsoon day (0.75 vs 0.50).** The signal then sharpens as the event
approaches.

**Why:** landslides here follow *sustained wet spells*, not isolated flash
storms. The ground saturates progressively, so the danger builds over days — and
our 3-day and 7-day rainfall features are built to see exactly that.

⚠️ **Honest caveat:** wet spells are autocorrelated. "Day −5 was wet" and "event
day was wet" are not independent observations. The elevated early signal partly
reflects that persistence rather than genuine 5-day predictive skill. What it
does establish is that **risk is elevated across a multi-day window**, which is
how the forecast should be used — not as a single-day pinpoint.

---

## 2. Alert frequency vs coverage — the real operational choice

**Localised alerts** (per rainfall cell — what the app does):

| alert when trigger ≥ | % of cell-days alerting | % of known landslides caught |
|---:|---:|---:|
| 0.75 | 22.7% | 63% |
| **0.90** | **7.9%** | **39%** |
| 0.95 | 3.5% | 29% |
| 0.99 | 0.6% | 1% |

**Statewide alerts** (fires if *any* point crosses):

| threshold | alert days per year | % caught |
|---:|---:|---:|
| 0.75 | 142 | 63% |
| 0.90 | 96 | 39% |
| 0.95 | 63 | 29% |

> **Statewide alerting is close to useless here.** Arunachal is 550 km wide and
> the monsoon runs six months — *somewhere* is always wet, so a statewide trigger
> fires ~96 days a year. **Alerts must be localised**, which is why the app maps
> them rather than issuing one state-level number.

**There is no free lunch in this table.** Catching 63% means alerting on nearly a
quarter of all cell-days. Catching 29% means alerting on 3.5%. Where to sit is a
policy decision about the cost of a missed slide versus the cost of an ignored
warning — not something the model can decide.

The 0.99 row is a warning in itself: pushed that far the threshold catches almost
nothing. Extreme rarity is not the same as extreme usefulness.

---

## 3. 🚨 What this backtest deliberately does NOT report

**There is no false-alarm rate here, and any number claiming to be one would be
fiction.**

An alert day with no recorded landslide might mean the system cried wolf — or it
might mean a slope failed in an empty valley and nobody wrote it down. We hold
**84 dated landslides across 16 years**. The true count is orders of magnitude
higher.

Absence of a record is not absence of an event. So we report:

- ✅ **alert frequency** — a real, measurable operational cost
- ✅ **capture rate** — share of *known* events caught
- ❌ **precision / false-alarm rate** — not measurable with this data

This is the same presence-only limitation that runs through the whole project.

---

## 4. Cross-check: the where-model is doing real work

Susceptibility at the places that actually failed: **median 0.161**, against a
statewide median of **0.047** — a 3.4× concentration.

The two halves are contributing independently, which is the point of multiplying
them rather than relying on either alone.

---

## 5. What this means for the deliverable

**This is a forecast, not a report.** The signal is present days ahead, which is
what makes the 7-day product legitimate rather than decorative.

**Alerts must be local.** A statewide number would fire a third of the year.

**The threshold is the client's call.** Present the trade-off table, recommend
~0.90 as a starting point (8% of cell-days, 39% of known slides), and let APSDMA
weigh the costs.

**Never quote a false-alarm rate.** If asked, explain why it cannot be measured —
that answer is more credible than a fabricated number, and it is the honest one.
