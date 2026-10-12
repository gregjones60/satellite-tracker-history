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


def next_release_version(current, tags):
    """Increment the highest stable version to avoid reusing an existing tag."""
    versions = [tuple(map(int, normalize_version(current).split(".")))]
    for tag in tags:
        if not tag.startswith("v"):
            continue
        try:
            versions.append(tuple(map(int, normalize_version(tag).split("."))))
        except ValueError:
            continue
    major, minor, patch = max(versions)
    return f"{major}.{minor}.{patch + 1}"


def build_release(root, version=None):
    source = root / "custom_components/spot_trace_history"
    manifest_path = source / "manifest.json"
    package_path = root / "package.json"
    manifest = json.loads(manifest_path.read_text())
    package = json.loads(package_path.read_text())
    version = normalize_version(version if version is not None else manifest["version"])
    readme_path = root / "README.md"
    readme = readme_path.read_text()
    updated_readme, count = re.subn(
        r"(?m)^(# SPOT Trace History v)\S+",
        lambda match: match[1] + version,
        readme,
    )
    if count != 1:
        raise ValueError("README.md must contain one versioned SPOT Trace History heading")
    updated_readme = re.sub(
        r"(/spot_trace_history/spot-trace-history-card\.js\?v=)[0-9]+\.[0-9]+\.[0-9]+",
        lambda match: match[1] + version,
        updated_readme,
    )
    for path, metadata in [(manifest_path, manifest), (package_path, package)]:
        if metadata.get("version") != version:
            metadata["version"] = version
            path.write_text(json.dumps(metadata, indent=2) + "\n")
    if updated_readme != readme:
        readme_path.write_text(updated_readme)
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
    parser.add_argument("--version", help="Update manifest, package, and README version before building (e.g. 0.5.3)")
    args = parser.parse_args()
    try:
        print(build_release(Path(__file__).resolve().parents[1], args.version))
    except ValueError as exc:
        parser.error(str(exc))
