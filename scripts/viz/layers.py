"""Registry of everything shown in the visualisation layer.

TO ADD A NEW DATASET
--------------------
1. Add a figure-producing function in `extract.py` (optional — a card can be
   numbers only).
2. Append a LAYER entry below.
3. Add the card's file globs to CARD_FILES in `extract_raw.py`, so the
   under-the-hood flip has something to show. Skip only if nothing was
   downloaded for it.
4. Re-run `extract.py`, `extract_raw.py`, then `build.py`.

Nothing else needs touching. Order here is the order on the page.
"""

# Sections group the cards. `id` is used for the nav.
SECTIONS = [
    ("basics", "Where we are", "The boundary everything else is cut to."),
    ("ground", "The ground itself", "Static properties. These barely change from "
     "year to year, and they decide <em>where</em> a slope is capable of failing."),
    ("water", "Water and rivers", "The drainage network, and how much water moves "
     "through it. This decides where flooding is even possible."),
    ("triggers", "Live triggers", "The things that change hour to hour and actually "
     "set a disaster off. This is the <em>when</em>."),
    ("eyes", "Eyes in the sky", "Satellites that watch the ground. One sees through "
     "cloud, one does not — and that difference shapes the whole system."),
    ("history", "What already happened", "Records of past events. Without these you "
     "can build a model but you cannot prove it works."),
    ("people", "Who is exposed", "A prediction only matters if it reaches someone. "
     "This is who and what is in the way."),
    ("tiers", "What each tier buys", "The product is a <em>forecast</em>. "
     "Susceptibility is the spatial prior inside it, not the deliverable. This is "
     "what accuracy, resolution and lead time look like at each level of data — "
     "free, requested, and purchased."),
    ("gaps", "What we could not get", "Sources that were listed as available and "
     "turned out not to be. Knowing what is missing matters as much as knowing what "
     "is here."),
]

