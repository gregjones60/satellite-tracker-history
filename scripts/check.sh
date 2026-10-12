#!/usr/bin/env bash
set -euo pipefail
python -m compileall -q custom_components
python -m pytest -q
node --check custom_components/spot_trace_history/www/spot-trace-history-card.js
node --test tests-js/*.test.cjs
python scripts/validate_package.py
