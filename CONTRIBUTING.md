# Contributing

Requirements: Python 3.13, Node.js 22.

Run `python -m pip install pytest pytest-asyncio voluptuous`, then `bash scripts/check.sh`.
Run `python scripts/build_release.py` to produce a release ZIP in `dist/` using
the version in `manifest.json`, and synchronize `package.json` and the README
heading/card URL to that version. Historical release notes retain their versions.
To prepare a new stable release, run `python scripts/build_release.py --version 0.5.3`.
This updates the version fields and README, and embeds the version in the ZIP's manifest.

Create a GitHub repository with these files at the root, push to `main`,
and enable GitHub Actions. CI runs on pushes to every branch and on pull requests.
To publish, commit the prepared version changes and push to `main`.
After all CI jobs succeed for that push, the release workflow checks out the
tested commit, builds and validates its manifest version, and creates a GitHub
release and tag such as `v0.5.2` with the matching ZIP. No manual tag push is needed.
If that version tag already points to another commit, release fails; bump the
version before the next release. Pull-request and manually triggered CI runs do
not publish. HACS displays published release tags; branch installs may still
display a commit hash.

The release ZIP contains the **contents** of `custom_components/spot_trace_history`,
which is the HACS integration release asset layout.
Do not commit credentials, SPOT feed passwords, GPX history or SQLite databases.
