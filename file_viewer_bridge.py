"""Connect source-bound Lens paths to a dedicated, reusable Files preview."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time

from lens import FileRef, api, atomic_json, state_root


def configuration() -> dict | None:
    directory = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if not directory:
        return None
    path = Path(directory) / "file-viewer.json"
    try:
        value = json.loads(path.read_text())
        binary = Path(value["binary"])
        if binary.is_absolute() and binary.is_file() and os.access(binary, os.X_OK):
            return value
    except (OSError, ValueError, KeyError, TypeError):
        pass
    # Fresh marketplace installations have no machine-specific configuration.
    # Without Glow use Lens's built-in Markdown renderer instead of raw text.
    binary = Path(__file__).resolve().parent / "build/herdr-file-viewer-lens"
    if not path.exists() and binary.is_file() and os.access(binary, os.X_OK) and shutil.which("glow"):
        config_dir = Path(directory) / "file-viewer"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.toml"
        try:
            with config_file.open("x") as out:
                # This binary is our derivative; upstream update notices do not
                # describe its release stream. User settings remain editable.
                out.write('changed_file_view = "content"\nupdate_check = false\n')
        except FileExistsError:
            pass
        return {"binary": str(binary), "config_dir": str(config_dir)}
    return None


def preview_root(path: Path) -> Path:
    """Use the target's repository root, or its directory outside Git."""
    parent = path.parent.resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if result.returncode == 0:
            candidate = Path(result.stdout.strip()).resolve()
            if candidate.is_dir() and path.is_relative_to(candidate):
                return candidate
    except (OSError, subprocess.TimeoutExpired):
        pass
    return parent


def lease_busy(path: Path) -> bool:
    with path.open("a") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def open_preview(ref: FileRef, source: str) -> dict:
    origin = api("pane.get", {"pane_id": source})["pane"]
    root = preview_root(Path(ref.path))
    target = str(Path(ref.path).relative_to(root))
    if ref.line:
        target += f":{ref.line}"
    state = state_root()
    scope = f"{os.environ.get('HERDR_SOCKET_PATH')}|{origin['workspace_id']}|{origin['tab_id']}|{root}"
    key = "files-" + hashlib.sha256(scope.encode()).hexdigest()[:24]
    request = state / f"{key}.json"
    record = state / f"{key}.pane.json"
    lease = state / f"{key}.lease"
    with (state / f"{key}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        atomic_json(request, {"id": secrets.token_hex(16), "target": target})
        if record.exists():
            try:
                saved = json.loads(record.read_text())
                pane = api("pane.get", {"pane_id": saved["pane_id"]})["pane"]
                actual_root = Path(pane.get("foreground_cwd") or pane.get("cwd") or "/").resolve()
                if (pane["workspace_id"] == origin["workspace_id"]
                        and pane["tab_id"] == origin["tab_id"]
                        and actual_root == root and lease_busy(lease)):
                    return {"reused": True, "pane_id": pane["pane_id"], "backend": "file-viewer"}
            except (OSError, RuntimeError, KeyError, ValueError):
                pass
        result = api("plugin.pane.open", {
            "plugin_id": "eason.lens", "entrypoint": "files", "placement": "split",
            "target_pane_id": source, "direction": "right", "focus": False,
            # Host defaults the executable's cwd to the plugin root.
            "env": {"HERDR_FILE_VIEWER_ROOT": str(root), "HERDR_FILE_VIEWER_OPEN": target,
                    "HERDR_FILE_VIEWER_REQUEST_FILE": str(request),
                    "LENS_FILES_LEASE": str(lease)},
        })
        pane_id = result["plugin_pane"]["pane"]["pane_id"]
        atomic_json(record, {"pane_id": pane_id, "root": str(root)})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if lease_busy(lease):
                return result
            # A failed startup must not be reported as a successful preview.
            api("pane.get", {"pane_id": pane_id})
            time.sleep(0.05)
        raise RuntimeError("Files 预览尚未启动，请查看 Lens 插件日志。")


def run_preview() -> None:
    config = configuration()
    if not config:
        raise RuntimeError("File Viewer integration is not configured.")
    root = Path(os.environ["HERDR_FILE_VIEWER_ROOT"]).resolve()
    launch_dir = Path(__file__).resolve().parent
    env = dict(os.environ)
    env["HERDR_PLUGIN_CONFIG_DIR"] = config["config_dir"]
    # The wrapper owns the lease; close_fds prevents renderers inheriting it.
    with Path(os.environ["LENS_FILES_LEASE"]).open("a") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.chdir(root)
        result = subprocess.run([config["binary"]], env=env, cwd=launch_dir, check=False)
        if result.returncode:
            raise RuntimeError(f"File Viewer exited with code {result.returncode}")
