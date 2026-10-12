# Contributing

Requirements: Python 3.13, Node.js 22.

Run `python -m pip install pytest pytest-asyncio voluptuous`, then `bash scripts/check.sh`.
Run `python scripts/build_release.py` to produce a release ZIP in `dist/` using
the version in `manifest.json`, and synchronize `package.json` and the README
heading/card URL to that version. Historical release notes retain their versions.
To build a specific stable version locally, run `python scripts/build_release.py --version 0.5.3`.
This updates the version fields and README, and embeds the version in the ZIP's manifest.

Create a GitHub repository with these files at the root, push to `main`,
and enable GitHub Actions. CI runs on pushes to every branch and on pull requests.
To publish, push changes to `main`; no manual patch-version bump is needed.
After all CI jobs succeed for that push, the release workflow checks out the
tested commit and increments the highest stable version found in the manifest
or existing `vX.Y.Z` tags (for example, `0.5.2` becomes `0.5.3`). It updates the
manifest, package metadata, and README, then builds and validates the archive.
The workflow commits these version changes back to `main` and creates the
matching GitHub release/tag. The bot push uses `GITHUB_TOKEN`, so it does not
trigger recursive CI/releases. No manual tag push is needed. The repository
must permit Actions to push to `main`; a protected branch or a newer main commit
can reject the push, in which case publication stops without forcing changes.
Pull-request and manually triggered CI runs do not publish. HACS displays
published release tags; branch installs may still display a commit hash.

The release ZIP contains the **contents** of `custom_components/spot_trace_history`,
which is the HACS integration release asset layout.
Do not commit credentials, SPOT feed passwords, GPX history or SQLite databases.
