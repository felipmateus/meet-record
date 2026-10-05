"""Simulates a recorder: creates the output file, writes until it receives SIGINT/SIGTERM and exits with 0.

Usage: fake_recorder.py --out PATH [--die]   (--die: exits immediately with code 3)
"""
import signal
import sys
import time

out = sys.argv[sys.argv.index("--out") + 1]
if "--die" in sys.argv:
    print("simulated failure", file=sys.stderr)
    sys.exit(3)

running = True


def _stop(signum, frame):
    global running
    running = False


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)

with open(out, "wb") as fh:
    fh.write(b"RIFF" + b"\x00" * 2000)
    fh.flush()
    while running:
        time.sleep(0.05)
    fh.write(b"END")
