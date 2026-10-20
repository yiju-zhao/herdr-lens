# Herdr Lens

Preview files mentioned by Claude Code, Codex, or any terminal agent inside [Herdr](https://herdr.dev/).

Absolute paths, relative paths, quoted paths with spaces, and `file://` links resolve against the source pane's working directory. Repeated previews reuse a dedicated pane. Files are read-only.

## Install

Requires **Herdr 0.9.3+** and **uv or Python 3.11+**. macOS and Linux are supported by the Python plugin; Windows is not supported.

```sh
herdr plugin install yiju-zhao/herdr-lens
```

The install step creates an isolated Python environment and installs locked dependencies. On Apple Silicon Macs it also downloads the checksum-verified native File Viewer. If `glow` is on PATH, Markdown uses that viewer; otherwise the built-in Markdown renderer works without external renderers.

Open the Herdr command palette and choose **Lens: preview selected path / enter a path**. Select a path first, or type one into the preview's path field. Explicit terminal `file://` hyperlinks support Ctrl+click on stock Herdr with mouse capture enabled.

The [Herdr marketplace](https://herdr.dev/plugins/) is a discovery index. Installation uses the command above; it does not synchronize plugins between devices. For a fixed version add `--ref v0.1.0`.

## Ctrl+click ordinary paths

**Clicking bare text such as `docs/plan.md` needs the optional companion client. A marketplace plugin alone cannot intercept arbitrary text clicks.**

The first prebuilt companion supports **macOS Apple Silicon + Herdr 0.9.3**. On that combination, after installing Lens:

```sh
herdr plugin action invoke eason.lens.setup-clicks
```

This installs a version-matched companion under `~/.local/share/herdr-lens/runtime`, creates `~/.local/bin/herdr` and `herdr-lens` shims, and adds the `prefix+f` action after checking for conflicts. It preserves the package-manager Herdr binary and running sessions. Keep `~/.local/bin` first in PATH, then open a new terminal and run `herdr`. Hold **Control** and click a file path. macOS also uses Control, not Command.

On newer Herdr versions, normal plugin previews remain available; the companion refuses to replace a different version. If you later upgrade Herdr, the shim automatically forwards to the new original binary until a matching companion is released. Check `herdr plugin log list --plugin eason.lens` if setup reports an error.

For the native Markdown viewer on macOS, optionally install its renderers:

```sh
brew install glow git-delta bat
```

| Device | Installable plugin preview | Bare-path Ctrl+click |
| --- | --- | --- |
| macOS Apple Silicon | Yes; end-to-end verified | Optional prebuilt companion, Herdr 0.9.3 only |
| macOS Intel / Linux | Python preview; automated checks on Linux | Source build required; not end-to-end verified |
| Windows | Not supported | Not supported |

## Preview controls

The native Markdown viewer is based on [smarzban/herdr-file-viewer](https://github.com/smarzban/herdr-file-viewer): `v` toggles rendered/source content, `z` toggles the tree, `/` searches, `q`/Esc returns or exits. Clicks within the same source tab and project reuse its process. New opens wait while a modal is editing input; saved in-session annotations and pins remain. Manually opened upstream Files panes are independent.

The built-in viewer uses `s` for rendered/source, `/` to enter a path, `r` to refresh, `w` to toggle watching, `b` for an external viewer, and `q` to close. It renders Markdown, code, JSON and directories. HTML is shown as source; `b` opens HTML, PDF or images in the local browser/default viewer. Built-in text reads are capped at 4 MiB.

Relative paths use the pane's **current** directory, so use absolute paths for old output after changing directories. The plugin runs on the machine containing the files; remote-to-local browser forwarding is not implemented. Bare-path detection reads up to eight terminal rows either side of the click; select very long paths and invoke the action instead.

## Optional shortcut

Without the companion, you can add this to your Herdr `config.toml` (choose a free key):

```toml
[[keys.command]]
key = "prefix+f"
type = "plugin_action"
command = "eason.lens.open"
description = "Lens: preview file"
```

Then run `herdr server reload-config`. The default prefix is Ctrl+b.

## Development and updates

See [development and release workflow](docs/development.md), [upstream pins](upstream.json), and [changelog](CHANGELOG.md). Source changes live in this repository; the two native components are pinned upstream sources plus reviewable patches. No sibling checkout or personal filesystem path is required.

Herdr versions with `plugin update` can run `herdr plugin update yiju-zhao/herdr-lens`. On 0.9.3, repeat `herdr plugin install yiju-zhao/herdr-lens` to reinstall. A pinned `--ref` stays pinned; install the newer tag explicitly. A locally linked development copy must be unlinked before switching to GitHub installation.

To remove the plugin, run `herdr plugin uninstall eason.lens`. If you enabled the companion, remove only its two symlinks from `~/.local/bin`, its `~/.local/share/herdr-lens/runtime` directory, and the Lens shortcut block from Herdr config. Open a new terminal to use the original Herdr again.

MIT for original Lens code. Native derivatives retain their upstream licenses; see [third-party notices](THIRD-PARTY-NOTICES.md). This is an independent project.
