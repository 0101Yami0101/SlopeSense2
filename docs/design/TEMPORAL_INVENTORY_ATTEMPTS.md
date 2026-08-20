# Enlarging the temporal landslide inventory — everything we tried

**Purpose:** a complete, client-facing record of how we attacked the project's
single hardest constraint, what each attempt cost, and exactly where it failed.
Written so it can be explained to APSDMA without re-deriving anything.

**Last updated:** 2026-08-02

---

## 1. The constraint in one paragraph

A landslide forecast must answer two questions: **where** can a slope fail, and
**when** will it. We have excellent data for *where* — **37,788 mapped landslide
polygons**, which produced a susceptibility model scoring **AUC 0.860**. We have
almost nothing for *when*: only **90 landslides carry a date**, and 72 of those
line up with a rainfall grid cell.

That is a **three-orders-of-magnitude** gap between the two halves of the same
system. Every attempt below was aimed at closing it.

---

## 2. What we started with

| Source | Records | Dates? | Verdict |
|---|---:|---|---|
| GSI National Landslide Inventory | 26,459 polygons | **none** | spatial only |
| Bhuvan / NRSC 2014, 2017, 2023 | 11,329 polygons | survey year only | **not failure dates** — see §3 |
| NASA Global Landslide Catalog | 99 points | **90 dated**, 2008–2018 | the entire temporal set |

---

## 3. Attempt 1 — Use Bhuvan's year labels as event dates

**Idea:** Bhuvan mapped landslides in 2014, 2017 and 2023. If those are annual
event catalogues, that is 11,329 dated events — a 125× increase.

**Test:** for the cells that failed in each inventory year, rank that year's
monsoon severity against all 25 monsoons *at those same cells*. A real event year
should stand out.

**Result:** 2017 ranked **#3 of 25** (a genuine signal). But 2014 ranked **#12** —
mid-pack. Inspecting the data explained why: every polygon in the 2014 file reads
`Year=2014, Activity=Active`, and the 2023 file separately flags **914
"Reactivated"** slides that first failed earlier.

**Initial conclusion (2026-08-02, morning): ❌ mapping campaigns, not event catalogues.**

## 3b. ⚠️ REVERSED the same day — the year IS the event year

The conclusion above was **wrong**, and the evidence that overturned it is decisive.

### Evidence 1 — the three inventories barely overlap

If each campaign re-mapped everything visible (a cumulative snapshot), the same slides
would reappear each time. Measured, with a 50 m tolerance:

| comparison | slides reappearing |
|---|---:|
| 2014 → 2017 | 125 of 3,029 (**4.1%**) |
| 2014 → 2023 | 130 of 3,029 (**4.3%**) |
| 2017 → 2023 | 199 of 4,708 (**4.2%**) |

~4%, where a cumulative re-survey would give 60–90%.

### Evidence 2 — it is not different survey areas either

The obvious alternative — each campaign covering different districts — is ruled out:

| | 2014 | 2017 | 2023 |
|---|---|---|---|
| districts | 16 | 20 | 25 |
| extent | 541×267 km | 525×274 km | 551×275 km |
| slides in the 15 shared districts | 2,968 | 4,305 | 2,241 |

**Same ground, three times, different slides.**

### Evidence 3 — APSAC says so explicitly

The 2023 inventory is the **SILAAS project** (Satellite Integrated Landslide Assessment
and Alert System), run by **APSAC — the Arunachal Pradesh Space Application Centre**,
Department of Science & Technology, Government of Arunachal Pradesh. From their own
project page (`srsac.arunachal.gov.in/silaas.php`):

> *"To prepare landslide inventory for **post monsoon 2023**… To generate a detailed
> database on **landslides occurred during 2023**"*

Method: Resourcesat-2A LISS-IV (5.8 m) + CartoDEM, **ground-verified with the FLIM
mobile app**.

**Post-monsoon inventory of landslides that occurred that year — field verified.**

