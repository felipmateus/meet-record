"""Simulates a recorder: creates the output file, writes until it receives SIGINT/SIGTERM
(or until its --stop-file appears) and exits with 0.

Usage: fake_recorder.py --out PATH [--stop-file PATH] [--die] [--hang]
  --die:  exits immediately with code 3
  --hang: ignores SIGINT/SIGTERM and the stop file (to test forced termination)
"""
import os
import signal
import sys
import time

out = sys.argv[sys.argv.index("--out") + 1]
stop_file = sys.argv[sys.argv.index("--stop-file") + 1] if "--stop-file" in sys.argv else None
hang = "--hang" in sys.argv
if "--die" in sys.argv:
    print("simulated failure", file=sys.stderr)
    sys.exit(3)

running = True


def _stop(signum, frame):
    global running
    if not hang:
        running = False


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)

with open(out, "wb") as fh:
    fh.write(b"RIFF" + b"\x00" * 2000)
    fh.flush()
    while running:
        if stop_file and not hang and os.path.exists(stop_file):
            break
        time.sleep(0.05)
    fh.write(b"END")
