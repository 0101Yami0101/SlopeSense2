"""Tier A — Rain forecast (NOAA GFS) and seasonal context (NOAA CPC).

GFS is pulled through the NOMADS GRIB filter, which subsets server-side to the
AOI so each file is small. Lead times are chosen to test the full forecast
horizon, not just the first step — the 168 h request is the real check on
whether a 7-day warning is possible from free data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime as dt

import requests

from common import AOI_BBOX, AOI_NAME, UA, WEATHER, http_get, record

NOMADS = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
CPC_ONI = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
OUT_GFS = WEATHER / "noaa_gfs_0p25"

LEAD_HOURS = [6, 24, 72, 120, 168]   # 168 h = the 7-day claim
W, S, E, N = AOI_BBOX


def try_cycle(day: str, cycle: str, fh: int) -> bytes | None:
    params = {
        "dir": f"/gfs.{day}/{cycle}/atmos",
        "file": f"gfs.t{cycle}z.pgrb2.0p25.f{fh:03d}",
        "var_APCP": "on", "var_PRATE": "on",
        "lev_surface": "on",
        "subregion": "",
        "toplat": N, "bottomlat": S, "leftlon": W, "rightlon": E,
    }
    try:
        r = requests.get(NOMADS, params=params, timeout=180, headers=UA)
        if r.ok and r.content[:4] == b"GRIB":
            return r.content
    except Exception:  # noqa: BLE001
        pass
    return None


def latest_cycle() -> tuple[str, str] | None:
    """Walk back from now until a cycle actually serves data."""
    now = dt.datetime.now(dt.timezone.utc)
    for back in range(0, 36, 6):
        t = now - dt.timedelta(hours=back)
        day, cycle = t.strftime("%Y%m%d"), f"{(t.hour // 6) * 6:02d}"
        if try_cycle(day, cycle, 6) is not None:
            return day, cycle
    return None


def main() -> None:
    written = []

    print("NOAA GFS 0.25 deg — rain forecast")
    found = latest_cycle()
    if not found:
        print("  [fail] no GFS cycle served data — check NOMADS availability")
    else:
        day, cycle = found
        print(f"  latest usable cycle: {day} {cycle}Z")
        OUT_GFS.mkdir(parents=True, exist_ok=True)
        for fh in LEAD_HOURS:
            blob = try_cycle(day, cycle, fh)
            if not blob:
                print(f"  [warn] f{fh:03d} unavailable")
                continue
            p = OUT_GFS / f"noaa-gfs_precip_0p25_{AOI_NAME}_{day}{cycle}z_f{fh:03d}.grib2"
            p.write_bytes(blob)
            written.append(p)
            print(f"  [ok]   {p.name} ({len(blob) / 1e3:.0f} KB)")

    print("NOAA CPC — ENSO (ONI) seasonal context")
    try:
        r = http_get(CPC_ONI, timeout=120)
        p = WEATHER / "noaa-cpc_oni_enso_global.txt"
        p.write_text(r.text)
        written.append(p)
        lines = [l for l in r.text.strip().splitlines() if l.strip()]
        print(f"  [ok]   {p.name} ({len(lines) - 1} seasons, latest: {lines[-1].split()})")
    except Exception as exc:  # noqa: BLE001
        print(f"  [fail] CPC ONI: {str(exc)[:140]}")

    record(
        WEATHER, source="NOAA GFS 0.25 (NOMADS) + NOAA CPC ONI",
        url=f"{NOMADS} ; {CPC_ONI}", files=written,
        license_="Public domain (US Government)",
        notes="GFS subset server-side to the AOI. Lead times "
              + ", ".join(f"{h}h" for h in LEAD_HOURS)
              + ". GRIB2 files are overwritten each run — this is a live feed, "
                "not an archive; historical GFS needs a separate archive source.",
    )


if __name__ == "__main__":
    main()
