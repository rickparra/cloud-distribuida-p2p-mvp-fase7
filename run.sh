#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3.13}"
if [ ! -x .venv/bin/python ]; then
    "$PYTHON_BIN" -m venv .venv
fi
./.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
exec ./.venv/bin/python launch.py
