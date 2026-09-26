"""Load the standalone client without importing Home Assistant."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audac_protocol_test", ROOT / "custom_components/audac_nwp/nwp220.py")
nwp = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = nwp
spec.loader.exec_module(nwp)
