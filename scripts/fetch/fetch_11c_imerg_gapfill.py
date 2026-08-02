"""Fill whatever days are missing from the IMERG archive, whatever the reason.

The backfill (fetch_11b) probes V07B first because that is right for 2000-2025.
Recent data is published as V07C, and fetch_11b's per-year version cache locks
onto the first version that answers — so as the crawl reached 2026 it kept
asking for V07B and got 404s. Result: 73 gaps, all after 2026-03-03.

This script does not guess. It reads what is actually on disk, computes the
difference against the calendar, and tries BOTH versions per day with no
caching. That is slower per file, but a gap list is small and correctness
matters more than throughput here.

    python scripts/fetch/fetch_11c_imerg_gapfill.py            # whole archive
    python scripts/fetch/fetch_11c_imerg_gapfill.py 2026       # one year

Safe to re-run: anything already on disk is skipped. Days that stay missing
after this are genuine holes in the NASA archive, not our bug — 2000-2025 has
four such days out of 9,373 and no amount of retrying will produce them.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import AOI_NAME, EarthdataSession

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_11_imerg import OUT, urls_for            # noqa: E402

ARCHIVE_START = dt.date(2000, 6, 1)
LATENCY_DAYS = 4          # IMERG late run publishes ~3-4 days behind
WORKERS = 6


def dest_for(day: dt.date) -> Path:
    return OUT / f"gpm-imerg_precip_0p1_{AOI_NAME}_{day:%Y%m%d}.nc4"


def missing_days(year: int | None) -> list[dt.date]:
    end = dt.date.today() - dt.timedelta(days=LATENCY_DAYS)
    start = ARCHIVE_START
    if year:
        start = max(start, dt.date(year, 1, 1))
        end = min(end, dt.date(year, 12, 31))
    out, d = [], start
    while d <= end:
        p = dest_for(d)
        if not (p.exists() and p.stat().st_size > 1000):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def grab(session, day: dt.date) -> tuple[dt.date, bool, str]:
    """Try every known version for this day. No caching, no assumptions."""
    dest = dest_for(day)
    if dest.exists() and dest.stat().st_size > 1000:
        return day, True, "cached"
    last = "no attempt"
    for url in urls_for(day):                    # V07C then V07B
        for attempt in range(3):
            try:
                r = session.get(url, timeout=180)
            except Exception as exc:             # noqa: BLE001
                last = type(exc).__name__
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 503:             # GES DISC throttling
                last = "HTTP 503"
                time.sleep(2 ** attempt + 1)
                continue
            if r.status_code == 404:             # wrong version — try the next
                last = "HTTP 404"
                break
            if not r.ok:
                last = f"HTTP {r.status_code}"
                break
            if not r.content.startswith(b"\x89HDF") and b"CDF" not in r.content[:8]:
                return day, False, "not netCDF (auth issue)"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            return day, True, "ok"
    return day, False, last


def main() -> None:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else None
    days = missing_days(year)
    print("IMERG gap fill" + (f" — {year}" if year else ""))
    if not days:
        print("  nothing missing.")
        return

    from collections import Counter
    print(f"  {len(days)} missing days: "
          + ", ".join(f"{y}×{n}" for y, n in
                      sorted(Counter(d.year for d in days).items())))

    s = EarthdataSession()
    ok, bad = 0, []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(grab, s, d): d for d in days}
        for i, fut in enumerate(as_completed(futs), 1):
            day, good, why = fut.result()
            if good:
                ok += 1
            else:
                bad.append((day, why))
            if i % 20 == 0 or i == len(days):
                print(f"    {i}/{len(days)} — {ok} ok, {len(bad)} failed",
                      flush=True)

    print(f"\n  retrieved {ok}/{len(days)}")
    if bad:
        print(f"  still missing ({len(bad)}):")
        for day, why in sorted(bad)[:15]:
            print(f"    {day}  {why}")
        if len(bad) > 15:
            print(f"    ... and {len(bad)-15} more")


if __name__ == "__main__":
    main()
