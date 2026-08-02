"""Tier B — Sentinel-1 and Sentinel-2 (Copernicus Dataspace).

Scenes are 0.7-1.8 GB each, so downloading a full archive is not the point
here. What matters for verification is:

  * how many scenes actually cover the AOI
  * the real revisit interval (InSAR needs a consistent repeat orbit)
  * cloud cover for Sentinel-2, which in monsoon Himalaya is the binding
    constraint on any optical product
  * that a download genuinely works with our token

So this searches the catalogue thoroughly and downloads one scene as proof.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime as dt
from collections import Counter

import requests

from common import AOI_BBOX, AOI_NAME, HYDROLOGY, RAW, credential

ODATA = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
TOKEN_URL = ("https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
             "protocol/openid-connect/token")
DOWNLOAD = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products({id})/$value"

W, S, E, N = AOI_BBOX
AOI_WKT = (f"POLYGON(({W} {S},{E} {S},{E} {N},{W} {N},{W} {S}))")
OUT = RAW / "11_satellite"


def token() -> str:
    r = requests.post(TOKEN_URL, data={
        "client_id": "cdse-public",
        "username": credential("CDSE_USERNAME"),
        "password": credential("CDSE_PASSWORD"),
        "grant_type": "password",
    }, timeout=90)
    r.raise_for_status()
    return r.json()["access_token"]


def _filter(collection: str, start: dt.date, end: dt.date, extra: str = "") -> str:
    # `extra` must be parenthesised: OData binds `or` loosely, so an unwrapped
    # "A or B" escapes the collection clause and returns other missions.
    flt = (f"Collection/Name eq '{collection}' and "
           f"OData.CSC.Intersects(area=geography'SRID=4326;{AOI_WKT}') and "
           f"ContentDate/Start gt {start}T00:00:00.000Z and "
           f"ContentDate/Start lt {end}T23:59:59.000Z")
    if extra:
        flt += f" and ({extra})"
    return flt


def _get(params: dict, tries: int = 4) -> dict | None:
    """OData is flaky on wide queries — retry with backoff, give up cleanly."""
    import time
    for attempt in range(tries):
        try:
            r = requests.get(ODATA, params=params, timeout=300)
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            if attempt == tries - 1:
                return None
            time.sleep(3 * (attempt + 1))
    return None


def count(collection: str, start: dt.date, end: dt.date, extra: str = "") -> int | None:
    """Total matches, without paging through them. None if the server refuses."""
    j = _get({"$filter": _filter(collection, start, end, extra),
              "$count": "true", "$top": 1})
    return None if j is None else int(j.get("@odata.count", 0))


def search(collection: str, start: dt.date, end: dt.date,
           extra: str = "", limit: int = 1000) -> list[dict]:
    """Page through results — a single request caps out and silently truncates."""
    out, skip = [], 0
    while len(out) < limit:
        j = _get({"$filter": _filter(collection, start, end, extra),
                  "$top": 100, "$skip": skip,
                  "$orderby": "ContentDate/Start desc",
                  "$expand": "Attributes"})
        page = [] if j is None else j.get("value", [])
        if not page:
            break
        out.extend(page)
        skip += len(page)
        if len(page) < 100:
            break
    return out[:limit]


def attr(prod: dict, name: str):
    for a in prod.get("Attributes", []):
        if a.get("Name") == name:
            return a.get("Value")
    return None


def report_s1(prods: list[dict]) -> None:
    print(f"  scenes found: {len(prods)}")
    if not prods:
        return
    modes = Counter(attr(p, "operationalMode") or "?" for p in prods)
    orbits = Counter(str(attr(p, "orbitDirection") or "?") for p in prods)
    types = Counter(attr(p, "productType") or "?" for p in prods)
    print(f"  modes       : {dict(modes)}")
    print(f"  orbit dir   : {dict(orbits)}")
    print(f"  product type: {dict(types)}")
    dates = sorted({p["ContentDate"]["Start"][:10] for p in prods})
    print(f"  date range  : {dates[0]} to {dates[-1]}  ({len(dates)} distinct days)")
    if len(dates) > 1:
        ds = [dt.date.fromisoformat(d) for d in dates]
        gaps = [(ds[i + 1] - ds[i]).days for i in range(len(ds) - 1)]
        gaps = [g for g in gaps if g > 0]
        if gaps:
            print(f"  revisit     : median {sorted(gaps)[len(gaps) // 2]} d, "
                  f"max gap {max(gaps)} d")
    rel = Counter(str(attr(p, "relativeOrbitNumber")) for p in prods)
    print(f"  relative orbits (InSAR stacks): "
          f"{dict(sorted(rel.items(), key=lambda kv: -kv[1])[:5])}")


def report_s2(prods: list[dict]) -> None:
    print(f"  scenes found: {len(prods)}")
    if not prods:
        return
    dates = sorted({p["ContentDate"]["Start"][:10] for p in prods})
    print(f"  date range  : {dates[0]} to {dates[-1]}  ({len(dates)} distinct days)")

    pairs = [(p["ContentDate"]["Start"][:10], float(attr(p, "cloudCover") or -1))
             for p in prods]
    pairs = [(d, c) for d, c in pairs if c >= 0]
    if not pairs:
        return
    clouds = sorted(c for _, c in pairs)
    print(f"  cloud cover : median {clouds[len(clouds) // 2]:.0f}%, "
          f"min {clouds[0]:.0f}%, max {clouds[-1]:.0f}%")
    for thr in (10, 20, 50):
        n = sum(1 for c in clouds if c < thr)
        print(f"    scenes below {thr:>2}% cloud: {n}/{len(clouds)} "
              f"({100 * n / len(clouds):.0f}%)")

    # Monsoon vs dry season — an annual median hides the seasonal split that
    # actually determines when optical imagery is usable.
    mon = [c for d, c in pairs if d[5:7] in ("05", "06", "07", "08", "09")]
    dry = [c for d, c in pairs if d[5:7] in ("11", "12", "01", "02", "03")]
    for label, vals in (("monsoon May-Sep", mon), ("dry Nov-Mar", dry)):
        if vals:
            vals = sorted(vals)
            usable = sum(1 for c in vals if c < 20)
            print(f"  {label:16}: n={len(vals):4}  median {vals[len(vals) // 2]:5.0f}%  "
                  f"below 20% cloud: {usable} ({100 * usable / len(vals):.0f}%)")


def download_one(prod: dict, tok: str) -> Path | None:
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / (prod["Name"] + ".zip")
    if dest.exists() and dest.stat().st_size > 1e6:
        print(f"  [skip] {dest.name}")
        return dest
    url = DOWNLOAD.format(id=prod["Id"])
    print(f"  downloading {prod['Name'][:60]}... ({prod.get('ContentLength', 0) / 1e9:.2f} GB)")
    try:
        # Dataspace redirects to a separate download host. requests drops the
        # Authorization header across hosts, so follow the redirect by hand
        # and re-attach the bearer token.
        sess = requests.Session()
        hdr = {"Authorization": f"Bearer {tok}"}
        r = sess.get(url, headers=hdr, stream=True, timeout=1800,
                     allow_redirects=False)
        hops = 0
        while r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
            nxt = r.headers["Location"]
            r.close()
            hops += 1
            if hops > 5:
                print("  [fail] too many redirects")
                return None
            r = sess.get(nxt, headers=hdr, stream=True, timeout=1800,
                         allow_redirects=False)
        with r:
            if not r.ok:
                print(f"  [fail] HTTP {r.status_code} after {hops} redirect(s)")
                return None
            tmp = dest.with_suffix(".part")
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(1 << 22):
                    fh.write(chunk)
            tmp.replace(dest)
        print(f"  [ok]   {dest.name} ({dest.stat().st_size / 1e9:.2f} GB)")
        return dest
    except Exception as exc:  # noqa: BLE001
        print(f"  [fail] {type(exc).__name__}: {str(exc)[:120]}")
        return None


def main() -> None:
    end = dt.date.today()
    year_start = end - dt.timedelta(days=365)
    print(f"Copernicus Dataspace catalogue — AOI, {year_start} to {end}\n")

    # --- Sentinel-1: land-imaging modes only ------------------------------
    print("SENTINEL-1 (flood extent + InSAR ground creep)")
    s1_extra = "contains(Name,'IW_GRDH') or contains(Name,'IW_SLC')"
    n1 = count("SENTINEL-1", year_start, end, s1_extra)
    print(f"  total matching scenes in 12 months: "
          f"{n1:,}" if n1 is not None else "  total: query timed out")
    # 60-day window so paging reaches back far enough to measure revisit
    win = end - dt.timedelta(days=60)
    s1 = search("SENTINEL-1", win, end, s1_extra, limit=1000)
    print(f"  sampled {len(s1)} scenes over the last 60 days")
    report_s1(s1)

    # --- Sentinel-2: cloud is the binding constraint ----------------------
    print("\nSENTINEL-2 (landslide scars, glacial lakes)")
    s2_extra = "contains(Name,'MSIL2A')"
    # Sample one month per season rather than paging a whole year: the
    # seasonal contrast is the finding, and wide queries time out.
    s2 = []
    for label, (m0, m1) in [("Jan", (1, 2)), ("Apr", (4, 5)),
                            ("Jul", (7, 8)), ("Oct", (10, 11))]:
        yr = end.year if m0 <= end.month else end.year - 1
        a = dt.date(yr, m0, 1)
        b = dt.date(yr if m1 > m0 else yr + 1, m1, 1)
        got = search("SENTINEL-2", a, b, s2_extra, limit=300)
        print(f"  {label} {yr}: {len(got)} scenes")
        s2.extend(got)
    print(f"  sampled {len(s2)} scenes across four seasonal windows")
    report_s2(s2)

    # --- prove download works --------------------------------------------
    print("\nProving download access with one Sentinel-1 IW scene:")
    if s1:
        tok = token()
        smallest = min(s1, key=lambda p: p.get("ContentLength") or 9e18)
        download_one(smallest, tok)
    else:
        print("  skipped — no Sentinel-1 scenes found")


if __name__ == "__main__":
    main()
