#!/usr/bin/env bash
set -euo pipefail
python -m compileall -q custom_components
python -m pytest -q
node --check custom_components/satellite_tracker_history/www/satellite-tracker-history-card.js
node --test tests-js/*.test.cjs
python scripts/validate_package.py
