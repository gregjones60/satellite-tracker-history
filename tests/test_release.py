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
    with zipfile.ZipFile(archive) as z:
        assert json.loads(z.read("manifest.json")) == manifest
        assert "__init__.py" in z.namelist()
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in z.namelist())


@pytest.mark.parametrize("invalid", ["e61df73", "v0.5", "../0.5.2", "01.5.2"])
def test_invalid_release_version_does_not_change_project(project, invalid):
    paths = [project / "package.json", project / "custom_components/spot_trace_history/manifest.json"]
    before = [path.read_bytes() for path in paths]
    with pytest.raises(ValueError, match="Expected a version"):
        builder.build_release(project, invalid)
    assert [path.read_bytes() for path in paths] == before
    assert not (project / "dist").exists()
