"""Tier B — SMAP soil moisture (NSIDC DAAC). The antecedent-wetness term.

SMAP granules are global HDF5, so this pulls a small sample rather than a long
series: enough to confirm access, resolution, and — the thing that actually
matters — how much usable signal survives over steep Himalayan terrain.

Granules are located through NASA's CMR search API, which avoids hardcoding
directory layouts that change between product versions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime as dt

import numpy as np

from common import AOI_BBOX, AOI_NAME, EarthdataSession, SOIL_GEOLOGY, http_get, record

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
OUT = SOIL_GEOLOGY / "smap_soil_moisture"

# L3 enhanced 9 km daily — smaller than L4 and adequate for a wetness proxy
CANDIDATES = [("SPL3SMP_E", "006"), ("SPL3SMP_E", "005"), ("SPL4SMGP", "008")]
SAMPLE_DAYS = 3


def search(short_name: str, version: str, start: dt.date, end: dt.date) -> list[dict]:
    w, s, e, n = AOI_BBOX
    params = {
        "short_name": short_name, "version": version,
        "bounding_box": f"{w},{s},{e},{n}",
        "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z",
        "page_size": 20, "sort_key": "-start_date",
    }
    try:
        return http_get(CMR, params=params, timeout=120).json()["feed"]["entry"]
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] CMR search failed for {short_name} v{version}: {str(exc)[:100]}")
        return []


def main() -> None:
    print("SMAP soil moisture — antecedent wetness")
    end = dt.date.today() - dt.timedelta(days=3)
    start = end - dt.timedelta(days=20)

    entries, product = [], None
    for short_name, version in CANDIDATES:
        entries = search(short_name, version, start, end)
        print(f"  {short_name} v{version}: {len(entries)} granules "
              f"in {start}..{end}")
        if entries:
            product = f"{short_name}.{version}"
            break
    if not entries:
        print("  [fail] no SMAP granules found for the AOI")
        return

    session = EarthdataSession()
    written = []
    for entry in entries[:SAMPLE_DAYS]:
        link = next((l["href"] for l in entry.get("links", [])
                     if l.get("href", "").endswith(".h5")), None)
        if not link:
            continue
        dest = OUT / Path(link).name
        if dest.exists() and dest.stat().st_size > 10000:
            print(f"  [skip] {dest.name}")
            written.append(dest)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = session.get(link, timeout=900, stream=True)
            if not r.ok:
                print(f"  [fail] {dest.name}: HTTP {r.status_code}")
                continue
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
            print(f"  [ok]   {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
            written.append(dest)
        except Exception as exc:  # noqa: BLE001
            print(f"  [fail] {dest.name}: {type(exc).__name__}")

    if not written:
        print("  [fail] nothing downloaded")
        return

    # ------------------------------------------------------- verification
    print("\n  --- verification ---")
    try:
        import h5py
    except ImportError:
        print("  h5py not installed — install to inspect contents")
        h5py = None

    if h5py:
        with h5py.File(written[0], "r") as f:
            groups = list(f.keys())
            print(f"  file groups: {groups[:6]}")
            sm_path = next((f"{g}/soil_moisture" for g in groups
                            if f"{g}/soil_moisture" in f), None)
            if sm_path:
                a = f[sm_path][:]
                fill = f[sm_path].attrs.get("_FillValue", -9999.0)
                valid = a[(a != fill) & np.isfinite(a)]
                print(f"  grid        : {a.shape} (global 9 km EASE-Grid 2.0)")
                print(f"  valid global: {valid.size:,}/{a.size:,} "
                      f"({100 * valid.size / a.size:.1f}%)")
                if valid.size:
                    print(f"  range       : {valid.min():.3f} to {valid.max():.3f} "
                          f"m3/m3")

    record(
        SOIL_GEOLOGY, source=f"SMAP {product} (NSIDC DAAC)",
        url=CMR, files=written,
        license_="NASA open data",
        notes=(f"{len(written)} granules sampled via CMR. Global HDF5 at 9 km. "
               "Coarse for mountain slopes — the Appendix flags this as the "
               "weakest free substitute for pore pressure, and that stands."),
    )


if __name__ == "__main__":
    main()
