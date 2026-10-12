"""Check packaging metadata without requiring Home Assistant."""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "custom_components/spot_trace_history/manifest.json").read_text())
hacs = json.loads((root / "hacs.json").read_text())
assert manifest["domain"] == "spot_trace_history"
assert re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", manifest["version"])
package = json.loads((root / "package.json").read_text())
assert package["version"] == manifest["version"], "package.json and manifest.json versions differ"
readme = (root / "README.md").read_text()
readme_version = re.search(r"(?m)^# SPOT Trace History v(\S+)", readme)
assert readme_version and readme_version[1] == manifest["version"], "README and manifest versions differ"
assert (root / "custom_components/spot_trace_history/www/spot-trace-history-card.js").is_file()
assert (root / "LICENSE").is_file()
assert isinstance(hacs, dict)
print("Package metadata OK")
