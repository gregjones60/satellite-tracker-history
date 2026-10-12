# Contributing

Requirements: Python 3.13, Node.js 22.

Run `python -m pip install pytest pytest-asyncio voluptuous`, then `bash scripts/check.sh`.
Run `python scripts/build_release.py` to produce a release ZIP in `dist/` using
the version in `manifest.json`, and synchronize `package.json` to that version.
To prepare a new stable release, run `python scripts/build_release.py --version 0.5.3`.
This updates both version fields and embeds the version in the ZIP's manifest.

Create a GitHub repository with these files at the root, push to `main`,
and enable GitHub Actions. To publish, commit the prepared version changes,
push the changes, and push a matching annotated tag such as `v0.5.2`.
The release workflow rejects a tag that differs from the committed manifest,
builds with that tag's version, runs tests, and attaches only the matching ZIP
to the GitHub release. HACS displays published release tags; branch installs
may still display a commit hash. A tag alone does not create a HACS release.

The release ZIP contains the **contents** of `custom_components/spot_trace_history`,
which is the HACS integration release asset layout.
Do not commit credentials, SPOT feed passwords, GPX history or SQLite databases.
