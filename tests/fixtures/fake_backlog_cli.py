"""Simulates `backlog task create … --plain` (Backlog.md 1.53.0 output format).

Appends {"args", "cwd"} as one JSON line to the file in FAKE_BACKLOG_LOG, then behaves per
FAKE_BACKLOG_MODE: success (default: prints the plain task layout with id TASK-<n>),
fail (exit 1 with Backlog.md's invalid-status message) or no_id (exit 0 without a task line).
"""
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
log = Path(os.environ["FAKE_BACKLOG_LOG"])
with log.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps({"args": args, "cwd": os.getcwd()}, ensure_ascii=False) + "\n")
number = sum(1 for _ in log.open(encoding="utf-8"))

mode = os.environ.get("FAKE_BACKLOG_MODE", "success")
if mode == "fail":
    print("Invalid status: Triagem. Valid statuses are: To Do, In Progress, Done")
    sys.exit(1)
if mode == "no_id":
    print("Created.")
    sys.exit(0)

assert args[:2] == ["task", "create"] and args[-2] == "--" and "--plain" in args, args
title = args[-1]
print(f"File: {os.getcwd()}/backlog/tasks/task-{number} - {title.replace(' ', '-')}.md\n")
print(f"Task TASK-{number} - {title}")
print("=" * 50)
print(f"\nStatus: ○ {args[args.index('-s') + 1]}")
