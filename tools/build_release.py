"""Build a manual-install archive without caches, tests or local captures."""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
component = ROOT / "custom_components/audac_nwp"
version = json.loads((component / "manifest.json").read_text())["version"]
destination = ROOT / "dist" / f"audac_nwp-{version}.zip"
destination.parent.mkdir(exist_ok=True)
with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for path in sorted(component.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".json", ".yaml"}:
            archive.write(path, path.relative_to(ROOT))
    archive.write(ROOT / "LICENSE", "AUDAC_NWP_LICENSE")
print(destination)
