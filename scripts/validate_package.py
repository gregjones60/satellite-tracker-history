"""Check packaging metadata without requiring Home Assistant."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "custom_components/spot_trace_history/manifest.json").read_text())
hacs = json.loads((root / "hacs.json").read_text())
assert manifest["domain"] == "spot_trace_history"
assert manifest["version"]
assert (root / "custom_components/spot_trace_history/www/spot-trace-history-card.js").is_file()
assert (root / "LICENSE").is_file()
assert isinstance(hacs, dict)
print("Package metadata OK")
