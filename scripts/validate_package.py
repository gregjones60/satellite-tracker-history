"""Check packaging metadata without requiring Home Assistant."""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "custom_components/satellite_tracker_history/manifest.json").read_text())
hacs = json.loads((root / "hacs.json").read_text())
assert manifest["domain"] == "satellite_tracker_history"
assert re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", manifest["version"])
package = json.loads((root / "package.json").read_text())
assert package["version"] == manifest["version"], "package.json and manifest.json versions differ"
readme = (root / "README.md").read_text()
readme_version = re.search(r"(?m)^# Satellite Tracker History v(\S+)", readme)
assert readme_version and readme_version[1] == manifest["version"], "README and manifest versions differ"
assert (root / "custom_components/satellite_tracker_history/www/satellite-tracker-history-card.js").is_file()
leaflet = root / "custom_components/satellite_tracker_history/www/leaflet"
for name in ("leaflet-src.esm.js", "leaflet.css", "LICENSE"):
    assert (leaflet / name).is_file(), f"Bundled Leaflet is missing {name}"
leaflet_version = re.search(r'var version = "([^"]+)"', (leaflet / "leaflet-src.esm.js").read_text())[1]
card = (root / "custom_components/satellite_tracker_history/www/satellite-tracker-history-card.js").read_text()
assert f"LEAFLET_VERSION='{leaflet_version}'" in card, "Card requests a different Leaflet version than the bundled one"
assert (root / "LICENSE").is_file()
assert isinstance(hacs, dict)
print("Package metadata OK")
