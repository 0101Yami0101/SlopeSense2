"""Pre-flight check: can the ECMWF token actually retrieve data for the AOI?

Submits one deliberately tiny request to each store. This is the only reliable
way to confirm licence status — the catalogue metadata reports nothing missing
even when a request would be refused.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cdsapi

from common import AOI_BBOX, WEATHER, ecmwf_key

W, S, E, N = AOI_BBOX
AREA = [N, W, S, E]          # ECMWF wants north, west, south, east
OUT = WEATHER / "_access_test"


def attempt(store: str, dataset: str, request: dict, filename: str) -> bool:
    url, key = ecmwf_key(store)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / filename
    print(f"\n--- {store.upper()} / {dataset}")
    try:
        c = cdsapi.Client(url=url, key=key, quiet=True, wait_until_complete=True)
        c.retrieve(dataset, request, str(target))
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        print(f"  FAILED: {type(exc).__name__}")
        print(f"  {msg[:400]}")
        low = msg.lower()
        if "licence" in low or "license" in low or "not been accepted" in low:
            print("  -> A licence still needs accepting in the browser.")
        elif "403" in msg or "permission" in low:
            print("  -> Permission denied: likely an unaccepted licence.")
        return False
    size = target.stat().st_size if target.exists() else 0
    print(f"  OK: {target.name} ({size / 1e3:.0f} KB)")
    return True


def main() -> None:
    print("Copernicus access test — AOI:", AOI_BBOX)
    results = {}

    results["ERA5-Land (CDS)"] = attempt(
        "cds", "reanalysis-era5-land",
        {
            "variable": ["total_precipitation"],
            "year": "2024", "month": "06", "day": "01",
            "time": ["00:00"],
            "data_format": "netcdf",
            "download_format": "unarchived",
            "area": AREA,
        },
        "test_era5land_precip.nc",
    )

    results["GloFAS forecast (EWDS)"] = attempt(
        "ewds", "cems-glofas-forecast",
        {
            "system_version": ["operational"],
            "hydrological_model": ["lisflood"],
            "product_type": ["control_forecast"],
            "variable": "river_discharge_in_the_last_24_hours",
            "year": "2026", "month": "07", "day": ["20"],
            "leadtime_hour": ["24"],
            "data_format": "grib2",
            "download_format": "unarchived",
            "area": AREA,
        },
        "test_glofas_discharge.grib",
    )

    print("\n=== summary ===")
    for k, v in results.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")


if __name__ == "__main__":
    main()
