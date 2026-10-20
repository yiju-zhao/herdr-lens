#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export CARGO_HOME="$ROOT/.toolchain/cargo"
export RUSTUP_HOME="$ROOT/.toolchain/rustup"
export RUSTUP_TOOLCHAIN=1.96.1
export PATH="$CARGO_HOME/bin:$PATH"
cd "$ROOT/../herdr-file-viewer"
exec "$@"
