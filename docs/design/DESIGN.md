# How This System Works — A Builder's Guide

**Read this before writing any modelling code.** It explains what we are building,
what every piece of data is for, which techniques we use and why, and — importantly —
where the hard parts and honest limits are.

No prior GIS or machine-learning knowledge assumed. Every technical term is explained
the first time it appears. If a sentence needs jargon, the plain-English version comes
first.

---

## Part 0 — The whole thing in one paragraph

We are building a system that wakes up every morning, looks at how much rain fell
yesterday and how much is forecast for the next three days, compares that against a
map of which slopes in Arunachal Pradesh are physically capable of collapsing, and
publishes a risk level for each administrative area. Same idea for floods, using river
levels instead of slopes. That's it. Everything below is detail about how each of those
steps actually works.

> **Current scope: landslide only.** The flood leg is parked (Part 10) — the two models
> are independent, so this is safe, provided the shared spine stays hazard-agnostic.

---

## Part 1 — What we are actually building

Two products. Only two. Everything else in this document is machinery *inside* them.

| # | Product | What the user sees |
|---|---|---|
| 1 | **Landslide Forecast / Early Warning** | A daily map + table: for each **administrative circle** (186 of them, ~17 km), a risk level (Normal / Watch / Alert / Severe) for today and the next 1–3 days, rolled up to district for the headline |
| 2 | **Flood Forecast / Early Warning** | Same shape, but for river flooding — with an honest split between "we can really forecast this" (big rivers) and "we can only watch" (small mountain streams) |

### What "forecast" means here — at each data tier

This matters enormously, because over-promising is how these projects die. But
*under*-promising loses the upgrade path, so be precise about which limits are permanent
and which are just "not yet."

**What the MVP says:** *"Dirang circle is at ALERT level for the next 48 hours."*

**What the MVP does NOT say:** *"The slope at kilometre 47 of NH-13 will fail at 3pm
tomorrow."*

### Three different resolutions — do not confuse them

This trips everyone up, including me while first drafting this document. There are three
separate numbers and they are not the same thing:

| | Size | Role |
|---|---|---|
| **Compute grid** | **100 m** | What we *calculate* on — 8.2 M cells. Fine, because slope genuinely varies over metres |
| **Skill limit** | **~11 km** | One IMERG rainfall cell. The trigger signal **physically cannot vary finer than this**. The real ceiling |
| **Report unit** | **Circle, ~17 km** | 186 units, median 286 km². **What we publish** |
| *Headline rollup* | *District, ~61 km* | *22 units, median 3,660 km². Too coarse to act on — summary only* |

```
   100 m grid          ~11 km rainfall cell     ~17 km circle      ~61 km district
   ┌┬┬┬┬┬┬┬┬┬┐         ┌─────────┐              ┌──────────┐       ┌───────────────┐
   ├┼┼┼┼┼┼┼┼┼┤         │  ONE    │              │  REPORT  │       │   headline    │
   ├┼┼┼┼┼┼┼┼┼┤  ──►    │  RAIN   │     ──►      │   HERE   │       │   rollup only │
   └┴┴┴┴┴┴┴┴┴┘         │  VALUE  │              │          │       │               │
                       └─────────┘              └──────────┘       └───────────────┘
   we compute here     skill dies here          we publish here    too big to act on
```

**Why the circle is the right reporting unit:** at ~17 km it sits just above the physical
skill limit of ~11 km. That is a fortunate alignment — the unit is both administratively
real (it has a name, an officer, a phone number) *and* physically defensible. Publishing
finer would be fake precision. Publishing at district level would smear a single alert
across up to 7,798 km².

The 100 m grid is not wasted: susceptibility genuinely varies at that scale, so *within*
an alerted circle we can still show **which slopes** carry the risk. What we cannot claim
is that the *timing* is slope-specific.

So: the unit of space is a **circle**, and the unit of time is a **day**.
That is a limit of *satellite data*, not a limit of the product. Nobody can get
slope-specific, hour-specific prediction from satellites alone — the thing that decides
*which particular* slope goes (exact crack pattern, exact soil depth, whether a tree root
happened to be holding it) is invisible from space. What *is* visible is the regional
pattern: steep + weak rock + soaked = several slopes here will go.

### The resolution ladder — and how we climb it

```
 TIER          UNIT OF SPACE      UNIT OF TIME     WHAT UNLOCKS IT
 ─────────────────────────────────────────────────────────────────────────
 FREE          admin circle       1–3 days         satellite only    ◄ MVP
 (satellite)   ~17 km, 186 units  daily bulletin   (already on disk)

 ASK           village cluster    + 0–6 h nowcast  IMD rain gauges
 (gov data)    ~2–5 km

 PAID          ONE SLOPE          HOURS ahead,     ground sensors on
 (instrument)  ~50 m              with a time      that specific slope
                                                   (extensometer / tiltmeter
                                                    / piezometer / InSAR)
```

**So yes — slope-level, hours-ahead prediction IS achievable.** It's the standard
technique on instrumented slopes worldwide: a slope about to fail usually **creeps
first**, the creep accelerates, and you extrapolate the acceleration curve to the
failure time (the **inverse-velocity method**). This is operational, not theoretical.

**The escalation path is the point of the whole design:**

```
   ①  Statewide forecast runs on free data
                    │
                    ▼
   ②  The system's own output ranks the worst slopes
      (high susceptibility × repeatedly triggered × people/road below)
                    │
                    ▼
   ③  Client instruments those specific slopes  ── PAID upgrade
                    │
                    ▼
   ④  Those slopes get hours-ahead, slope-specific warnings
      Everything else keeps the area-level forecast
```

We never instrument blindly — the free tier *earns* the shortlist. That's the commercial
story: the MVP pays for itself by telling you where to spend the sensor budget.

### The one limit money does NOT fix

Sensors work on slopes that **creep before failing**. They do not work on **debris
flows**, which go from stable to gone in minutes with no measurable precursor.

```
   SLOW / CREEPING FAILURE              DEBRIS FLOW
   movement                             movement
     │              ╱                     │            │
     │         ╱╱╱╱╱                      │            │  ← no warning,
     │    ╱╱╱╱╱      ← accelerates,       │            │    then gone
     │╱╱╱╱             sensors see it     │────────────┘
     └──────────► time                    └──────────► time

   ✅ hours of warning                   ❌ sensors give ~nothing
      with sensors                          rainfall thresholds are all you have
```

**How common is each, in our actual data?** From GSI's 26,213 Arunachal polygons,
classified by *how the mass moved*:

| Movement | Count | Share | Sensors help? |
|---|---:|---:|---|
| **Slide** — moves as a mass along a failure surface | 25,349 | **96.6%** | ✅ yes, it creeps first |
| **Flow** — liquefies and pours downhill | 620 | **2.4%** | ❌ no precursor |
| **Fall** — free-falls off a cliff face | 242 | 0.9% | ❌ no precursor |

*(Separately, by* material *: Debris 37.8%, Rock 37.2%. Material and movement are
different things — most debris in Arunachal* slides *rather than* flows *.)*

> ⚠️ **Treat 96.6% with some caution.** A single bucket holding almost everything looks
> like it may carry a default value from GSI's data entry. Flows are also structurally
> under-mapped: they scour their channel and revegetate within a few seasons, while slide
> scars stay visible for decades. The real flow share is probably higher than 2.4% — but
> it is clearly a minority, not a majority.

**So the sensor tier applies to most dangerous slopes in Arunachal, not a fringe.** Say
the caveat plainly in any PAID proposal — sensors cannot help with flows or falls — but
do not let it shrink the offer, because that is a small share of failures here.

**And the shortlist comes free:** Bhuvan flags **914 slides (8.1%) as "Reactivated"** —
slopes that have provably moved more than once. Those are repeat offenders by
observation, not by model. That is where the first sensors go.

---

## Part 2 — The one idea everything hangs on

If you remember nothing else, remember this equation:

```
        WHERE                    WHEN                    FORECAST
   (susceptibility)    ×    (trigger)        =      (daily risk)

   "which slopes are        "is something         "warn these areas
    capable of failing"      pulling the           today"
                             trigger today?"

   Changes over decades      Changes hourly        Published daily
```

### The loaded-gun metaphor

Think of every slope in Arunachal as a gun.

- **Susceptibility** = is the gun loaded? A steep slope of loose clay on fractured rock
  is a loaded gun. A flat plain of solid bedrock is an unloaded one. This barely changes
  from year to year.
- **Trigger** = is someone pulling the trigger? Almost always rain. Sometimes an
  earthquake.
- **A landslide happens only when both are true.**

This is why neither half alone is useful:

- A susceptibility map alone tells you *nothing about today*. It says "these 4,000 slopes
  are dangerous" — which was equally true last year and will be true next year. You
  can't evacuate anyone based on that.
- Rainfall alone tells you nothing about *where*. 200 mm of rain on flat Assam plains
  does nothing; the same rain on a West Kameng hillside is lethal.

**This is also why the client keeps hearing "susceptibility map" from other vendors and
should not accept it as the product.** It's an ingredient, not the meal.

---

## Part 3 — A 5-minute primer on the two shapes of data

Every file we hold is one of two shapes. You need to know the difference because it
determines what you can do with it.

### Shape 1: Raster — "a grid of numbers"

Imagine graph paper laid over the state. Each square holds **one number**.

```
   A raster of elevation (heights in metres):

        col0  col1  col2  col3
  row0 │ 1840│ 1855│ 1871│ 1866│
  row1 │ 1852│ 1869│ 1888│ 1879│      ← each cell = one 30m × 30m
  row2 │ 1861│ 1884│ 1902│ 1897│         patch of real ground
  row3 │ 1858│ 1877│ 1891│ 1888│
```

That's literally it. A `.tif` file is this grid plus a header saying "cell [0,0] starts
at longitude 91.4, latitude 29.6, and each cell is 30 m wide."

**Our rasters:** elevation, slope, soil clay %, land cover, rainfall, population.
Anything that has a value *everywhere*.

> You already saw one of these raw. When you flipped the soil card in the viz and saw
> `107 109 108 110...` — that was an actual raster grid, bulk density in
> centigrams/cm³. Divide by 100 → 1.07–1.10 g/cm³.

### Shape 2: Vector — "a list of shapes with labels"

A list of specific things, each with a location and a row of attributes — like a
spreadsheet where one column happens to be a shape.

```
   A vector of landslides:

   id  │ shape                    │ district    │ material │ year
   ────┼──────────────────────────┼─────────────┼──────────┼──────
   1   │ POLYGON((93.4 26.5, ...))│ West Kameng │ Debris   │ 2017
   2   │ POLYGON((93.2 26.5, ...))│ Tawang      │ Soil     │ 2017
   3   │ POINT(94.1 27.8)         │ Changlang   │ Rock     │ 2014
```

**Our vectors:** landslide polygons, rivers, roads, district boundaries, lineaments,
settlements.

### Why the distinction matters

Models eat **tables of numbers**. So a huge part of the engineering work is converting
everything — rasters *and* vectors — into one big table where each row is a place and
each column is a measurement. That conversion is Stage 1 below.

---

## Part 4 — Every dataset, sorted by the job it does

We hold **7.7 GB across 11 categories**. Rather than list them by source, here they are
by *what they're for*.

### Bucket A — WHERE: the permanent character of the ground

These answer "is this slope capable of failing?" They change over decades, so we
download once.

| Data | What it literally is | Why it matters for landslides |
|---|---|---|
| **Elevation (DEM)** 30 m, 28 tiles | Height above sea level, per cell | Everything below is computed *from* this |
| **Slope** *(computed)* | Steepness in degrees | **The single strongest predictor.** Loose soil sits stable up to ~30–35°; steeper than that it's already near its limit |
| **Aspect** *(computed)* | Which compass direction the slope faces | Controls sun, moisture retention, snowmelt timing |
| **Curvature** *(computed)* | Is the ground bowl-shaped or ridge-shaped? | Bowls *collect* water; ridges shed it. Bowls fail more |
| **TWI** *(computed)* | Topographic Wetness Index — how much upslope land drains into this cell | Predicts where water piles up underground |
| **Soil** 18 rasters | Clay/sand/silt %, density, organic carbon, at 3 depths | **Clay is the dangerous one** — it holds water, and when saturated it loses grip and acts almost like a lubricant |
| **Lithology** 562 polygons, 24 rock units | What rock is underneath | Decides how thick the loose surface layer is and how water moves through it |
| **Lineaments** 4,777 lines | Fault lines and fractures in the bedrock | Rock near a fault is shattered and weak. Distance-to-lineament is a real predictor |
| **Land cover** 10 m | Forest / cropland / bare / built | Tree roots physically bind soil. Deforested slopes fail far more |
| **Rivers** 50,800 reaches | The drainage network | Rivers erode the *toe* of a slope, removing its support |
| **Roads** (OSM) | Road network | Road cuts slice into hillsides and destabilise them — a genuine human cause |

### Bucket B — WHEN: the things that change and set it off