### ✅ Revised conclusion

**We hold ~11,329 landslides dated to a monsoon season, with field-verified locations** —
not 72 dated events and nothing else.

| | resolution |
|---|---|
| NASA GLC (72 usable) | **a day** — but km-level locations |
| **Bhuvan/SILAAS (11,329)** | **a monsoon season (~6 months)** — precise, field-verified locations |

⚠️ **Honest limits.** A 6-month window is still not a day, so this does not directly train
a daily trigger. And one loose end remains: 2014's monsoon ranked only #12 of 25 for
rainfall (§3), which sits awkwardly with 3,029 slides occurring that year. The 2023
methodology is confirmed; 2014/2017 are Bhuvan products whose methodology we have **not**
verified and may differ — most plausibly 2014 was a baseline year.

**Cost:** ~2 hours across both passes.

---

## 3c. ❌ Weak supervision on the season labels — TESTED, FAILED

§3b ended by claiming these season labels could be narrowed to candidate storm days,
"backed by real data rather than hope." **That claim was untested when written. It has now
been tested and it does not hold.**

**Test — hold place fixed, vary time.** At a single IMERG cell, across the 2014 / 2017 /
2023 monsoons: does the wetter season carry more landslides? Susceptibility cannot
confound this, because the location is identical in all three.

Rainfall genuinely differed between the years (per-cell max/min ratio 1.50; AOI-mean peak
7-day rain 324 / 420 / 374 mm), so there was signal available to find.

| test | r3 | r7 | storm_id_ratio | chance |
|---|---:|---:|---:|---:|
| raw counts, worst year = wettest year | 34.9% | 34.9% | 38.8% | 33.3% |
| **share of year** (survey effort removed) | **26.9%** | **29.5%** | **34.4%** | 33.3% |
| **cells failing in exactly ONE year** | **24.9%** | **23.4%** | **25.4%** | 33.3% |

Mean within-cell correlations: −0.140, −0.032, +0.009.

**At or below chance once survey effort is removed.** Below-chance is itself informative —
it points to landslide counts being driven by *how much surveying happened in that
district that year*, not by how much it rained.

**Conclusion: ❌ the season labels do not carry extractable timing information.** Two
plausible reasons, and we cannot separate them:

1. **Survey coverage varies by district and year** in ways we cannot normalise out. The
   ~4% overlap (§3b) proves the campaigns mapped *different slides*; it does not prove they
   mapped *all* slides in a season.
2. **Seasonal totals may simply not predict seasonal counts.** Landslides are caused by
   specific storms hitting specific already-weakened slopes — an aggregate over six months
   may genuinely wash that out.

### What survives from §3b, and what does not

| claim | status |
|---|---|
| The three inventories map different slides (~4% overlap, same ground) | ✅ **holds** |
| APSAC describes 2023 as *"landslides occurred during 2023"*, field-verified | ✅ **holds** |
| Therefore the labels can be narrowed to candidate trigger days | ❌ **refuted by test** |

The dataset is still 11,329 precisely-located landslides and remains valuable for the
**where** half. It does **not** rescue the **when** half.

**Cost:** ~1 hour. **Value:** stopped a weak-supervision pipeline that would have trained on
noise — and caught an over-claim before it reached a client deck.

---

## 4. Attempt 2 — Train a machine-learning trigger on the 72 events anyway

**Idea:** maybe 72 is enough if the features are good.

**Test:** fit a logistic model on six rainfall features, validated with 5-fold
cross-validation, against 20,000 ordinary monsoon days at the same locations.
Compare to a simple unfitted rule.

**Result:**

| approach | accuracy (AUC) |
|---|---:|
| fitted model, 6 features, cross-validated | 0.755 |
| **simple unfitted rule (3-day + 7-day rain percentile)** | **0.768** |

**Conclusion: ❌ the machine-learning model performed *worse* than not using
one.** With 72 examples it memorises quirks of those specific events instead of
learning a general pattern.

