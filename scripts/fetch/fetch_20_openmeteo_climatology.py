"""Open-Meteo daily-rainfall climatology on the query grid the live app uses.

Output: data/interim/rainfall_om/{precip_mm.npy, dates.npy, points.json}

════════════════════════════════════════════════════════════════════════════
WHY NOT JUST USE OUR 26 YEARS OF IMERG
════════════════════════════════════════════════════════════════════════════
The live app forecasts from Open-Meteo, and the trigger scores a day by its
PERCENTILE against local climatology. Climatology and live value must come from
the SAME source or the percentile is meaningless. Measured over 1,068 matched
cell-days:

    mean mm/day   Open-Meteo 12.56   IMERG 7.45      (1.68x wetter)
    p90                      33.80         18.36
    daily correlation                       0.320

A day at IMERG's 50th percentile is nowhere near Open-Meteo's 50th.

Measured fix: Open-Meteo's ARCHIVE and its FORECAST API's past data are the same
source chain — mean ratio 1.00, correlation 1.000. So archive climatology +
forecast-API live values are consistent by construction.

IMERG is NOT abandoned. It remains the basis of the hindcast and everything
already validated (P7/P8, the 0.768 trigger). It is simply not on the live path.

════════════════════════════════════════════════════════════════════════════
WHY A ~0.3 DEG GRID AND NOT THE 892 IMERG CELLS
════════════════════════════════════════════════════════════════════════════
Open-Meteo weights requests by locations x days. Measured:

    25 locs x 1,461 d  -> 200 OK, 2.3 s
    50 locs x 1,461 d  -> 200 OK, 9.9 s
   100 locs            -> 429 (minutely)
   ~40 locs x 6 yr, repeated -> 429 (HOURLY limit)

892 cells x 7,900 days is ~7 M location-days — it does not fit, and it never
would have. But the binding constraint is the LIVE app, not this fetch: 892
points would need ~23 calls per refresh, a two-minute wait for the first
visitor. A ~0.3 deg grid needs 3.

⚠️ The cost is real and must be stated in the app: rainfall input is sampled at
~33 km, against the 11 km IMERG used for the hindcast. The live forecast is
therefore expected to be somewhat weaker than the 0.768 hindcast figure.

Restartable — each batch is cached to disk, so a rate-limit stall costs nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))

import datetime as dt
import json
import time
import warnings

import numpy as np
import pandas as pd
import rasterio
import requests

from common import INTERIM

warnings.filterwarnings("ignore")

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
SRC = INTERIM / "rainfall"
OUT = INTERIM / "rainfall_om"
CACHE = OUT / "_batches"

GRID_DEG = 0.3             # query-grid spacing -> ~120 in-state points
START_YEAR = 2010
BATCH = 25                 # locations per call (50 works; 25 is the safe size)
YEAR_CHUNK = 4             # years per call
PAUSE = 12.0               # between calls — the hourly limit is the real one


def query_points() -> pd.DataFrame:
    """A ~GRID_DEG lattice clipped to cells that actually cover the state."""
    meta = json.loads((SRC / "_stack_meta.json").read_text())
    with rasterio.open(SRC / "imerg_index.tif") as s:
        idx = s.read(1)
    used = set(np.unique(idx[idx >= 0]).tolist())
    nlat = int(round((meta["lat_max"] - meta["lat_min"]) / meta["cell_deg"])) + 1
    nlon = int(round((meta["lon_max"] - meta["lon_min"]) / meta["cell_deg"])) + 1
    lat = np.linspace(meta["lat_max"], meta["lat_min"], nlat)
    lon = np.linspace(meta["lon_min"], meta["lon_max"], nlon)

    step = max(1, int(round(GRID_DEG / meta["cell_deg"])))
    pts = []
    for r in range(0, nlat, step):
        for c in range(0, nlon, step):
            if r * nlon + c in used:
                pts.append({"lat": round(float(lat[r]), 4),
                            "lon": round(float(lon[c]), 4)})
    return pd.DataFrame(pts)


def fetch(la, lo, d0, d1, tag) -> pd.DataFrame | None:
    f = CACHE / f"{tag}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    for attempt in range(10):
        try:
            r = requests.get(ARCHIVE, params={
                "latitude": ",".join(map(str, la)),
                "longitude": ",".join(map(str, lo)),
                "start_date": d0, "end_date": d1,
                "daily": "precipitation_sum", "timezone": "UTC"}, timeout=300)
            if r.status_code == 429:
                # Hourly limits need minutes, not seconds. Back off hard.
                wait = 90 if "Hourly" in r.text else 35
                print(f"      429 — waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            js = r.json()
            if isinstance(js, dict) and js.get("error"):
                time.sleep(60)
                continue
            res = js if isinstance(js, list) else [js]
            if "daily" not in res[0]:
                time.sleep(30)
                continue
            days = pd.to_datetime(res[0]["daily"]["time"])
            arr = np.array([[0.0 if v is None else float(v)
                             for v in x["daily"]["precipitation_sum"]]
                            for x in res], dtype=np.float32)
            df = pd.DataFrame(arr.T, index=days)
            df.to_parquet(f)
            return df
        except Exception:                                       # noqa: BLE001
            time.sleep(15 * (attempt + 1))
    return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(exist_ok=True)
    pts = query_points()
    end = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    years = list(range(START_YEAR, int(end[:4]) + 1))
    chunks = [(f"{years[i]}-01-01",
               f"{min(years[i]+YEAR_CHUNK-1, years[-1])}-12-31")
              for i in range(0, len(years), YEAR_CHUNK)]
    chunks[-1] = (chunks[-1][0], end)
    batches = [pts.iloc[i:i + BATCH] for i in range(0, len(pts), BATCH)]

    print(f"Open-Meteo climatology — {len(pts)} query points "
          f"(~{GRID_DEG}° grid), {START_YEAR} .. {end}")
    print(f"  {len(batches)} batches x {len(chunks)} chunks = "
          f"{len(batches)*len(chunks)} calls")

    t0 = time.time()
    blocks = []
    for bi, sub in enumerate(batches):
        ps = []
        for ci, (d0, d1) in enumerate(chunks):
            d = fetch(sub.lat.tolist(), sub.lon.tolist(), d0, d1, f"b{bi:02d}_c{ci}")
            if d is None:
                print(f"  batch {bi} chunk {ci} FAILED — rerun to resume")
                return
            ps.append(d)
            time.sleep(PAUSE)
        b = pd.concat(ps).sort_index()
        b.columns = [f"{bi}_{k}" for k in range(b.shape[1])]
        blocks.append(b)
        print(f"    batch {bi+1}/{len(batches)}  {(time.time()-t0)/60:.0f} min",
              flush=True)

    full = pd.concat(blocks, axis=1)
    full = full.loc[~full.index.duplicated()].sort_index()
    np.save(OUT / "precip_mm.npy", full.to_numpy(dtype=np.float32))
    np.save(OUT / "dates.npy", full.index.values.astype("datetime64[D]"))
    (OUT / "points.json").write_text(json.dumps({
        "lat": pts.lat.tolist(), "lon": pts.lon.tolist(),
        "grid_deg": GRID_DEG, "n_points": int(len(pts)),
        "source": "Open-Meteo archive (ERA5) — same chain as the forecast API",
        "start": str(full.index[0].date()), "end": str(full.index[-1].date()),
        "caveat": "~33 km sampling vs 11 km IMERG in the hindcast",
    }, indent=2))
    v = full.to_numpy()
    print(f"\n  wrote {v.shape[0]:,} days x {v.shape[1]} points "
          f"({v.nbytes/1e6:.1f} MB)   mean {np.nanmean(v):.2f} mm/day")
    print(f"  done in {(time.time()-t0)/60:.0f} min")


if __name__ == "__main__":
    main()
