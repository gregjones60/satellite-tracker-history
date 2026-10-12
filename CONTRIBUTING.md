# Contributing

Requirements: Python 3.13, Node.js 22.

Run `python -m pip install pytest pytest-asyncio voluptuous`, then `bash scripts/check.sh`.
Run `python scripts/build_release.py` to produce a release ZIP in `dist/`.

Create a GitHub repository with these files at the root, push to `main`,
and enable GitHub Actions. To publish, update `manifest.json` version,
push the changes, and push a matching annotated tag such as `v0.5.2`.
The release workflow runs tests and attaches the ZIP to the GitHub release.

The release ZIP contains the **contents** of `custom_components/spot_trace_history`,
which is the HACS integration release asset layout.
Do not commit credentials, SPOT feed passwords, GPX history or SQLite databases.
