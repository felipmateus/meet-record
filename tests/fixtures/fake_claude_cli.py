"""Simulates `claude -p --output-format json`: reads the message from stdin and prints an envelope.

Behavior is controlled by the FAKE_CLAUDE_MODE variable: success (default), error, no_structured, bad_schema.
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
assert "Transcript" in user_message, user_message[:100]

out = {
    "summary": "Revisão da sprint com entregas definidas.",
    "decisions": ["Relatório até quarta."],
    "my_actions": [{"description": "Enviar relatório de integração", "owner": "usuário", "due": "2026-10-08"}],
    "others_actions": [],
    "deadlines": [],
    "open_questions": [],
    "next_meetings": [],
}
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