| Data | What it is | Role |
|---|---|---|
| **IMERG rainfall** 11 km, daily | Satellite-estimated rain | **The main trigger.** Both "how hard now" and "how much already" |
| **GFS forecast** 25 km, to +7 days | Forecast rain from NOAA | This is what gives us *lead time* — it's why we can warn *before* not *after* |
| **SMAP soil moisture** | How wet the top soil already is, measured | Shortcut for "is the ground already loaded?" |
| **ERA5-Land** 9 km hourly | Reanalysis — a physics model of past weather | Backup/gap-filler for rainfall and temperature |
| **GloFAS discharge** | Modelled river flow, m³/s, to +7 days | **The flood forecast's engine** |
| **ENSO index** | El Niño / La Niña state | Seasonal context — shifts monsoon strength |
| **Earthquakes** (USGS) | Historic quakes M4+ | Secondary trigger; also long-term rock weakening |

### Bucket C — WHAT ALREADY HAPPENED: the answer key

This is what the model learns from. **This bucket is our weakest link and the most
important thing for you to understand — see Part 7.**

| Data | Count | Has location? | Has a date? |
|---|---:|---|---|
| GSI polygons | 26,213 | ✅ exact outlines | ❌ **none at all** |
| Bhuvan polygons | 11,329 | ✅ exact outlines | ⚠️ **year only** (2014 / 2017 / 2023) |
| *(overlap removed)* | **35,744 unique** | | |
| NASA Global Landslide Catalog | 99 (90 dated) | ⚠️ coarse points | ✅ **exact date**, 2008–2018 |
| Observed flood extent | 2003–2020 mask | ✅ | ⚠️ aggregate, not per-event |

### Bucket D — WHO'S THERE: turning hazard into risk

| Data | Use |
|---|---|
| **Population** 100 m | A landslide in empty mountains is a hazard; one above a village is an emergency |
| **Buildings, schools, health centres** | Who specifically to warn |
| **Admin boundaries** (GADM + APSSDI circles) | The unit warnings are issued in |

---

