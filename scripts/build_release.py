"""Build a HACS integration release archive."""
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "custom_components/spot_trace_history/manifest.json").read_text())
version = manifest["version"]
dist = root / "dist"
dist.mkdir(exist_ok=True)
archive = dist / f"spot_trace_history-{version}.zip"
source = root / "custom_components/spot_trace_history"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
    for file in sorted(source.rglob("*")):
        if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
            z.write(file, file.relative_to(source))
print(archive)
