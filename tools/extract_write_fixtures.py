"""Extract exact bytes from local logs; never fabricate missing responses."""

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sessions = []
for name in ("write-validation-2.log", "optional-validation-2.log"):
    pending = {}
    exchanges = []
    for line in (ROOT / "captures" / name).read_text(encoding="utf-8-sig").splitlines():
        match = re.search(r"\b(TX|RX): (b'.*'|b\".*\")$", line)
        if not match:
            continue
        data = ast.literal_eval(match[2])
        fields = data.split(b"|")
        if match[1] == "TX":
            row = {"request_hex": data.hex(), "response_hex": None}
            exchanges.append(row)
            pending[fields[2]] = row
        elif fields[1] in pending:
            pending[fields[1]]["response_hex"] = data.hex()
    sessions.append({"source_log": name, "exchanges": exchanges})
output = {
    "provenance": {
        "kind": "physical_device_capture",
        "model": "NWP220",
        "firmware": "unknown",
        "date": "2026-09-26",
        "transport": "UDP",
        "remote_port": 8711,
        "null_response": "No response received within the investigation timeout",
    },
    "sessions": sessions,
}
path = ROOT / "tests/fixtures/hardware_write_observations.json"
path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
print(path)
