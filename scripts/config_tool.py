"""Installer helper, run with the project's virtualenv Python (scripts/install.sh and install.ps1).

  config_tool.py get                         prints the settings the installers need, as key=value
  config_tool.py set <section> <key> <value> rewrites one `key = "value"` line in config.toml
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def get() -> None:
    from teams_recorder.config import load_settings
    from teams_recorder.constants import Files

    s = load_settings(PROJECT)
    values = {
        "data_dir": s.data_dir,
        "model_path": s.whisper_model_path,
        "vad_path": s.vad_model_path or "",
        "provider": s.llm_provider.value,
        "user_name": s.user_name,
        "active": s.data_dir / Files.ACTIVE_RECORDING,
    }
    for key, value in values.items():
        print(f"{key}={value}")


def set_value(section: str, key: str, value: str) -> None:
    path = PROJECT / "config.toml"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    current = None
    for i, line in enumerate(lines):
        header = re.match(r"\s*\[([^\]]+)\]", line)
        if header:
            current = header.group(1).strip()
        elif current == section and re.match(rf"\s*{re.escape(key)}\s*=", line):
            lines[i] = f"{key} = {json.dumps(value, ensure_ascii=False)}\n"
            path.write_text("".join(lines), encoding="utf-8")
            return
    sys.exit(f"[{section}] {key} not found in {path}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["get"]:
        get()
    elif len(args) == 4 and args[0] == "set":
        set_value(*args[1:])
    else:
        sys.exit(__doc__)
