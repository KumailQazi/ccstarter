#!/usr/bin/env bash
# Runs everything that needs no internet. Safe in a classroom with bad wifi.
set -euo pipefail
cd "$(dirname "$0")"
PY=""
if [[ -f ".venv/bin/python" ]]; then
    PY=".venv/bin/python"
elif [[ -f "../../.venv/bin/python" ]]; then
    PY="../../.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    echo "Python not found" >&2
    exit 1
fi

"$PY" -m unittest discover -s tests -p 'test_*.py' -v
