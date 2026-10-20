import json
import os
from pathlib import Path

import pytest

from lens import MAX_BYTES, FileRef, atomic_json, read_file, resolve
from viewer import LensApp


def test_source_directory_and_literal_punctuation(tmp_path):
    directory = tmp_path / "中文 空格"
    directory.mkdir()
    target = directory / "a(b)#c.md"
    target.write_text("# hi")
    ref = resolve("`中文 空格/a(b)#c.md`", str(tmp_path))
    assert ref.path == str(target)
    assert resolve(f"[link]({target})", "/").path == str(target)
    assert resolve(target.as_uri(), "/").path == str(target)


def test_lines_url_and_existing_colon_name(tmp_path):
    assert resolve("src/x.py:42:8", str(tmp_path)).line == 42
    assert resolve("src/x.py:42:8", str(tmp_path)).column == 8
    assert resolve("src/x.py#L42C8", str(tmp_path)).column == 8
    ref = resolve((tmp_path / "报告.md").as_uri() + "#L7C3", "/")
    assert (ref.line, ref.column) == (7, 3)
    literal = tmp_path / "x:42"
    literal.touch()
    assert resolve("x:42", str(tmp_path)).line is None
    with pytest.raises(ValueError):
        resolve("x.py:0", str(tmp_path))


def test_no_shell_expansion_or_cross_host_resolution(tmp_path):
    ref = resolve("$(touch PWNED).md", str(tmp_path))
    assert ref.path.endswith("$(touch PWNED).md")
    assert not (tmp_path / "PWNED").exists()
    with pytest.raises(ValueError):
        resolve("file://another-machine/tmp/report.md", str(tmp_path))
    with pytest.raises(ValueError):
        resolve("a.md\nb.md", str(tmp_path))


def test_distinct_sources_and_symlinks(tmp_path):
    for name in ["one", "two"]:
        (tmp_path / name).mkdir()
        (tmp_path / name / "report.md").write_text(name)
    first = resolve("report.md", str(tmp_path / "one"))
    second = resolve("report.md", str(tmp_path / "two"))
    assert read_file(first)[1] == "one"
    assert read_file(second)[1] == "two"
    (tmp_path / "alias").symlink_to(tmp_path / "one" / "report.md")
    assert resolve("alias", str(tmp_path)).path == first.path


def test_boundaries_and_terminal_control_characters(tmp_path):
    file = tmp_path / "x.txt"
    file.write_bytes(b"hello\x1b]52;evil\x07\n")
    assert "\x1b" not in read_file(resolve("x.txt", str(tmp_path)))[1]
    file.write_bytes(b"\0bin")
    with pytest.raises(ValueError, match="二进制"):
        read_file(resolve("x.txt", str(tmp_path)))
    file.write_bytes(b"x" * (MAX_BYTES + 1))
    with pytest.raises(ValueError, match="4 MiB"):
        read_file(resolve("x.txt", str(tmp_path)))
    with pytest.raises(ValueError, match="不存在"):
        read_file(resolve("missing.md", str(tmp_path)))


def test_browser_never_executes_script_file_associations(tmp_path, monkeypatch):
    import lens
    calls = []
    monkeypatch.setenv("HERDR_PLUGIN_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)
    monkeypatch.setattr(lens.subprocess, "run", lambda args, **kwargs: calls.append(args))
    script = tmp_path / "danger.command"
    script.write_text("<script>alert('x')</script>\necho do-not-execute")
    lens.browser_open(resolve(str(script), str(tmp_path)))
    assert calls[0][-1].endswith(".html")
    generated = next((tmp_path / "state").glob("preview-*.html")).read_text()
    assert "&lt;script&gt;" in generated
    assert "<script>" not in generated
    monkeypatch.setenv("SSH_CONNECTION", "remote")
    with pytest.raises(ValueError, match="远程"):
        lens.browser_open(resolve(str(script), str(tmp_path)))


@pytest.mark.asyncio
async def test_viewer_loads_switches_updates_and_recovers(tmp_path):
    file = tmp_path / "report.md"
    file.write_text("# First\n\nA real file.")
    request = tmp_path / "request.json"
    def write_request(path):
        from dataclasses import asdict
        atomic_json(request, {"cwd": str(tmp_path), "source": "w1:p1", "workspace": "w1",
                              "host": "test-host", "raw": path, "file": asdict(resolve(path, str(tmp_path)))})
    write_request("report.md")
    app = LensApp(request)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        assert app.ref.path == str(file)
        assert app.query_one("#markdown").display
        await pilot.press("s")
        assert app.source_mode
        assert app.query_one("#source").display
        file.write_text("# Updated\n\nChanged on disk.")
        await app.poll_request()
        assert "Updated" in app.query_one("#source").content.code
        write_request("missing.md")
        await app.poll_request()
        assert "不存在" in str(app.query_one("#source").content)
        write_request("report.md")
        await app.poll_request()
        assert app.query_one("#markdown").display
