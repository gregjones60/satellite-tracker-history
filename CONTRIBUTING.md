# Contributing

Requirements: Python 3.14 (required by current Home Assistant), Node.js 22.

Create a virtual environment, run `python -m pip install -r requirements_test.txt`,
then `bash scripts/check.sh`. With [uv](https://docs.astral.sh/uv/):
`uv venv --python 3.14 .venv && uv pip install --python .venv -r requirements_test.txt`,
then `PATH="$PWD/.venv/bin:$PATH" bash scripts/check.sh`.

`requirements_test.txt` pins `pytest-homeassistant-custom-component`, which pins a
Home Assistant release. Tests marked `ha` (`tests/test_ha_integration.py`) run the
integration in that real Home Assistant: entry setup/unload/reload, entities and
devices, config and options flows, actions and WebSocket commands, with the SPOT
API mocked. Without the harness installed (for example on an older Python with only
`pytest pytest-asyncio voluptuous aiohttp`), those tests are skipped and the remaining
tests use lightweight Home Assistant stand-ins. Neither replaces checking the UI
in a running Home Assistant instance.
Run `python scripts/build_release.py` to produce a release ZIP in `dist/` using
the version in `manifest.json`, and synchronize `package.json` and the README
heading/card URL to that version. Historical release notes retain their versions.
To build a specific stable version locally, run `python scripts/build_release.py --version 0.5.3`.
This updates the version fields and README, and embeds the version in the ZIP's manifest.

After building, run `python scripts/validate_release.py` to validate the actual
ZIP. An explicit artifact/version can be checked with
`python scripts/validate_release.py dist/satellite_tracker_history-0.5.12.zip --version 0.5.12`.
Add `--ref v0.5.12` to also compare every packaged file with the Git tag HACS
uses. Both the tag's files and the current checkout must match the ZIP.
The check requires Node.js and verifies the package's complete file list,
byte-for-byte agreement with integration source, manifest version/domain, and
ZIP integrity. It executes the packaged card in a minimal browser-like test
environment and verifies custom-element registration, playback methods,
timeline controls, visibility for a selected trip, and scrubbing behavior.
The output includes the bundled card's SHA-256 fingerprint.

CI builds and validates the package after tests. Release validates the exact
versioned ZIP before pushing its version commit or publishing. This checks the
release artifact; it does not verify the files installed in a running HA instance
or replace live browser testing.

Create a GitHub repository with these files at the root, push to `main`,
and enable GitHub Actions. CI runs on pushes to every branch and on pull requests.
To publish, push changes to `main`; no manual patch-version bump is needed.
After all CI jobs succeed for that push, the release workflow checks out the
tested commit and increments the highest stable version found in the manifest
or existing `vX.Y.Z` tags and GitHub releases, including drafts (for example,
`0.5.2` becomes `0.5.3`). Published version names are never reused, even if their
Git tags were deleted. It updates the
manifest, package metadata, and README, then builds and validates the archive.
The workflow commits these version changes back to `main` and creates the
matching GitHub release/tag. The workflow explicitly creates the tag at the
validated version commit, checks ZIP/source/tag agreement, and verifies the
remote tag after publishing. HACS currently installs the tagged repository
contents, so validating only the attached ZIP is insufficient. The bot push uses `GITHUB_TOKEN`, so it does not
trigger recursive CI/releases. No manual tag push is needed. The repository
must permit Actions to push to `main`; a protected branch or a newer main commit
can reject the push, in which case publication stops without forcing changes.
Pull-request and manually triggered CI runs do not publish. HACS displays
published release tags; branch installs may still display a commit hash.

The release ZIP contains the **contents** of `custom_components/satellite_tracker_history`,
which is the HACS integration release asset layout.
Do not commit credentials, SPOT feed passwords, GPX history or SQLite databases.
