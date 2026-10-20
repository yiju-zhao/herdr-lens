#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export CARGO_HOME="$ROOT/.toolchain/cargo"
export RUSTUP_HOME="$ROOT/.toolchain/rustup"
export PATH="$CARGO_HOME/bin:$PATH"
export ZIG="$ROOT/.toolchain/zig-aarch64-macos-0.16.0/zig"
export ZIG_GLOBAL_CACHE_DIR="$ROOT/.toolchain/zig-cache"
cd "$ROOT/vendor/herdr"
exec "$@"
