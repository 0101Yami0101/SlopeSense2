"""Tier A — Earthquakes (USGS) and seismic station inventory (IRIS/EarthScope).

Two catalogues are pulled:
  * AOI      — events inside Arunachal Pradesh
  * regional — events within ~2 degrees, since shaking that triggers a slope
               failure often originates outside the state boundary

The IRIS station query is a coverage check: how much real seismic
instrumentation exists near the AOI.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

from common import AOI_BBOX, AOI_NAME, SEISMIC, http_get, record

USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"
IRIS_STATION = "https://service.iris.edu/fdsnws/station/1/query"

START = "1900-01-01"
BUFFER_DEG = 2.0


def fetch_quakes(bbox, minmag, label) -> Path:
    w, s, e, n = bbox
    params = {
        "format": "geojson", "starttime": START,
        "minlatitude": s, "maxlatitude": n,
        "minlongitude": w, "maxlongitude": e,
        "minmagnitude": minmag, "orderby": "time",
    }
    r = http_get(USGS, params=params, timeout=180)
    data = r.json()
    out = SEISMIC / f"usgs_earthquakes_point_{label}_{START[:4]}-2026.geojson"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data))

    feats = data.get("features", [])
    print(f"  [ok]   {out.name} ({len(feats)} events, {out.stat().st_size / 1e6:.1f} MB)")
    if feats:
        mags = [f["properties"]["mag"] for f in feats if f["properties"].get("mag")]
        times = sorted(f["properties"]["time"] for f in feats)
        import datetime as dt
        # epoch arithmetic, not utcfromtimestamp: pre-1970 events give a
        # negative timestamp, which raises OSError on Windows
        epoch = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
        first = (epoch + dt.timedelta(milliseconds=times[0])).date()
        last = (epoch + dt.timedelta(milliseconds=times[-1])).date()
        print(f"         magnitude {min(mags):.1f} to {max(mags):.1f}, {first} to {last}")
        big = [f for f in feats if (f["properties"].get("mag") or 0) >= 6]
        print(f"         M6.0+: {len(big)} events")
    return out


def fetch_stations() -> Path | None:
    w, s, e, n = AOI_BBOX
    params = {
        "format": "text", "level": "station",
        "minlatitude": s - BUFFER_DEG, "maxlatitude": n + BUFFER_DEG,
        "minlongitude": w - BUFFER_DEG, "maxlongitude": e + BUFFER_DEG,
        "nodata": "404",
    }
    try:
        r = http_get(IRIS_STATION, params=params, timeout=120, retries=2)
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] IRIS station query returned nothing: {exc}")
        return None
    out = SEISMIC / f"iris_stations_text_{AOI_NAME}-buffered.txt"
    out.write_text(r.text)
    rows = [ln for ln in r.text.splitlines() if ln and not ln.startswith("#")]
    print(f"  [ok]   {out.name} ({len(rows)} stations within {BUFFER_DEG} deg)")
    return out


def main() -> None:
    print("USGS earthquakes + IRIS stations")
    written = []

    print("  AOI catalogue (M2.5+):")
    written.append(fetch_quakes(AOI_BBOX, 2.5, AOI_NAME))

    w, s, e, n = AOI_BBOX
    regional = (w - BUFFER_DEG, s - BUFFER_DEG, e + BUFFER_DEG, n + BUFFER_DEG)
    print(f"  Regional catalogue (M4.0+, +{BUFFER_DEG} deg):")
    written.append(fetch_quakes(regional, 4.0, f"{AOI_NAME}-regional"))

    print("  IRIS station inventory:")
    st = fetch_stations()
    if st:
        written.append(st)

    record(
        SEISMIC, source="USGS FDSN event + IRIS FDSN station",
        url=f"{USGS} ; {IRIS_STATION}", files=written,
        license_="Public domain (USGS); open (IRIS/EarthScope)",
        notes="Real-time capable APIs, no key. Regional catalogue buffered "
              f"{BUFFER_DEG} deg because triggering shaking often originates outside the AOI.",
    )


if __name__ == "__main__":
    main()
