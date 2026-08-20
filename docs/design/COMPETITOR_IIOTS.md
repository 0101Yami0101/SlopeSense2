# Competitor scan: iIoTs / Intiot Services (IIT Mandi)

Research pass on 2026-08-20, triggered by the team page at https://www.iiots.in/team.html.
Sources are linked inline; nothing here was independently verified beyond what's in the
cited articles/papers, and several numbers (esp. "99% accuracy") are founder soundbites
from press interviews, not audited figures — flagged where that matters.

## 1. Who they are

- **iIoTs** is the product/brand name; the legal entity is **Intiot Services Pvt Ltd**,
  described as "IIT Mandi's first student-faculty-led startup," founded 2019-20 and
  incubated through **IIT Mandi Catalyst**. Team page also lists an "IIT Madras" line in
  the site header, but every deployment, award, and press mention ties back to IIT Mandi
  (Kamand campus, Himachal Pradesh) — Madras appears to be a secondary
  affiliation/incubation credit, not the operating base.
- Four directors, all IIT Mandi-affiliated: **Varun Dutt** (faculty, data science/ML),
  **K.V. Uday** (faculty, geotechnical engineering), **Praveen Kumar** (ML/IoT,
  postdoc'd at Max Planck), **Ankush Pathania** (hardware/embedded systems). Plus an
  advisor (ex-IFS officer) and a business-development manager — a small, real team, not
  a shell.
- Origin story: the 2017 Kotropi landslide (Mandi district) killed dozens on a highway;
  Dutt and Uday built the first prototype in response and field-tested it near their own
  campus (Gharpa hill) within months.
  [The Better India](https://thebetterindia.com/259584/iit-mandi-innovation-himachal-landslide-rainfall-early-warning-device-save-lives/),
  [Tribune](https://www.tribuneindia.com/news/himachal/developed-by-iit-landslide-monitoring-system-reviewed-355312)

## 2. Are they "exactly like us"? — No. Different shape of product entirely

They are a **hardware/IoT company that also does ML**, not a forecasting platform.
Our project (SlopeSense/FloodSense) is a **statewide remote-sensing + ML forecasting
layer** with no physical field hardware. iIoTs is the mirror image: **physical
sensors bolted to named, already-known-dangerous slopes**, with ML riding on top of
that sensor stream.

| | iIoTs / Intiot | Us (SlopeSense/FloodSense) |
|---|---|---|
| Core asset | Physical sensor boxes installed on specific slopes | Statewide model over satellite + government data feeds |
| Coverage model | Point — one slope at a time, ~60 sites total | Area-wide — every pixel/slope across a state |
| Ground truth | Their own live sensors (soil moisture, rainfall, displacement) + a physical flume test-bed | GSI/Bhuvan inventories, GSI PDF reports, CWC/NWDP gauges, satellite rainfall/LULC |
| Alerting | Local siren/blinker/traffic-signal hardware + SMS, at the exact site | Would be advisory/dashboard-based (no field hardware) |
| Business model | Sell + install + maintain hardware, mostly to district administrations (govt contracts) | Platform/data product |
| Geography | Himachal Pradesh (western Himalaya), a few Uttarakhand sites, Kangra MoU | Arunachal Pradesh (eastern Himalaya) |
| Product range | Landslide + weather station + air quality + medicine cold-chain + glucose breath sensor + ECG wearable | Landslide + flood, single hazard-agnostic core (see [[landslide-first-flood-parked]]) |

They have **no flood product** found anywhere on the site or in press coverage — their
whole hazard focus is landslide (plus unrelated health/air-quality/IoT side products).
Flood is untouched territory for them.

## 3. What did they do, and how?

- **Landslide Monitoring System (LMS)**: an in-situ sensor pod per slope — soil
  moisture, rainfall, temperature, humidity, and (in the ML papers) **triaxial
  acceleration** for ground-movement/displacement, claimed sensitive to
  **sub-millimetre shifts**. Data is sent to a cloud backend; alerts go out as SMS to
  residents/authorities and trigger physical hooters/blinkers and traffic-signal
  control at the site itself.
- **Flume Test Bed Setup**: a physical, scaled rainfall-induced-slope-failure rig used
  to generate controlled training data and calibrate/train the sensors before field
  deployment — i.e. they don't rely solely on waiting for real slopes to fail; they
  manufacture labelled failure events in a lab-scale flume.
  ([Springer chapter, "Training of Sensors for Early Warning System of
  Rainfall-Induced Landslides"](https://link.springer.com/chapter/10.1007/978-3-030-01665-4_104))
- First real-world save: **27 July 2018, Kotropi**, the system sounded the alarm ahead
  of a flash-flood-triggered slide on the Mandi–Joginder Nagar highway — this is the
  single incident every article and their own homepage lean on.
- Scale as of the most recent reporting: **~60 sites installed, ~45 operational**
  (25% down to malfunction/vandalism) across Mandi, Kinnaur, Kangra (HP), a few in
  Uttarakhand (Balianala), Sirmaur, and one railway site (Dharampur). A Kangra DDMA MoU
  (Feb 2022) targets up to 100 sites there specifically, running through 2027.
  **Correction on re-check:** the MoU also mentions InSAR/satellite subsidence imaging,
  but its documented role is narrower than first read — it's a **site-selection aid**:
  new sensor locations "will be selected based on on-site visits and satellite imaging
  through InSAR-based analysis," feeding into "the development of machine learning
  approaches to generate prediction-based warnings" (i.e. back into their per-slope
  movement models). It has never been published or offered as a standalone regional
  forecast — see §6 for why this matters.
  ([Tribune, Kangra 100 systems](https://www.tribuneindia.com/news/himachal/kangra-to-have-100-early-landslide-warning-systems-366247),
  [OpenGov Asia](https://opengovasia.com/2022/02/09/ten-landslide-early-warning-systems-to-be-set-up-in-kangra-india/))
- Cost pitch: **~₹1 lakh (~$1,200) per site**, pitched as ~200× cheaper than
  conventional (crore-scale, imported) slope instrumentation. This is their core
  commercial USP against traditional geotechnical monitoring vendors, not against
  forecasting platforms like ours.

## 4. Are they using deep learning? What ML, exactly?

Yes, and it's more rigorous than the press coverage suggests — the actual published
papers are the real signal, not the "99% accuracy" quotes:

- **DISEL** (Deep Learning Integrated **S**tacked **E**nsemble **L**earning),
  Chand/Dutt/Uday, presented at **ICVGIP 2025**: heterogeneous base learners — kNN,
  Logistic Regression, Random Forest, XGBoost, LightGBM, CatBoost — each producing a
  probability vector, fed into a **deep-learning meta-model/blender** (best variant:
  LightGBM blender). Multi-class **movement prediction, ~10 minutes ahead**, evaluated
  with **macro-F1 and PR-AUC** (not blanket accuracy) on multi-year data from five
  sites near Gharpa/Griffon Peak, HP.
- **LogISEL** (interpretable variant), Geoscience Letters (2026): six ML classifiers
  stacked through a **logistic-regression meta-learner** instead of a black-box
  blender, tested at two geologically different sites (**Griffon Peak** and
  **Ghora Farm**, HP), predicting 10 minutes ahead. Explicitly **does not
  artificially rebalance** the landslide-vs-stable class imbalance (a problem we've
  hit too — see [[constrained-negatives-dont-help-in-steep-terrain]]). Reports
  15–20%+ improvement over baselines, and uses **SHAP** to show which sensor feature
  drives each site's predictions (temperature lag at the alpine site, light/pressure
  swings at the cultivated-slope site) — genuinely interpretable, not just a
  black box with a headline number.
- **Separately**, their Air Quality product uses "an ensemble of deep learning models"
  for pollutant forecasting — same ensemble-DL house style applied to a different
  hazard.

So: yes to deep learning, but it's deep learning **as a meta-learner stacked on top of
classical tree/linear models**, trained on **dense, high-frequency, single-site
time-series sensor streams** — a completely different data regime from ours. This is
much closer to a signal-processing/time-series anomaly problem (minutes-ahead, one
instrumented slope, continuous readings) than to our problem (which-slope-out-of-thousands,
days-ahead, sparse historical labels). It's *why* trees-plus-DL-blender works for them
and isn't in tension with our own [[why-trees-not-deep-learning]] finding — their label
scarcity is solved by literally wiring up the slope and the flume rig; ours can't be,
because there's no equivalent physical instrument for an un-visited slope 200 km from
a road in Arunachal.

## 5. Where did their training data come from?

Entirely **their own instruments**, not third-party inventories or satellite archives:

1. Live sensor streams from the ~45–60 deployed field sites (soil moisture, rainfall,
   temperature, humidity, ground displacement/acceleration), accumulated over
   multiple years since ~2018.
2. The physical **flume test-bed** — controlled, repeatable, lab-induced slope
   failures used to generate clean labelled events and calibrate sensor thresholds
   before trusting them in the field.
3. (Emerging) satellite-based ground subsidence data for the Kangra MoU — their first
   documented move toward remote sensing.

This is the opposite failure mode from ours: **they have dense continuous data but
only at ~60 named points**; we have **statewide coverage but sparse, low-frequency
event labels** (see [[only-90-dated-landslide-events-exist]],
[[bhuvan-year-is-the-event-year]]). Neither data regime transfers to the other's
problem — you cannot use their per-slope sensor time-series to train a statewide
susceptibility model, and our statewide susceptibility layer can't tell you a specific
slope will move in the next 10 minutes.

## 6. How different are we, really — and what's the overlap?

**Genuinely complementary, not head-to-head competitors**, because they solve a
different half of the same national problem — and a GSI official said as much in the
Down To Earth piece: site-specific sensors are "extremely cost-prohibitive" at the
scale of India's 87,000+ known active landslides, while regional/statewide systems
"sacrifice specificity," and local officials want both. That's precisely the two
halves iIoTs and we occupy:

- **They answer**: "Is *this one slope we already worry about* about to move in the
  next few minutes to hours?" — hyper-local, real-time, needs the slope to already be
  on someone's watch-list and be reachable enough to install/maintain hardware.
- **We answer** (or aim to): "*Which* of the thousands of slopes/catchments across an
  entire state are worth worrying about at all, this season?" — statewide triage, no
  hardware, works even for slopes nobody has visited yet.

**Checked directly (2026-08-20): no evidence they have a "which slope" model at all.**
Every published model of theirs (DISEL, LogISEL, the 2022 MLP movement-prediction
paper) takes live sensor readings from an already-instrumented slope as input — none
of them run on an un-instrumented site, and none produce a regional/statewide ranking.
Their one satellite/InSAR component (§3) is explicitly a manual site-selection aid for
a human picking where to bolt the next sensor, not a published or sold forecasting
product. So the "find the dangerous slope" layer isn't just something we do better —
it's a layer that doesn't exist on their side at all. That's the real gap, not merely
a difference in emphasis.

A mature disaster-management stack in a state needs both stages: our kind of model to
find/rank the dangerous slopes and catchments, then something like their kind of
device on the handful that make the cut. That's the honest relationship, and it's a
genuinely strong pitch line if this ever comes up with a government client: **"we tell
you where to put the ₹1-lakh sensor; on their own, they only work once you already
know where to look."**

## 7. What do they have that we don't?

- **A real, publicly documented life-saving event** (Kotropi, 2018) — the single most
  persuasive thing in their entire pitch, and something no amount of backtest AUC can
  substitute for.
- **Direct, sustained government trust**: PM Modi personally reviewed the system
  (Dec 2021, Mandi visit); a signed MoU with Kangra DDMA; HP Chief Minister's
  entrepreneurship award (2022); multiple Skotch Awards; national press (BBC, Economic
  Times, India Today) since 2021; a NITI Aayog Frontier Tech feature. That's five-plus
  years of visible institutional relationship-building we don't have yet — see
  [[gsi-licence-blocks-commercial-delivery]] for our own current gap on the
  government-access side.
- **Four filed patents** on the hardware/system side.
- **Actual ground-truth instrumentation** — a real accelerometer on a real slope
  measures real movement; no satellite product can do that at sub-millimetre
  resolution, full stop. This is a hard physical capability gap, not a modelling
  choice.
- **A revenue-generating hardware/services business** already selling into district
  administrations, vs. our still-unvalidated platform (see
  [[landslide-first-flood-parked]]).

## 8. Could we do what they did? Should we?

Technically yes — none of it is exotic (soil-moisture/rainfall/tilt sensors, a
microcontroller, SMS/cloud backend, a stacked-ensemble classifier). But it's a
different company shape: hardware manufacturing, field installation, and physical
maintenance crews. Arunachal Pradesh makes this materially harder than Himachal:
far worse road access, an active international border with associated security/permit
friction (Inner Line Permit zones), much lower population density near many
slopes/catchments to notice vandalism or failures quickly, and a much larger
unroaded area per person than HP. Their own numbers already show a 25% field-failure
rate in HP, which has vastly better infrastructure than most of AP — a straight port of
their model would likely see worse uptime here, not better.

The more defensible move is the hybrid described in §6: keep building the statewide
forecast layer (our actual comparative advantage — see §9), and treat point sensors as
a possible **downstream product for the highest-priority sites the model identifies**,
not a parallel effort to their whole build. That could even be a literal
partnership/licensing conversation with them rather than a from-scratch competitor
build, given they already have the hardware, patents, and government relationships for
that half of the stack.

## 9. Our USP against them

1. **Statewide, hardware-free coverage.** No boxes to install, steal, vandalize, or
   maintain in terrain where iIoTs' own 25% field-failure rate would likely be worse.
2. **Flood is untouched by them.** We're building it as a first-class second hazard
   ([[flood-build-own-not-feed]]); they have zero flood presence in any source found.
3. **Answers a question they structurally cannot**: which un-instrumented, never-
   visited slope or catchment deserves attention in the first place. Their model only
   ever runs on slopes someone already chose to wire up.
4. **Eastern Himalaya, not western** — genuinely different terrain, rainfall regime,
   and (per our own data work) different data ecosystem (CWC/NWDP gauges, GSI reports,
   NESDR LULC) that a Himachal-tuned sensor product wouldn't automatically transfer to
   without re-validation anyway.

## 10. Reaching their stature, tech-wise

Their credibility didn't come from a single big model — it came from **stacking small,
verifiable wins over ~5 years**: one real save (Kotropi) → district-administration
pilot → press coverage → PM-level visit → formal MoU → awards → peer-reviewed papers
validating what the press already believed. The technical bar (stacked ensembles,
SHAP interpretability, honest macro-F1/PR-AUC reporting instead of vanity accuracy) is
achievable for us on our own hazard once we have a comparable real-world validation
event and a similarly patient multi-year government relationship — there's no
technique here we couldn't replicate; what's missing is time-in-market and one public
proof point, which is exactly the gap the MVP-first plan is meant to close (see
[[gsi-licence-blocks-commercial-delivery]]).

## Sources

- [iIoTs — Home](https://www.iiots.in/) · [Team](https://www.iiots.in/team.html) · [Products](https://www.iiots.in/products.html) · [News coverage index](https://iiots.in/News%20Pages.html)
- [The Better India — original 2021 feature](https://thebetterindia.com/259584/iit-mandi-innovation-himachal-landslide-rainfall-early-warning-device-save-lives/)
- [The Better India — 2026 follow-up, "3-hour warning"](https://thebetterindia.com/innovation/iit-mandi-ai-landslide-warning-system-dr-uday-10780755)
- [Down To Earth — critical piece on localized EWS limits, GSI quote, 45/60 operational](https://www.downtoearth.org.in/natural-disasters/stemming-the-landslide-heres-why-localised-early-warnings-in-india-still-an-uphill-battle)
- [NITI Aayog Frontier Tech feature](https://frontiertech.niti.gov.in/story/low-cost-indigenous-sensors-ai-deliver-real-time-landslide-alerts-across-himalayan-slopes)
- [Tribune — PM Modi review, patents, Rs 1 lakh pricing](https://www.tribuneindia.com/news/himachal/developed-by-iit-landslide-monitoring-system-reviewed-355312)
- [Careers360 — Chief Minister's Entrepreneurship Award 2022](https://news.careers360.com/iit-mandi-startiup-won-entrepreneurship-award-for-developing-landslide-monitoring-system)
- [Tribune — Kangra to have 100 systems](https://www.tribuneindia.com/news/himachal/kangra-to-have-100-early-landslide-warning-systems-366247)
- [OpenGov Asia — Kangra MoU detail](https://opengovasia.com/2022/02/09/ten-landslide-early-warning-systems-to-be-set-up-in-kangra-india/)
- DISEL and LogISEL papers — abstracts via search (ResearchGate/Springer full text paywalled): ICVGIP 2025 (Chand, Dutt, Uday) and *Geoscience Letters* 2026 (LogISEL)
- [Springer — "Training of Sensors for Early Warning System of Rainfall-Induced Landslides" (flume test-bed)](https://link.springer.com/chapter/10.1007/978-3-030-01665-4_104)
