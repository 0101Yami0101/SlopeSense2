"""Tier B — GPM IMERG rainfall (NASA GES DISC). The core landslide trigger.

Global daily IMERG is ~4 MB per file; a decade would be ~16 GB before we
looked at a single pixel. This uses the OPeNDAP constraint expression to
subset server-side to the AOI, which turns each day into a few KB.

Fetches a full monsoon season at daily resolution plus the most recent days,
which together verify both the archive depth and the near-real-time latency.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import requests
import xarray as xr

from common import AOI_BBOX, AOI_NAME, WEATHER, EarthdataSession, record

BASE = "https://gpm1.gesdisc.eosdis.nasa.gov/opendap/GPM_L3/GPM_3IMERGDL.07"
OUT = WEATHER / "gpm_imerg_daily"

# IMERG grid: 0.1 deg, lon -180..180 (3600), lat -90..90 (1800)
W, S, E, N = AOI_BBOX
LON0, LON1 = int((W + 180) / 0.1), int((E + 180) / 0.1)
LAT0, LAT1 = int((S + 90) / 0.1), int((N + 90) / 0.1)

SEASON_START = dt.date(2024, 6, 1)
SEASON_END = dt.date(2024, 9, 30)
RECENT_DAYS = 10


# IMERG re-versions over time: the 2024 archive is V07B, 2026 files are V07C.
# Hardcoding one silently 404s a whole date range, so try both.
VERSIONS = ("V07C", "V07B")


def urls_for(day: dt.date) -> list[str]:
    stamp = day.strftime("%Y%m%d")
    ce = (f"precipitation[0:1:0][{LON0}:1:{LON1}][{LAT0}:1:{LAT1}],"
          f"lon[{LON0}:1:{LON1}],lat[{LAT0}:1:{LAT1}],time[0:1:0]")
    return [f"{BASE}/{day:%Y/%m}/3B-DAY-L.MS.MRG.3IMERG.{stamp}"
            f"-S000000-E235959.{v}.nc4.nc4?{ce}" for v in VERSIONS]


def grab(session: requests.Session, day: dt.date) -> tuple[dt.date, Path | None, str]:
    dest = OUT / f"gpm-imerg_precip_0p1_{AOI_NAME}_{day:%Y%m%d}.nc4"
    if dest.exists() and dest.stat().st_size > 1000:
        return day, dest, "cached"
    last = "no attempt"
    for url in urls_for(day):
        for attempt in range(3):
            try:
                r = session.get(url, timeout=180)
            except Exception as exc:  # noqa: BLE001
                last = type(exc).__name__
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 503:      # GES DISC throttling — back off
                last = "HTTP 503"
                time.sleep(2 ** attempt + 1)
                continue
            if r.status_code == 404:      # wrong version for this date
                last = "HTTP 404"
                break
            if not r.ok:
                return day, None, f"HTTP {r.status_code}"
            if not r.content.startswith(b"\x89HDF") and b"CDF" not in r.content[:8]:
                return day, None, "not netCDF (auth issue)"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            return day, dest, "ok"
    return day, None, last


def main() -> None:
    print("GPM IMERG daily (late run) — rainfall trigger")
    print(f"  AOI subset: lon idx {LON0}-{LON1}, lat idx {LAT0}-{LAT1}")

    days = []
    d = SEASON_START
    while d <= SEASON_END:
        days.append(d)
        d += dt.timedelta(days=1)
    today = dt.date.today()
    days += [today - dt.timedelta(days=i) for i in range(2, 2 + RECENT_DAYS)]
    print(f"  requesting {len(days)} days "
          f"({SEASON_START} to {SEASON_END}, plus last {RECENT_DAYS})")

    s = EarthdataSession()

    got, failed = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {pool.submit(grab, s, day): day for day in days}
        for i, fut in enumerate(as_completed(futs), 1):
            day, path, status = fut.result()
            if path:
                got.append(path)
            else:
                failed.append((day, status))
            if i % 25 == 0:
                print(f"    {i}/{len(days)} — {len(got)} ok, {len(failed)} failed")

    print(f"  retrieved {len(got)}/{len(days)} days")
    if failed:
        print(f"  failures ({len(failed)}):")
        for day, why in sorted(failed)[:8]:
            print(f"    {day}  {why}")

    if not got:
        return

    # --- verify: read one file and summarise the season ---------------------
    print("\n  --- verification ---")
    ds = xr.open_dataset(sorted(got)[0])
    var = "precipitation"
    print(f"  variable   : {var} [{ds[var].attrs.get('units', '?')}]")
    print(f"  grid       : {ds[var].shape} (time, lon, lat)")
    print(f"  resolution : ~0.1 deg (~11 km)")
    print(f"  lat range  : {float(ds.lat.min()):.2f} to {float(ds.lat.max()):.2f}")
    print(f"  lon range  : {float(ds.lon.min()):.2f} to {float(ds.lon.max()):.2f}")

    season = [p for p in got if SEASON_START.strftime("%Y%m") <= p.stem[-8:-2]]
    vals = []
    for p in sorted(got):
        try:
            a = xr.open_dataset(p)[var].values
            vals.append(float(np.nanmax(a)))
        except Exception:  # noqa: BLE001
            pass
    if vals:
        print(f"  daily max across sample: {min(vals):.1f} to {max(vals):.1f} mm/day")
        print(f"  missing pixels in first file: "
              f"{100 * np.mean(~np.isfinite(xr.open_dataset(sorted(got)[0])[var].values)):.2f}%")

    newest = max(p.stem[-8:] for p in got)
    print(f"  newest day retrieved: {newest} "
          f"(today is {today:%Y%m%d}) — latency check")

    record(
        WEATHER, source="GPM IMERG Late Daily V07B (GES DISC)",
        url=BASE, files=got[:5],
        license_="NASA open data",
        notes=(f"{len(got)} daily files, OPeNDAP-subset to the AOI (~11 km, 0.1 deg). "
               f"Season {SEASON_START}..{SEASON_END} plus recent days for latency. "
               f"Units mm/day. Late run has ~1 day latency; Final run (3IMERGDF) "
               f"is research-grade with ~3 month lag."),
    )


if __name__ == "__main__":
    main()
