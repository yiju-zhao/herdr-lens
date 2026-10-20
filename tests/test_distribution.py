"""Distribution boundaries: integrity, first install, upgrades, and conflicts."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import assets
import file_viewer_bridge as bridge

ROOT = Path(__file__).resolve().parent.parent


def test_download_rejects_changed_bytes_and_keeps_existing_binary(tmp_path, monkeypatch):
    manifest = {"repository": "test/repo", "tag": "v1", "platforms": {
        "test": {"viewer": {"filename": "viewer", "asset": "viewer-test",
                            "sha256": hashlib.sha256(b"expected").hexdigest()}}}}
    (tmp_path / "release-assets.json").write_text(json.dumps(manifest))
    (tmp_path / "build").mkdir()
    binary = tmp_path / "build/viewer"
    binary.write_bytes(b"previous")
    monkeypatch.setattr(assets, "platform_key", lambda: "test")
    monkeypatch.setattr(assets.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"tampered"))
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        assets.fetch("viewer", tmp_path)
    assert binary.read_bytes() == b"previous"
    assert not list((tmp_path / "build").glob(".download-*"))
    monkeypatch.setattr(assets.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"expected"))
    assert assets.fetch("viewer", tmp_path) == binary
    assert binary.read_bytes() == b"expected"
    assert os.access(binary, os.X_OK)
    monkeypatch.setattr(assets.urllib.request, "urlopen", lambda *a, **k: pytest.fail("cached binary downloaded again"))
    assert assets.fetch("viewer", tmp_path) == binary


def fixture_install(tmp_path, version="0.9.3"):
    package = tmp_path / "package"
    package.mkdir()
    shutil.copytree(ROOT / "scripts", package / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ["herdr-lens", "launcher.py"]:
        shutil.copy2(ROOT / name, package / name)
    (package / "build").mkdir()
    client = package / "build/herdr-lens-client"
    client.write_text('#!/bin/sh\necho "herdr 0.9.3"\n')
    client.chmod(0o755)
    upstream = tmp_path / "stock-herdr"
    upstream.write_text(f'#!/bin/sh\nif [ "$1" = --version ]; then echo "herdr {version}"; fi\n')
    upstream.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
           "HERDR_BIN_PATH": str(upstream)}
    return package, home, env


def invoke_install(package, env):
    return subprocess.run([sys.executable, str(package / "scripts/install.py"), "--managed"],
                          env=env, capture_output=True, text=True)


def test_managed_companion_survives_package_cleanup_and_repeat_install(tmp_path):
    package, home, env = fixture_install(tmp_path)
    result = invoke_install(package, env)
    assert result.returncode == 0, result.stderr
    result = invoke_install(package, env)
    assert result.returncode == 0, result.stderr
    config = home / ".config/herdr/config.toml"
    assert config.read_text().count('command = "eason.lens.open"') == 1
    shim = home / ".local/bin/herdr"
    assert shim.resolve() == home / ".local/share/herdr-lens/runtime/herdr-lens"
    shutil.rmtree(package)
    result = subprocess.run([str(shim)], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "herdr 0.9.3"


def test_newer_host_refused_before_config_or_shim_changes(tmp_path):
    package, home, env = fixture_install(tmp_path, "0.9.5")
    result = invoke_install(package, env)
    assert result.returncode != 0
    assert "supports Herdr 0.9.3" in result.stderr
    assert not (home / ".config").exists()
    assert not (home / ".local").exists()


def test_existing_shortcut_is_preserved(tmp_path):
    package, home, env = fixture_install(tmp_path)
    config = home / ".config/herdr/config.toml"
    config.parent.mkdir(parents=True)
    original = '[[keys.command]]\nkey = "prefix+f"\ncommand = "other.open"\n'
    config.write_text(original)
    result = invoke_install(package, env)
    assert result.returncode != 0
    assert "already bound" in result.stderr
    assert config.read_text() == original
    assert not (home / ".local").exists()


def test_packaged_viewer_needs_no_absolute_override_and_falls_back_without_glow(tmp_path, monkeypatch):
    plugin = tmp_path / "plugin"
    (plugin / "build").mkdir(parents=True)
    binary = plugin / "build/herdr-file-viewer-lens"
    binary.write_bytes(b"binary")
    binary.chmod(0o755)
    config_dir = tmp_path / "config"
    monkeypatch.setattr(bridge, "__file__", str(plugin / "file_viewer_bridge.py"))
    monkeypatch.setenv("HERDR_PLUGIN_CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(bridge.shutil, "which", lambda _: None)
    assert bridge.configuration() is None
    monkeypatch.setattr(bridge.shutil, "which", lambda _: "/tools/glow")
    config = bridge.configuration()
    assert config["binary"] == str(binary)
    assert config["config_dir"] == str(config_dir / "file-viewer")
    renderer_config = Path(config["config_dir"]) / "config.toml"
    renderer_config.write_text('changed_file_view = "diff"\n')
    bridge.configuration()
    assert renderer_config.read_text() == 'changed_file_view = "diff"\n'
