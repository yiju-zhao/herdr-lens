"""Print representative native-agent file references for terminal integration QA."""
from pathlib import Path

root = Path(__file__).resolve().parent
print("\033[2J\033[H", end="")
print("Lens integration test — files below exist on this machine.\n")
print("Claude Code / Codex path formats:")
print("examples/demo.py:8")
print('"' + str(root / "欢迎使用 Lens.md") + '"')
print("examples/report.html")
print("\033]8;;" + (root / "demo.py").as_uri() + "#L8\033\\Explicit file link\033]8;;\033\\")
