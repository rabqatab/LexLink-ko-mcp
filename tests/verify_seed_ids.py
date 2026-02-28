"""Verify seed law IDs against live law.go.kr API."""
import os
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.getenv("LAW_OC") and not os.getenv("OC"):
    os.environ["OC"] = os.getenv("LAW_OC")

from lexlink.server import create_server
from lexlink.client import LawAPIClient
from lexlink.params import map_params_to_upstream, resolve_oc
from lexlink.parser import parse_xml_response, extract_law_list

import json

server = create_server()
rm = server._resource_manager
cached = json.loads(rm._resources["lexlink://laws/frequently-used"].fn())

print(f"Verifying {len(cached)} seed entries against live API...\n")
print(f"{'Query':<45} {'Seed ID':>8}  {'API ID':>8}  Status")
print("-" * 80)

client = LawAPIClient()
oc = resolve_oc(override_oc=None, session_oc=None)

ok_count = 0
mismatch_count = 0

for entry in cached:
    query = entry["full_name"]
    seed_id = entry["id"]

    # Search with enough results and multiple pages if needed
    found = False
    for page in range(1, 6):
        params = map_params_to_upstream({
            "oc": oc, "target": "eflaw", "type": "XML",
            "query": query, "display": 100, "page": page,
        })
        response = client.get("/DRF/lawSearch.do", params, "XML")
        if response.get("status") != "ok":
            break
        raw = response.get("raw_content", "")
        if not raw:
            break
        parsed = parse_xml_response(raw)
        if not parsed:
            break
        laws = extract_law_list(parsed)
        if not laws:
            break

        for law in laws:
            if law.get("법령명한글", "") == query:
                api_id = str(law.get("법령ID", ""))
                match = "OK" if api_id == seed_id else f"MISMATCH (API={api_id})"
                print(f"{query:<45} {seed_id:>8}  {api_id:>8}  {match}")
                if api_id == seed_id:
                    ok_count += 1
                else:
                    mismatch_count += 1
                found = True
                break
        if found:
            break
        time.sleep(0.2)

    if not found:
        print(f"{query:<45} {seed_id:>8}  {'?':>8}  NOT FOUND IN API")
        mismatch_count += 1

    time.sleep(0.3)

print(f"\nResult: {ok_count} OK, {mismatch_count} mismatches out of {len(cached)}")
