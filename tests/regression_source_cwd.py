"""Real Herdr regression: preview must survive when opened outside the plugin repo."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

from lens import api

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--plugin-cwd", action="store_true", help="Control case: use plugin repo as source cwd")
args = parser.parse_args()
stock = "/opt/homebrew/bin/herdr"
session = "lens-cwd-" + secrets.token_hex(3)
env = dict(os.environ)
for key in ("HERDR_SOCKET_PATH", "HERDR_CLIENT_SOCKET_PATH", "HERDR_SESSION",
            "HERDR_PANE_ID", "HERDR_WORKSPACE_ID", "HERDR_TAB_ID"):
    env.pop(key, None)
env["XDG_STATE_HOME"] = str(root / "build/cwd-regression-state")
server = subprocess.Popen([stock, "--session", session, "server"], env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
started = False
try:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        status = subprocess.run([stock, "--session", session, "status", "--json"],
                                env=env, text=True, capture_output=True)
        if status.returncode == 0:
            data = json.loads(status.stdout)
            if data["server"]["running"]:
                socket_path = data["server"]["socket"]
                os.environ["HERDR_SOCKET_PATH"] = socket_path
                started = True
                break
        time.sleep(0.05)
    assert started, "test server failed to start"
    with tempfile.TemporaryDirectory(prefix="lens-outside-repo-") as directory:
        source_cwd = str(root) if args.plugin_cwd else directory
        fixture = Path(directory) / "实际预览.md"
        fixture.write_text("# Preview survives\n\nOpened from another project.\n")
        created = json.loads(subprocess.check_output(
            [stock, "--session", session, "workspace", "create", "--cwd", source_cwd,
             "--label", "Lens CWD regression", "--no-focus"], env=env, text=True))["result"]
        source = created["root_pane"]
        result = api("plugin.action.invoke", {"plugin_id": "eason.lens", "action_id": "open",
            "context": {"workspace_id": source["workspace_id"], "focused_pane_id": source["pane_id"],
                        "focused_pane_cwd": source_cwd, "workspace_cwd": source_cwd,
                        "clicked_url": str(fixture)}})
        log_id = result["log"]["log_id"]
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            log = next(item for item in api("plugin.log.list", {"plugin_id": "eason.lens", "limit": 5})["logs"]
                       if item["log_id"] == log_id)
            if log["status"] != "running":
                break
            time.sleep(0.05)
        assert log["status"] == "succeeded", log
        opened = json.loads(log["stdout"])
        viewer_id = opened["plugin_pane"]["pane"]["pane_id"]
        time.sleep(0.5)
        try:
            output = api("pane.read", {"pane_id": viewer_id, "source": "visible", "lines": 45})["read"]["text"]
        except RuntimeError as error:
            lines = (Path(socket_path).parent / "herdr-server.log").read_text().splitlines()
            for line in lines:
                if 'pane child exited' in line:
                    print(line, flush=True)
            raise AssertionError("FAIL: preview pane appeared then exited before showing the file") from error
        assert "Preview survives" in output, output
        assert api("pane.get", {"pane_id": source["pane_id"]})["pane"]["terminal_id"] == source["terminal_id"]
        print("PASS: real preview stays open; source terminal preserved; cwd=" +
              ("plugin repo (control)" if args.plugin_cwd else "outside plugin repo"))
finally:
    if started:
        subprocess.run([stock, "--session", session, "server", "stop"], env=env, check=True)
        subprocess.run([stock, "session", "delete", session], env=env, check=True)
    if server.poll() is None:
        server.terminate()
    server.wait(timeout=5)