> This is why the shipped trigger is a transparent rule, not a model. It is more
> accurate *and* explainable to a government reviewer — a rare case where the
> simple option wins on both counts.

**Cost:** ~2 hours. **Value:** avoided shipping something less accurate and
harder to defend.

---

## 5. Attempt 3 — Recover dates from optical satellite imagery ❌ **VETOED**

**Idea:** a landslide scar appears in satellite photos at a specific moment.
Detect when each of our 37,788 scars first appeared and we manufacture our own
dated inventory. This was the highest-leverage idea in the project.

**Test:** take the 45 landslides whose dates we *already know* that fall in the
Sentinel-2 era, and ask the Copernicus catalogue how much cloud-free imagery
exists either side of each. *If we cannot recover dates we already have, we
cannot discover dates we don't.*

**Result:**

| cloud tolerance | median date uncertainty | within 14 days |
|---|---:|---:|
| ≤20% (what detection really needs) | 160 d — and 80% of events have no usable pair at all | 0% |
| ≤40% | 80 d | 3% |
| ≤80% (most permissive possible) | **55 d** | 2% |

A daily forecast needs **≤7 days**. The best case is **~8× short**.

**Root cause:** 86% of landslides here occur May–October — peak monsoon, peak
cloud. **The imagery we need is exactly the imagery hardest to get.** And because
it rained heavily throughout an 80-day window, such a date could not identify
which storm was responsible even if we had it.

**Conclusion: ❌ physically dead for optical.** No model fixes it; the information
is not in the imagery.

**Cost: ~20 minutes.** **Value: prevented ~2 weeks** building a detection system —
including the project's only neural-network component — that would have failed
only *after* it was working, when its dates turned out 80 days wide.

📄 Full evidence: [PX0_CLOUD_FEASIBILITY.md](PX0_CLOUD_FEASIBILITY.md)

---

## 6. Attempt 4 — The same idea with radar instead ✅ **PASSED**

**Idea:** radar penetrates cloud. Sentinel-1 images through the monsoon exactly
as well as through the dry season, so the thing that killed Attempt 3 does not
apply.

**The risk:** radar looks *sideways*, so steep slopes are lost to **layover**
(image folds over itself) or **shadow** (never illuminated) — and both happen on
exactly the steep ground where landslides are. We expected this to be fatal.

**Test:** revisit frequency from the catalogue, plus layover/shadow computed on
our own elevation model across all 91,610 mapped landslide cells.

**Result:**

| | requirement | measured | |
|---|---|---|---|
| gap between views | ≤14 d | **4–5 d** | ✅ |
| landslide cells viewable | ≥60% | **99.4%** | ✅ |

The geometric fear was **overstated**: only 7.6% layover on the ascending pass and
3.6% on descending, and because the two passes look at opposite sides, nearly
every slope is visible from one of them.

**Conclusion: ✅ the data gate is cleared.** Against optical's 55–80 days, radar
gives 4–5 — roughly **15× better**, and comfortably inside requirement.

> ⚠️ **This proves the satellite can see the slope often enough. It does not yet
> prove a model can spot a scar in radar**, which is harder than in optical
> (speckle noise; soil moisture and vegetation changes mimic landslides). The next
> gate, **PX0c**, tests detection itself on landslides with known dates. If that
> fails, this route ends there too.

**Cost:** ~30 minutes.

📄 Full evidence: [PX0B_SAR_FEASIBILITY.md](PX0B_SAR_FEASIBILITY.md)

---

## 6b. Attempt 5 — Can radar actually *see* a scar? ❌ **VETOED**

**Idea:** Attempt 4 proved the satellite looks at the right places often enough.
This asks the next question — is the image clear enough to recognise a landslide?

**Test:** take landslides that definitely exist (our precisely mapped polygons)
and check whether radar can tell them apart from the hillside immediately around
them. Controls matched for steepness, so we measure the *scar*, not the slope.
Dry-season images only — the clearest conditions available.

