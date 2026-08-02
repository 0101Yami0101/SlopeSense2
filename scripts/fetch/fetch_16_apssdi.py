"""APSSDI — Arunachal Pradesh state geoscience layers via open WFS.

The APSAC geoportal (apssdi.in) runs a GeoServer whose OWS endpoint is open —
no authentication, despite the catalogue UI behind it requiring a login. This
matters because it retires the single worst finding in DATA_VERIFICATION.md:
free global geology gave three lithology classes for the whole state, which is
useless for susceptibility. The state lithology layer gives 24 lithological
units and 32 named stratigraphic units, and the lineament layer supplies the
structural control that had otherwise been a GSI ask.

Everything here is statewide, matching the project's scope.

Note on terms: the portal publishes no licence statement. Attribute coding
(GWMAP_CODE, GU_CODE) indicates NRSC/Bhuvan lineage. Confirm attribution
requirements with APSAC before anything from here ships in a deliverable.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import certifi
import requests

from common import AOI_NAME, CONTEXT, SOIL_GEOLOGY, HYDROLOGY, EXPOSURE, UA, record

OWS = "https://apssdi.in/geoserver/ows"

# apssdi.in serves only its leaf certificate — the Go Daddy G2 intermediate is
# missing from the chain. curl's system store papers over this; Python's does
# not, so requests fails with CERTIFICATE_VERIFY_FAILED. The fix is to supply
# the missing intermediate rather than to switch verification off: the chain is
# still fully verified, we are only handing it the link the server omits.
_CA_BUNDLE = Path(__file__).resolve().parents[1] / "certs" / "apssdi_chain.pem"


def _ca_bundle() -> str:
    """Build (once) a CA bundle of certifi's roots plus the missing intermediate."""
    if not _CA_BUNDLE.exists():
        intermediate = _CA_BUNDLE.with_name("godaddy_g2_intermediate.pem")
        _CA_BUNDLE.write_text(
            Path(certifi.where()).read_text(encoding="utf-8")
            + "\n" + intermediate.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return str(_CA_BUNDLE)


def get(url: str, params: dict, timeout: int = 300) -> requests.Response:
    """GET with the repaired trust chain. Verification stays on."""
    r = requests.get(url, params=params, timeout=timeout,
                     headers=UA, verify=_ca_bundle())
    r.raise_for_status()
    return r

# (workspace:layer, output stem, destination folder)
LAYERS = [
    ("sdi_128:Lithology_Layer_-_Arunachal_Pradesh",
     "apssdi_lithology_vector", SOIL_GEOLOGY),
    ("sdi_141:Lineament_layer_-_Arunachal_Pradesh",
     "apssdi_lineaments_vector", CONTEXT),
    ("sdi_149:Geomorphology_Layer_-_Arunachal_Pradesh",
     "apssdi_geomorphology_vector", CONTEXT),
    ("sdi_143:Litho-geomorphology_Layer_-_Arunachal_Pradesh",
     "apssdi_litho-geomorphology_vector", CONTEXT),
    ("sdi_122:Geology_and_Mining_Information_Layer_-_Arunachal_Pradesh",
     "apssdi_geology-mining_vector", CONTEXT),
    ("sdi_139:Snow_cover_layer_-_Arunachal_Pradesh",
     "apssdi_snow-cover_vector", CONTEXT),
    ("sdi_142:Drainage_Layer_-_Arunachal_Pradesh",
     "apssdi_drainage_vector", HYDROLOGY),
    ("sdi_126:Settlement_Layer_-_Arunachal_Pradesh",
     "apssdi_settlements_vector", EXPOSURE),
    ("sdi_137:Administrative_Circle_Layer_-_Arunachal_Pradesh",
     "apssdi_admin-circles_vector", EXPOSURE),
]


def feature_count(typename: str) -> int | None:
    """Ask the server how many features exist before pulling them."""
    r = get(OWS, {"service": "WFS", "version": "2.0.0",
                  "request": "GetFeature", "typeNames": typename,
                  "resultType": "hits"}, timeout=120)
    import re
    m = re.search(r'numberMatched="(\d+)"', r.text)
    return int(m.group(1)) if m else None


def fetch(typename: str, stem: str, folder: Path) -> Path | None:
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{stem}_{AOI_NAME}.geojson"

    n = feature_count(typename)
    print(f"  {typename.split(':')[1][:44]:46} {n if n is not None else '?':>6} features")

    r = get(OWS, {"service": "WFS", "version": "2.0.0",
                  "request": "GetFeature", "typeNames": typename,
                  "outputFormat": "application/json"})
    try:
        gj = r.json()
    except Exception:  # noqa: BLE001
        print("      ! non-JSON response, skipped")
        return None

    feats = gj.get("features")
    if not feats:
        print("      ! no features returned, skipped")
        return None

    # GeoServer emits nulled portal bookkeeping columns on every record.
    # They carry no information and roughly double the file size.
    noise = {"created_at", "updated_at", "status", "user_id", "parent_id"}
    for f in feats:
        for k in noise & f["properties"].keys():
            del f["properties"][k]

    dest.write_text(json.dumps(gj), encoding="utf-8")
    print(f"      -> {dest.relative_to(folder.parents[2])}  "
          f"({dest.stat().st_size / 1e6:.1f} MB, {len(feats)} features)")
    return dest


def main() -> None:
    print("APSSDI (apssdi.in GeoServer) — state geoscience layers\n")

    written: dict[Path, list[Path]] = {}
    for typename, stem, folder in LAYERS:
        try:
            p = fetch(typename, stem, folder)
        except Exception as e:  # noqa: BLE001
            print(f"      ! {typename}: {e}")
            continue
        if p:
            written.setdefault(folder, []).append(p)

    for folder, files in written.items():
        record(
            folder,
            source="APSSDI / Arunachal Pradesh Space Application Centre (APSAC)",
            url=OWS,
            files=files,
            license_="UNSTATED — portal publishes no licence. Confirm with APSAC "
                     "before redistribution. Attribute coding suggests NRSC/Bhuvan lineage.",
            notes="Open WFS, no auth required. Statewide, ~1:50,000. Replaces the "
                  "3-class free geology that DATA_VERIFICATION.md marked unusable.",
        )

    total = sum(len(v) for v in written.values())
    print(f"\n  {total}/{len(LAYERS)} layers written")


if __name__ == "__main__":
    main()
