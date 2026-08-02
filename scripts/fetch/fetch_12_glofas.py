"""Tier B — GloFAS river discharge (Copernicus EWDS).

Two products, two purposes:
  * forecast   — operational, what a live warning would use
  * historical — reanalysis discharge, what you calibrate and validate against

GloFAS is the independent alternative to Google Flood Hub, which is still
waitlisted. Verifying it properly removes the single-vendor dependency from
the Level 1 flood story.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime as dt

import cdsapi
import numpy as np
import xarray as xr

from common import AOI_BBOX, AOI_NAME, HYDROLOGY, ecmwf_key, record

W, S, E, N = AOI_BBOX
AREA = [N, W, S, E]
OUT = HYDROLOGY / "glofas"

# Forecast horizons: 1 day out to 30 days, the full advertised range
LEADTIMES = ["24", "72", "120", "168", "240", "360", "720"]


def client():
    url, key = ecmwf_key("ewds")
    return cdsapi.Client(url=url, key=key, quiet=True, wait_until_complete=True)


def fetch(dataset: str, request: dict, dest: Path) -> Path | None:
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"  [skip] {dest.name}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        client().retrieve(dataset, request, str(dest))
    except Exception as exc:  # noqa: BLE001
        print(f"  [fail] {dest.name}: {str(exc)[:220]}")
        return None
    print(f"  [ok]   {dest.name} ({dest.stat().st_size / 1e3:.0f} KB)")
    return dest


def main() -> None:
    print("GloFAS — river discharge forecast and reanalysis")
    written = []

    # ---------------------------------------------------------- forecast
    day = dt.date.today() - dt.timedelta(days=2)
    print(f"  forecast, run {day}, lead times {'/'.join(LEADTIMES)}h:")
    f = fetch("cems-glofas-forecast", {
        "system_version": ["operational"],
        "hydrological_model": ["lisflood"],
        "product_type": ["control_forecast"],
        "variable": "river_discharge_in_the_last_24_hours",
        "year": f"{day:%Y}", "month": f"{day:%m}", "day": [f"{day:%d}"],
        "leadtime_hour": LEADTIMES,
        "data_format": "grib2", "download_format": "unarchived",
        "area": AREA,
    }, OUT / f"glofas_forecast_0p05_{AOI_NAME}_{day:%Y%m%d}.grib")
    if f:
        written.append(f)

    # -------------------------------------------------------- historical
    print("  historical reanalysis, monsoon 2024:")
    h = fetch("cems-glofas-historical", {
        "system_version": ["version_4_0"],
        "hydrological_model": ["lisflood"],
        "product_type": ["consolidated"],
        "variable": ["river_discharge_in_the_last_24_hours"],
        "hyear": ["2024"],
        "hmonth": ["06", "07", "08", "09"],
        "hday": [f"{d:02d}" for d in range(1, 32)],
        "data_format": "grib2", "download_format": "unarchived",
        "area": AREA,
    }, OUT / f"glofas_historical_0p05_{AOI_NAME}_2024-monsoon.grib")
    if h:
        written.append(h)

    # ------------------------------------------------------- verification
    for p in written:
        print(f"\n  --- {p.name} ---")
        try:
            ds = xr.open_dataset(p, engine="cfgrib")
        except Exception as exc:  # noqa: BLE001
            print(f"  unreadable: {type(exc).__name__}")
            continue
        var = list(ds.data_vars)[0]
        a = ds[var].values
        print(f"  variable   : {var} [{ds[var].attrs.get('GRIB_units', 'm3 s-1')}]")
        print(f"  dims       : {dict(ds.sizes)}")
        print(f"  grid       : 0.05 deg (~5.5 km)")
        print(f"  valid      : {int(np.isfinite(a).sum()):,}/{a.size:,} "
              f"({100 * np.isfinite(a).mean():.1f}%)")
        print(f"  discharge  : {np.nanmin(a):.1f} to {np.nanmax(a):,.0f} m3/s")
        if "step" in ds.sizes:
            print(f"  lead times : {ds.step.size} steps")
        if "time" in ds.sizes and ds.time.size > 1:
            print(f"  time span  : {str(ds.time.values[0])[:10]} to "
                  f"{str(ds.time.values[-1])[:10]}")

    record(
        HYDROLOGY, source="GloFAS v4 (Copernicus EWDS)",
        url="https://ewds.climate.copernicus.eu", files=written,
        license_="Copernicus / CEMS-FLOODS licence",
        notes="0.05 deg (~5.5 km) river discharge. Forecast = operational control "
              "run out to 30 days; historical = consolidated reanalysis for "
              "calibration. Independent of Google Flood Hub.",
    )


if __name__ == "__main__":
    main()
