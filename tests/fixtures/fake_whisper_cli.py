"""Simulates whisper-cli: copies the sample JSON to <prefix>.json.

Usage: fake_whisper_cli.py -m MODEL -f WAV -l LANG -t N -oj -of PREFIX -np [--fail]
"""
import shutil
import sys
from pathlib import Path

args = sys.argv[1:]
if "--fail" in args:
    print("simulated whisper error", file=sys.stderr)
    sys.exit(2)
prefix = Path(args[args.index("-of") + 1])
wav = Path(args[args.index("-f") + 1])
assert wav.exists(), f"wav does not exist: {wav}"
shutil.copy(Path(__file__).with_name("whisper_output.json"), prefix.with_suffix(".json"))
