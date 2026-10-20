#!/bin/sh
# Herdr invokes this in a fresh managed checkout; never change shell or host config.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
if command -v uv >/dev/null 2>&1; then
    uv sync --frozen --no-dev
else
    PYTHON=""
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1 &&
            "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>/dev/null; then
            PYTHON=$candidate
            break
        fi
    done
    if [ -z "$PYTHON" ]; then
        echo 'Herdr Lens needs uv or Python 3.11+. Install uv, then retry herdr plugin install.' >&2
        exit 1
    fi
    "$PYTHON" -m venv .venv
    .venv/bin/python -m pip install --require-hashes -r requirements.txt
fi
"$ROOT/.venv/bin/python" "$ROOT/scripts/assets.py" viewer --optional
