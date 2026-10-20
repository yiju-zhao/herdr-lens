"""Emit absolute and relative Markdown references from an ordinary project."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
print("\033[2J\033[H", end="")
print("Markdown click preview test\n")
print("Relative: docs/first.md")
print('Absolute: "' + str(root / "docs/中文 空格.md") + '"')
print("Relative again: ./docs/first.md")
