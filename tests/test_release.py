"""Verify release versions in metadata and the install archive."""
import importlib.util
import json
from pathlib import Path
import zipfile
import subprocess

import pytest

spec = importlib.util.spec_from_file_location(
    "build_release", Path(__file__).resolve().parents[1] / "scripts/build_release.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

validator_spec = importlib.util.spec_from_file_location(
    'validate_release', Path(__file__).resolve().parents[1]/'scripts/validate_release.py'
)
validator = importlib.util.module_from_spec(validator_spec)
validator_spec.loader.exec_module(validator)


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
    # A manifest version that has never been released is published as it is.
    ("0.5.2", [], "0.5.2"),
    ("0.6.0", ["v0.5.10"], "0.6.0"),
    ("0.6.0", ["v0.5.17", "v0.5.3", "other"], "0.6.0"),
    # Once released, the next merge increments the highest released patch.
    ("0.5.2", ["v0.5.2"], "0.5.3"),
    ("0.6.0", ["v0.6.0"], "0.6.1"),
    ("0.5.2", ["v0.5.9", "v0.5.10"], "0.5.11"),
    ("0.5.2", ["v1.0.0", "v2.0.0-beta", "other", "vbad"], "1.0.1"),
])
def test_next_release_version(current, tags, expected):
    assert builder.next_release_version(current, tags) == expected


@pytest.fixture
def packaged_project(project):
    source = project/'custom_components/spot_trace_history/www'
    source.mkdir()
    card = Path(__file__).resolve().parents[1]/'custom_components/spot_trace_history/www/spot-trace-history-card.js'
    (source/card.name).write_bytes(card.read_bytes())
    return project


def rewrite_archive(archive, change):
    with zipfile.ZipFile(archive) as z:
        files = {name:z.read(name) for name in z.namelist()}
    change(files)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in files.items():
            z.writestr(name,content)


def test_validate_release_runs_packaged_playback_code(packaged_project):
    archive = builder.build_release(packaged_project)
    result = validator.validate_release(packaged_project,archive,'0.5.2')
    assert result['version'] == '0.5.2'
    assert result['files'] == 3
    assert len(result['card_sha256']) == 64


@pytest.mark.parametrize('problem', ['missing-card','stale-card','stale-backend','extra-file','wrong-version'])
def test_validate_release_rejects_incorrect_archive_contents(packaged_project,problem):
    archive = builder.build_release(packaged_project)
    def change(files):
        if problem == 'missing-card':
            del files['www/spot-trace-history-card.js']
        elif problem == 'stale-card':
            files['www/spot-trace-history-card.js'] = b'// old card'
        elif problem == 'stale-backend':
            files['__init__.py'] = b'# old backend'
        elif problem == 'extra-file':
            files['debug.txt'] = b'unexpected'
        else:
            files['manifest.json'] = b'{"domain":"spot_trace_history","version":"0.5.1"}'
    rewrite_archive(archive,change)
    with pytest.raises(ValueError,match='Release file list|differs from source|Packaged manifest'):
        validator.validate_release(packaged_project,archive)


@pytest.mark.parametrize('source_change', ['missing-playback','missing-controls','missing-play-button','invalid-js'])
def test_validate_release_rejects_broken_source_even_when_archive_matches(packaged_project,source_change):
    card = packaged_project/'custom_components/spot_trace_history/www/spot-trace-history-card.js'
    if source_change == 'missing-playback':
        card.write_text(card.read_text().replace('renderPlayback','oldRenderPlayback'))
    elif source_change == 'missing-controls':
        card.write_text(card.read_text().replace('class="playback-enabled"','class="missing-control"'))
    elif source_change == 'missing-play-button':
        card.write_text(card.read_text().replace('startPlayback','oldStartPlayback'))
    else:
        card.write_text('(() => {')
    archive = builder.build_release(packaged_project)
    with pytest.raises(ValueError,match='runtime smoke test'):
        validator.validate_release(packaged_project,archive)


def test_validate_release_rejects_duplicate_zip_entries(packaged_project):
    archive = builder.build_release(packaged_project)
    with zipfile.ZipFile(archive,'a') as z:
        with pytest.warns(UserWarning,match='Duplicate name'):
            z.writestr('www/spot-trace-history-card.js','// duplicate')
    with pytest.raises(ValueError,match='duplicate file entries'):
        validator.validate_release(packaged_project,archive)


def test_validate_release_rejects_unexpected_version(packaged_project):
    archive = builder.build_release(packaged_project)
    with pytest.raises(ValueError,match='requested release version'):
        validator.validate_release(packaged_project,archive,'0.5.3')


def test_validate_release_checks_the_tagged_source_not_just_the_zip(packaged_project):
    root=packaged_project
    subprocess.run(['git','init','-q'],cwd=root,check=True)
    subprocess.run(['git','config','user.name','Release Test'],cwd=root,check=True)
    subprocess.run(['git','config','user.email','release@example.test'],cwd=root,check=True)
    builder.build_release(root)
    subprocess.run(['git','add','.'],cwd=root,check=True)
    subprocess.run(['git','commit','-qm','Original source'],cwd=root,check=True)
    subprocess.run(['git','tag','v0.5.2'],cwd=root,check=True)
    card=root/'custom_components/spot_trace_history/www/spot-trace-history-card.js'
    card.write_text(card.read_text()+'\n// newer working copy\n')
    archive=builder.build_release(root)
    # Source and artifact match and playback works, but the tag is stale.
    validator.validate_release(root,archive)
    with pytest.raises(ValueError,match='differs from Git ref'):
        validator.validate_release(root,archive,ref='v0.5.2')
    subprocess.run(['git','add','.'],cwd=root,check=True)
    subprocess.run(['git','commit','-qm','Updated source'],cwd=root,check=True)
    assert validator.validate_release(root,archive,ref='HEAD')['version']=='0.5.2'


def test_successive_releases_increment_version_and_readme(project):
    current = "0.5.2"
    tags = ["v0.5.2"]
    for expected in ["0.5.3", "0.5.4"]:
        current = builder.next_release_version(current, tags)
        assert current == expected
        builder.build_release(project, current)
        assert f"# SPOT Trace History v{expected}" in (project / "README.md").read_text()
        tags.append(f"v{current}")
