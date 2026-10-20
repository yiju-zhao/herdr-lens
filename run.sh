#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "${1:-}" = setup-clicks ]; then
    shift
    exec "$ROOT/.venv/bin/python" "$ROOT/scripts/install.py" --managed "$@"
fi
exec "$ROOT/.venv/bin/python" "$ROOT/lens.py" "$@"
