"""IMERG for the central+eastern Himalayan arc — training data for a pooled trigger.

Arunachal has 72 day-dated landslides; the arc has 617 in this box. Same IMERG
product, same feature pipeline, so a trigger trained here can be tested on
Arunachal's own held-out events.

    box    lon 76-98 E, lat 26-32 N     13,200 cells (6.8x the Arunachal box)
    span   2000-06-01 .. 2020-12-31     ~7,500 days, ~2 GB

⚠️ THE WESTERN HIMALAYA IS DELIBERATELY EXCLUDED (lon < 76). Pakistan and Kashmir
get winter western disturbances — a different rainfall regime from the
monsoon-dominated centre and east. Including them would add ~190 events but make
the pool climatically heterogeneous, which is the opposite of what pooling needs.
Trimming is a scientific choice, not just a size one.

Same restartable design as fetch_11b: anything already on disk is skipped, so
this can be interrupted and resumed freely.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime as dt
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from common import EarthdataSession, WEATHER

BASE = "https://gpm1.gesdisc.eosdis.nasa.gov/opendap/GPM_L3/GPM_3IMERGDL.07"
OUT = WEATHER / "gpm_imerg_himalaya"

W, S, E, N = 76.0, 26.0, 98.0, 32.0
LON0, LON1 = int((W + 180) / 0.1), int((E + 180) / 0.1)
LAT0, LAT1 = int((S + 90) / 0.1), int((N + 90) / 0.1)

START = dt.date(2000, 6, 1)
END = dt.date(2020, 12, 31)
VERSIONS = ("V07B", "V07C")
WORKERS = 6

_vcache: dict[int, str] = {}
_lock = threading.Lock()


def url_for(day: dt.date, v: str) -> str:
    ce = (f"precipitation[0:1:0][{LON0}:1:{LON1}][{LAT0}:1:{LAT1}],"
          f"lon[{LON0}:1:{LON1}],lat[{LAT0}:1:{LAT1}],time[0:1:0]")
    return (f"{BASE}/{day:%Y/%m}/3B-DAY-L.MS.MRG.3IMERG.{day:%Y%m%d}"
            f"-S000000-E235959.{v}.nc4.nc4?{ce}")


def dest_for(day: dt.date) -> Path:
    return OUT / f"gpm-imerg_precip_0p1_himalaya_{day:%Y%m%d}.nc4"


def _is_nc(b: bytes) -> bool:
    return b.startswith(b"\x89HDF") or b"CDF" in b[:8]


def grab(session, day):
    dest = dest_for(day)
    if dest.exists() and dest.stat().st_size > 1000:
        return day, True, "cached"
    with _lock:
        vs = [_vcache[day.year]] if day.year in _vcache else list(VERSIONS)
    last = "no attempt"
    for v in vs + [x for x in VERSIONS if x not in vs]:
        for attempt in range(3):
            try:
                r = session.get(url_for(day, v), timeout=240)
            except Exception as exc:                        # noqa: BLE001
                last = type(exc).__name__
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 503:
                last = "HTTP 503"
                time.sleep(2 ** attempt + 1)
                continue
            if r.status_code == 404:
                last = "HTTP 404"
                break
            if not r.ok:
                last = f"HTTP {r.status_code}"
                break
            if not _is_nc(r.content):
                return day, False, "not netCDF (auth?)"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            with _lock:
                _vcache[day.year] = v
            return day, True, "ok"
    return day, False, last


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    days = []
    d = START
    while d <= END:
        if not (dest_for(d).exists() and dest_for(d).stat().st_size > 1000):
            days.append(d)
        d += dt.timedelta(days=1)
    total = (END - START).days + 1
    print(f"IMERG Himalaya  lon {W}-{E}  lat {S}-{N}")
    print(f"  {total:,} days in range, {len(days):,} still to fetch")
    if not days:
        print("  complete."); return

    s = EarthdataSession()
    ok, bad = 0, []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(grab, s, x): x for x in days}
        for i, fut in enumerate(as_completed(futs), 1):
            day, good, why = fut.result()
            if good:
                ok += 1
            else:
                bad.append((day, why))
            if i % 250 == 0 or i == len(days):
                el = time.time() - t0
                mb = sum(p.stat().st_size for p in OUT.glob("*.nc4")) / 1e6
                print(f"    {i:,}/{len(days):,}  {ok:,} ok  {len(bad)} failed  "
                      f"{mb:,.0f} MB  {el/60:.0f} min", flush=True)

    print(f"\n  retrieved {ok:,}/{len(days):,}")
    if bad:
        print(f"  failed {len(bad)} — rerun to retry")


if __name__ == "__main__":
    main()
