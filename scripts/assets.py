"""Download version-pinned release files and verify their committed SHA-256."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def platform_key() -> str:
    machine = {"arm64": "aarch64", "AMD64": "x86_64"}.get(platform.machine(), platform.machine())
    return f"{platform.system().lower()}-{machine}"


def fetch(component: str, root: Path = ROOT) -> Path | None:
    manifest = json.loads((root / "release-assets.json").read_text())
    asset = manifest["platforms"].get(platform_key(), {}).get(component)
    if not asset:
        return None
    destination = root / "build" / asset["filename"]
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == asset["sha256"]:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f'https://github.com/{manifest["repository"]}/releases/download/{manifest["tag"]}/{asset["asset"]}'
    request = urllib.request.Request(url, headers={"User-Agent": "Herdr-Lens-installer"})
    fd, name = tempfile.mkstemp(prefix=".download-", dir=destination.parent)
    try:
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(request, timeout=60) as source:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > 100 * 1024 * 1024:
                    raise ValueError("Release binary exceeds 100 MiB")
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest() != asset["sha256"]:
            raise ValueError(f"SHA-256 mismatch for {asset['asset']}")
        os.chmod(name, 0o755)
        os.replace(name, destination)
    finally:
        Path(name).unlink(missing_ok=True)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=["viewer", "client"])
    parser.add_argument("--optional", action="store_true")
    args = parser.parse_args()
    try:
        path = fetch(args.component)
        if path:
            print(f"Verified {args.component}: {path}")
        elif not args.optional:
            raise RuntimeError(f"No {args.component} binary for {platform_key()}; see docs/development.md")
        else:
            print("No native binary for this platform; built-in Markdown preview remains available.")
    except Exception as error:
        if not args.optional:
            raise SystemExit(str(error)) from error
        print(f"Native preview unavailable ({error}); built-in Markdown preview remains available.")


if __name__ == "__main__":
    main()
