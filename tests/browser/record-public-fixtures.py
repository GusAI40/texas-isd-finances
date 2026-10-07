"""Record the small, public GET payloads used by deterministic browser tests.

Run deliberately when refreshing evidence; the test suite itself never reaches
the network.  The output contains only district-level public numeric results.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

BASE = "https://txisd.dev"
DISTRICTS = {"dallas": "057905", "houston": "101912", "tioga": "091907", "charter": "003801"}
PATHS = {"stats": "/stats"}
for name, number in DISTRICTS.items():
    PATHS[f"{name}_summary"] = f"/district/{number}/summary"
    PATHS[f"{name}_peers"] = f"/district/{number}/peers"
    PATHS[f"{name}_anomalies"] = f"/anomalies?district_number={number}&limit=50"
    PATHS[f"{name}_breakdown"] = f"/district/{number}/breakdown"
    PATHS[f"{name}_detail"] = f"/district/{number}/spending-detail"
OUT = Path(__file__).with_name("fixtures") / "public-endpoints.json"


def main():
    payloads = {}
    hashes = {}
    for key, route in PATHS.items():
        with urlopen(BASE + route, timeout=30) as response:  # nosec B310: fixed public HTTPS origin
            raw = response.read()
        payloads[key] = json.loads(raw)
        hashes[key] = hashlib.sha256(raw).hexdigest()
    OUT.write_text(json.dumps({
        "origin": BASE,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "routes": PATHS,
        "sha256": hashes,
        "payloads": payloads,
    }, indent=2) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
