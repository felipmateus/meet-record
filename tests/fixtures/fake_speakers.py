"""Stands in for the `teams-speakers` helper.

Usage: fake_speakers.py --check
       fake_speakers.py --out PATH --epoch SECONDS [--interval S]

FAKE_SPEAKERS_TRUSTED=1 means the Accessibility permission is granted: `--check` exits 0 and a run proceeds. Any other
value means missing: both exit 3 before creating a file (the helper's own behaviour).
A run writes a `start` line to PATH, then `PATH.ready`, and waits; on SIGTERM/SIGINT it appends a `stop` line (last) and
exits 0. Every line is flushed as it is written.
"""
import json
import os
import signal
import sys
import time

trusted = os.environ.get("FAKE_SPEAKERS_TRUSTED") == "1"

if "--check" in sys.argv:
    print("Accessibility permission: granted" if trusted else "Accessibility permission: missing", file=sys.stderr)
    sys.exit(0 if trusted else 3)

if "--out" not in sys.argv or "--epoch" not in sys.argv:
    print("usage: --out and --epoch are required", file=sys.stderr)
    sys.exit(2)
out = sys.argv[sys.argv.index("--out") + 1]
epoch = float(sys.argv[sys.argv.index("--epoch") + 1])

if not trusted:
    print("Accessibility permission missing", file=sys.stderr)
    sys.exit(3)

running = True


def _stop(signum, frame):
    global running
    running = False


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)

with open(out, "a") as fh:
    fh.write(json.dumps({"t": time.time(), "event": "start", "epoch": epoch, "version": 1}) + "\n")
    fh.flush()
    with open(out + ".ready", "w") as ready:
        ready.write("ready")
    while running:
        time.sleep(0.05)
    fh.write(json.dumps({"t": time.time(), "event": "stop", "reason": "signal"}) + "\n")
    fh.flush()
