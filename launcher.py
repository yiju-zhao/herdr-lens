"""Transparent `herdr` entry point: Lens for the UI, upstream CLI for commands."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def is_client_launch(args: list[str]) -> bool:
    if any(arg in {"--help", "-h", "--version", "-V", "--skill", "--default-config"}
           for arg in args):
        return False
    remaining = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--machine" or arg.startswith("--machine="):
            return False
        if arg in {"--session", "--remote", "--remote-keybindings"}:
            if i + 1 >= len(args):
                return False
            i += 2
            continue
        if any(arg.startswith(flag + "=") for flag in
               ("--session", "--remote", "--remote-keybindings")):
            i += 1
            continue
        if arg == "--handoff":
            i += 1
            continue
        remaining.append(arg)
        i += 1
    return (not remaining or remaining == ["client"] or
            len(remaining) == 3 and remaining[:2] == ["session", "attach"])


def choose_program(args: list[str], root: Path, config: dict) -> Path:
    upstream = Path(config["upstream"])
    client = root / "build/herdr-lens-client"
    if not is_client_launch(args) or not client.is_file():
        return upstream
    # Keep package-manager upgrades effective. Never run an older pinned client
    # in place of a newer upstream installation without rebuilding its adapter.
    try:
        version = subprocess.check_output(
            [str(upstream), "--version"], text=True, stderr=subprocess.DEVNULL, timeout=5
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return upstream
    return client if version == config["version"] else upstream


def main() -> None:
    root = Path(__file__).resolve().parent
    config = json.loads((root / "build/launcher.json").read_text())
    args = sys.argv[1:]
    program = choose_program(args, root, config)
    if program.resolve() == (root / "herdr-lens").resolve():
        raise SystemExit("Lens launcher configuration points to itself.")
    env = dict(os.environ)
    if program == root / "build/herdr-lens-client":
        env["HERDR_LENS"] = "1"
    # Preserve the upstream CLI's session, socket, cwd, and nesting semantics.
    # The complete binary can also start a fresh server through its native path.
    os.execve(program, [str(program), *args], env)


if __name__ == "__main__":
    main()
