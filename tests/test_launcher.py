from pathlib import Path
import subprocess

import pytest

from launcher import choose_program, is_client_launch


@pytest.mark.parametrize("args", [
    [], ["--session", "work"], ["--session=work"],
    ["session", "attach", "work"], ["--remote", "host", "--session", "work"],
    ["--remote=host"], ["client"],
])
def test_native_launch_forms(args):
    assert is_client_launch(args)


@pytest.mark.parametrize("args", [
    ["--version"], ["--help"], ["--session", "work", "server", "stop"],
    ["--machine", "host", "pane", "list"], ["--machine=host", "agent", "list"],
    ["update"], ["plugin", "list"], ["completion", "zsh"], ["session", "list"],
    ["--session"], ["--unknown"],
])
def test_cli_commands_keep_upstream_semantics(args):
    assert not is_client_launch(args)


def test_upgrade_and_missing_client_fall_back_without_recursion(tmp_path, monkeypatch):
    upstream = tmp_path / "upstream"
    client = tmp_path / "build/herdr-lens-client"
    client.parent.mkdir()
    client.touch()
    config = {"upstream": str(upstream), "version": "herdr 0.9.3"}
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: "herdr 0.9.3\n")
    assert choose_program([], tmp_path, config) == client
    assert choose_program(["plugin", "list"], tmp_path, config) == upstream
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: "herdr 0.9.4\n")
    assert choose_program([], tmp_path, config) == upstream
    client.unlink()
    assert choose_program([], tmp_path, config) == upstream
