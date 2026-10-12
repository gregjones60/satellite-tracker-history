"""Synchronize release versions and build a HACS integration archive."""
import argparse
import json
import re
import zipfile
from pathlib import Path


def normalize_version(value):
    """Accept a stable semantic version or its Git tag, never a commit hash."""
    version = value.removeprefix("v")
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError(f"Expected a version such as 0.5.2 or v0.5.2, got {value!r}")
    return version


def build_release(root, version=None):
    source = root / "custom_components/spot_trace_history"
    manifest_path = source / "manifest.json"
    package_path = root / "package.json"
    manifest = json.loads(manifest_path.read_text())
    package = json.loads(package_path.read_text())
    version = normalize_version(version if version is not None else manifest["version"])
    for path, metadata in [(manifest_path, manifest), (package_path, package)]:
        if metadata.get("version") != version:
            metadata["version"] = version
            path.write_text(json.dumps(metadata, indent=2) + "\n")
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    archive = dist / f"spot_trace_history-{version}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for file in sorted(source.rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                z.write(file, file.relative_to(source))
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Update manifest and package version before building (e.g. 0.5.3)")
    args = parser.parse_args()
    try:
        print(build_release(Path(__file__).resolve().parents[1], args.version))
    except ValueError as exc:
        parser.error(str(exc))