**Result: no.** Across four independent images:

| radar channel | score (0.50 = pure chance) |
|---|---:|
| VV | 0.526 |
| VH | 0.533 |
| VH/VV | 0.516 |

Larger landslides were no easier to see (0.568 → 0.536 → 0.511 as size increases),
so this is not something a sharper sensor would fix. The difference points the
right way physically — scars are slightly darker, as bare ground should be — but
it is far too small to work with.

**And the decisive test could not be run at all.** The real question is whether
radar changes *at the moment* a slope fails. To check that we need landslides that
are both **precisely located** and **already dated** — and we have neither
combination:

| our data | precise location | known date |
|---|---|---|
| GSI / Bhuvan polygons (37,788) | ✅ | ❌ |
| NASA points (90) | ❌ | ✅ |

**That is circular.** The whole point of the exercise was to generate dates — but
validating it would require dates we already trust. The label shortage blocks not
only the solution but the means of testing it.

**Conclusion: ❌ vetoed for the MVP.** Not "radar is impossible" — "radar cannot be
proven with the evidence we can obtain." Reviving it needs precisely-located dated
landslides first, most plausibly from GSI — which, if it arrives, likely solves
the original problem directly and makes radar dating unnecessary.

**Cost:** ~1 hour.

📄 Full evidence: [PX0C_SAR_DETECTION.md](PX0C_SAR_DETECTION.md)

---

## 7. Routes not yet attempted

### ⚠️ Correction 2026-08-02 — GSI `Landslidedata_1` will probably NOT fill the gap

Earlier drafts of this document called it "the single highest-value item" and said it
"solves the date shortage". **Re-checking the live service shows that was overstated.**

What we can verify today:

| Check | Finding |
|---|---|
| Schema | ✅ correct — `LandslideDate`, `LandslideTime`, `Latitude`, `Longitude`, `Amount_of_rainfall`, `RainfallIntensity`, 113 fields |
| Public records | **2** |
| **Max OBJECTID (≈ size of the internal table)** | **402 — nationally, across all of India** |
| Both visible records | **Tamil Nadu** (Valparai and Chennai) — **zero evidence of Arunachal coverage** |
| Rainfall detail | partly categorical, not measured: `Duration = "The last few days, but less than a week"`, `Intensity = "Heavy (>25 mm/day)"` |
| Accuracy fields (`date_acc`, `geo_acc`) | **not populated** in either record |

It is the **Bhooskhalan app** submission backend — a field-reporting tool. ~402 rows
nationally, spread over 28 states. Arunachal is remote and thinly populated, so its share is
likely **below** proportional: realistically **0–20 records**.

**We have 72 dated events. This would at best take us to ~90.** That does not enable a
machine-learning trigger; it is not the fix this document previously claimed.

> **Honest status: worth requesting — it costs an email — but it should not be presented to
> the client as the solution.** The rainfall columns remain genuinely useful for calibration
> even in small numbers, but the date shortage would survive it.

---

## 6c. ⏸️ PARKED — pool the whole Himalayan arc, hold out Arunachal

> **Paused 2026-08-02 by decision, not by failure.** Fetch stopped at 751 of 7,519
> days (10%). Untested and unrefuted — the most promising remaining route for the
> *when* half, and the only one needing nothing from outside the project.
>
> 📄 **Full resume instructions, state on disk and risks:
> [PARKED_HIMALAYAN_POOLED_TRIGGER.md](PARKED_HIMALAYAN_POOLED_TRIGGER.md)**

The rationale below is kept because it is what justifies resuming.

**Idea:** stop trying to enlarge *Arunachal's* dated inventory. Train the trigger on
**every dated rainfall landslide along the Himalaya**, then validate it on Arunachal's
own events which it has never seen.

**Why this is different from everything above:** it needs no new data collection and no
department's cooperation. The data is already public.

