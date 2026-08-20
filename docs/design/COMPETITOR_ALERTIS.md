# Competitor scan: Alertis Private Limited (alertis.in)

Research pass on 2026-08-20, same question set as [[COMPETITOR_IIOTS]]. Sources linked
inline. Two of the site's own PDFs (case study + certificates) were fetched and read
directly rather than through the summarizing web-fetch, since the first pass on them
came back garbled — the direct read is quoted below and is the more reliable source in
this doc.

## 1. Who they are

- **Alertis Private Limited**, HQ **Dehradun, Uttarakhand**. Registered address: P179,
  Alaknanada Enclave, Lane H, Nathanpur, Jogiwala, Badripur, Dehradun-248005.
- **Incorporated 29 October 2025** — under a year old as of this research (Aug 2026).
  CIN `U62099UT2025PTC020154`. ([Tofler company record](https://www.tofler.in/alertis-private-limited/company/U62099UT2025PTC020154))
- **Two directors: Tanmay Benjwal and Jyoti Benjwal.** No IIT/academic affiliation, no
  faculty co-founders, and no bios published anywhere on the site or in press — unlike
  iIoTs there is no "About/Team" page at all on alertis.in.
- Branded under Startup India (`#startupindia`) and "Make in India" marks on their own
  materials — self-declared scheme registration, not a merit award.
- **No independent press coverage found anywhere** — not one news article, blog post,
  or third-party mention turned up in repeated searches, only the company's own site
  and its own PDFs, plus company-registry listings (Tofler/Tracxn). Compare to iIoTs'
  40+ press articles including BBC, PM Modi's office, and NITI Aayog.

## 2. Are they "exactly like us"? — No, and also not quite like iIoTs

Structurally they're closer to iIoTs than to us (a hardware/sensor company, not a
forecasting platform), but shallower and much newer:

| | Alertis | iIoTs / Intiot | Us |
|---|---|---|---|
| Founded | Oct 2025 (<1 yr) | 2019-20 (~6 yrs) | — |
| Founders | 2 non-academic directors | 4, IIT Mandi faculty + researchers | — |
| Core asset | Physical sensor pods, sold as a monitoring product | Physical sensor pods, sold as a monitoring product | Statewide forecast model, no field hardware |
| Hazard scope | Landslide, flood, **forest fire**, **structural health** (bridges/buildings) | Landslide + weather + air quality + unrelated health devices | Landslide + flood only |
| ML claimed | "SVM and time-series forecasting" (one-line site claim, no papers) | Published, peer-reviewed stacked-ensemble + deep-learning models (DISEL, LogISEL) | Trees, statewide, published internally |
| Proof of a real save | None found — own case study explicitly reports no real event occurred | Kotropi 2018, documented, government-acknowledged | None yet (unvalidated, by design — see [[landslide-first-flood-parked]]) |
| Government relationship | None found | MoUs, PM visit, state award, NITI Aayog feature | None yet |
| Certs held | ISO 9001:2015 (quality process), DoT wireless Equipment Type Approval | 4 patents | — |
| Geography | Uttarakhand (western Himalaya) | Himachal Pradesh + a little Uttarakhand (western Himalaya) | Arunachal Pradesh (eastern Himalaya) |

## 3. What did they do, and how?

- **Landslide Monitoring**: tilt sensors, ground-displacement sensors, rainfall
  telemetry. Alerts are **threshold-based** with a continuously-updated "dynamic risk
  score." No sub-millimetre or inverse-velocity claims like iIoTs — just threshold
  crossing.
- **Flood Monitoring**: water-level sensors, radar-based rainfall feeds, "predictive
  modeling" across river basins/reservoirs/catchments — SMS/email/control-room alerts.
  This is the one area where Alertis is *ahead of iIoTs on paper*: iIoTs has no flood
  product at all; Alertis claims one (though with no case study or data to back it, see
  below).
- **Forest Fire Monitoring**: thermal imaging + "AI-assisted smoke detection" to filter
  false alarms (fog/dust) — a hazard neither we nor iIoTs touch.
- **Structural Health Monitoring**: vibration/strain sensors on bridges, buildings,
  general infrastructure — general industrial IoT, not disaster-specific.
- **Hardware, confirmed from their own regulatory filing**: model
  `alertisEWS/SHM_2026_v1M:I`, radios at **865-867 MHz (India's LoRa/ISM band), 2.4 GHz,
  and 5.2 GHz** (Wi-Fi bands), solar-powered, cloud dashboard branded **alertis.ai**.
  This is a real, DoT-registered piece of hardware, not vaporware — see §9.
  (Source: Alertis' own Equipment Type Approval certificate, Department of
  Telecommunications, Reg. No. ETA-SD-20251211401, dated 06-01-2026.)
- **The one case study on their site** ("Himalayan Highway, India" — filed under the
  URL name `tota_ghati_case_study.pdf`, though the document itself never names Tota
  Ghati; possibly the same demo deployment the URL slug refers to, on the geologically
  active NH-58 corridor known locally as **Tota Ghati**, Tehri district, Uttarakhand —
  a real, well-documented active-landslide stretch,
  [Down To Earth on the actual site](https://www.downtoearth.org.in/environment/char-dham-how-geological-instability-and-blasting-are-causing-landslides-in-tota-ghati-74677)).
  Quoting their own PDF directly:

  > "During six months of continuous operation: System performed reliably in real
  > terrain conditions. Sensor readings remained stable and consistent. **No natural
  > displacement was detected.** External disturbances were correctly identified.
  > These findings validated the platform's reliability and field readiness."

  In plain terms: **this is a hardware-reliability trial, not a disaster-prevention
  event.** No landslide happened during the six months monitored, so the case study
  proves the sensors stayed online and read stable values — it does not demonstrate a
  correct alert being issued ahead of a real slope failure. That's a meaningfully
  weaker claim than iIoTs' Kotropi story, and worth being precise about if this ever
  comes up in a client conversation: Alertis has not yet published a case where their
  system caught a real event.

## 4. Are they using deep learning? What ML, exactly?

Much less than iIoTs, and unverifiable. The entire technical claim, site-wide, is one
line: **"Support Vector Machines (SVM) and time-series forecasting."** No papers, no
architecture detail, no accuracy/F1/AUC numbers, no named dataset, no interpretability
analysis. The landslide and structural-health products are explicitly described as
**threshold-based alerting** (a risk score crossing a line), which is a much simpler
and more conventional technique than "AI" branding suggests — thresholding on tilt/
displacement/rainfall doesn't require SVM or any ML at all; the ML claim and the
described alerting mechanism don't obviously line up. No deep learning claim is made
anywhere on the site, despite "AI-enabled" language throughout the marketing copy.

Compare directly to iIoTs' DISEL/LogISEL: peer-reviewed, presented at a real venue
(ICVGIP 2025) and a real journal (*Geoscience Letters*), with macro-F1/PR-AUC/SHAP
reporting. Alertis has nothing comparable published anywhere found.

## 5. Where did their training data come from?

Unknown/unstated. The only data lineage mentioned anywhere is the one six-month field
trial described in §3, which by their own account **recorded no landslide event** — so
if an SVM or any classifier exists, its positive-class training data (what a landslide
actually looks like in their sensor stream) cannot have come from that trial. No other
data source, historical dataset, or lab test-bed (cf. iIoTs' flume rig) is mentioned
anywhere on the site or in any filing found. This is the single biggest open question
about the company: there's no visible answer to "what did you train the model on."

## 6. How different are we, really?

Same structural relationship as with iIoTs (§6 of [[COMPETITOR_IIOTS]] applies almost
verbatim) — they're a point-sensor company, we're a statewide-forecast company — but
with a much thinner evidence base underneath it on their side. No published model, no
demonstrated real-event catch, no independent validation of any kind. If iIoTs is "a
real research group with 6 years of field validation building point sensors," Alertis
reads as "a brand-new hardware/IoT company applying an early-warning label to a
general-purpose SHM sensor product line, days into its public existence." Both are
non-competing with a statewide forecast layer for the reasons in §6 of the iIoTs doc —
but Alertis additionally isn't yet a fully proven point-sensor player either.

## 7. What do they have that we don't?

- **A shipped, DoT-certified piece of hardware today.** Whatever the ML rigor, the
  radio/sensor/solar hardware itself is real and regulator-approved — that's a genuine,
  concrete thing that exists, which we don't have any equivalent of.
- **A published flood-monitoring product**, on paper covering exactly the hazard where
  we've flagged our own weakest leg (see [[arunachal-forecast-tiers]] — flood free tier
  covers only large rivers). No detail or validation behind their claim was found, so
  this is "they say they built it," not proof they solved anything we haven't.
- **Forest fire and general structural-health monitoring** — hazards outside our scope
  entirely; not directly relevant to a landslide/flood comparison but shows a wider
  commercial footprint if they execute on it.

## 8. Could/should we do what they did?

Less relevant here than for iIoTs — there isn't yet a demonstrated technology to
benchmark against. If anything, Alertis is a useful **cautionary comparison**: "AI-
enabled" marketing copy, a threshold-based alert system with an SVM name-drop and no
published methodology, and a case study that (read carefully) reports zero real events
caught. It's a reminder of the bar our own materials should clear — cite what's
actually validated (see [[percentile-max-is-not-a-probability]]) rather than lean on
AI branding the way this one line of their homepage does.

## 9. Our USP against them

Everything in §9 of [[COMPETITOR_IIOTS]] still applies (statewide + hardware-free +
answers a question point sensors structurally can't). Against Alertis specifically,
add: **we have more disclosed methodology than they do.** Our own internal docs name
actual models, actual data sources, and actual measured numbers (including the ones
that came back negative, e.g. [[constrained-negatives-dont-help-in-steep-terrain]]).
Alertis' public materials, by contrast, don't show their work anywhere — that's not
automatically damning for a pre-seed hardware startup, but it does mean nothing here
should be treated as a bar we need to catch up to; if anything the flood-monitoring
claim is worth quietly re-checking again in 6-12 months once (if) they publish more,
since it's the one place their stated scope sits closer to ours than iIoTs' does.

## 10. Reaching "their stature" — not applicable yet

There's no stature to reach here in the way there is with iIoTs — no government
relationship, no press, no independent validation found as of this research. Worth a
re-check later (company is 10 months old; give it time) rather than treating anything
here as an established bar.

## Sources

- [alertis.in — home](https://www.alertis.in/) · [services](https://alertis.in/services)
- [Alertis case study PDF](https://alertis.in/docs/tota_ghati_case_study.pdf) — read directly, quoted in §3
- [Alertis certificates PDF](https://alertis.in/docs/certificates.pdf) — ISO 9001:2015 (QRO, cert 305025121046Q) + DoT Equipment Type Approval (Reg. ETA-SD-20251211401) — read directly
- [Tofler — company registry record, incorporation date, directors](https://www.tofler.in/alertis-private-limited/company/U62099UT2025PTC020154)
- [Tracxn — company profile](https://tracxn.com/d/legal-entities/india/alertis-private-limited/__z0osIiK-W69NMs9lO7AGb29t4TqjksrF-jRRU27p3TA)
- [Down To Earth — Tota Ghati site background (unrelated to Alertis, confirms the location is real and actively unstable)](https://www.downtoearth.org.in/environment/char-dham-how-geological-instability-and-blasting-are-causing-landslides-in-tota-ghati-74677)
- Cross-reference: [docs/design/COMPETITOR_IIOTS.md](COMPETITOR_IIOTS.md)
