"""Verify release versions in metadata and the install archive."""
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location(
    "build_release", Path(__file__).resolve().parents[1] / "scripts/build_release.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture
def project(tmp_path):
    source = tmp_path / "custom_components/spot_trace_history"
    source.mkdir(parents=True)
    (source / "manifest.json").write_text(json.dumps({"domain": "spot_trace_history", "version": "0.5.2"}))
    (tmp_path / "package.json").write_text(json.dumps({"version": "0.5.1", "private": True}))
    (tmp_path / "README.md").write_text(
        '# SPOT Trace History v0.5.1 — history\n\n'
        '/spot_trace_history/spot-trace-history-card.js?v=0.5.1\n\n'
        '## Release notes 0.5.0\nPrevious release.\n'
    )
    (source / "__init__.py").write_text("# integration\n")
    (source / "__pycache__").mkdir()
    (source / "__pycache__/cached.pyc").write_bytes(b"cached")
    return tmp_path


@pytest.mark.parametrize("requested, expected", [(None, "0.5.2"), ("0.5.3", "0.5.3"), ("v1.0.0", "1.0.0")])
def test_build_synchronizes_metadata_and_archive(project, requested, expected):
    archive = builder.build_release(project, requested)
    assert archive.name == f"spot_trace_history-{expected}.zip"
    package = json.loads((project / "package.json").read_text())
    assert package == {"version": expected, "private": True}
    manifest = json.loads((project / "custom_components/spot_trace_history/manifest.json").read_text())
    assert manifest == {"domain": "spot_trace_history", "version": expected}
    readme = (project / "README.md").read_text()
    assert f"# SPOT Trace History v{expected} — history" in readme
    assert f"/spot_trace_history/spot-trace-history-card.js?v={expected}" in readme
    assert "## Release notes 0.5.0\nPrevious release." in readme
    with zipfile.ZipFile(archive) as z:
        assert json.loads(z.read("manifest.json")) == manifest
        assert "__init__.py" in z.namelist()
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in z.namelist())


@pytest.mark.parametrize("invalid", ["e61df73", "v0.5", "../0.5.2", "01.5.2"])
def test_invalid_release_version_does_not_change_project(project, invalid):
    paths = [project / "package.json", project / "custom_components/spot_trace_history/manifest.json",
             project / "README.md"]
    before = [path.read_bytes() for path in paths]
    with pytest.raises(ValueError, match="Expected a version"):
        builder.build_release(project, invalid)
    assert [path.read_bytes() for path in paths] == before
    assert not (project / "dist").exists()


@pytest.mark.parametrize("current,tags,expected", [
    ("0.5.2", [], "0.5.3"),
    ("0.5.2", ["v0.5.2"], "0.5.3"),
    ("0.5.2", ["v0.5.9", "v0.5.10"], "0.5.11"),
    ("0.6.0", ["v0.5.10"], "0.6.1"),
    ("0.5.2", ["v1.0.0", "v2.0.0-beta", "other", "vbad"], "1.0.1"),
])
def test_next_release_version(current, tags, expected):
    assert builder.next_release_version(current, tags) == expected


def test_successive_releases_increment_version_and_readme(project):
    current = "0.5.2"
    tags = ["v0.5.2"]
    for expected in ["0.5.3", "0.5.4"]:
        current = builder.next_release_version(current, tags)
        assert current == expected
        builder.build_release(project, current)
        assert f"# SPOT Trace History v{expected}" in (project / "README.md").read_text()
        tags.append(f"v{current}")
