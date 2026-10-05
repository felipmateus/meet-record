import json
from pathlib import Path

from teams_recorder.adapters.outbound.transcriber_whispercpp import WhisperCppTranscriber, parse_whisper_json

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_parse_whisper_json_converts_offsets_and_drops_blank_segments():
    data = json.loads((FIXTURES / "whisper_output.json").read_text())

    t = parse_whisper_json(data, "pt")

    assert t.language == "pt"
    assert len(t.segments) == 2
    assert t.segments[0].start == 0.0 and t.segments[0].end == 3.2
    assert t.segments[1].text == "Felipe, você fica responsável pelo relatório até quarta."
    assert t.duration_seconds == 9.8


def test_parse_whisper_json_tolerates_missing_fields():
    t = parse_whisper_json({"transcription": [{"text": "oi"}]}, "pt")
    assert t.segments[0].start == 0.0 and t.segments[0].end == 0.0
    assert parse_whisper_json({}, "en").language == "en"


def test_commands(tmp_path: Path):
    tr = WhisperCppTranscriber(tmp_path / "ggml-x.bin", threads=4)
    conv = tr.convert_command(tmp_path / "a.m4a", tmp_path / "a.wav")
    assert conv[conv.index("-ar") + 1] == "16000" and conv[conv.index("-ac") + 1] == "1"
    wc = tr.whisper_command(tmp_path / "a.wav", "pt", tmp_path / "out")
    assert wc[0] == "whisper-cli" and "-oj" in wc and "-np" in wc
    assert wc[wc.index("-l") + 1] == "pt" and wc[wc.index("-t") + 1] == "4"
    assert wc[wc.index("-m") + 1].endswith("ggml-x.bin")


def test_threads_default_is_positive(tmp_path: Path):
    assert WhisperCppTranscriber(tmp_path / "m.bin").threads >= 1


def test_vad_flags_only_when_model_exists(tmp_path: Path):
    vad = tmp_path / "ggml-silero.bin"
    without = WhisperCppTranscriber(tmp_path / "m.bin", vad_model_path=vad).whisper_command(tmp_path / "a.wav", "pt", tmp_path / "o")
    assert "--vad" not in without
    vad.write_bytes(b"\x00")
    with_vad = WhisperCppTranscriber(tmp_path / "m.bin", vad_model_path=vad).whisper_command(tmp_path / "a.wav", "pt", tmp_path / "o")
    assert "--vad" in with_vad and with_vad[with_vad.index("-vm") + 1] == str(vad)