LAYERS = [
    # ---------------------------------------------------------------- basics
    dict(
        id="boundaries", section="basics", title="State and district boundaries",
        source="GADM 4.1", tier="Tier A · free, no account",
        figure="boundaries.png",
        what="""The outline of Arunachal Pradesh and its districts, as polygons.
        Unremarkable in itself, but it is the reference every other layer is cut
        against.""",
        why="""Two practical reasons this matters more than it looks.
        <br><br>First, every raster we downloaded covers a rectangular
        <b>bounding box</b>, not the state. That box reaches deep into Assam, which is
        far more developed and far better mapped. Quoting any number from an unclipped
        box overstates it badly — for OpenStreetMap it inflated road counts by roughly
        7× and buildings by 33×.
        <br><br>Second, a caveat to remember: GADM 4.1 predates recent district
        reorganisation. It has 22 districts; Arunachal now has around 25–26. Fine for
        clipping, not authoritative for reporting by district.""",
        facts=[("Districts", "22"), ("Area", "81,995 km²"),
               ("Format", "Vector polygons"), ("Caveat", "Districts out of date")],
        charts=[],
    ),

    # ---------------------------------------------------------------- ground
    dict(
        id="terrain", section="ground", title="Elevation and terrain",
        source="Copernicus DEM GLO-30", tier="Tier A · free, no account",
        figure="terrain_elevation.jpg",
        what="""A <b>DEM</b> — Digital Elevation Model — is simply a grid where every
        cell holds one number: the height of the ground above sea level. Ours has a
        cell every 30 metres across the whole state. That is 28 tiles and 1.2 GB of
        nothing but heights.""",
        why="""Almost everything else about landslides is derived from this one layer.
        <b>Slope</b> (how steep), <b>aspect</b> (which way the hill faces) and
        <b>curvature</b> (whether the ground is bowl-shaped and collects water, or
        ridge-shaped and sheds it) are all calculated <i>from</i> elevation — they are
        not separate downloads. Get the DEM right and you get all three free.""",
        facts=[("Resolution", "30 m"), ("Tiles", "28"), ("Size", "1.2 GB"),
               ("Missing data", "0.000%")],
        charts=["elev_hist"],
    ),
    dict(
        id="slope", section="ground", title="Slope steepness",
        source="Derived from Copernicus DEM", tier="Computed, not downloaded",
        figure="terrain_slope.jpg",
        what="""Slope is the angle of the ground, in degrees. 0° is a flat floor, 45°
        is a very steep staircase, 90° is a cliff. This map is computed from the
        elevation grid — each cell compares itself to its neighbours.""",
        why="""Loose material on a slope has an <b>angle of repose</b> — roughly
        30–35° for most soils. Below that it generally stays put; above it, the slope
        is already near its limit and only needs a trigger such as rain. This is the
        single strongest predictor of where landslides happen.
        <br><br><b>Caveat worth knowing:</b> the figures below are computed at about
        300 m sampling, which smooths out the sharpest ground. True local slopes are
        steeper than these numbers suggest — treat them as a floor, not a ceiling.""",
        facts=[("Median slope", "14.9°"), ("Steeper than 15°", "49.6%"),
               ("Steeper than 25°", "20.2%"), ("Steeper than 35°", "3.1%")],
        charts=["slope_hist"],
    ),
    dict(
        id="soil", section="ground", title="Soil properties",
        source="SoilGrids 250 m (ISRIC)", tier="Tier A · free, no account",
        figure="soil_properties.jpg",
        what="""Modelled soil chemistry and texture, at 250 m cells, for six depth
        layers. We pulled clay, sand, silt, bulk density, coarse fragments and organic
        carbon at three depths — 18 rasters in total.""",
        why="""Soil texture decides how a slope fails.
        <ul>
        <li><b>Sand</b> drains fast and holds together by friction — grains grip each
        other. Wet sand mostly stays put.</li>
        <li><b>Clay</b> is the dangerous one. It holds water, and when saturated it
        loses cohesion and behaves almost like a lubricant. Clay-rich slopes fail
        after prolonged rain.</li>
        <li><b>Organic carbon</b> is a rough proxy for roots and topsoil structure —
        more of it usually means a better-bound surface layer.</li>
        </ul>
        Soil depth and permeability are not separate downloads — they are estimated
        from these same properties.""",
        facts=[("Resolution", "250 m"), ("Rasters", "18"),
               ("Depths", "0–5, 15–30, 60–100 cm"), ("Coverage", "Complete")],
        charts=[],
    ),
    dict(
        id="geology", section="ground", title="Geology — solved",
        source="APSSDI / APSAC state geoportal", tier="Tier A · free, open WFS",
        figure="geology_state.png",
        what="""<b>Lithology</b> means what kind of rock is underneath. It matters
        because rock type controls how thick the loose surface layer is, how water
        moves through it, and how the slope weathers over time. Alongside it,
        <b>lineaments</b> — the mapped traces of faults, fractures and structural
        breaks, drawn as the dark lines on this map.""",
        why="""This was previously the clearest gap in the project. The free global
        source resolved the whole state into <b>three rock types</b>, which is useless
        at slope scale, and detailed geology was logged as something that could only
        be obtained by formal request to the Geological Survey of India.
        <br><br>That turned out to be wrong. The state's own geoportal (APSSDI, run by
        APSAC) exposes an <b>open WFS endpoint with no authentication</b> — the
        catalogue behind it needs a login, but the map server itself does not. It
        carries the state lithology and, critically, the <b>lineament map</b>.
        <br><br>Published work ranks fault and lineament proximity among the top few
        predictors of landslide location. Both are now downloaded, statewide, and the
        rock resolves into named local formations — Sela Group gneiss, Dirang/Lumla
        schist, Tenga quartzite and others — with schist units in particular being the
        ones that fail.
        <br><br><b>Caveat:</b> the portal publishes no licence statement, and the
        server is intermittent — it refused connections for roughly 30 minutes during
        collection. It also serves a broken TLS chain, which blocks most HTTP clients
        until the missing intermediate certificate is supplied.""",
        facts=[("Lithology polygons", "562"), ("Lithological units", "24"),
               ("Lineaments", "4,777"), ("Was", "3 rock types")],
        charts=["geology_groups"],
    ),
    dict(
        id="landcover", section="ground", title="Land cover",
        source="ESA WorldCover 10 m (2021)", tier="Tier A · free, no account",
        figure="landcover.jpg",
        what="""What is physically on the surface — forest, grass, crops, bare rock,
        snow, water, buildings — classified into 11 types at 10 m resolution. This is
        the sharpest layer we have.""",
        why="""Vegetation holds slopes together. Tree roots physically bind soil and
        draw water out of it, so forested slopes fail less often than cleared ones at
        the same steepness. Where forest is removed — logging, road cutting, shifting
        cultivation — slope stability drops within a few years as old roots rot before
        new ones establish.
        <br><br>Arunachal being 64% tree cover is genuinely protective. The 0.3%
        built-up figure tells you something else: this is a very empty state, and
        exposure is concentrated in a small footprint.""",
        facts=[("Resolution", "10 m"), ("Classes", "11"), ("Tree cover", "63.7%"),
               ("Built-up", "0.3%")],
        charts=["landcover_bar"],
    ),

    # ----------------------------------------------------------------- water
    dict(
        id="rivers", section="water", title="The river network",
        source="HydroSHEDS v1", tier="Tier A · free, no account",
        figure="rivers.jpg",
        what="""Every mapped river reach in the state — 50,800 of them, 91,684 km end
        to end — each tagged with its <b>upstream drainage area</b>: how much land
        drains into that point, in km².""",
        why="""Upstream area is the number that decides everything about flood
        forecasting. A stream draining 5 km² responds to rain in minutes and is
        invisible to a global model. A river draining 50,000 km² responds over days
        and is easy to forecast.
        <br><br>Global flood forecasting systems need drainage areas in the
        <b>thousands</b> of km². The chart below is the single most important finding
        in this whole dataset: at a 5,000 km² threshold, only <b>3% of Arunachal's
        stream network</b> qualifies. The other 97% is invisible to free forecasting —
        and that is precisely the gap the Level 2 build exists to fill.""",
        facts=[("Reaches", "50,800"), ("Total length", "91,684 km"),
               ("Above 5,000 km²", "3.0%"), ("Basins mapped", "348 + 1,680")],
        charts=["river_bands"],
    ),
    dict(
        id="discharge", section="water", title="River discharge forecast",
        source="GloFAS v4 (Copernicus EWDS)", tier="Tier B · free account",
        figure="discharge_peak.png",
        what="""<b>Discharge</b> is the volume of water passing a point each second,
        in cubic metres per second (m³/s). A small mountain stream might run 1 m³/s; the
        Brahmaputra in flood exceeds 50,000. GloFAS models this globally at 5.5 km
        cells and forecasts it 30 days ahead.""",
        why="""This is the operational flood product at Level 1 — and importantly, it
        is <i>not</i> Google Flood Hub, which is still waitlisted. Having GloFAS
        verified means flood forecasting has a working path today with no single-vendor
        dependency.
        <br><br>We pulled both the live forecast and the 2024 monsoon reanalysis. The
        reanalysis is what you calibrate against: it tells you what the model said
        happened, which you compare with what actually happened.""",
        facts=[("Resolution", "5.5 km"), ("Forecast horizon", "30 days"),
               ("Valid pixels", "100%"), ("Peak observed", "56,040 m³/s")],
        charts=["discharge_series"],
    ),

    # -------------------------------------------------------------- triggers
    dict(
        id="rainfall", section="triggers", title="Rainfall — the main trigger",
        source="GPM IMERG Late (NASA)", tier="Tier B · free account",
        figure="rainfall_total.png",
        what="""Satellite-estimated rainfall, every day, at roughly 11 km cells.
        IMERG combines a constellation of microwave and infrared sensors — it does not
        measure rain directly but infers it from cloud properties, calibrated against
        ground radar where available.""",
        why="""Rainfall is what actually sets landslides off. Two quantities matter
        and they are different:
        <ul>
        <li><b>Intensity</b> — how hard it is raining right now. Sudden bursts trigger
        shallow, fast debris flows.</li>
        <li><b>Antecedent rainfall</b> — how much has already fallen over the previous
        3, 7, 15 days. This is often the better predictor, because it is what
        saturates the soil. A moderate rainstorm on already-soaked ground is far more
        dangerous than a heavy one on dry ground.</li>
        </ul>
        Why satellite rather than rain gauges? Arunachal has very few gauges, and
        published research finds satellite rainfall outperforms sparse gauge networks
        for landslide work in India. The trade-off is that above about 2,500 m
        satellite estimates drift, which is why ground records from IMD are a Level 2
        ask.
        <br><br><b>This is the one collection job still on the critical path.</b> What
        is on disk proves the pipeline works — the 2024 monsoon end to end, plus recent
        days — but a forecast needs thresholds fitted against history, and that means
        the full archive back to 2000. Roughly 9,500 more days. Nobody has to grant
        permission for it; it is download time.""",
        facts=[("Resolution", "~11 km"), ("Latency", "2 days"),
               ("Days on disk", "132"), ("Days needed", "~9,500")],
        charts=["rain_series"],
    ),
    dict(
        id="soilmoisture", section="triggers", title="Soil moisture",
        source="SMAP L3 Enhanced (NASA)", tier="Tier B · free account",
        figure="soil_moisture.png",
        what="""How wet the top few centimetres of soil already are, measured from
        orbit at 9 km cells. Units are m³/m³ — cubic metres of water per cubic metre
        of soil. 0.1 is dry, 0.4 is quite wet, 0.6+ is saturated.""",
        why="""This is a proxy for <b>pore water pressure</b> — the thing that
        actually causes most rain-triggered failures. Water filling the gaps between
        soil grains pushes them apart, reducing the friction holding the slope
        together. Enough of it and the slope simply lets go.
        <br><br>Satellites only see the surface layer, while failures usually initiate
        a metre or more down, so this is an indirect signal. The proper instrument is
        a buried <b>piezometer</b>, which is a paid, per-slope option.
        <br><br><b>Better than expected:</b> the source docs called this the weakest
        free substitute. Over Arunachal it returns valid data for 93.9% of cells,
        against 11.9% globally — the low global figure comes from ocean, ice and
        dense forest elsewhere.""",
        facts=[("Resolution", "9 km"), ("Valid over AOI", "93.9%"),
               ("Valid globally", "11.9%"), ("Range", "0.03–0.70 m³/m³")],
        charts=[],
    ),
    dict(
        id="gfs", section="triggers", title="Rain forecast — looking ahead",
        source="NOAA GFS 0.25° (NOMADS)", tier="Tier A · free, no account",
        figure="gfs_forecast.png",
        what="""A global weather model, run four times a day, forecasting rainfall out
        to 16 days at 25 km cells. We pull it already cropped to the state by the
        server, so each file is 2–3 KB rather than a global grid.""",
        why="""Everything else here is <i>observation</i> — it tells you what has
        already happened. This is the only layer that looks forward, and forward is
        where warnings live. Observed rainfall tells you a slope is <i>currently</i>
        dangerous; a forecast tells you it <i>will be</i> dangerous on Thursday, which
        is the difference between a report and an evacuation.
        <br><br>We verified all lead times out to <b>168 hours</b>, so the 7-day
        warning horizon in the plan is real and not an assumption. Accuracy degrades
        with distance, as the chart shows — treat day 7 as a heads-up and day 1 as
        actionable.""",
        facts=[("Resolution", "25 km"), ("Horizon verified", "168 h"),
               ("Updates", "4× daily"), ("File size", "2–3 KB")],
        charts=["gfs_leads"],
    ),
    dict(
        id="enso", section="triggers", title="ENSO — the seasonal backdrop",
        source="NOAA CPC (Oceanic Niño Index)", tier="Tier A · free, no account",
        figure=None,
        what="""A single number per season describing whether the tropical Pacific is
        in an <b>El Niño</b> (warm, positive) or <b>La Niña</b> (cool, negative) state.
        The record runs back to 1950 — 917 seasons.""",
        why="""ENSO shifts monsoon behaviour across South Asia. Broadly, El Niño years
        tend toward a weaker Indian monsoon and La Niña years toward a stronger one,
        though the Northeast does not always follow the all-India pattern.
        <br><br>This is <b>not</b> a predictor of individual landslides — it will never
        tell you a slope fails on Tuesday. It is seasonal context: a way of saying
        "this looks like a heavy monsoon year, staff and prepare accordingly" months in
        advance. Useful for planning, useless for warnings.""",
        facts=[("Seasons on record", "917"), ("Since", "1950"),
               ("Latest", "AMJ 2026"), ("Latest ONI", "+0.98")],
        charts=["enso_series"],
    ),
    dict(
        id="era5", section="triggers", title="Soil water at depth and snowmelt",
        source="ERA5-Land (Copernicus CDS)", tier="Tier B · free account",
        figure="era5_soilwater.png",
        what="""A <b>reanalysis</b> — not a satellite and not a gauge, but a physics
        model of the atmosphere and land surface run backwards over history, with every
        available observation fed into it. The result is a complete, gap-free record of
        variables nobody actually measured everywhere.""",
        why="""This fills the gaps the satellites leave.
        <ul>
        <li><b>Soil water at depth.</b> SMAP only sees the top few centimetres. ERA5-Land
        models several layers down, closer to where failures actually initiate.</li>
        <li><b>Snowmelt.</b> Above roughly 3,000 m, a warm spell can release far more
        water than rainfall. Rain-only triggering misses this entirely — and a
        substantial part of Arunachal sits at that altitude.</li>
        <li><b>Temperature.</b> Drives melt, freeze-thaw cycling and evaporation.</li>
        </ul>
        The trade-off is resolution and honesty about what it is: 9 km cells, and
        modelled rather than observed. Use it for the variables satellites cannot give
        you, not as a replacement for IMERG rainfall.""",
        facts=[("Resolution", "~9 km"), ("Variables", "5"),
               ("Time steps", "240 (3-hourly)"), ("Missing data", "0.0%")],
        charts=["era5_temp"],
    ),
    dict(
        id="seismic", section="triggers", title="Earthquakes",
        source="USGS + IRIS", tier="Tier A · free, no account",
        figure="earthquakes.png",
        what="""Every recorded earthquake in and around the state since 1900 — 2,367
        events of magnitude 4.0+ within about 2° of the border, updated in real time.""",
        why="""Shaking is the second major landslide trigger after rain, and it works
        differently: it can fail a dry slope instantly, with no warning from rainfall
        at all. Arunachal sits on the Himalayan collision front, one of the most
        seismically active regions on Earth. The largest event in this record is
        <b>magnitude 8.6</b> — the 1950 Assam–Tibet earthquake, one of the largest
        continental earthquakes ever measured.
        <br><br>We deliberately pulled a buffered region rather than just the state,
        because shaking that fails a slope inside Arunachal often originates
        outside it.""",
        facts=[("Events (M4+)", "2,367"), ("M6.0+", "82"),
               ("Largest", "M8.6 (1950)"), ("Stations nearby", "159")],
        charts=["quake_mag"],
    ),

    # ------------------------------------------------------------------ eyes
    dict(
        id="sentinel1", section="eyes", title="Sentinel-1 — radar",
        source="Copernicus Dataspace", tier="Tier B · free account",
        figure=None,
        what="""A radar satellite. Instead of photographing reflected sunlight, it
        emits its own microwave pulses and measures what bounces back. That has one
        enormous consequence: <b>it works through cloud, and at night.</b>""",
        why="""Radar does two separate jobs here.
        <ul>
        <li><b>Flood mapping.</b> Smooth water reflects radar away from the sensor, so
        flooded ground appears almost black. Mapping flood extent becomes
        straightforward — and it works during the storm, which optical cannot.</li>
        <li><b>InSAR — ground movement.</b> By comparing the phase of radar waves
        between two passes over the same spot, you can measure ground shifting by
        <b>millimetres</b>. Many large landslides creep slowly for weeks or months
        before failing. InSAR can catch that creep from orbit.</li>
        </ul>
        InSAR requires images from the same <b>relative orbit</b> — the satellite
        repeating the identical path — otherwise the geometry doesn't match. We
        confirmed five usable orbit stacks over the state.""",
        facts=[("Scenes / 12 months", "2,962"), ("Revisit", "median 1 day"),
               ("Largest gap", "3 days"), ("InSAR stacks", "5 orbits")],
        charts=["s1_orbits"],
    ),
    dict(
        id="sentinel2", section="eyes", title="Sentinel-2 — optical, and its limit",
        source="Copernicus Dataspace", tier="Tier B · degraded by cloud",
        figure=None,
        what="""A conventional optical satellite — essentially a very good camera at
        10 m resolution. Excellent for spotting fresh landslide scars (bare earth
        against green forest) and for tracking glacial lakes that can burst.""",
        why="""And here is the problem, quantified. We sampled 1,196 scenes across a
        full year. During monsoon — <i>exactly</i> when landslides and floods happen —
        the median scene is <b>86% cloud</b>, and only <b>1%</b> of scenes are clear
        enough to use. In the dry season the same satellite gives 69% usable scenes.
        <br><br>This is physics, not a fixable engineering problem, and it drives two
        design decisions:
        <ul>
        <li>Flood extent must come from <b>radar</b>, not optical.</li>
        <li>Scar mapping is a <b>dry-season, retrospective</b> activity — you map what
        happened during monsoon in the following November–March window, to build
        training labels. It is not live detection.</li>
        </ul>""",
        facts=[("Scenes sampled", "1,196"), ("Monsoon usable", "1%"),
               ("Dry season usable", "69%"), ("Resolution", "10 m")],
        charts=["s2_cloud"],
    ),

    # --------------------------------------------------------------- history
    dict(
        id="inventory", section="history",
        title="Mapped landslides — the official inventories",
        source="GSI Bhusanket + NRSC Bhuvan", tier="Tier A · free, no account",
        figure="landslide_inventory.png",
        what="""Landslides that government agencies have actually mapped, as
        <b>polygons</b> — the true outline of each failure, not a dot. Two independent
        national programmes cover the state: the Geological Survey of India's national
        inventory, and ISRO/NRSC's season-by-season mapping on Bhuvan.""",
        why="""This replaces what was the project's single worst constraint. The
        position was 28 usable labels for the whole state; it is now roughly
        <b>36,000 mapped landslides</b> covering every district.
        <br><br>Be careful how that number is quoted. Two corrections were applied to
        get to a defensible figure. GSI delivers by map tile, not by state, so 246 of
        its polygons actually sit in Nagaland or Assam — those are dropped. And the two
        sources mapped the state independently, so the remaining sum of 37,542
        double-counts: 16% of Bhuvan's polygons land on a slide GSI had already mapped.
        The union is <b>35,744</b>, and the 1,798 shared slides are useful in their own
        right, because two agencies independently agreeing on a failure is the closest
        thing to validation this data offers.
        <br><br>The two sources do different jobs and are both worth holding:
        <ul>
        <li><b>GSI (26,213 polygons in Arunachal)</b> is the larger and more thorough mapping, with
        material type, movement class, geomorphology and land cover per slide. But it
        carries <b>no dates</b> — it is a spatial inventory, not an event catalogue.</li>
        <li><b>Bhuvan (11,329 polygons)</b> is smaller but <b>season-tagged</b> across
        2014, 2017 and 2023, and records length, width, height, area and whether each
        slide is active or reactivated. The dates are what allow a slide to be linked
        to the rainfall that triggered it.</li>
        </ul>
        Neither is a substitute for the other: GSI gives coverage, Bhuvan gives time.
        <br><br><b>Caveats.</b> Bhuvan publishes these through WMS only — bulk vector
        download is switched off — so they were harvested by walking a grid of map
        queries. A naive single query silently returns a biased subset that omits whole
        districts. Neither source states redistribution terms.
        <br><br>Flip this card to <b>raw data</b> to see the actual columns and rows —
        including the out-of-state records, which is how they were caught.""",
        facts=[("Unique mapped", "35,744"), ("Out-of-state dropped", "246"),
               ("Cross-confirmed", "1,798"), ("Was", "28 usable labels")],
        charts=["inventory_source", "inventory_district"],
    ),
    dict(
        id="susceptibility", section="history",
        title="The government's own susceptibility map",
        source="GSI National Landslide Susceptibility (50 m)",
        tier="Tier A · free, via portal proxy",
        figure="susceptibility.jpg",
        what="""GSI's national landslide susceptibility map, at 50 metre resolution,
        classifying every slope as Low, Moderate or High susceptibility.""",
        why="""This is <b>not training data — it is the benchmark</b>. It is the number
        the client's own government already publishes, so any susceptibility surface
        this project produces will be compared against it whether we invite that or
        not. Better to hold it from the start and know exactly where we agree and
        where we differ, because the disagreements are what a reviewer will ask about.
        <br><br>Using it as an input instead would be circular: we would be predicting
        GSI's model rather than predicting landslides.
        <br><br>It is served from an ArcGIS image server that requires a token, so it
        is reached through the portal's own public proxy — the same route its web map
        uses. Undocumented, and availability is not guaranteed.""",
        facts=[("Resolution", "50 m"), ("Classes", "3"),
               ("Role", "Benchmark, not input"), ("Access", "Portal proxy")],
        charts=["susceptibility_class"],
    ),
    dict(
        id="floodextent", section="history", title="Where water has actually gone",
        source="NRSC Bhuvan aggregated flood layer", tier="Tier A · free, no account",
        figure="flood_extent.png",
        what="""Satellite-observed flood inundation for Arunachal Pradesh, aggregated
        across every mapped flood event from <b>2003 to 2020</b>. Blue is anywhere
        water has been observed at least once in those eighteen years.""",
        why="""The flood half of this project had forecasts but no history. GloFAS
        tells us what discharge is predicted; nothing told us where water has actually
        spread. This does, and it is the flood equivalent of the landslide inventory —
        the ground truth a flood model is tested against.
        <br><br>It also sets realistic expectations. Only about <b>1.3%</b> of the
        search box has ever been observed flooded, because Arunachal is overwhelmingly
        steep terrain where water passes through rather than pools. Flood risk here
        concentrates in a small number of valley floors and the southern plains edge —
        which is a useful finding in itself for scoping where flood work is worth doing.
        <br><br><b>Caveat:</b> it is served as rendered map tiles, not data values, so
        what we hold is a binary mask. Per-year extents and depths are not available
        through this endpoint.""",
        facts=[("Period", "2003–2020"), ("Box ever flooded", "1.3%"),
               ("Type", "Observed, not modelled"), ("Limit", "Mask only, no depths")],
        charts=[],
    ),
    dict(
        id="labels", section="history",
        title="NASA catalogue — superseded, kept for dates",
        source="NASA Global Landslide Catalog", tier="Tier A · degraded",
        figure="landslide_labels.png",
        what="""A catalogue of landslides that actually happened, with date, location
        and a description. 99 events fall in our search box; 72 are inside the state.""",
        why="""These are <b>labels</b> — the ground truth a model learns from and, more
        importantly, is tested against. Without them you can produce a map that looks
        plausible and have no way to know whether it is right.
        <br><br>Three problems, and they compound:
        <ul>
        <li><b>Precision.</b> Each record carries a location accuracy. Only 12 are
        "exact" and 16 are within 1 km. The rest are 5–50 km — which on a map is an
        area containing hundreds of separate slopes. You cannot learn <i>which slope</i>
        failed from a 25 km circle.</li>
        <li><b>Age.</b> The catalogue stops in <b>2018</b>. Eight years of events are
        simply absent.</li>
        <li><b>Provenance.</b> Every official NASA endpoint for this dataset is
        currently dead. We retrieved it from a community re-host, so treat currency as
        unverified.</li>
        </ul>
        <b>28 usable labels for 81,995 km².</b>
        <br><br><b>Superseded.</b> The official inventories above now provide roughly
        36,000 mapped landslides, so this is no longer the label set. It is kept for one
        reason only: it carries <b>event dates and triggers</b> at daily precision.
        GSI's inventory has no dates at all and Bhuvan's resolve only to a season, so
        these 72 records remain the sharpest link between an individual slide and the
        weather that caused it — a small but genuinely irreplaceable role.""",
        facts=[("Inside state", "72"), ("Precise enough to train", "28"),
               ("Date range", "2008–2018"), ("Now used for", "Event timing only")],
        charts=["label_acc", "label_month"],
    ),

    # ---------------------------------------------------------------- people
    dict(
        id="population", section="people", title="Population",
        source="WorldPop 100 m (2020)", tier="Tier A · free, no account",
        figure="population.jpg",
        what="""Modelled population count per 100 m cell. Not a census — it takes
        census totals and redistributes them using satellite-detected buildings and
        roads, so it estimates <i>where</i> within a district people actually live.""",
        why="""Risk is not the same as hazard. A landslide on an empty mountainside is
        a hazard; the same landslide above a village is a disaster. This layer converts
        "a slope will fail" into "these people are in the way", which is what a warning
        system actually needs to say.""",
        facts=[("Resolution", "100 m"), ("Total in state", "1,757,407"),
               ("Reference year", "2020"), ("Census 2011", "1.38 M")],
        charts=[],
    ),
    dict(
        id="osm", section="people", title="Roads, buildings and facilities",
        source="OpenStreetMap", tier="Tier A · degraded coverage",
        figure=None,
        what="""Community-mapped infrastructure — roads, building footprints,
        hospitals, schools — clipped to the state boundary.""",
        why="""Roads matter twice over. They are what gets cut when a slope fails,
        isolating villages; and road <b>cutting</b> itself destabilises slopes, because
        excavating the toe of a hill removes what was holding it up. Roughly a third of
        Himalayan landslides cluster within a few hundred metres of a road.
        <br><br><b>But be careful with these numbers.</b> Arunachal is thinly mapped:
        17,719 buildings for 1.76 million people works out to about 99 people per
        mapped building, so real coverage is a few percent at best. 48 health
        facilities statewide is clearly incomplete.
        <br><br>There is also a trap worth remembering: fetched on a bounding box, OSM
        returned 107,302 roads and 585,320 buildings — but 86% and 97% of those were in
        neighbouring Assam, which is far better mapped. Always clip to the actual
        boundary before quoting a number.""",
        facts=[("Roads", "14,943 (16,015 km)"), ("Buildings", "17,719"),
               ("Health facilities", "48"), ("Schools", "81")],
        charts=["osm_bar"],
    ),

    # ------------------------------------------------------------------ gaps
    dict(
        id="gap_floodhub", section="gaps", title="Google Flood Hub — waitlisted",
        source="Google", tier="Blocked · application required",
        figure=None,
        what="""Google's machine-learning river forecasting service, covering 150+
        countries. The original plan treated it as the backbone of flood prediction.""",
        why="""Its API is behind a waitlist we have not been granted, so it could not be
        verified at all.
        <br><br>This turned out not to matter, which is the useful finding. GloFAS —
        verified and working — covers the same job with a 30-day horizon and no access
        gate. Flood Hub moves from <i>dependency</i> to <i>cross-check</i>. That is a
        materially better position for a government contract, because relying on a
        single vendor with a closed waitlist is a fair thing for a client to
        challenge.""",
        facts=[("Status", "Waitlisted"), ("Verified", "No"),
               ("Mitigation", "GloFAS"), ("Impact", "None — replaced")],
        charts=[],
    ),
    dict(
        id="gap_wdpa", section="gaps", title="Protected areas — effectively empty",
        source="Protected Planet / WDPA", tier="Blocked · source limitation",
        figure=None,
        what="""The World Database on Protected Areas. Intended to provide national
        parks and wildlife sanctuaries as a constraint layer.""",
        why="""The download works and returns 63 areas for India — but they are
        <b>only international designations</b>: Ramsar wetlands, World Heritage Sites,
        UNESCO biosphere reserves. India does not publish its national parks and
        wildlife sanctuaries to WDPA.
        <br><br>Result: <b>zero protected areas inside Arunachal</b>. Namdapha, Pakke,
        Mouling and Mehao are all absent despite being major reserves. This looked like
        a bug for a while; it is not. A protected-area layer has to come from the State
        Forest Department instead.""",
        facts=[("India total", "63"), ("Inside Arunachal", "0"),
               ("Cause", "National PAs not published"),
               ("Alternative", "State Forest Dept")],
        charts=[],
    ),
    dict(
        id="gap_gfd", section="gaps", title="Global Flood Database — gone",
        source="Cloud to Street / Dartmouth", tier="Blocked · service retired",
        figure=None,
        what="""A historical archive of satellite-mapped flood extents, intended as a
        source of past flood footprints for training and validation.""",
        why="""The website is now a JavaScript shell with no API, and the Dartmouth
        Flood Observatory archive it derives from returns <b>HTTP 410 Gone</b> —
        permanently removed. The underlying data survives only inside Google Earth
        Engine, which needs its own account.
        <br><br>Practical consequence: it should be reclassified from "free, no
        account" to "account required", and historical flood marks from the Central
        Water Commission become more important than they looked.""",
        facts=[("Web API", "None"), ("DFO archive", "HTTP 410"),
               ("Survives in", "Earth Engine"), ("Reclassify", "Tier A → Tier B")],
        charts=[],
    ),
    dict(
        id="tier_landslide", section="tiers",
        title="Landslide forecast — what each tier delivers",
        source="FREE · ASK · PAID", tier="Roadmap",
        figure=None,
        what="""The daily landslide forecast is the product. What changes between
        tiers is mostly <b>spatial resolution and lead time</b> — not the headline
        accuracy.""",
        why="""<table class="tiertab">
        <tr><th></th><th>FREE — held now</th><th>ASK — free, must be released</th>
        <th>PAID</th></tr>
        <tr><td><b>Trigger data</b></td><td>IMERG 10 km, GFS 25 km</td>
        <td>+ IMD gauges &amp; nowcast, hydropower met stations</td>
        <td>+ 1–3 km custom forecast, own telemetered network</td></tr>
        <tr><td><b>Spatial unit</b></td><td>~10 km → <b>district / circle</b></td>
        <td>~2–5 km → <b>village cluster</b></td>
        <td>1 km; instrumented sites → <b>individual slope</b></td></tr>
        <tr><td><b>Lead time</b></td><td>1–3 days</td>
        <td>1–3 days + <b>0–6 h nowcast</b></td>
        <td>+ <b>hours-ahead on sensored slopes</b></td></tr>
        <tr><td><b>POD / FAR</b></td><td>55–70% / 40–60%</td>
        <td>65–78% / 30–45%</td><td>75–85% / 25–35%</td></tr>
        </table>
        <br><b>POD</b> = of landslides that happened, the share you warned for.
        <b>FAR</b> = of warnings issued, the share that were wrong. They trade against
        each other — where the threshold sits is a <i>client policy decision</i>, not
        a technical one.
        <br><br><b>The honest pattern:</b> accuracy barely improves across tiers,
        because pore pressure inside a slope is unobservable at any budget. What money
        buys is <i>actionability</i> — from "this district, elevated risk, tomorrow" to
        "this slope, moving now, evacuate within hours".
        <br><br>The best paid item is not sensors but <b>statewide InSAR processing</b>:
        Sentinel-1 data is free, you pay only for processing, and it yields a live
        watchlist of slopes actually deforming. Ground sensors then go on the worst of
        those. Note they only help slopes that <i>creep before failing</i> — GSI field
        validation found ~59% of Arunachal failures are debris flows, which give no
        precursor warning.""",
        facts=[("Free unit", "District"), ("Paid unit", "Single slope"),
               ("Gain", "Resolution, not accuracy"), ("Best paid buy", "InSAR")],
        charts=[],
    ),
    dict(
        id="tier_flood", section="tiers",
        title="Flood forecast — what each tier delivers",
        source="FREE · ASK · PAID", tier="Roadmap",
        figure=None,
        what="""Flood splits cleanly by river size, and that split decides everything.
        GloFAS reaches only the largest rivers; Google Flood Hub, which the plan
        originally assumed, is waitlisted and unavailable.""",
        why="""<table class="tiertab">
        <tr><th></th><th>FREE — held now</th><th>ASK</th><th>PAID</th></tr>
        <tr><td><b>Large rivers</b><br>(Siang / Brahmaputra)</td>
        <td>GloFAS, <b>3–7 day lead</b>, ~75–85%</td>
        <td>+ CWC data → 5–10 day, better calibrated</td>
        <td>+ hydrodynamic model → depth &amp; extent</td></tr>
        <tr><td><b>Small mountain rivers</b><br>(~97% of the network)</td>
        <td>⚠️ <b>Watch only, not a forecast</b></td>
        <td><b>Real 6–24 h forecast</b> on gauged basins, POD 70–80%</td>
        <td>Telemetered sensors → forecast anywhere you instrument</td></tr>
        <tr><td><b>Inundation</b></td><td>Historical mask 2003–2020 only</td>
        <td>Same</td><td><b>LiDAR + 2D model → village-level depth maps</b></td></tr>
        <tr><td><b>Dam-release flooding</b></td><td>❌ Not possible</td>
        <td><b>Release schedules → forecastable</b></td>
        <td>Real-time telemetry</td></tr>
        </table>
        <br><b>Flood is the weaker leg — and the better upgrade story.</b> Landslide
        false-alarm rates stay stubbornly high at every tier because the physics is
        genuinely uncertain. Flood forecasting on a gauged basin is comparatively
        well-solved engineering: give it gauge data and it works. Flood improves more
        per rupee than landslide does.
        <br><br>Two asks are disproportionately valuable here: <b>river gauge records</b>
        (the unlock for the 97%) and <b>dam release schedules</b> — in dam-heavy
        Arunachal, controlled releases cause downstream flooding, and a model without
        them will produce confident, wrong forecasts and be blamed for them.""",
        facts=[("Large rivers", "3–7 day forecast"), ("Small rivers", "Watch only"),
               ("Reach coverage", "3% of network"), ("Unlock", "Gauge data")],
        charts=[],
    ),
    dict(
        id="tier_asks", section="tiers", title="The asks, ranked",
        source="Requests to make now", tier="Free, but must be released",
        figure=None,
        what="""Everything below is free of charge but held by a department. Two items
        previously top of this list — the landslide inventory and the fault maps —
        have been removed, because they turned out to be downloadable without asking.""",
        why="""<ol>
        <li><b>IMD ground rainfall records.</b> Corrects the satellite bias that caps
        <i>all</i> landslide timing accuracy. Biggest single gain in the roadmap, for
        zero money.</li>
        <li><b>GSI <code>Landslidedata_1</code> event table.</b> Hour-precision dates
        plus <i>measured</i> rainfall amount, duration and intensity per landslide.
        Request it by table and field name — the schema is public and confirmed live,
        only the rows are withheld. That is a much harder request to deflect than a
        general enquiry.</li>
        <li><b>River gauge records</b> (client dept / CWC). The single unlock for
        flood, which is otherwise stuck at 3% of the stream network.</li>
        <li><b>Dam and hydropower release schedules.</b> Without them a flood model
        will be confidently wrong about human-caused floods.</li>
        <li><b>State PWD road-blockage logs.</b> Every landslide that closed a road,
        with a date — the cheapest route to dated events, and almost certainly already
        exists as maintenance records.</li>
        </ol>
        <b>Ask, but do not wait.</b> Sentinel change detection over the ~36,000 known
        landslide polygons generates dated events for free at 1–2 week precision —
        enough to attribute each failure to a specific monsoon storm in the rainfall
        record. Build that in parallel; if the requests land, the thresholds sharpen.
        If they do not, the system still ships.""",
        facts=[("Top ask", "IMD rainfall"), ("Cost", "₹0, all of it"),
               ("Removed as asks", "Inventory, faults"), ("Blocking?", "None")],
        charts=[],
    ),
    dict(
        id="gap_geology", section="gaps",
        title="Detailed geology — resolved, and worth reading twice",
        source="APSSDI open WFS / GSI Bhusanket", tier="Resolved · was blocked",
        figure=None,
        what="""This entry used to read: detailed geology and the landslide inventory
        cannot be downloaded and must be formally requested from GSI, with long lead
        times. Both have since been obtained, free and without any request.""",
        why="""Worth keeping visible because the mistake is instructive rather than
        embarrassing. Both datasets <i>were</i> genuinely available the whole time; the
        blockers were incidental, and all three were things a quick look would miss:
        <ul>
        <li>The state geoportal's <b>catalogue</b> requires a login, which made the
        whole site look closed. Its <b>map server</b> underneath was open all along.</li>
        <li>The same server serves a <b>broken TLS certificate chain</b>. Browsers and
        <code>curl</code> paper over it; most code does not, so it fails in a way that
        reads as "server down" rather than "missing intermediate certificate".</li>
        <li>GSI's inventory sits behind a search UI that is <b>broken in production</b>
        — every query returns "No data" because of a missing server-side component.
        The data was never gone, only unsearchable.</li>
        </ul>
        The general lesson for the remaining gaps: when an Indian government portal
        appears to have nothing, test the machine endpoints directly before believing
        the interface. What is left genuinely blocked below has been checked this way.""",
        facts=[("Was", "Formal request, months"), ("Actually", "Open, no account"),
               ("Lithological units", "24"), ("Landslides obtained", "35,744")],
        charts=[],
    ),
]