## Part 5 — The pipeline, end to end

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │ STAGE 0 · DOWNLOAD                       (scripts/fetch/*)          │
 │   ~7.7 GB of rasters & vectors from 15 sources          [MOSTLY DONE]│
 └───────────────────────────────┬─────────────────────────────────────┘
                                 ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │ STAGE 1 · BUILD THE GRID                     data/interim/          │
 │   Lay one grid over the state. Convert every raster and every       │
 │   vector into a column on that grid. Output: one big table.  [TODO] │
 │                                                                     │
 │   cell_id │ lon   │ lat   │ slope │ clay │ litho │ dist_fault │ ... │
 │   ────────┼───────┼───────┼───────┼──────┼───────┼────────────┼──── │
 │   0       │ 91.40 │ 29.60 │  4.2  │  19  │  12   │   4,100    │ ... │
 │   1       │ 91.41 │ 29.60 │  7.8  │  21  │  12   │   3,950    │ ... │
 └───────────────────────────────┬─────────────────────────────────────┘
                                 ▼
        ┌────────────────────────┴────────────────────────┐
        ▼                                                 ▼
 ┌──────────────────────────┐              ┌──────────────────────────┐
 │ STAGE 2 · SUSCEPTIBILITY │              │ STAGE 3 · TRIGGER        │
 │ "WHERE can it fail?"     │              │ "WHEN does it fire?"     │
 │                          │              │                          │
 │ Supervised ML on 35,744  │              │ Rainfall thresholds +    │
 │ mapped landslides        │              │ soil wetness             │
 │                          │              │                          │
 │ Output: score 0–1 per    │              │ Output: score 0–1 per    │
 │ cell. Static, rebuilt    │              │ cell PER DAY. Recomputed │
 │ ~yearly.          [READY]│              │ every morning.  [BLOCKED]│
 └────────────┬─────────────┘              └────────────┬─────────────┘
              └──────────────┬──────────────────────────┘
                             ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │ STAGE 4 · COMBINE → DAILY FORECAST                                  │
 │   risk = f(susceptibility, trigger) → aggregate to admin circle     │
 │   → Normal / Watch / Alert / Severe                                 │
 └───────────────────────────────┬─────────────────────────────────────┘
                                 ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │ STAGE 5 · DELIVER   API · dashboard map · bulletin text · SMS       │
 └─────────────────────────────────────────────────────────────────────┘
```

`[READY]` = all input data is on disk, can start today.
`[BLOCKED]` = needs the rainfall archive downloaded first (see Part 12).

---

## Part 6 — Stage 1: Building the grid

**Goal:** turn 7.7 GB of mismatched files into one table.

Right now our data is a mess of incompatible things: elevation at 30 m, soil at 250 m,
rainfall at 11 km, geology as polygons, rivers as lines. You cannot feed that to a
model. So we pick **one grid** and force everything onto it.

### Choosing the cell size

| Option | Cells for Arunachal | Verdict |
|---|---:|---|
| 30 m (native DEM) | ~91 million | Too many. Training would take days, and our labels aren't that precise anyway |
| **100 m** | **~8.2 million** | ✅ **Pick this.** Fine enough to capture a hillside, coarse enough to compute |
| 1 km | ~82,000 | Too coarse — averages away the steep bits that matter |

### The three conversion moves

**1. Raster → column (resampling).** Different resolutions get stretched or squashed
onto our 100 m grid.

```
   Soil at 250 m                Our grid at 100 m
   ┌───────────┐                ┌───┬───┬───┐
   │           │      ──►       │ 28│ 28│ 28│   one 250 m soil value
   │    28%    │                ├───┼───┼───┤   is copied into the
   │           │                │ 28│ 28│ 28│   several 100 m cells
   └───────────┘                └───┴───┴───┘   that sit inside it
```

> ⚠️ **Honesty note:** this does not create detail that wasn't there. The soil map is
> still really 250 m. We're just making the shapes line up.

**2. Polygon → column.** For each grid cell, ask "which rock unit am I inside?" and
write down that code.

**3. Line/point → distance column.** For each cell, measure the distance to the nearest
fault, river, road. Distance is far more useful to a model than a yes/no.

```
   Lineaments (faults)          Becomes: dist_to_fault
   ─────╲                       ┌────┬────┬────┐
         ╲                      │ 900│ 600│ 300│    metres to the
          ╲                     ├────┼────┼────┤    nearest fault
           ╲                    │1200│ 900│ 600│
```

### The output

One table, ~8.2 million rows, ~25 columns. Roughly 1–2 GB as
[Parquet](https://parquet.apache.org/) (a compressed table format that loads far faster
than CSV). Lands in `data/interim/`.

**Tools:** `rasterio` (rasters), `geopandas` (vectors), `numpy` (maths), `pyarrow`
(Parquet).

---

## Part 7 — Stage 2: The susceptibility model (WHERE)

This is the part where actual machine learning happens, and it's the part our data
strongly supports.

### What "machine learning" means here, concretely

Forget the hype. Here is literally what happens:

1. We show the computer thousands of examples of places where a landslide **did** happen,
   along with all their measurements (slope, clay, rock type, distance to fault…).
2. We show it thousands of places where one **did not**, with the same measurements.
3. The computer finds the pattern that separates the two groups.
4. We then hand it a new place it's never seen and it outputs a number 0–1: *how much
   does this look like the failure group?*

That's it. No magic. It's pattern-matching on a table.

### The training table

```
 slope│aspect│curv │clay│sand│density│litho│d_fault│d_river│d_road│cover│elev │LANDSLIDE?
 ─────┼──────┼─────┼────┼────┼───────┼─────┼───────┼───────┼──────┼─────┼─────┼─────────
  34.2│  NE  │-0.02│ 28 │ 41 │ 1.09  │  7  │  380  │  210  │  95  │ for │1850 │   YES  ←real
  38.7│  N   │-0.05│ 31 │ 38 │ 1.12  │  7  │  210  │  180  │ 140  │ for │2010 │   YES  ←real
   4.1│  S   │ 0.01│ 19 │ 55 │ 1.31  │ 12  │ 4100  │ 3200  │2100  │ crop│ 320 │   NO
  12.8│  W   │ 0.03│ 22 │ 49 │ 1.28  │ 12  │ 2800  │ 1500  │ 800  │ for │ 780 │   NO
       ↑                                                                        ↑
    "features" — what the model looks at                   "label" — the answer
```

The model learns things like: *"when slope > 30 AND clay > 25 AND distance-to-fault <
500, the answer is usually YES."* Except it learns thousands of such rules
simultaneously and weights them.

### The trap nobody warns beginners about: where do the NOs come from?

Our data has 35,744 places where a landslide happened. It has **zero** confirmed places
where one didn't — nobody maps "here is a slope that is fine."

This matters enormously. If you grab random cells as your NO examples, most land in flat
valley bottoms, and the model learns the useless rule *"steep = landslide, flat = safe."*
It'll score 97% accurate and be worthless, because it never learned to tell a dangerous
steep slope from a safe steep slope.

**The fix — constrained negative sampling:** draw the NO examples only from terrain that
*could* plausibly fail (say, slope > 10°) but has no mapped landslide, and keep them a
safe distance (>500 m) from any mapped one so we don't accidentally label part of a real
slide as "safe."

```
   ❌ NAIVE                              ✅ CONSTRAINED
   ┌──────────────────────┐              ┌──────────────────────┐
   │ ●● landslides (hills)│              │ ●● landslides (hills)│
   │                      │              │ ○○ non-slides — also │
   │        ○○○○○○        │              │    on hills, but     │
   │    (flat valleys)    │              │    >500 m away       │
   └──────────────────────┘              └──────────────────────┘
   Model learns "steep=bad"              Model learns what actually
   → useless                             separates them → useful
```

> This one decision affects the final quality more than the choice of algorithm. Get it
> right before tuning anything.

### Which algorithm, and why

| Approach | Verdict |
|---|---|
| Logistic regression | Too simple — assumes effects add up linearly. Slope and rainfall interact multiplicatively in reality |
| **Gradient-boosted trees** (XGBoost / LightGBM) | ✅ **Use this.** Handles mixed data types, captures interactions, needs no scaling, trains in minutes, and **tells you which features mattered** |
| Deep learning (CNN/U-Net) | Overkill *for this step*. Needs far more data and gives you no explanation. (It has a real use later — see Part 12) |

**Why "explains itself" matters commercially:** when the client asks *"why is Tawang
red?"*, "because slope contributed 34%, antecedent rainfall 28%, lithology 15%" is an
answer that builds trust. "The neural network said so" loses the contract.

### How to test it honestly (the leakage trap)

The standard ML move — shuffle rows, keep 80% to train, 20% to test — **is wrong for
geographic data** and will give you a beautiful, fake result.

Why: neighbouring cells are nearly identical. A random split puts a cell in training and
the cell 100 m away in testing. The model effectively sees the answer. You'll report 96%
accuracy and it will fail completely in a district it's never seen.

**Do this instead — spatial block cross-validation:** hold out whole *regions*.

```
   ❌ RANDOM SPLIT (leaks)              ✅ SPATIAL BLOCKS (honest)
   ┌─────────────────────┐             ┌─────────┬───────────┐
   │ ▓░▓░▓░▓░▓░▓░▓░▓░▓░▓ │             │ ▓▓▓▓▓▓▓ │  ░░░░░░░  │
   │ ░▓░▓░▓░▓░▓░▓░▓░▓░▓░ │             │ ▓ TRAIN │  ░ TEST   │
   │ ▓░▓░▓░▓░▓░▓░▓░▓░▓░▓ │             │ ▓▓▓▓▓▓▓ │  ░░░░░░░  │
   └─────────────────────┘             └─────────┴───────────┘
   "96% accurate" — a lie              "82% accurate" — the truth
```

Expect the honest number to be **much lower**. That's correct and healthy.

We also have an independent check most projects don't: **GSI's own national
susceptibility map at 50 m**. Compare against it — but *never train on it*, or we'd just
be cloning their model and inheriting its mistakes.

### Status: this stage is ready to build today. All inputs are on disk.

---

## Part 8 — Stage 3: The trigger model (WHEN)

**This is the hard part.** Read this section twice.

### The core problem, stated plainly

To learn "how much rain causes a landslide", you need examples of the form:

> *On **12 July 2017**, at **this location**, it had rained **165 mm over 3 days**, and a
> landslide **happened**.*

Now look at what our answer key actually contains:

```
   35,744 landslide polygons
        │
        ├── 26,213 from GSI ──────────► NO DATE AT ALL
        │                               (spatial inventory, not an event log)
        │
        ├── 11,329 from Bhuvan ───────► YEAR ONLY (2014, 2017 or 2023)
        │                               "sometime in that year"
        │
        └── 99 from NASA GLC ─────────► EXACT DATE (90 of them, 2008–2018)
                                        but locations are coarse (km-scale)
                                        and it's only 99 records
```

**So: we know WHERE 35,744 landslides are. We know WHEN for essentially none of them.**

This is why you cannot just throw a neural network at "predict landslides." The training
examples for the *when* half don't exist **in the form we need them** — which is not the
same as saying they can't be created. Techniques 2, 4 and 5 below are three different ways
of manufacturing them.

> **Where this came from:** I verified it directly. GSI's date columns exist in the file
> but hold 13 blank strings. Bhuvan's `Year` column is uniform per file — every 2017
> record just says 2017. You can confirm both yourself by flipping the inventory card to
> **Raw data** in the viz.

### So what do we actually do? Four techniques, stacked

**Technique 1 — Rainfall thresholds (the workhorse).**

Established landslide science, used operationally worldwide including by GSI. The idea:
plot rainfall intensity against duration for events that *did* cause slides, and draw a
line under them.

```
   rain
   intensity        ●  ● ●        ● = a day that caused landslides
    (mm/hr)      ●    ●   ●       ○ = a day that didn't
              ●  ● ●      ●
        ────────────────────────  ← THE THRESHOLD LINE
           ○  ○    ○   ○    ○     above it → issue a warning
        ○     ○  ○   ○  ○         below it → stay quiet
        └──────────────────────►
              duration (hours)
```

We fit this using the 90 NASA-dated events plus published thresholds from the Northeast
Himalaya, then tune it against the year-level Bhuvan data.

**Technique 2 — Weak labels from year-tagged data.**

We can't pin a 2017 Bhuvan slide to a day, but we know it happened *during the 2017
monsoon*. So: take that year's rainfall record, find the extreme-rain days, and treat
those as the likely trigger days. This is **weak supervision** — learning from labels
that are imprecise but not useless. It gives us roughly 5,856 datable events instead of 90.

**Technique 3 — Antecedent conditions, not just today's rain.**

The single biggest improvement available, and it's free. A moderate storm on
already-soaked ground is far more dangerous than a heavy one on dry ground.

```
   Two days with IDENTICAL rainfall today (60 mm):

   Day A:  ░░░░░░░░░░  previous 15 days: dry
           ▓▓▓▓▓▓      today: 60 mm          → soil absorbs it → probably fine

   Day B:  ▓▓▓▓▓▓▓▓▓▓  previous 15 days: 280 mm
           ▓▓▓▓▓▓      today: 60 mm          → soil already full → SLIDES
```

So we compute rolling sums — rain over the past 3, 7, 15 and 30 days — and feed those as
separate features. Plus SMAP's directly-measured soil moisture.

**Technique 4 — Regional transfer, done the simple way.**

GSI already runs an operational landslide forecast for 187 districts across 10 states —
including Assam, Nagaland, Meghalaya and Sikkim, all of which border us — and **zero
districts in Arunachal**. Their published thresholds for neighbouring Himalayan terrain
are a legitimate, defensible starting point.

Beyond published thresholds, we can pull in *dated events* from the wider Himalaya —
NASA's COOLR / Global Landslide Catalog, and the Froude & Petley fatal-landslide database.
Rainfall-triggering physics genuinely transfers across the range, so these rows carry real
signal. Realistic yield: **~2,000–5,000 dated Himalayan events.**

> **Important: transfer learning does not require a neural network.** You do *not* need to
> pretrain a model elsewhere and fine-tune it here. Just **pool the rows** into one model
> with a `region` feature and sample weights favouring Arunachal:
>
> ```
>    Nepal / Uttarakhand / Sikkim events  ┐
>                                          ├─►  one model, region-aware
>    Arunachal events (upweighted)        ┘
> ```
>
> Same benefit — general physics from the pooled rows, local peculiarity from the weighted
> local ones — but it stays readable, trains in seconds, and you can *measure* the transfer
> by dropping the other regions and re-running. That experiment is cheap here and expensive
> with a pretrained network.

⚠️ **Exclude earthquake-triggered inventories.** Nepal's largest (Roback/Gorkha, ~25,000
slides) is seismic. Pooling it into a *rainfall* trigger model poisons it.

**Technique 5 — Manufacture our own dates (the highest-leverage move).**

We don't need someone else's inventory nearly as much as we need **dates on the 35,744
polygons we already own**. A landslide scar appears in satellite imagery at a specific
time; Sentinel-2 goes back to 2015 and Landsat to 1984. Find when each scar first appears,
and an undated polygon becomes a dated event.

```
   Landsat/Sentinel-2 time series over one polygon
   ▓▓▓ ▓▓▓ ▓▓▓ ▓▓▓ ░░░ ░░░ ░░░      ▓ = vegetated
                ▲                    ░ = bare scar
        scar first appears here → that's your date window
```

This yields **local, correctly-biased** training data — unlike imported inventories, which
carry another state's mapping practice and fatality bias. **This is the one place in the
whole system where a neural network is the right tool** (see below).

### The negatives problem — bigger than the label shortage

A trigger model needs *non-events* too: "it rained 180 mm here and nothing failed." Those
look easy to generate — every cell-day with no recorded slide — but landslides are heavily
under-reported, so **many of your "negatives" are unreported positives.** The model learns
"this much rain is safe" from days that actually failed and were never written down.

This corrupts the trigger more than the positive shortage does, and **no amount of extra
data or pretraining fixes it.** The fix is sampling discipline: draw negatives only from
well-mapped corridors and periods where an absence is genuinely credible — the same logic
as the constrained-negative trap in Part 7, applied to time instead of space.

### Where ML fits — and where a neural network does

The trigger *is* a machine-learning model. What it is not, at MVP, is a deep one.

| Task | Approach | Why |
|---|---|---|
| Susceptibility (WHERE) | ✅ **Trees (LightGBM)** | 35,744 labelled examples, ~20 tabular features. Textbook supervised learning |
| Trigger (WHEN) | ✅ **Trees**, physics inside | ~5,800 weak + ~2,000–5,000 pooled events. Tabular and small — trees beat networks at this size |
| Combining the two | ✅ Light | After 1–2 live monsoons, a small model can learn the combination rule from logged hits/misses |
| **Dating our inventory from imagery** | ✅ **Neural network** | Image segmentation over a time series. No tree-based alternative exists |

**Physics goes *inside* the trigger model, not beside it.** Don't compute an ML score and a
threshold score and add them — that's not a coherent quantity. Instead:

```
   ID-threshold exceedance ratio  ──┐
   3/7/15/30-day rainfall sums    ──┤
   rainfall intensity, duration   ──┼──►  TRIGGER MODEL  ──►  P(trigger)
   SMAP soil moisture             ──┤        (trees)
   season, ENSO                   ──┘

   HAZARD = SUSCEPTIBILITY × P(trigger)
            ...with the physics threshold also acting as an alert FLOOR:
               never fire below the established ID curve
```

The threshold becomes a **feature and a guardrail**. One model, physically constrained,
still explainable.

**The rule for the whole system:** *no neural network in the thing that makes predictions;
one neural network in the thing that makes training data.* The dating model sits offline
and never touches a live forecast, so it adds no opacity to anything the client sees —
while every model in the forecast path can still justify itself cell by cell, which is what
APSDMA needs to sign an evacuation order.

### When a neural network becomes justified in the forecast path

Not "when we finally have data" — a specific, testable condition:

```
   dated events < 500        →  trees, pooled with Himalayan rows
   500 – 5,000               →  trees, Arunachal-weighted        ← where we expect to land
   > 5,000  AND sub-daily    →  temporal NN (LSTM/TCN) worth TESTING against trees
```

Only the third row changes the answer, and it needs both halves. The real condition is
*"we have enough sub-daily sequences that the shape of a rainfall burst carries signal our
engineered lag features can't capture."* Hour-precision dates from GSI's `Landslidedata_1`
plus half-hourly IMERG would put us there. Even then: **benchmark it against trees and drop
it if it doesn't win by a margin that survives spatial block cross-validation.**

**Be straight with the client about this.** The forecast's first version is machine
learning on both halves, with established rainfall physics constraining the trigger. It
gets stronger as we accumulate our own dated record — which starts the day we go live, and
accelerates the moment the dating model runs.

### Status: BLOCKED — but not by permission. See Part 12.

---

## Part 9 — Stage 4: Producing the daily forecast

### Follow one cell through a real day

Take a 100 m cell in West Kameng (the district with the most mapped landslides — 5,823).

**Step 1 — Static features** (computed once, sitting in the table):

```
  slope              34.2°     ← steep, above the ~32° danger line
  curvature         -0.02      ← concave: collects water
  clay content        28 %     ← high: holds water, loses grip when saturated
  bulk density      1.09 g/cm³ ← loose  (this is that 107 you saw in the raw viewer)
  lithology       schist       ← foliated, weak, weathers to clay
  dist to fault      380 m     ← close: fractured rock
  dist to river      210 m     ← close: toe erosion possible
  land cover      forest       ← protective (roots bind soil)
  elevation        1,850 m
```

→ **Susceptibility model outputs: `0.81`** — high. This slope is a loaded gun. Same
value yesterday, same tomorrow.

**Step 2 — Today's dynamic features** (recomputed every morning):

```
  rain yesterday          78 mm   (IMERG, observed)
  rain last 3 days       165 mm   (rolling sum)
  rain last 15 days      310 mm   ← ground already loaded
  soil moisture           0.41    (SMAP, near saturation)
  forecast rain next 24h  95 mm   (GFS) ← this is where lead time comes from
```

**Step 3 — Trigger check:**

```
  3-day threshold for this terrain:  120 mm
  actual 3-day rainfall:             165 mm   ► EXCEEDED (1.38×)
  antecedent 15-day:                 310 mm   ► soil already saturated
  forecast adds:                      95 mm   ► will get worse

  → trigger score: 0.87
```

**Step 4 — Combine:**

```
  risk = 0.81  ×  0.87   =  0.70   →  ALERT
         WHERE    WHEN
```

**Step 5 — Aggregate to the reporting unit.** We don't publish per-cell (false
precision). We roll up the 100 m cells inside each **administrative circle** — e.g. "12%
of Dirang circle's cells are above ALERT, including 340 within 500 m of a settlement" →
Dirang circle goes **ALERT**. Districts get a headline summary ("3 of 8 circles on
alert"), never a single district-wide number, because a district can span 7,798 km².

**Step 6 — Publish:** map + district table + bulletin text + alerts to subscribers.

### Setting the threshold is a *policy* decision, not a technical one

Where you draw the ALERT line trades two errors against each other:

- **POD** (Probability of Detection) — of the landslides that happened, what share did we
  warn for? *Higher is better.*
- **FAR** (False Alarm Ratio) — of the warnings we issued, what share were wrong?
  *Lower is better.*

**You cannot maximise both.** Warn more freely → catch more real events (POD up) but cry
wolf more (FAR up).

```
      cautious ◄──────────── threshold ────────────► aggressive
   ┌────────────────┐                          ┌────────────────┐
   │ POD  40%       │                          │ POD  85%       │
   │ FAR  20%       │                          │ FAR  70%       │
   │                │                          │                │
   │ Rarely wrong,  │                          │ Catches almost │
   │ misses over    │                          │ everything,    │
   │ half of them   │                          │ but 7 in 10    │
   │                │                          │ warnings are   │
   │                │                          │ false          │
   └────────────────┘                          └────────────────┘
```

Realistic free-tier target: **POD 55–70%, FAR 40–60%.**

A 50% false-alarm rate sounds terrible until you frame it correctly: *the cost of a false
alarm is a road crew on standby for a day; the cost of a miss is a bus in a debris flow.*
**Make the client choose the threshold** — put it in writing. It's their risk appetite,
not our technical parameter.

---

## Part 10 — The flood side

> 🅿️ **PARKED as of 2026-07-31 — not cancelled.** We're building the landslide forecast
> first. Both still ship as products. This part stays in the document because it defines
> what the shared spine has to accommodate: keep the grid builder, exposure join, alert
> publisher and delivery layer **hazard-agnostic**, and flood plugs into them later instead
> of forcing a rewrite. While parked, ignore `05_hydrology/glofas` and the 2003–2020 flood
> extent mask. Read the rest of this part as a design constraint, not a work item.

Same skeleton, different plumbing — and we must be honest that this leg is weaker.

```
   ┌─────────────────────────────────────────────────────────────┐
   │  BIG RIVERS (Siang / Brahmaputra trunk)                     │
   │  GloFAS models these directly → REAL FORECAST               │
   │  3–7 day lead, ~75–85% skill                                │
   │  ~3% of the network by length — but most people live there  │
   └─────────────────────────────────────────────────────────────┘
   ┌─────────────────────────────────────────────────────────────┐
   │  SMALL MOUNTAIN STREAMS                                     │
   │  Below GloFAS's minimum catchment size → NO MODEL EXISTS    │
   │  We can only issue a rainfall-based WATCH, uncalibrated     │
   │  ~97% of reaches — and where most Arunachal damage happens  │
   └─────────────────────────────────────────────────────────────┘
```

**Say the quiet part out loud in the proposal.** Free-tier flood forecasting covers the
big rivers well and the small ones barely. The fix is river gauges (an ASK) or
telemetered sensors (PAID). Pretending otherwise sets up a very public failure the first
time a flash flood hits an ungauged valley.

**Also not forecastable for free:** dam-release flooding. That needs release schedules
from the operators — no model substitutes for knowing when someone opens a gate.

---

## Part 11 — How we prove it works

Three independent checks. Do all three.

**1. Spatial hold-out** *(Part 7)* — train on some districts, test on districts the model
has never seen. Answers "does this generalise?"

**2. Temporal hold-out** — train only on data before 2023, then test whether it would
have flagged the 2023 Bhuvan-mapped slides. Answers "would it have worked in real time?"
This is the strongest test we can run before going live.

**3. Benchmark against GSI's 50 m susceptibility map** — do our high-risk zones agree
with theirs? Disagreement isn't automatically failure (theirs is coarser and older) but
large disagreement means investigate.

Then, once live: **log every forecast, and score it later.** Publish POD/FAR honestly
every season. A vendor who reports their own misses is far more credible than one who
reports only successes — and after two monsoons that log becomes the dated event record
we currently lack, which is what unlocks real ML on the trigger side.

---

## Part 12 — What's missing, and what to do about it

From the audit I just ran against the actual disk:

### ✅ Complete — nothing more to fetch

Elevation · soil · lithology · lineaments · land cover · rivers · roads · landslide
inventory (35,744) · flood extent · susceptibility benchmark · population · buildings ·
admin boundaries · ENSO · earthquakes

**Everything the WHERE half needs is on disk.** Stage 1 and Stage 2 can start today.

### 🔴 The one real blocker

| | |
|---|---|
| **What** | IMERG rainfall archive |
| **Have** | 132 days (the 2024 monsoon Jun–Sep, plus 10 recent days) |
| **Need** | ~9,500 days (2000 → now) |
| **Why** | You cannot fit a rainfall threshold without rainfall history. This is the *entire* WHEN half |
| **Blocked by** | **Nothing.** No permission, no department, no money. It's a NASA Earthdata download — credentials already work, script already exists |
| **Cost** | **~2 hours, ~320 MB.** Measured, not estimated — see below |

> **This is why I said the critical path is collection, not permission.** No ASK-tier
> data blocks the forecast MVP. The blocker is a download queue.

**On the "2 hours" figure** — I originally guessed "days" and was wrong by an order of
magnitude. Measured against the 132 files already on disk: each subsetted day is **34 kB**
and takes **~2.4 s**. The whole 26-year archive is ~320 MB, so bandwidth is irrelevant —
your connection is idle almost the entire run. What you're paying for is **9,500 queue
waits**: for each request NASA opens the global 3600×1800 grid, slices out the Arunachal
window, and re-encodes it.

`fetch_11_imerg.py` already does that subsetting server-side via an OPeNDAP constraint
expression — that's why files are 34 kB instead of ~4 MB. **Never "optimise" this by
downloading un-subsetted global files**; that turns 320 MB into ~40 GB.

> ⚠️ **Known bug to fix before the backfill.** The script tries versions in the order
> `("V07C", "V07B")`. I probed 2005, 2012, 2020 and 2024 — **all four 404 on V07C, then
> succeed on V07B**, burning ~2.2 s per file. Harmless for the recent days the script was
> written for; roughly **doubles** a full backfill. Fix by probing the version once per
> year and caching it, not per file. With that fixed: ~2.1 h at 3 workers, ~50 min at 8
> (GES DISC throttles, so more workers eventually buys retries, not speed). Runs are
> restartable — existing files >1 kB are skipped.

### 🟡 Should fetch alongside it

- **SMAP soil moisture archive** — 3 days on disk; needs to span the same period as the rain
- **Multi-state Bhuvan landslides (~80k across ~15 states)** — the pooled rows for
  Technique 4, and it lets us *measure* whether out-of-state data actually helps by
  dropping it and re-running
- **NASA COOLR / Global Landslide Catalog + Froude & Petley fatal-landslide DB** — the
  dated Himalayan events for Technique 4. Free, immediate, ~2,000–5,000 rows.
  ⚠️ filter out earthquake-triggered events
- ~~**GloFAS reforecast archive**~~ — flood only, **parked** with Part 10

### 🔧 Compute, not download

`data/interim/` and `data/processed/` are **both empty**. Everything in Stage 1 —
slope, aspect, curvature, TWI, distance-to-fault/river/road, the joined grid table —
still has to be built. No downloads involved; this is pure code.

### 📋 Worth asking for (but not blocking)

- **IMD rain gauge records** — improves resolution above 2,500 m where satellite estimates drift
- **GSI's `Landslidedata_1` table** — hour-precision dates + measured per-event rainfall.
  The schema is public and live but only 2 of ~402 rows are exposed. **This is the single
  most valuable ask**, because it directly fixes the WHEN-label gap. Request it by table
  and field name.
  - The **per-event rainfall** column is quietly the most valuable part: it's ground truth
    we cannot get any other way, and it lets us **bias-correct IMERG**, which is known to
    underestimate orographic rain over ridges at 11 km resolution.
  - **Ask one extra question when requesting it:** *is this every recorded event in the
    covered area and period, or only notable/damaging ones?* If it's systematic, absence
    of a record becomes real evidence of non-failure — which gives us credible negatives,
    worth more than the positives (see Part 8, "the negatives problem"). If it's
    notable-events-only, we still can't trust a quiet day.
- **State PWD road-block records** — an unglamorous but excellent proxy event log with dates

### ⚠️ One open item

The `gsi-nlfc_*` files in `08_labels/` were fetched on 2026-07-28 by a process that
wasn't this session, and they're ~70% of the inventory. Worth confirming their
provenance before anything client-facing leans on them.

---

## Part 13 — Build order

Do these in sequence. Each produces something checkable before the next starts.

> **Scope note:** we are building the **landslide forecast only** for now. The flood
> forecast is *parked, not cancelled* — see Part 10. The two models are genuinely
> independent (verified: only 2.66% of landslides sit on a historically flooded pixel), so
> separating them is safe. But roughly **half of this build is shared spine** — the IMERG
> archive, the DEM, admin units, exposure, and the whole delivery layer. **Parametrise
> those by hazard from day one.** Hardcoding `"landslide"` into the grid builder, the
> exposure join or the alert publisher means rewriting them when flood resumes; passing a
> hazard argument costs nothing today.

```
 ①  Fix + kick off the IMERG archive download    ← START FIRST, ~2 h in background
     └─ fix the V07C/V07B version-probe bug (Part 12) BEFORE the range run
     └─ scripts/fetch/fetch_11_imerg.py, extended to a date range
        It finishes in a couple of hours, not days — don't plan the week around it

 ②  Build the 100 m grid + terrain derivatives   [~2–3 days]
     └─ slope, aspect, curvature, TWI from the DEM
     └─ distance-to-fault / river / road
     └─ join every raster + polygon onto the grid → data/interim/grid_100m.parquet
     ✓ CHECK: eyeball the slope map. Do the steep areas match the mountains?

 ③  Build the susceptibility model               [~3–4 days]
     └─ sample positives (35,744) + constrained negatives
     └─ train LightGBM, spatial-block cross-validate
     └─ compare against GSI's 50 m map
     ✓ CHECK: honest AUC ≥ 0.80 on held-out districts, and the feature-importance
       ranking is physically sensible (slope should be near the top)

 ④  Build the rainfall pipeline                  [once ① finishes]
     └─ rolling sums (3/7/15/30 day) over the archive
     └─ fit intensity–duration thresholds
     ✓ CHECK: do the 2017 and 2023 Bhuvan slide years light up?

 ⑤  Build the trigger model                      [~1 week]
     └─ weak labels (Technique 2) + pooled Himalayan events (Technique 4)
     └─ ID exceedance ratio as a feature; threshold as an alert floor
     └─ negatives drawn ONLY from well-mapped corridors
     ✓ CHECK: POD/FAR on held-out years, not held-out rows

 ⑥  Wire the daily run                           [~1 week]
     └─ fetch yesterday's IMERG + today's GFS → score → aggregate → store
     ✓ CHECK: it runs unattended for 7 days without intervention

 ⑦  Delivery layer                               [~2 weeks]
     └─ API, dashboard map, bulletin generator, alert dispatch
     ⚠ build hazard-agnostic — flood plugs in here later

 ⑧  Backtest & publish honest numbers            [ongoing]
     └─ replay 2023, report POD/FAR, let the client set the threshold

 ── parked / later ──────────────────────────────────────────────
 ⑨  Label factory: date the inventory from imagery   ← the one NN
     └─ prototype on a SAMPLE of known-date slides first:
        are the scars actually detectable in Sentinel-2?
     └─ only scale up if the prototype works
     ✓ CHECK: recovers known dates on NASA GLC's 90 dated events

 ⑩  Flood leg                                    [parked]
     └─ GloFAS for big rivers; rainfall-accumulation watch for small ones
```

**Steps ② and ③ need no new data.** You can start tomorrow — and since ① now finishes in
about two hours rather than days, the archive won't be what's holding you up.

**Step ⑨ is deliberately last-but-prototyped-early.** It's the highest-leverage item in the
whole plan (it manufactures the temporal labels everything else is starved of), but it's
also the one most likely to fail on contact with reality. Spend a day proving scars are
detectable before committing weeks to it.

---

## Part 14 — Glossary

| Term | Plain English |
|---|---|
| **Raster** | A grid of numbers laid over the map. One value per cell |
| **Vector** | A list of shapes (points/lines/polygons), each with attributes |
| **DEM** | Digital Elevation Model — a raster of ground heights. Slope, aspect and curvature are all computed *from* it |
| **Feature** | One input column the model looks at (slope, clay %, rainfall…) |
| **Label** | The answer we're teaching from ("landslide happened here: yes/no") |
| **Supervised learning** | Learning from examples where we know the answer |
| **Weak supervision** | Learning from imprecise labels ("sometime in 2017") |
| **Strong / weak label** | Strong = "slide here on 12 July 2017". Weak = "slide here sometime in 2017". Weak ones still work in bulk: wrong guesses scatter, right ones pile up on the extreme-rain days |
| **Gradient-boosted trees** | The model we use. Builds many small if-then rulebooks, each fixing the last one's mistakes. Best-in-class for tabular data; explains itself |
| **SHAP** | Method that says *how much each feature contributed* to one specific prediction. Why a cell scored 0.81, not just that it did |
| **Transfer learning** | Reusing knowledge from data-rich regions in a data-poor one. Does **not** require a neural network — pooling rows with a `region` feature is the simple version |
| **Fine-tuning** | Taking a model trained elsewhere and nudging its weights with local data. Buys accuracy when labels are scarce; costs explainability and debuggability |
| **Intensity–duration (ID) threshold** | The classic rainfall rule: a curve of "this hard for this long" above which slides start. We use it as a model *feature* and as an alert floor |
| **Susceptibility** | WHERE slopes are capable of failing. Carries no date. Loaded guns |
| **Trigger** | What sets it off — almost always rain |
| **Antecedent rainfall** | How much already fell over previous days. Often a better predictor than today's rain |
| **Angle of repose** | Steepest angle loose material holds without sliding, ~30–35° for most soils |
| **TWI** | Topographic Wetness Index — how much upslope land drains into a cell |
| **Lithology** | What rock is underneath |
| **Lineament** | A fault or fracture line in the bedrock. Rock near one is shattered and weak |
| **POD** | Probability of Detection — of events that happened, the share we warned for |
| **FAR** | False Alarm Ratio — of warnings issued, the share that were wrong |
| **Discharge** | Water passing a river point per second (m³/s) |
| **Reanalysis** | A physics model of past weather, run with observations fed in, producing a gap-free record |
| **Spatial cross-validation** | Testing on whole held-out *regions* rather than random rows, so neighbouring cells can't leak the answer |
| **Parquet** | A compressed table file format. Loads far faster than CSV |
| **Tier A / B / C** | How hard data is to get. A = open. B = free account. C = human action (waitlist, portal, formal request) |

---

## The five things to remember

1. **The product is a forecast.** Susceptibility is an ingredient inside it, never the
   deliverable.
2. **WHERE × WHEN.** Neither half alone warns anyone.
3. **We have 35,744 answers to WHERE and almost none to WHEN.** That single fact
   determines the entire architecture. Both halves are machine learning — but the WHEN
   half is trained on manufactured labels (weak labels, pooled Himalayan events, and
   eventually dates recovered from satellite imagery) with rainfall physics constraining
   it from the inside.
4. **No neural network in the thing that makes predictions; one neural network in the
   thing that makes training data.** Trees are the right tool for tabular data at our
   size, and they can explain a score to APSDMA. Image-based dating of the inventory is
   the one genuine deep-learning job — and it sits offline.
5. **Nothing is blocked by permission.** The only real blocker is a rainfall archive that
   needs downloading — and that's a ~2-hour job, not a multi-day one.
6. **POD/FAR is the client's decision, not ours.** Put the threshold choice in writing.
