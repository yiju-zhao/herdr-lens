import json
import os
from pathlib import Path

import file_viewer_bridge as bridge
import lens


def test_absolute_and_relative_markdown_paths_use_the_source_directory(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / "docs").mkdir(parents=True)
    target = project / "docs" / "设计 文档.md"
    target.write_text("# real document")
    monkeypatch.setenv("HERDR_PLUGIN_CONTEXT_JSON", json.dumps({
        "focused_pane_id": "w1:p1", "workspace_id": "w1", "focused_pane_cwd": str(project),
    }))
    monkeypatch.setattr(bridge, "configuration", lambda: {"binary": "/not-used"})
    opened = []
    monkeypatch.setattr(bridge, "open_preview", lambda ref, source: opened.append((ref, source)) or {"ok": True})
    for path in [str(target), "./docs/设计 文档.md", "`docs/设计 文档.md`"]:
        assert lens.open_action(path) == {"ok": True}
    assert {item[0].path for item in opened} == {str(target)}
    assert {item[0].cwd for item in opened} == {str(project)}
    assert {item[1] for item in opened} == {"w1:p1"}


def test_reuses_only_owned_viewer_in_same_project_and_source_tab(tmp_path, monkeypatch):
    project = (tmp_path / "project").resolve()
    project.mkdir()
    first = project / "a.md"
    second = project / "b.md"
    first.write_text("first")
    second.write_text("second")
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(bridge, "state_root", lambda: state)
    monkeypatch.setattr(bridge, "preview_root", lambda path: project)
    monkeypatch.setattr(bridge, "lease_busy", lambda path: True)
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/test/socket")
    source = {"pane_id": "w1:p1", "workspace_id": "w1", "tab_id": "w1:t1"}
    viewers = {}
    launches = []

    def api(method, params):
        if method == "pane.get":
            return {"pane": source if params["pane_id"] == source["pane_id"] else viewers[params["pane_id"]]}
        assert method == "plugin.pane.open"
        assert "cwd" not in params
        launches.append(params)
        pane_id = f"test-viewer-{len(launches)}"
        viewers[pane_id] = {"pane_id": pane_id, "workspace_id": source["workspace_id"],
                            "tab_id": source["tab_id"], "foreground_cwd": str(project)}
        return {"plugin_pane": {"pane": viewers[pane_id]}}

    monkeypatch.setattr(bridge, "api", api)
    first_result = bridge.open_preview(lens.resolve(str(first), str(project)), source["pane_id"])
    reused = bridge.open_preview(lens.resolve("b.md", str(project)), source["pane_id"])
    assert reused["reused"]
    assert reused["pane_id"] == first_result["plugin_pane"]["pane"]["pane_id"]
    assert len(launches) == 1
    request_path = Path(launches[0]["env"]["HERDR_FILE_VIEWER_REQUEST_FILE"])
    assert json.loads(request_path.read_text())["target"] == "b.md"
    source["tab_id"] = "w1:t2"
    bridge.open_preview(lens.resolve(str(first), str(project)), source["pane_id"])
    assert len(launches) == 2
    assert launches[0]["env"]["HERDR_FILE_VIEWER_REQUEST_FILE"] != launches[1]["env"]["HERDR_FILE_VIEWER_REQUEST_FILE"]
