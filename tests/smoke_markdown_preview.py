"""Isolated end-to-end acceptance test for direct Markdown path previews."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix="lens-cfg-", dir="/tmp") as temporary:
    profile = Path(temporary) / "herdr"
    config = profile / "plugins/config/eason.lens"
    config.mkdir(parents=True)
    (profile / "config.toml").write_text(
        'onboarding = false\n[theme]\nname = "one-dark"\n'
        '[[keys.command]]\nkey = "prefix+f"\ntype = "plugin_action"\n'
        'command = "eason.lens.open"\ndescription = "Lens: preview file"\n'
    )
    # Exercise the marketplace defaults: no absolute binary/config override.
    env = {k: v for k, v in os.environ.items()
           if k not in {"HERDR_SOCKET_PATH", "HERDR_CLIENT_SOCKET_PATH", "HERDR_SESSION"}}
    env.update(XDG_CONFIG_HOME=temporary, XDG_STATE_HOME=str(root / "build/direct-preview-state"),
               PYTHONPATH=str(root))
    upstream = os.environ.get("HERDR_TEST_BIN") or json.loads((root / "build/launcher.json").read_text())["upstream"]
    subprocess.run([upstream, "plugin", "link", str(root), "--enabled"],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(root / "tests/smoke_launcher.py"), "--markdown"],
                   env=env, check=True)
