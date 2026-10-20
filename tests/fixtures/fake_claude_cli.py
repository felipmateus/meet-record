"""Simulates `claude -p --output-format json`: reads the message from stdin and prints an envelope.

Behavior is controlled by the FAKE_CLAUDE_MODE variable: success (default), error, no_structured, bad_schema.

By default it answers with a meeting analysis. Other answers, for the other structured calls:
- FAKE_CLAUDE_OUTPUT_FILE: path to a JSON file holding the structured output to return on every call;
- FAKE_CLAUDE_SCRIPT: path to a JSON file holding a list of structured outputs, returned in order (the last one repeats);
  the position is kept in `<script>.n`, so a test that runs several calls shares one script;
- FAKE_CLAUDE_RECORD: path of a JSON-lines file where every call appends `{"system": ..., "user": ...}`.
With an output file or a script the message is not required to hold a transcript.
"""
import json
import os
import sys

mode = os.environ.get("FAKE_CLAUDE_MODE", "success")
if any(k.startswith("ANTHROPIC_") for k in os.environ):
    print("ANTHROPIC_* leaked into the claude environment", file=sys.stderr)
    sys.exit(4)
args = sys.argv[1:]
assert "-p" in args and "--json-schema" in args and "--system-prompt" in args, args
user_message = sys.stdin.read()
output_file = os.environ.get("FAKE_CLAUDE_OUTPUT_FILE")
script_file = os.environ.get("FAKE_CLAUDE_SCRIPT")
record_file = os.environ.get("FAKE_CLAUDE_RECORD")
if record_file:
    with open(record_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"system": args[args.index("--system-prompt") + 1], "user": user_message}, ensure_ascii=False) + "\n")
if not (output_file or script_file):
    assert "Transcript" in user_message, user_message[:100]

out = {
    "title": "Revisão da sprint",
    "purpose": "Definir as entregas da semana.",
    "meeting_type": "project_review",
    "participants": ["Felipe"],
    "summary": "Revisão da sprint com entregas definidas.",
    "topics": [{"title": "Entregas", "points": ["Relatório até quarta."]}],
    "decisions": [{"text": "Relatório até quarta.", "at": "00:00:03"}],
    "my_actions": [{"description": "Enviar relatório de integração", "owner": "usuário", "due": "2026-10-08", "priority": "high", "at": "00:00:03", "kind": "communication"}],
    "risks": [],
    "others_actions": [],
    "deadlines": [],
    "open_questions": [],
    "next_meetings": [],
}
if output_file:
    with open(output_file, encoding="utf-8") as fh:
        out = json.load(fh)
elif script_file:
    with open(script_file, encoding="utf-8") as fh:
        script = json.load(fh)
    counter = script_file + ".n"
    position = int(open(counter).read()) if os.path.exists(counter) else 0
    with open(counter, "w") as fh:
        fh.write(str(position + 1))
    out = script[min(position, len(script) - 1)]
envelope = {
    "type": "result", "subtype": "success", "is_error": False,
    "result": json.dumps(out, ensure_ascii=False), "structured_output": out,
    "usage": {"input_tokens": 900, "output_tokens": 120, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 1100},
    "modelUsage": {"claude-opus-5": {}}, "total_cost_usd": 0.0123, "session_id": "sess-1",
}
if mode == "error":
    envelope.update(subtype="error_during_execution", is_error=True, result="Not logged in", structured_output=None)
elif mode == "no_structured":
    envelope["structured_output"] = None
elif mode == "bad_schema":
    envelope["structured_output"] = {"summary": 42}
print(json.dumps(envelope, ensure_ascii=False))
