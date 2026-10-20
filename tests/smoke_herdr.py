"""Live smoke test; requires an explicitly supplied disposable Herdr pane."""
import argparse
import json
import os
from pathlib import Path
import time
from lens import api

parser = argparse.ArgumentParser()
parser.add_argument("--socket", required=True)
parser.add_argument("--pane", required=True)
args = parser.parse_args()
os.environ["HERDR_SOCKET_PATH"] = args.socket
root = Path(__file__).resolve().parent.parent
source = api("pane.get", {"pane_id": args.pane})["pane"]
context = {"focused_pane_id": args.pane, "workspace_id": source["workspace_id"],
           "focused_pane_cwd": str(root), "workspace_cwd": str(root)}
viewer_ids = []
for raw in ["examples/欢迎使用 Lens.md", "examples/demo.py:8", "examples/report.html", "missing.md", "examples/欢迎使用 Lens.md"]:
    result = api("plugin.action.invoke", {"plugin_id": "eason.lens", "action_id": "open",
                 "context": {**context, "clicked_url": raw}})
    log_id = result["log"]["log_id"]
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        logs = api("plugin.log.list", {"plugin_id": "eason.lens", "limit": 20})["logs"]
        log = next(item for item in logs if item["log_id"] == log_id)
        if log["status"] != "running":
            break
        time.sleep(0.1)
    assert log["status"] == "succeeded", log
    payload = json.loads(log["stdout"])
    viewer_id = payload.get("pane_id") or payload["plugin_pane"]["pane"]["pane_id"]
    viewer_ids.append(viewer_id)
    time.sleep(0.7)
    rendered = api("pane.read", {"pane_id": viewer_id, "source": "visible", "lines": 50})
    text = rendered["read"]["text"]
    if raw == "missing.md":
        assert "文件不存在" in text, text
    elif raw.endswith(":8"):
        assert "return" in text and "8" in text, text
    elif raw.endswith(".html"):
        assert "doctype" in text, text
    else:
        assert "Herdr Lens" in text, text
    print(f"PASS {raw} -> {viewer_id}")
assert len(set(viewer_ids)) == 1, viewer_ids
assert api("pane.get", {"pane_id": args.pane})["pane"]["terminal_id"] == source["terminal_id"]
print("PASS pane reuse and source terminal identity")
