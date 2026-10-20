"""Opt in to the version-matched Ctrl+click companion without replacing Herdr."""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

from assets import fetch


def install(root: Path, managed: bool) -> None:
    home = Path.home()
    runtime = home / ".local/share/herdr-lens/runtime" if managed else root
    launchers = [home / ".local/bin" / name for name in ("herdr", "herdr-lens")]
    previous = None
    for launcher in launchers:
        if launcher.exists() or launcher.is_symlink():
            target = launcher.resolve()
            if target not in {root / "herdr-lens", runtime / "herdr-lens"}:
                raise SystemExit(f"Refusing to replace another launcher: {launcher}")
            config_path = target.parent / "build/launcher.json"
            if config_path.exists():
                previous = json.loads(config_path.read_text())
    upstream = (previous or {}).get("upstream") or os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr")
    if not upstream or Path(upstream).resolve() in {p.resolve() for p in launchers}:
        raise SystemExit("Cannot locate the original Herdr installation.")
    version = subprocess.check_output([upstream, "--version"], text=True).strip()
    if version != "herdr 0.9.3":
        raise SystemExit(f"Ctrl+click companion supports Herdr 0.9.3; found {version}. Ordinary preview still works.")
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    config = config_home / "herdr/config.toml"
    text = config.read_text() if config.exists() else ""
    commands = tomllib.loads(text).get("keys", {}).get("command", [])
    if any(c.get("key") == "prefix+f" and c.get("command") != "eason.lens.open" for c in commands):
        raise SystemExit("prefix+f is already bound; installation stopped without replacing it.")
    client = root / "build/herdr-lens-client"
    if not client.exists():
        client = fetch("client", root)
    if not client:
        raise SystemExit("No prebuilt Ctrl+click companion for this platform. See docs/development.md.")
    client_version = subprocess.check_output([str(client), "--version"], text=True).strip()
    if client_version != version:
        raise SystemExit(f"Client and installed Herdr versions differ: {client_version} / {version}")
    if not managed:
        subprocess.run([upstream, "plugin", "link", str(root), "--enabled"], check=True)
    if not any(c.get("command") == "eason.lens.open" and c.get("description") == "Lens: preview file"
               for c in commands):
        if any(c.get("key") == "prefix+f" for c in commands):
            raise SystemExit('Set the existing Lens shortcut description to "Lens: preview file" and retry.')
        updated = text.rstrip() + '''

# Herdr Lens: Ctrl+b, then f previews the selected file path.
[[keys.command]]
key = "prefix+f"
type = "plugin_action"
command = "eason.lens.open"
description = "Lens: preview file"
'''
        tomllib.loads(updated)
        config.parent.mkdir(parents=True, exist_ok=True)
        if config.exists():
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(config, config.with_name(f"config.toml.before-lens-{stamp}"))
        config.write_text(updated)
    (runtime / "build").mkdir(parents=True, exist_ok=True)
    if managed:
        for filename in ("herdr-lens", "launcher.py"):
            shutil.copy2(root / filename, runtime / filename)
        pending = runtime / "build/.herdr-lens-client-new"
        shutil.copy2(client, pending)
        os.replace(pending, runtime / "build/herdr-lens-client")
    (runtime / "build/launcher.json").write_text(json.dumps({"upstream": upstream, "version": version}) + "\n")
    os.chmod(runtime / "herdr-lens", 0o755)
    for launcher in launchers:
        launcher.parent.mkdir(parents=True, exist_ok=True)
        if launcher.is_symlink():
            launcher.unlink()
        launcher.symlink_to(runtime / "herdr-lens")
    subprocess.run([upstream, "server", "reload-config"], check=False)
    print("Installed the Ctrl+click companion. Keep ~/.local/bin first in PATH; open a new terminal and run herdr.")
    print("Existing server and agent sessions are preserved; package-manager Herdr was not replaced.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--managed", action="store_true", help="Keep GitHub plugin registration; install a stable companion copy")
    args = parser.parse_args()
    install(Path(__file__).resolve().parent.parent, args.managed)
