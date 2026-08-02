"""Tier B — ERA5-Land reanalysis (Copernicus CDS).

Secondary to IMERG for rainfall, but it carries variables satellites cannot
observe directly — soil water at four depths, snowmelt, evaporation — which
matter for antecedent wetness and for high-altitude melt-driven triggering.

Hourly at ~9 km, requested for one monsoon season over the AOI.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cdsapi
import numpy as np
import xarray as xr

from common import AOI_BBOX, AOI_NAME, WEATHER, ecmwf_key, record

W, S, E, N = AOI_BBOX
AREA = [N, W, S, E]
OUT = WEATHER / "era5_land"

VARIABLES = [
    "total_precipitation",
    "volumetric_soil_water_layer_1",
    "volumetric_soil_water_layer_2",
    "snowmelt",
    "2m_temperature",
]
YEAR = "2024"
MONTHS = ["06", "07", "08", "09"]


def main() -> None:
    print("ERA5-Land — reanalysis (soil water, snowmelt, precip)")
    url, key = ecmwf_key("cds")
    OUT.mkdir(parents=True, exist_ok=True)
    written = []

    for month in MONTHS:
        dest = OUT / f"era5land_hourly_9km_{AOI_NAME}_{YEAR}{month}.nc"
        if dest.exists() and dest.stat().st_size > 10000:
            print(f"  [skip] {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
            written.append(dest)
            continue
        print(f"  requesting {YEAR}-{month} ...")
        try:
            cdsapi.Client(url=url, key=key, quiet=True,
                          wait_until_complete=True).retrieve(
                "reanalysis-era5-land",
                {
                    "variable": VARIABLES,
                    "year": YEAR, "month": [month],
                    "day": [f"{d:02d}" for d in range(1, 32)],
                    "time": [f"{h:02d}:00" for h in range(0, 24, 3)],
                    "data_format": "netcdf",
                    "download_format": "unarchived",
                    "area": AREA,
                }, str(dest))
        except Exception as exc:  # noqa: BLE001
            print(f"  [fail] {YEAR}-{month}: {str(exc)[:200]}")
            continue
        print(f"  [ok]   {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        written.append(dest)

    if not written:
        return

    print("\n  --- verification ---")
    ds = xr.open_dataset(written[0])
    print(f"  variables : {list(ds.data_vars)}")
    print(f"  dims      : {dict(ds.sizes)}")
    lat = ds["latitude"] if "latitude" in ds else ds["lat"]
    lon = ds["longitude"] if "longitude" in ds else ds["lon"]
    print(f"  grid      : {lat.size} x {lon.size} at ~0.1 deg (~9 km)")
    print(f"  lat range : {float(lat.min()):.2f} to {float(lat.max()):.2f}")
    for v in list(ds.data_vars)[:5]:
        a = ds[v].values
        pct = 100 * np.mean(~np.isfinite(a))
        print(f"  {v:32} units={ds[v].attrs.get('units','?'):8} "
              f"missing={pct:5.1f}%  max={np.nanmax(a):.4g}")

    record(
        WEATHER, source="ERA5-Land hourly (Copernicus CDS)",
        url="https://cds.climate.copernicus.eu", files=written,
        license_="Licence to use Copernicus Products",
        notes=f"3-hourly, ~9 km, {YEAR}-{MONTHS[0]}..{MONTHS[-1]}. Carries soil water "
              f"at depth and snowmelt — variables IMERG and SMAP cannot provide. "
              f"Precipitation is in metres per hour, not mm.",
    )


if __name__ == "__main__":
    main()
