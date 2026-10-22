"""Simulates whisper-cli: writes <prefix>.json for a scripted scenario.

Usage: fake_whisper_cli.py -m MODEL -f WAV -l LANG -t N -mc N -oj -of PREFIX -np [--vad -vm VAD ...]
                           [--fail] [--loop | --loop-always] [--log FILE]
       fake_whisper_cli.py -m MODEL -l auto -dl -t N -f WAV [-f WAV ...] [--langs code:p,...] [--fail] [--log FILE]

  (default)      copies whisper_output.json (two Portuguese sentences)
  --fail         exits 2 with a message on stderr
  --loop         a 10-minute meeting whose first 8 minutes are one hallucinated line repeated every 5 s,
                 unless --vad is given: then the same meeting comes out healthy (the anti-loop retry works)
  --loop-always  the loop even with --vad (the retry does not help)
  -dl            language detection only (the language-detection adapter): prints, for each -f, `main: processing '<path>' (`
                 and the `auto-detected language` line to stderr, like whisper-cli, and writes nothing
  --langs LIST   with -dl, the answers per file in order: `en:0.99,is:0.96,-`; `-` (or a missing entry) = no answer line for
                 that file; all `-` = whisper ran and printed no answer line (the output format changed)
  --log FILE     appends the arguments received, as one JSON line, so tests can check what reached whisper
"""
import json
import shutil
import sys
from pathlib import Path

LOOP_LINE = "A CIDADE NO BRASIL"
MINUTES, LOOP_MINUTES = 10, 8

args = sys.argv[1:]
if "--log" in args:
    with open(args[args.index("--log") + 1], "a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
if "--fail" in args:
    print("simulated whisper error", file=sys.stderr)
    sys.exit(2)
if "-dl" in args:
    files = [Path(args[i + 1]) for i, arg in enumerate(args) if arg == "-f"]
    answers = args[args.index("--langs") + 1].split(",") if "--langs" in args else []
    for n, path in enumerate(files):
        assert path.exists(), f"wav does not exist: {path}"
        print(f"main: processing '{path}' (480000 samples, 30.0 sec), 4 threads, 1 processors, 5 beams + best of 5, lang = auto, task = transcribe, timestamps = 1 ...", file=sys.stderr)
        answer = answers[n] if n < len(answers) else "-"
        if answer != "-":
            code, probability = answer.split(":")
            print(f"whisper_full_with_state: auto-detected language: {code} (p = {float(probability):.6f})", file=sys.stderr)
    sys.exit(0)
prefix = Path(args[args.index("-of") + 1])
wav = Path(args[args.index("-f") + 1])
assert wav.exists(), f"wav does not exist: {wav}"


def segment(start: int, seconds: int, text: str) -> dict:
    return {"offsets": {"from": start * 1000, "to": (start + seconds) * 1000}, "text": f" {text}"}


looping = "--loop-always" in args or ("--loop" in args and "--vad" not in args)
if "--loop" in args or "--loop-always" in args:
    speech_from = LOOP_MINUTES * 60 if looping else 0
    items = [segment(t, 5, LOOP_LINE) for t in range(0, speech_from, 5)]
    items += [segment(t, 8, f"Fala {t} sobre o cronograma do projeto.") for t in range(speech_from, MINUTES * 60, 10)]
    prefix.with_suffix(".json").write_text(json.dumps({"result": {"language": "pt"}, "transcription": items}), encoding="utf-8")
else:
    shutil.copy(Path(__file__).with_name("whisper_output.json"), prefix.with_suffix(".json"))
