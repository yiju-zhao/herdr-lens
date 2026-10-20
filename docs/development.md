# Development and releases

## Local development

```sh
git clone https://github.com/yiju-zhao/herdr-lens.git
cd herdr-lens
uv sync --frozen
herdr plugin link "$PWD" --enabled
.venv/bin/python -m pytest -q
```

`plugin link` does not run build steps. `sh scripts/bootstrap.sh` installs runtime dependencies without the test group, using uv when available and Python + hash-locked pip requirements otherwise. Native File Viewer is optional; the built-in viewer works independently.

The working repository is the source of truth. Use feature branches and small commits; tag reviewed versions as `vX.Y.Z`. Keep `herdr-plugin.toml`, `pyproject.toml`, `uv.lock`, `release-assets.json` and CHANGELOG versions aligned. Export requirements after dependency changes with `uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file requirements.txt`.

## Native sources

`upstream.json` pins full Git commits; `patches/` contains all local modifications, including new source files and tests. Source checkouts and binaries live under ignored `build/`.

Install Rust 1.96.1. The companion also requires Zig 0.16.0 on PATH (or via `ZIG`) and the upstream platform build dependencies.

```sh
python3 scripts/build_native.py viewer
python3 scripts/build_native.py client
```

To inspect/test before compiling:

```sh
python3 scripts/build_native.py viewer --prepare-only
cd build/sources/viewer
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
```

The `Build native viewer` Actions workflow runs these checks and produces macOS ARM64/Linux x86_64 build artifacts on manual dispatch. Artifacts are candidates, not automatically published releases. The regular `Tests` workflow checks the Python layer on macOS and Linux for pushes and pull requests.

The Herdr companion patch changes only client click handling and associated tests; it uses the existing server protocol. Run `cargo test --locked --bin herdr client::shell` in its source checkout, plus the local PTY journeys below. Never claim another Herdr version compatible merely because it compiles.

Zig's pinned translate-c dependency can be fetched from its exact GitHub mirror if Codeberg is unavailable: `moderatelyConfused/translate-c` at `4e879eb8aba615de112eabd1231ea6e01920cead`. Its required Zig content hash is `translate_c-0.0.0-Q_BUWhVNBwDOEcIqub4VFPJPB6D9dgwzUMHTX5KWr8Xr`; do not change the hash or vendor code to bypass verification.

The legacy `scripts/toolchain.sh` helpers are conveniences for the original isolated local toolchain. Fresh clones should use the commands above.

## Native runtime configuration

Fresh installations locate the native viewer relative to the plugin root; no personal path is stored in the package. Its renderer config is created under `HERDR_PLUGIN_CONFIG_DIR/file-viewer/config.toml`. Missing Glow uses Lens's built-in Markdown renderer. Upstream update notices are disabled for the derivative because they do not describe this release stream.

For development, `HERDR_PLUGIN_CONFIG_DIR/file-viewer.json` can explicitly set an absolute `binary` and a `config_dir`. Remove that override to return to packaged defaults. See the File Viewer patch's `docs/external-open.md` for the private, atomic file-open request protocol.

## End-to-end validation

`tests/smoke_markdown_preview.py` opens and cleans up its own named Herdr session. It requires the built native components, `build/launcher.json`, and Glow; it does not interact with existing agent panes. `HERDR_TEST_BIN` can name the original Herdr binary. The test checks relative paths, absolute Unicode/spaced paths, repeat-open process reuse, and unchanged source terminal identity.

The initial macOS verification covered 343 Herdr client tests, 1,650 File Viewer tests, and real PTY click journeys. The native dependency audit had no vulnerability entries and two inherited informational unsoundness advisories (`RUSTSEC-2026-0190`, `RUSTSEC-2026-0253`); these are not a claim of a warning-free audit.

## Release

1. Run Python tests and relevant native checks. Validate patches against the exact pinned base.
2. Build supported native binaries; upload no local configuration, state, virtual environments or toolchains.
3. Record each binary's SHA-256 in `release-assets.json`. Include upstream/dependency license notices with release assets.
4. Commit, push `main`, wait for CI, tag `vX.Y.Z`, and create a GitHub Release with the matching assets and CHANGELOG entry.
5. Test `herdr plugin install yiju-zhao/herdr-lens --ref vX.Y.Z` in an isolated Herdr config. Test the opt-in companion separately.
6. Add the `herdr-plugin` topic. The Herdr marketplace indexes valid public non-fork repositories automatically, normally every 30 minutes. Verify actual appearance separately; topic submission is not proof of indexing.

The initial native assets support macOS Apple Silicon. Other platforms keep the built-in viewer until a verified binary is added. Marketplace installation never silently replaces the host client or installs the companion shim; enabling arbitrary text clicks is a separate, explicit setup action.
