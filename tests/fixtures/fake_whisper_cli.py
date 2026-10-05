"""Simula o whisper-cli: copia o JSON de exemplo para <prefix>.json.

Uso: fake_whisper_cli.py -m MODEL -f WAV -l LANG -t N -oj -of PREFIX -np [--fail]
"""
import shutil
import sys
from pathlib import Path

args = sys.argv[1:]
if "--fail" in args:
    print("erro simulado do whisper", file=sys.stderr)
    sys.exit(2)
prefix = Path(args[args.index("-of") + 1])
wav = Path(args[args.index("-f") + 1])
assert wav.exists(), f"wav não existe: {wav}"
shutil.copy(Path(__file__).with_name("whisper_output.json"), prefix.with_suffix(".json"))
