"""Prove normal `herdr` starts a new server and opens paths without setup steps."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
import secrets
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import tempfile
import time

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--markdown", action="store_true")
args = parser.parse_args()
upstream = json.loads((root / "build/launcher.json").read_text())["upstream"]
launcher = os.environ.get("HERDR_TEST_LAUNCHER", str(root / "herdr-lens"))
session = "lens-launch-" + secrets.token_hex(3)
source_dir = tempfile.TemporaryDirectory(prefix="lens-user-project-")
shutil.copytree(root / "examples", Path(source_dir.name) / "examples")
if args.markdown:
    documents = Path(source_dir.name) / "docs"
    documents.mkdir()
    (documents / "first.md").write_text("# Relative document\n\nMD_RELATIVE_PREVIEW_OK\n")
    (documents / "中文 空格.md").write_text("# Absolute document\n\nMD_ABSOLUTE_PREVIEW_OK\n")
env = dict(os.environ)
for key in ("HERDR_ENV", "HERDR_SOCKET_PATH", "HERDR_CLIENT_SOCKET_PATH",
            "HERDR_PANE_ID", "HERDR_WORKSPACE_ID", "HERDR_TAB_ID", "HERDR_SESSION", "HERDR_LENS"):
    env.pop(key, None)
env.update(TERM="xterm-256color", COLORTERM="truecolor",
           XDG_STATE_HOME=str(root / "build/launch-test-state"))
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 44, 160, 0, 0))
client = subprocess.Popen([launcher, "--session", session], env=env, stdin=slave,
                          stdout=slave, stderr=slave, start_new_session=True)
os.close(slave)
started = False
try:
    deadline = time.monotonic() + 15
    status = {}
    while time.monotonic() < deadline:
        if select.select([master], [], [], 0.1)[0]:
            os.read(master, 65536)
        check = subprocess.run([upstream, "--session", session, "status", "--json"],
                               env=env, text=True, capture_output=True)
        if check.returncode == 0:
            status = json.loads(check.stdout)
            if status["server"]["running"]:
                started = True
                break
    assert started, f"Normal herdr did not start the server: {status}"
    print("PASS normal herdr starts a new named session automatically", flush=True)
    created = json.loads(subprocess.check_output(
        [upstream, "--session", session, "workspace", "create", "--cwd", source_dir.name, "--label", "Lens Launch Test"],
        env=env, text=True))["result"]
    pane = created["root_pane"]["pane_id"]
    client.send_signal(signal.SIGTERM)
    client.wait(timeout=5)
    subprocess.run([sys.executable, str(root / "tests/smoke_client.py"),
                    "--launcher", launcher, "--session", session,
                    "--socket", status["server"]["socket"], "--pane", pane,
                    *(["--markdown"] if args.markdown else [])],
                   env={**env, "PYTHONPATH": str(root)}, check=True)
    print("PASS normal herdr enables Lens without a separate command or environment flag", flush=True)
finally:
    if client.poll() is None:
        client.terminate()
        client.wait(timeout=5)
    os.close(master)
    if started:
        subprocess.run([upstream, "--session", session, "server", "stop"], env=env, check=True)
        subprocess.run([upstream, "session", "delete", session], env=env, check=True)
    source_dir.cleanup()