**Measured 2026-08-02** — NASA Global Landslide Catalog, bbox 72–98°E / 26–36°N:

| | count |
|---|---:|
| landslides in the Himalayan arc | **1,818** |
| with a date | 1,783 |
| **dated AND located to ≤5 km** | **812** |
| of those, rainfall-triggered | **660** |
| in the IMERG era (≥2000-06) | 811 |

Countries: India, Nepal, Pakistan, Bhutan, Bangladesh, China.
Triggers: downpour 773, rain 413, continuous rain 240, monsoon 63.

**~10× the Arunachal sample.** This is the difference between ~12 events per feature
(hopeless — see §4) and ~66 per feature (a legitimate training set).

### Why the features transfer

**IMERG is global.** The entire P7 pipeline — `r3`, `r7`, `api`, `storm_id_ratio`,
percentile-normalisation against local climatology — computes identically anywhere on
Earth. Terrain comes from global DEMs. Nothing in the trigger is Arunachal-specific.

Percentile-normalising against **each location's own** climatology is what makes pooling
defensible: it automatically absorbs the difference between the dry western Himalaya and
the wet monsoon east, so the model learns *"unusually wet for here"* rather than a
millimetre threshold that would only suit one climate.

### The decisive test

**Train on the Himalaya excluding Arunachal. Test on Arunachal's 72 events.**

The model never sees a single Arunachal landslide. If it beats the physics rule's
**0.768**, transfer is proven — on held-out ground, in the client's own state.

If it does not beat 0.768, we lose nothing: the physics trigger already ships.

### Honest costs and risks

| | |
|---|---|
| **Cost** | IMERG must be re-fetched for the whole arc (~13× our current box, ~4 GB, ~2 h) plus ~1–2 days of work |
| **Risk: reporting bias** | GLC coverage is uneven by country; the model may learn where journalists are, not where slopes fail. Mitigate by holding out whole regions, never random rows |
| **Risk: location error** | ≤5 km is coarse for 100 m terrain features. Use rainfall (11 km) as the primary signal and terrain only coarsely |
| **Risk: transfer failure** | western Himalaya gets winter western disturbances; eastern is monsoon-dominated. The held-out test detects this rather than hiding it |

> ⚠️ **This refines an earlier project position.** [why-trees-not-deep-learning] argued
> transfer learning "solves a problem we don't have" — that was about **susceptibility**,
> where 37,788 local labels make pooling unnecessary. For the **temporal** half it is the
> opposite: pooling addresses exactly the shortage we have.

### Routes not yet attempted

| Route | Why it could work | Realistic scale | Status |
|---|---|---|---|
| **State PWD / BRO road-block logs** | every landslide that closed a road, with a date. Decades of maintenance records, kept for operational reasons | **potentially hundreds–thousands** — now the best remaining candidate | not requested |
| GSI `Landslidedata_1` | correct schema, measured rainfall on some rows | **0–20 for Arunachal** (see correction above) | not requested |
| IMD rain-gauge records + damage reports | dated heavy-rain events paired with reported damage | tens–hundreds | not requested |
| News / disaster archives | real dates; manual, slow, biased to severe events | tens–hundreds | not attempted |
| Record events going forward | reliable and precise, but slow | ~10s/year | ongoing by default |

---

## 8. Where this leaves the product

**The MVP is not blocked.** The forecast ships with:

- **Where:** susceptibility model, AUC **0.860**, on 37,788 polygons
- **When:** transparent rainfall rule, AUC **0.768**, on 72 dated events
- Combined into a daily hazard map

The *when* half is the weaker one, and §§3–6b document every route we took to
strengthen it.

**Every route to enlarging *Arunachal's* dated inventory is closed** (§§3–6b), and
weak supervision on the season labels was tested and failed (§3c).

