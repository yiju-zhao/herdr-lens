from __future__ import annotations

import json
from pathlib import Path

from rich.syntax import Syntax
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Input, Markdown, Static

from lens import FileRef, browser_open, read_file, resolve


class LensApp(App):
    TITLE = "Herdr Lens"
    CSS = """
    Screen { background: #101820; }
    #origin { height: auto; max-height: 4; padding: 0 1; background: #20303b; color: #89d5d0; }
    #path { margin: 0 1; height: 3; }
    #body { padding: 0 1; }
    #message { height: auto; padding: 0 1; color: #d8bb87; }
    #source { width: auto; min-width: 100%; }
    Markdown { margin: 0; padding: 0 1; }
    """
    BINDINGS = [
        ("q", "quit", "关闭"), ("escape", "focus_body", "返回"),
        ("s", "toggle_source", "源码/预览"), ("b", "browser", "浏览器"),
        ("r", "refresh_file", "刷新"), ("w", "toggle_watch", "自动更新"),
        ("/", "focus_path", "输入路径"),
    ]

    def __init__(self, request_path: Path):
        super().__init__()
        self.request_path = request_path
        self.request_stamp = None
        self.file_stamp = None
        self.ref: FileRef | None = None
        self.cwd = str(Path.home())
        self.payload = {}
        self.source_mode = False
        self.watch = True

    def compose(self) -> ComposeResult:
        yield Static("Lens · 正在读取来源…", id="origin", markup=False)
        yield Input(placeholder="输入来源机器上的文件路径，按 Enter", id="path")
        yield Static("", id="message", markup=False)
        with VerticalScroll(id="body"):
            yield Markdown("", id="markdown", open_links=False)
            yield Static("", id="source", markup=False)
        yield Footer()

    async def on_mount(self) -> None:
        await self.poll_request()
        self.set_interval(0.5, self.poll_request)
        if self.ref:
            self.query_one("#body").focus()
        else:
            self.query_one("#path", Input).focus()

    async def poll_request(self) -> None:
        try:
            stamp = self.request_path.stat().st_mtime_ns
            if stamp != self.request_stamp:
                payload = json.loads(self.request_path.read_text())
                self.request_stamp = stamp
                self.payload = payload
                self.cwd = payload["cwd"]
                self.source_mode = False
                self.file_stamp = None
                self.ref = FileRef(**payload["file"]) if payload.get("file") else None
                self.query_one("#path", Input).value = payload.get("raw", "")
                self.query_one("#origin", Static).update(
                    f"{payload['host']} · {payload['workspace']} · {payload['source']}\n{self.cwd}"
                )
                if self.ref:
                    await self.render_file(new_file=True)
                else:
                    self.query_one("#source", Static).update("")
                    self.query_one("#markdown", Markdown).display = False
                    self.query_one("#message", Static).update(payload.get("error", "输入文件路径，或从 agent 输出 Ctrl+点击路径。"))
            elif self.ref and self.watch:
                path = Path(self.ref.path)
                current = (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None
                if current != self.file_stamp:
                    await self.render_file()
        except (OSError, ValueError, KeyError) as error:
            self.query_one("#message", Static).update(str(error))

    async def render_file(self, new_file: bool = False) -> None:
        if not self.ref:
            return
        markdown = self.query_one("#markdown", Markdown)
        source = self.query_one("#source", Static)
        try:
            kind, text = read_file(self.ref)
            path = Path(self.ref.path)
            stat = path.stat()
            self.file_stamp = (stat.st_mtime_ns, stat.st_size)
            is_markdown = kind == "markdown" and not self.source_mode
            markdown.display = is_markdown
            source.display = not is_markdown
            if is_markdown:
                await markdown.update(text)
            elif kind in {"code", "markdown"}:
                if path.suffix.lower() == ".json" and not self.source_mode:
                    try:
                        text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
                    except ValueError:
                        pass
                language = Syntax.guess_lexer(path.name, text)
                source.update(Syntax(text, language, theme="monokai", line_numbers=True,
                                     word_wrap=True, highlight_lines={self.ref.line} if self.ref.line else set()))
            else:
                source.update(Text(text))
            status = "自动更新" if self.watch else "暂停更新"
            self.query_one("#message", Static).update(
                f"{self.ref.path}" + (f" · {self.ref.line}:{self.ref.column or 1}" if self.ref.line else "") + f"\n只读 · {status}"
            )
            if new_file:
                self.query_one("#body", VerticalScroll).scroll_to(y=max(0, (self.ref.line or 1) - 4), animate=False, force=True)
        except (OSError, ValueError) as error:
            markdown.display = False
            source.display = True
            source.update(Text(str(error), style="red"))
            self.file_stamp = None

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        try:
            self.ref = resolve(event.value, self.cwd)
            self.file_stamp = None
            await self.render_file(new_file=True)
            self.query_one("#body").focus()
        except (ValueError, OSError) as error:
            self.query_one("#message", Static).update(str(error))

    async def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        # Internal document links stay on the same source machine.
        if self.ref and not event.href.startswith(("http:", "https:", "#", "mailto:")):
            try:
                self.ref = resolve(event.href, str(Path(self.ref.path).parent))
                await self.render_file(new_file=True)
            except (OSError, ValueError) as error:
                self.notify(str(error), severity="error")

    async def action_toggle_source(self) -> None:
        self.source_mode = not self.source_mode
        await self.render_file()

    async def action_refresh_file(self) -> None:
        await self.render_file()

    async def action_toggle_watch(self) -> None:
        self.watch = not self.watch
        await self.render_file()

    def action_browser(self) -> None:
        if self.ref:
            try:
                browser_open(self.ref)
            except (OSError, ValueError) as error:
                self.notify(str(error), severity="error")

    def action_focus_path(self) -> None:
        self.query_one("#path", Input).focus()

    def action_focus_body(self) -> None:
        self.query_one("#body").focus()
