"""Herdr Lens: source-bound file references, reusable viewer, and local preview."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from urllib.parse import unquote, urlsplit

PLUGIN = "eason.lens"
MAX_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class FileRef:
    path: str
    cwd: str
    line: int | None = None
    column: int | None = None
    host: str = ""


def resolve(raw: str, cwd: str) -> FileRef:
    """Parse one path; never interpret shell syntax or environment variables."""
    raw = raw.strip()
    if raw.startswith("[") and "](" in raw and raw.endswith(")"):
        raw = raw[raw.index("](") + 2 : -1]
    if len(raw) > 1 and raw[0] == raw[-1] and raw[0] in "\"'`":
        raw = raw[1:-1]
    if raw.startswith("lens:"):
        raw = unquote(raw[5:])
    line = column = None
    if raw.startswith("file://"):
        parsed = urlsplit(raw)
        if parsed.netloc not in ("", "localhost", socket.gethostname()):
            raise ValueError("文件 URL 的主机与来源机器不符。请在文件所在机器打开。")
        raw = unquote(parsed.path)
        if parsed.fragment:
            match = re.fullmatch(r"L(\d+)(?:C(\d+))?", parsed.fragment)
            if match:
                line, column = int(match[1]), int(match[2]) if match[2] else None
            else:
                # Literal # in filenames must be encoded as %23 in file URLs.
                raise ValueError("file:// 行号请用 #L42 或 #L42C8；文件名里的 # 请编码为 %23。")
    elif "://" in raw:
        raise ValueError("请输入文件路径，不是网页地址。")
    if not raw or any(ord(c) < 32 or ord(c) == 127 for c in raw):
        raise ValueError("请输入一个完整的文件路径。")
    base = Path(cwd).expanduser()
    if not base.is_absolute():
        raise ValueError("来源目录必须是绝对路径。")
    path = Path(raw).expanduser()
    path = path if path.is_absolute() else base / path
    # An existing literal filename wins over a :line:column interpretation.
    if not path.exists() and (match := re.search(r"(?::(\d+)(?::(\d+))?|#L(\d+)(?:C(\d+))?)$", raw)):
        line = int(match[1] or match[3])
        column = int(match[2] or match[4]) if match[2] or match[4] else None
        path = Path(raw[: match.start()]).expanduser()
        path = path if path.is_absolute() else base / path
    if line is not None and (line < 1 or (column is not None and column < 1)):
        raise ValueError("行号和列号必须从 1 开始。")
    return FileRef(str(path.resolve()), str(base.resolve()), line, column, socket.gethostname())


def api(method: str, params: dict, socket_path: str | None = None) -> dict:
    target = socket_path or os.environ.get("HERDR_SOCKET_PATH")
    if not target:
        raise RuntimeError("请从 Herdr 的 Lens 动作打开预览。")
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(10)
        conn.connect(target)
        request = {"id": secrets.token_hex(8), "method": method, "params": params}
        conn.sendall(json.dumps(request).encode() + b"\n")
        with conn.makefile("rb") as stream:
            response = json.loads(stream.readline(8 * 1024 * 1024))
    if "error" in response:
        raise RuntimeError(response["error"].get("message", str(response["error"])))
    return response["result"]


def state_root() -> Path:
    root = Path(os.environ.get("HERDR_PLUGIN_STATE_DIR", Path.home() / ".local/state/herdr-lens"))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def atomic_json(path: Path, value: dict) -> None:
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".lens-")
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(value, out, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def open_action(raw: str | None = None, cwd: str | None = None) -> dict:
    context = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON", "{}"))
    source = context.get("focused_pane_id") or os.environ.get("HERDR_PANE_ID")
    workspace = context.get("workspace_id") or os.environ.get("HERDR_WORKSPACE_ID")
    if not source or not workspace:
        raise RuntimeError("Lens 需要来源 pane；请在 Herdr 终端中调用。")
    cwd = cwd or context.get("focused_pane_cwd") or context.get("workspace_cwd")
    if not cwd:
        raise RuntimeError("没有取得来源终端的工作目录。")
    raw = raw or context.get("clicked_url") or context.get("selected_text")
    if raw:
        from file_viewer_bridge import configuration, open_preview
        try:
            ref = resolve(raw, cwd)
        except (ValueError, OSError):
            ref = None
        if (ref and Path(ref.path).suffix.lower() in {".md", ".markdown", ".mdown"}
                and Path(ref.path).is_file() and configuration()):
            return open_preview(ref, source)
    root = state_root()
    key = hashlib.sha256(f"{os.environ.get('HERDR_SOCKET_PATH')}|{workspace}".encode()).hexdigest()[:24]
    request_path = root / f"{key}.json"
    record_path = root / f"{key}.pane.json"
    payload = {"cwd": cwd, "source": source, "workspace": workspace,
               "host": socket.gethostname(), "nonce": secrets.token_hex(8), "raw": raw or ""}
    if raw:
        try:
            payload["file"] = asdict(resolve(raw, cwd))
        except (ValueError, OSError) as error:
            payload["error"] = str(error)
    with (root / f"{key}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        atomic_json(request_path, payload)
        if record_path.exists():
            record = json.loads(record_path.read_text())
            try:
                pane = api("pane.get", {"pane_id": record["pane_id"]})
                if pane.get("pane", {}).get("workspace_id") == workspace:
                    # Record is valid only when the viewer still owns its lease.
                    lease = root / f"{key}.lease"
                    with lease.open("a") as probe:
                        try:
                            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            return {"reused": True, "pane_id": record["pane_id"]}
            except (RuntimeError, OSError):
                pass
        result = api("plugin.pane.open", {
            "plugin_id": PLUGIN, "entrypoint": "viewer", "placement": "split",
            "target_pane_id": source, "direction": "right",
            # Leave the launch cwd at Herdr's plugin-root default. The source
            # directory travels in the request, independently of the executable.
            "focus": False,
            "env": {"LENS_REQUEST_FILE": str(request_path), "LENS_LEASE_FILE": str(root / f"{key}.lease")},
        })
        pane = result.get("pane", {})
        pane_id = pane.get("pane_id") or result.get("plugin_pane", {}).get("pane", {}).get("pane_id")
        if not pane_id:
            raise RuntimeError(f"Herdr 未返回预览 pane ID: {result}")
        atomic_json(record_path, {"pane_id": pane_id})
        # Serialize rapid consecutive clicks until the viewer takes its lease.
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with (root / f"{key}.lease").open("a") as probe:
                try:
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    break
            time.sleep(0.03)
        return result


def read_file(ref: FileRef) -> tuple[str, str]:
    path = Path(ref.path)
    if path.is_dir():
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        return "directory", "\n".join(p.name + ("/" if p.is_dir() else "") for p in entries[:1000])
    if not path.is_file():
        raise ValueError(f"文件不存在或不是普通文件：{path}")
    if path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return "document", f"{path.name}\n\n按 b 在本机浏览器 / 默认查看器打开。\n大小：{path.stat().st_size:,} 字节"
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("文件超过 4 MiB；请用外部查看器打开。")
    if b"\0" in data:
        raise ValueError("这是二进制文件，请用外部查看器打开。")
    text = data.decode("utf-8-sig", errors="replace")
    # Escape terminal controls from untrusted files, preserving whitespace.
    text = "".join(c if c in "\n\t" or ord(c) >= 32 and ord(c) != 127 else f"\\x{ord(c):02x}" for c in text)
    return ("markdown" if path.suffix.lower() in {".md", ".markdown", ".mdown"} else "code"), text


def browser_open(ref: FileRef) -> None:
    """Open locally; never run a remote open command and claim a local browser."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        raise ValueError("当前预览运行在远程机器；此版本的浏览器入口仅支持本机文件。")
    path = Path(ref.path)
    if not path.exists():
        raise ValueError(f"文件不存在：{path}")
    uri = path.as_uri()
    # Text/code always becomes a document; never hand scripts/executables to
    # their OS file association. HTML and media are explicit preview formats.
    media = {".html", ".htm", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"}
    if path.suffix.lower() not in media or path.is_dir():
        from markdown_it import MarkdownIt
        kind, text = read_file(ref)
        body = (MarkdownIt("commonmark", {"html": False}).enable("table").render(text)
                if kind == "markdown" else f"<pre>{html.escape(text)}</pre>")
        rendered = state_root() / ("preview-" + hashlib.sha256(ref.path.encode()).hexdigest()[:20] + ".html")
        rendered.write_text(
            '<!doctype html><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src file: data: https:; style-src \'unsafe-inline\';">'
            f'<base href="{html.escape(path.parent.as_uri() + "/", quote=True)}">'
            f"<title>{html.escape(path.name)}</title>"
            "<style>body{max-width:980px;margin:45px auto;padding:24px;font:17px/1.7 system-ui}"
            "pre{overflow:auto;background:#f3f5f7;padding:18px}table{border-collapse:collapse}"
            "td,th{border:1px solid #bbb;padding:8px}img{max-width:100%}</style>" + body,
            encoding="utf-8",
        )
        rendered.chmod(0o600)
        uri = rendered.as_uri()
    command = ["/usr/bin/open", uri] if sys.platform == "darwin" else ["xdg-open", uri]
    subprocess.run(command, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)


def run_viewer(request_path: Path) -> None:
    from viewer import LensApp
    lease_path = Path(os.environ.get("LENS_LEASE_FILE", str(request_path) + ".lease"))
    with lease_path.open("a") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        LensApp(request_path).run()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["open", "view", "files", "resolve"])
    parser.add_argument("path", nargs="?")
    parser.add_argument("--cwd")
    args = parser.parse_args()
    if args.command == "resolve":
        print(json.dumps(asdict(resolve(args.path or "", args.cwd or os.getcwd())), ensure_ascii=False))
    elif args.command == "view":
        run_viewer(Path(os.environ["LENS_REQUEST_FILE"]))
    elif args.command == "files":
        from file_viewer_bridge import run_preview
        run_preview()
    else:
        print(json.dumps(open_action(args.path, args.cwd), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(f"Lens: {error}", file=sys.stderr)
        sys.exit(1)