**§6c — pooling the Himalayan arc — is the one route still standing.** It is
⏸️ **parked, not closed**: 617 dated events already public, needing no new
collection and nobody's permission, but stopped mid-fetch on 2026-08-02 to keep
focus on the MVP. It remains untested and unrefuted.

**For the MVP, the *when* half is the physics trigger at AUC 0.768, and that is
what ships.**

⚠️ **And the leading candidate has changed.** GSI `Landslidedata_1` was previously
named the answer; re-checking the live service (§7 correction) shows it holds only
**~402 rows nationally**, both public examples from Tamil Nadu, implying perhaps
**0–20 for Arunachal**. It is worth requesting but will not close the gap.

**The best remaining candidate is state PWD / BRO road-blockage logs** — every
landslide that shut a road, with a date, kept for decades for operational reasons.
That is the only identified source plausibly holding *hundreds to thousands* of
dated events for Arunachal specifically.

### The pattern worth showing a client

Five attempts, four failed. Each failed **cheaply and early**, on a test designed
against answers we already had:

| attempt | cost | prevented |
|---|---|---|
| Bhuvan year labels | ~1 h | training on 11,329 wrong dates |
| ML on 72 events | ~2 h | shipping a less accurate, less explainable model |
| Optical imagery | ~20 min | ~2 weeks building an unusable label factory |
| Radar — access | ~30 min | (passed — kept the option open one more step) |
| Radar — detection | ~1 h | ~2 weeks building a detector that cannot be validated |

**Total: under five hours to close out every technical alternative**, against
roughly a month of build time avoided.

That is the intended behaviour of the process, not a setback: **cheap gates ahead
of expensive builds**, and every claim validated against known answers before it
is trusted. The system ships either way — the *where* half is strong, the *when*
half is honest about what it is, and we can now say precisely what would improve
it and why nothing cheaper will.

## ⭐ Update 2026-08-20 — a sixth route, untested by any of the above

All five closed attempts above are remote-sensing or inference routes over the
existing spatial inventory. A different kind of route turned up while re-checking
`bhusanket.gsi.gov.in`: the site hosts a **report bibliography**
(`json/LandslideReport/LandslideReport.json`), 48 entries for Arunachal Pradesh,
1950 → 2024-25, including **11 Post Disaster Studies** — GSI's own written
investigations of specific events, several with an exact date already visible in
the title (*"22nd and 23rd April 2016 Tawang Town"*, *"14th June 2008 landslides
and flood related hazard studies of Itanagar"*, and others back to 1950). **46 of
the 48 download directly as PDF, no login** — verified by testing every one.

This is not a re-run of a closed route — GSI's *own field reports* were never one
of the five tested.

**Confirmed the same day, by reading, not just downloading.** 7 of the 46 have
now been read end to end. One file alone (`PDLS_2024_50185.pdf`) bundles four
fully-attributed 2024 events, each with a structured 42/43-point datasheet —
exact date, time, coordinates, material, failure mechanism, triggering factor.
Five more read from the pre-2016 narrative-style reports carry real dates back
to 1948, including one internal inconsistency worth flagging: two separate GSI
reports date the same 1989 debris avalanches nine days apart (9 May vs 15 June).

**Still not a corrected number** — but now a bounded, measured one. A full
automated scan (`scripts/proto/px2_gsi_report_archive.py`) downloaded and
text-checked all 255 candidate reports across Arunachal and the wider
Himalayan/NE arc's Post Disaster Studies. Result: **Arunachal alone,
~25–40 new events (total ~100–110) — still short of enough for ML.** Pooled
across all 11 states, **~200–280 new events** — a genuinely different scale,
enough to seriously attempt a cross-validated tree-based model trained
regionally and fine-tuned to Arunachal. This revives §6c below with a
stronger source than the 617 season-tagged Bhuvan events it was parked on.

Full detail: `docs/data_research/DATA_VERIFICATION.md` §D, `reports/px2_gsi_report_archive.json`,
memory `gsi-report-archive-open`.
