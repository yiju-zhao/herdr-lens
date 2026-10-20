"""Rebuild a native component from its pinned upstream source plus local patch."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=["viewer", "client"])
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    spec = json.loads((ROOT / "upstream.json").read_text())[args.component]
    source = ROOT / "build/sources" / args.component
    if not source.exists():
        source.mkdir(parents=True)
        for command in (["git", "init"], ["git", "remote", "add", "origin", spec["repository"]],
                        ["git", "fetch", "--depth", "1", "origin", spec["commit"]],
                        ["git", "checkout", "--detach", "FETCH_HEAD"]):
            subprocess.run(command, cwd=source, check=True)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if actual != spec["commit"]:
        raise SystemExit(f"Source is at {actual}, expected {spec['commit']}; refusing to reset your checkout.")
    patch = str(ROOT / spec["patch"])
    applied = subprocess.run(["git", "apply", "--reverse", "--check", patch], cwd=source,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not applied:
        subprocess.run(["git", "apply", "--check", patch], cwd=source, check=True)
        subprocess.run(["git", "apply", patch], cwd=source, check=True)
    if not args.prepare_only:
        subprocess.run(["cargo", "build", "--release", "--locked"], cwd=source, check=True)
        shutil.copy2(source / "target/release" / spec["binary"], ROOT / "build" / spec["output"])
    print(source)


if __name__ == "__main__":
    main()
