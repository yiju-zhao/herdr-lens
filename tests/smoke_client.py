"""Drive only a disposable Lens CLI PTY, without desktop input automation."""
import argparse
import codecs
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shlex
import signal
import struct
import subprocess
import sys
import termios
import time

import pyte
from wcwidth import wcswidth
from lens import api

parser = argparse.ArgumentParser()
parser.add_argument("--session", required=True)
parser.add_argument("--socket", required=True)
parser.add_argument("--pane", required=True)
parser.add_argument("--launcher", help="Test the installed normal herdr entry point")
parser.add_argument("--markdown", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
os.environ["HERDR_SOCKET_PATH"] = args.socket
stock = os.environ.get("HERDR_TEST_BIN") or json.loads((root / "build/launcher.json").read_text())["upstream"]
cli_env = dict(os.environ)
cli_env.pop("HERDR_SOCKET_PATH", None)
cli_env.pop("HERDR_CLIENT_SOCKET_PATH", None)
def cli(*commands):
    return subprocess.run([stock, "--session", args.session, *commands], env=cli_env,
                          capture_output=True, text=True, check=True)
source = api("pane.get", {"pane_id": args.pane})["pane"]
cli("workspace", "focus", source["workspace_id"])
emitter = root / ("examples/emit_markdown_paths.py" if args.markdown else "examples/emit_paths.py")
emit_command = f"{shlex.quote(sys.executable)} {shlex.quote(str(emitter))}"
if args.markdown:
    emit_command += " " + shlex.quote(source["cwd"])
cli("pane", "run", args.pane, emit_command)
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 44, 160, 0, 0))
env = {**cli_env, "TERM": "xterm-256color", "COLORTERM": "truecolor"}
if args.launcher:
    env.pop("HERDR_LENS", None)
else:
    env["HERDR_LENS"] = "1"
# Named servers still share the user's saved machine selection. Isolate all
# client state so a smoke test cannot auto-connect to a real remote machine.
env["XDG_STATE_HOME"] = str(root / "build/client-test-state")
env["HERDR_LOG"] = "herdr=info,herdr::client::shell::lens=debug"
env.pop("HERDR_ENV", None)
env.pop("HERDR_PANE_ID", None)
process = subprocess.Popen([args.launcher or str(root / "build/herdr-lens-client"), "--session", args.session],
                           stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
os.close(slave)
class TestScreen(pyte.Screen):
    def report_device_status(self, mode, **kwargs):
        if not kwargs:
            super().report_device_status(mode)

    def write_process_input(self, data):
        os.write(master, data.encode())

screen = TestScreen(160, 44)
stream = pyte.Stream(screen)
decode = codecs.getincrementaldecoder("utf-8")("replace")
raw_output = bytearray()
last_click_ms = 0
def pump(duration=0.1):
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        if select.select([master], [], [], min(0.05, max(0, deadline-time.monotonic())))[0]:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            raw_output.extend(chunk)
            stream.feed(decode.decode(chunk))
def click(text):
    global last_click_ms
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        pump()
        for y, row in enumerate(screen.display):
            if text in row:
                x = wcswidth(row[:row.index(text)]) + 2
                last_click_ms = int(time.time() * 1000) - 5
                os.write(master, f"\x1b[<16;{x+1};{y+1}M\x1b[<16;{x+1};{y+1}m".encode())
                return
    raise AssertionError(f"Text not visible: {text}\n" + "\n".join(screen.display))
def wait_preview(expected):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        pump()
        logs = api("plugin.log.list", {"plugin_id": "eason.lens", "limit": 10})["logs"]
        for log in logs:
            if log["status"] != "succeeded" or log["started_unix_ms"] < last_click_ms:
                continue
            payload = json.loads(log["stdout"])
            viewer = payload.get("pane_id") or payload.get("plugin_pane", {}).get("pane", {}).get("pane_id")
            if not viewer:
                continue
            try:
                text = api("pane.read", {"pane_id": viewer, "source": "visible", "lines": 50})["read"]["text"]
            except RuntimeError:
                continue
            if expected in text:
                return viewer
    raise AssertionError("Preview not opened: " + expected + "\n" + "\n".join(screen.display))
try:
    pump(1.5)
    if args.markdown:
        click("docs/first.md")
        viewer = wait_preview("MD_RELATIVE_PREVIEW_OK")
        identity = api("pane.process_info", {"pane_id": viewer})["process_info"]
        def viewer_pids(info):
            return {p["pid"] for p in info["foreground_processes"]
                    if "file-viewer" in (p.get("argv0") or p["name"])}
        before_pids = viewer_pids(identity)
        assert before_pids, identity
        print("PASS relative Markdown path -> rendered Files preview", flush=True)
        cli("pane", "run", args.pane, emit_command)
        pump(1)
        click("空格.md")
        second = wait_preview("MD_ABSOLUTE_PREVIEW_OK")
        assert second == viewer, (viewer, second)
        print("PASS absolute Unicode/spaced/wrapped Markdown path -> same Files pane", flush=True)
        cli("pane", "run", args.pane, emit_command)
        pump(1)
        click("./docs/first.md")
        third = wait_preview("MD_RELATIVE_PREVIEW_OK")
        assert third == viewer
        after = api("pane.process_info", {"pane_id": viewer})["process_info"]
        assert before_pids == viewer_pids(after), (identity, after)
        print("PASS repeated relative path reuses the existing preview process", flush=True)
    else:
        click("examples/demo.py:8")
        viewer = wait_preview("return {")
        print("PASS actual Ctrl+click -> source code at line 8")
        cli("pane", "run", args.pane, emit_command)
        pump(1)
        click("Lens.md")
        wait_preview("这是从磁盘读取的真实")
        print("PASS Ctrl+click quoted Chinese path with spaces across soft wraps")
    assert api("pane.get", {"pane_id": args.pane})["pane"]["terminal_id"] == source["terminal_id"]
    print("PASS source terminal identity preserved")
finally:
    (root / "build/client-smoke-screen.txt").write_text("\n".join(screen.display))
    (root / "build/client-smoke.ansi").write_bytes(raw_output)
    # Terminate only the client process created by this test; the server stays up.
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    os.close(master)
