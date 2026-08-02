"""Tier B — full GPM IMERG daily archive backfill (2000-06-01 → now).

fetch_11_imerg.py grabs one monsoon season to prove access works. This grabs the
whole record, which is what the trigger model is actually fitted on.

Two things make this cheap. First, the OPeNDAP constraint expression subsets to
the AOI server-side, so a day is ~34 kB instead of ~4 MB — the entire 26-year
archive is ~320 MB. Second, the cost is therefore latency, not bandwidth: ~2.4 s
per request, almost all of it NASA slicing the global grid. Never "optimise" this
by pulling un-subsetted global files; that turns 320 MB into ~40 GB.

The version probe matters more than it looks. fetch_11 tries V07C then V07B per
file, but every date before ~2025 is V07B — so each historical day burns a wasted
404 round-trip, roughly doubling a full backfill. Here the version is probed once
per year and cached.

Restartable: any existing file over 1 kB is skipped, so an interrupted run resumes
for free.

    python scripts/fetch/fetch_11b_imerg_archive.py               # full archive
    python scripts/fetch/fetch_11b_imerg_archive.py 2015 2020     # a year range
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime as dt
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from common import AOI_BBOX, AOI_NAME, WEATHER, EarthdataSession, record

BASE = "https://gpm1.gesdisc.eosdis.nasa.gov/opendap/GPM_L3/GPM_3IMERGDL.07"
OUT = WEATHER / "gpm_imerg_daily"

# IMERG grid: 0.1 deg, lon -180..180 (3600), lat -90..90 (1800)
W, S, E, N = AOI_BBOX
LON0, LON1 = int((W + 180) / 0.1), int((E + 180) / 0.1)
LAT0, LAT1 = int((S + 90) / 0.1), int((N + 90) / 0.1)

CE = (f"precipitation[0:1:0][{LON0}:1:{LON1}][{LAT0}:1:{LAT1}],"
      f"lon[{LON0}:1:{LON1}],lat[{LAT0}:1:{LAT1}],time[0:1:0]")

# The IMERG V07 record opens in June 2000 (TRMM era merged in). Nothing earlier
# exists to fetch.
ARCHIVE_START = dt.date(2000, 6, 1)
# The late run lands ~3.5 days behind real time; asking for yesterday just 404s.
LATENCY_DAYS = 4

VERSIONS = ("V07B", "V07C")   # historical first — the opposite of fetch_11
WORKERS = 6                   # GES DISC throttles; past ~8 you buy retries

_version_cache: dict[int, str] = {}
_lock = threading.Lock()


def url_for(day: dt.date, version: str) -> str:
    return (f"{BASE}/{day:%Y/%m}/3B-DAY-L.MS.MRG.3IMERG.{day:%Y%m%d}"
            f"-S000000-E235959.{version}.nc4.nc4?{CE}")


def dest_for(day: dt.date) -> Path:
    return OUT / f"gpm-imerg_precip_0p1_{AOI_NAME}_{day:%Y%m%d}.nc4"


def _looks_like_netcdf(body: bytes) -> bool:
    return body.startswith(b"\x89HDF") or b"CDF" in body[:8]


def probe_version(session: requests.Session, day: dt.date) -> str | None:
    """Find which version string this day's year uses, once per year."""
    year = day.year
    with _lock:
        if year in _version_cache:
            return _version_cache[year]
    for v in VERSIONS:
        try:
            r = session.get(url_for(day, v), timeout=180)
        except Exception:                                     # noqa: BLE001
            continue
        if r.ok and _looks_like_netcdf(r.content):
            with _lock:
                _version_cache[year] = v
            return v
    return None


def grab(session: requests.Session, day: dt.date) -> tuple[dt.date, bool, str]:
    dest = dest_for(day)
    if dest.exists() and dest.stat().st_size > 1000:
        return day, True, "cached"

    version = probe_version(session, day)
    if version is None:
        return day, False, "no version resolved"

    for attempt in range(4):
        try:
            r = session.get(url_for(day, version), timeout=180)
        except Exception as exc:                              # noqa: BLE001
            time.sleep(2 ** attempt)
            last = type(exc).__name__
            continue
        if r.status_code == 503:          # throttled — back off and retry
            time.sleep(2 ** attempt + 1)
            last = "HTTP 503"
            continue
        if r.status_code == 404:
            # Year probe picked the wrong version for this particular day, or
            # the day is genuinely absent from the archive.
            other = [v for v in VERSIONS if v != version]
            for v in other:
                rr = session.get(url_for(day, v), timeout=180)
                if rr.ok and _looks_like_netcdf(rr.content):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(rr.content)
                    return day, True, f"ok ({v})"
            return day, False, "HTTP 404"
        if not r.ok:
            return day, False, f"HTTP {r.status_code}"
        if not _looks_like_netcdf(r.content):
            return day, False, "not netCDF (auth issue)"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return day, True, "ok"
    return day, False, last


def main() -> None:
    start, end = ARCHIVE_START, dt.date.today() - dt.timedelta(days=LATENCY_DAYS)
    if len(sys.argv) == 3:
        start = max(start, dt.date(int(sys.argv[1]), 1, 1))
        end = min(end, dt.date(int(sys.argv[2]), 12, 31))

    days, d = [], start
    while d <= end:
        days.append(d)
        d += dt.timedelta(days=1)

    have = [x for x in days if dest_for(x).exists() and dest_for(x).stat().st_size > 1000]
    todo = [x for x in days if x not in set(have)]

    print("GPM IMERG daily — full archive backfill")
    print(f"  range      : {start} .. {end}  ({len(days)} days)")
    print(f"  already on disk: {len(have)}")
    print(f"  to fetch   : {len(todo)}")
    print(f"  AOI subset : lon idx {LON0}-{LON1}, lat idx {LAT0}-{LAT1}  (~34 kB/day)")
    print(f"  estimate   : ~{len(todo) * 2.4 / WORKERS / 3600:.1f} h at {WORKERS} workers")
    if not todo:
        print("  nothing to do")
        return

    session = EarthdataSession()
    t0 = time.time()
    ok, failed = 0, []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(grab, session, day): day for day in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            day, good, status = fut.result()
            if good:
                ok += 1
            else:
                failed.append((day, status))
            if i % 200 == 0 or i == len(todo):
                el = time.time() - t0
                rate = i / el if el else 0
                eta = (len(todo) - i) / rate / 60 if rate else 0
                print(f"    {i}/{len(todo)}  ok={ok} fail={len(failed)}  "
                      f"{rate:.1f}/s  ETA {eta:.0f} min", flush=True)

    print(f"\n  done in {(time.time()-t0)/60:.1f} min — {ok} fetched, {len(failed)} failed")
    print(f"  versions resolved per year: "
          f"{sorted((y, v) for y, v in _version_cache.items())[:5]} ...")
    if failed:
        print(f"  first failures:")
        for day, why in sorted(failed)[:10]:
            print(f"    {day}  {why}")
        print("  re-run to retry only these — existing files are skipped")

    files = sorted(OUT.glob(f"gpm-imerg_precip_0p1_{AOI_NAME}_*.nc4"))
    total = sum(f.stat().st_size for f in files)
    print(f"\n  archive on disk: {len(files)} days, {total/1e6:.0f} MB")
    record(OUT.parent, "gpm-imerg-archive", f"{BASE} (OPeNDAP AOI subset)",
           files[:1], license_="NASA open data",
           notes=f"Daily IMERG late run, {start}..{end}, subset to Arunachal bbox "
                 f"server-side. {len(files)} files on disk.")


if __name__ == "__main__":
    main()
