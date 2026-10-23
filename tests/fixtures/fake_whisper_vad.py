"""Simulates whisper-vad-speech-segments: prints a scripted segment list in the real tool's format.

Usage: fake_whisper_vad.py -vm MODEL -f WAV -np -t N -vt X -vsd X -vp X
                           [--segments S:E,S:E | --none | --garbled | --mismatch | --fail] [--log FILE]

The real tool prints its results to stdout, in centiseconds, and its ggml/Metal start-up lines to stderr:

    <blank line>
    Detected 2 speech segments:
    Speech segment 0: start = 0.00, end = 419.00
    Speech segment 1: start = 458.00, end = 720.00
    <blank line>

  (default)       no segment: `Detected 0 speech segments:`
  --segments LIST centisecond pairs, `0:419,458:720`
  --none          `Detected 0 speech segments:` (the same as the default, spelled out)
  --garbled       the segment lines of --segments with no count line (the output format changed)
  --mismatch      a count one higher than the segment lines that follow
  --fail          exits 1 with a message on stderr
  --log FILE      appends the arguments received, as one JSON line, so tests can check what reached the tool
"""
import json
import sys
from pathlib import Path

args = sys.argv[1:]
if "--log" in args:
    with open(args[args.index("--log") + 1], "a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
if "--fail" in args:
    print("simulated vad error", file=sys.stderr)
    sys.exit(1)

model, wav = Path(args[args.index("-vm") + 1]), Path(args[args.index("-f") + 1])
assert model.exists(), f"vad model does not exist: {model}"
assert wav.exists(), f"wav does not exist: {wav}"

print("ggml_metal_device_init: GPU name:   MTL0 (Apple M1)", file=sys.stderr)   # what the real tool logs before its results
print(f"read_audio_data: reading audio data from '{wav}' ...", file=sys.stderr)

scripted = args[args.index("--segments") + 1].split(",") if "--segments" in args and "--none" not in args else []
pairs = [tuple(int(cs) for cs in pair.split(":")) for pair in scripted]
print()
if "--garbled" not in args:
    print(f"Detected {len(pairs) + (1 if '--mismatch' in args else 0)} speech segments:")
for i, (start, end) in enumerate(pairs):
    print(f"Speech segment {i}: start = {start:.2f}, end = {end:.2f}")
print()
