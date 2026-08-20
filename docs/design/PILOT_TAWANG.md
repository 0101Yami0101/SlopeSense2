# Pilot idea — Tawang district, starting from Jang

> **Status: idea, not started.** Logged 2026-08-20 so it isn't lost. Nothing built yet.

## Why Tawang/Jang specifically

- Small enough to fully instrument on a modest budget — unlike a statewide rollout.
- Already has more real local data than most of the state (see below) — a head
  start no formal ask created.
- A genuine second hazard worth showcasing: **glacial lake outburst flood (GLOF)
  and snowmelt**, distinct from the rain-driven story everywhere else. Real
  glacial lakes sit upstream of the valley (see NWIA finding, `DATA_VERIFICATION.md`).
- Border-road corridor maintained by BRO — plausibly better on-ground access for
  installing/maintaining any paid sensors than remote interior districts.

## What's already free and usable today

- **Landslide susceptibility + daily trigger** — statewide build already covers
  this area, no extra work. Caveat: IMERG rainfall bias is known to be worse at
  this altitude than in the lowlands.
- **Flood static layer** — our own build already says **Tawang town itself is
  NOT flood-prone** (705 m above nearest drainage, class 0). **Jang, down in the
  valley on the actual river, is unconfirmed and worth checking specifically.**
- **Two real, live-updating CWC river-level gauges right in the area**:
  `Murga Bridge` (002Neid3) and `Rho Basti` (001NEID3), both reporting as
  recently as 2026-08-19. (A third station literally named "Jang" exists but
  is dead — stopped reporting in 2021, not useful.) No danger/warning
  threshold published for either yet — see Ask, below.
- **NESDR snow-cover layer** — relevant given Tawang's real seasonal snow.
- **NWIA wetland/glacial-lake maps** (APSAC, found 2026-08-20) — includes a
  glacial-lake category specifically; not yet confirmed downloadable, see
  `DATA_VERIFICATION.md`.

## Ask, specific to this one small district

1. CWC: history + danger/warning thresholds for Murga Bridge and Rho Basti.
2. BRO: road-block logs for this corridor — plausibly the best-kept landslide
   date records in the state, given military road maintenance.
3. Tawang DDMA: local incident records — a small office, more tractable than a
   state-wide request.
4. IMD: a ground rainfall station locally, to correct the high-altitude
   satellite bias.

## Paid, if this pilot gets funded

1. A few more water-level sensors along the river through Jang — a complete
   micro-network for one valley, not a token station.
2. Detailed terrain (LiDAR) for just the Jang valley — cheap at this scale,
   enough to turn a risk score into an actual "water reaches here" map.
   APSAC's own infrastructure page (`infrastructure.php`) says they already run
   in-house LiDAR point-cloud processing — worth asking whether a commissioned
   local survey is possible before sourcing this from an outside vendor.

Full source detail for everything referenced here: `DATA_VERIFICATION.md`.
