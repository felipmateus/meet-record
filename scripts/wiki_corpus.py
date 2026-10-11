#!/usr/bin/env python3
"""Synthetic meeting corpus for the LLM wiki evaluation (tasks/prd-llm-wiki/evaluation.md).

Runs the whole chain on fictional meetings, from audio to scored answers:

  render   dialogue scripts (tests/fixtures/wiki_corpus) → audio.m4a per meeting, one macOS
           `say` voice per speaker, in <data>/recordings/<id>/ (with meta.json)
  process  the project's own transcription (whisper.cpp) and analysis (Claude) on those
           meetings, through the container, with the data dir pointed at <data>
  ask      the questions under each condition, `--runs` times: "minutes" (every minutes.md in
           the context, no tools) and "wiki" (Claude Code inside the wiki folder, read-only tools)
  score    code checks (must_include / must_not_include / must_cite) plus a binary LLM judge,
           then report.md with pass^k and pass@k per category and condition

Scale test (evaluation.md §12), keeping the disk footprint small:

  fill     distractor meetings generated as transcripts only (no audio, no whisper), once, into
           a folder outside Git; `process --fillers <dir>` links them into a run's data dir
  ingest   builds the wiki meeting by meeting, oldest first: one fresh Claude Code process per
           meeting inside the wiki folder, one local Git commit per meeting
  clean    deletes a data dir's recordings and temporary files, keeping the wiki and the runs

Every step that writes much stops when the data volume has less free space than the recorder
needs (3 GB, or two hours of raw tracks) or when a real recording is in progress.

Use the project's virtualenv and a data dir OUTSIDE this repository: Claude Code loads every
CLAUDE.md from the working directory up, so a wiki under the repo would also see the repo's
instructions. Nothing here touches the real data dir or the running daemon.

  .venv/bin/python scripts/wiki_corpus.py render  --data /tmp/wiki-sim
  .venv/bin/python scripts/wiki_corpus.py process --data /tmp/wiki-sim
  (build the wiki in /tmp/wiki-sim/wiki)
  .venv/bin/python scripts/wiki_corpus.py ask   --data /tmp/wiki-sim --runs 3 --out /tmp/wiki-sim/runs/r1
  .venv/bin/python scripts/wiki_corpus.py score --run /tmp/wiki-sim/runs/r1

The model calls use Claude Code (the user's subscription), like the project's claude-code
provider; ANTHROPIC_* variables are removed from their environment.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import unicodedata
import wave
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

PROJECT = Path(__file__).resolve().parents[1]
CORPUS = PROJECT / "tests" / "fixtures" / "wiki_corpus"
sys.path.insert(0, str(PROJECT / "src"))

SAMPLE_RATE = 22050
TURN_GAP_SECONDS = 0.45
SPEECH_RATE = 185                # words per minute for `say`
CONDITIONS = ("minutes", "wiki")
WIKI_TOOLS = "Read,Grep,Glob"
INGEST_TOOLS = "Read,Write,Edit,Glob,Grep"
MIN_FREE_BYTES = 3_000_000_000   # never leave the recorder less than this (see disk_guard)
INGESTED_FILE = ".ingested"      # in the wiki folder: one meeting id per line

MINUTES_SYSTEM = """You answer questions about the work meetings of one user, Felipe, using ONLY the meeting minutes in the message. Answer in Brazilian Portuguese. Give the current state first. Cite the meeting date (DD/MM) and, when the minutes give one, the timestamp for every fact. If the minutes do not answer the question, say that it was not discussed in the meetings; never guess or use outside knowledge."""

WIKI_SYSTEM_SUFFIX = """

# Your task now

Answer the user's question with the "Answer a question" workflow above, reading only files inside the current folder (start with index.md). Do not modify any file."""

JUDGE_SYSTEM = """You grade one answer to a question about a user's work meetings. You receive the question, a rubric that states exactly what a passing answer must do, and the answer. Judge only what the rubric asks; ignore style, length and extra correct detail. Write a short critique first (in English), then the verdict: PASS or FAIL."""


# --- corpus -------------------------------------------------------------------------------
def load_corpus() -> dict[str, Any]:
    return tomllib.loads((CORPUS / "corpus.toml").read_text(encoding="utf-8"))


def load_questions(path: Path) -> list[dict[str, Any]]:
    return tomllib.loads(path.read_text(encoding="utf-8"))["question"]


def parse_script(path: Path) -> list[tuple[str, str]]:
    """Turns of a dialogue script: (speaker, text), or ("[pause]", seconds)."""
    turns: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pause = re.fullmatch(r"\[pausa (\d+(?:\.\d+)?)\]", line)
        if pause:
            turns.append(("[pause]", pause.group(1)))
            continue
        speaker, sep, text = line.partition(":")
        if not sep or not text.strip():
            raise SystemExit(f"{path.name}: not a 'Speaker: text' line: {line!r}")
        turns.append((speaker.strip(), text.strip()))
    return turns


# --- guards -------------------------------------------------------------------------------
def disk_guard(path: Path) -> None:
    """Stop before a step that writes when the real recorder could run out of room.

    The recorder needs about 1 GB per hour of call for its raw tracks (16-bit) and warns below
    two hours' worth; swap also grows into the same free space under memory pressure. A real
    call in progress always wins over the evaluation.
    """
    from teams_recorder.config import load_settings
    from teams_recorder.constants import Files
    real = load_settings(PROJECT)
    if (real.data_dir / Files.ACTIVE_RECORDING).exists():
        raise SystemExit("stopped: a real recording is in progress; run again after the call")
    need = max(MIN_FREE_BYTES, 2 * real.raw_bytes_per_hour)
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path).free
    if free < need:
        raise SystemExit(f"stopped: {free / 1e9:.1f} GB free on the data volume, the recorder needs {need / 1e9:.1f} GB; free space and run again")


# --- render -------------------------------------------------------------------------------
def say_to_frames(text: str, voice_spec: str, tmp: Path) -> bytes:
    """`voice_spec` is "<voice>" or "<voice>:<words per minute>"."""
    voice, _, rate = voice_spec.partition(":")
    out = tmp / "turn.wav"
    subprocess.run(["say", "-v", voice, "-r", rate or str(SPEECH_RATE), f"--data-format=LEI16@{SAMPLE_RATE}", "-o", str(out), text],
                   check=True)
    with wave.open(str(out), "rb") as w:
        if w.getframerate() != SAMPLE_RATE or w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise SystemExit(f"unexpected `say` output format for voice {voice}")
        return w.readframes(w.getnframes())


def silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(SAMPLE_RATE * seconds)


def write_wav(path: Path, frames: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(frames)


def raw_track(src: Path, out: Path, channels: int, bit_depth: int, noise: float) -> None:
    """A raw track as the recorder writes it: 48 kHz, `bit_depth` bits, mono (microphone) or
    stereo (Teams), with pink room noise mixed in when `noise` > 0."""
    from teams_recorder.constants import Audio
    room = (["-filter_complex", f"anoisesrc=color=pink:amplitude={noise}:sample_rate={SAMPLE_RATE}[n];"
                                f"[0:a][n]amix=inputs=2:duration=first:normalize=0"] if noise > 0 else [])
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), *room, "-ac", str(channels), "-ar", str(Audio.SAMPLE_RATE),
                    "-c:a", Audio.WAV_CODECS[bit_depth], str(out)], check=True)


def render(args: argparse.Namespace) -> None:
    """Two raw tracks per meeting, like a real call (the user on the microphone, everyone else on
    the Teams track, each silent while the other side speaks), mixed into audio.m4a by the
    project's own FfmpegMixer with the bitrate, bit depth and denoise settings of config.toml."""
    from teams_recorder.domain.status import MIC_TRACK, TAP_TRACK
    corpus = load_corpus()
    voices: dict[str, str] = corpus["voices"]
    user = corpus.get("user", "Felipe")
    container = container_for(args.data)
    settings = container.settings
    recordings = args.data / "recordings"
    for meeting in corpus["meeting"]:
        mid = meeting["id"]
        folder = recordings / mid
        if (folder / "audio.m4a").exists() and not args.force:
            print(f"{mid}: audio exists, skipped")
            continue
        disk_guard(args.data)
        folder.mkdir(parents=True, exist_ok=True)
        mic, tap = bytearray(), bytearray()
        (args.data / ".tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=args.data / ".tmp") as tmp:   # never /var/folders: `clean` frees everything
            for speaker, text in parse_script(CORPUS / meeting["script"]):
                if speaker == "[pause]":
                    gap = silence(float(text))
                    mic += gap
                    tap += gap
                    continue
                if speaker not in voices:
                    raise SystemExit(f"{mid}: no voice for speaker {speaker!r}")
                turn = say_to_frames(text, voices[speaker], Path(tmp)) + silence(TURN_GAP_SECONDS)
                (mic if speaker == user else tap).extend(turn)
                (tap if speaker == user else mic).extend(silence(len(turn) / 2 / SAMPLE_RATE))
            tracks = []
            for name, frames, channels in ((MIC_TRACK, mic, 1), (TAP_TRACK, tap, 2)):
                if any(frames):  # a side nobody speaks on (a solo test recording) gets no track
                    src = Path(tmp) / f"src-{name}"
                    write_wav(src, bytes(frames))
                    raw_track(src, folder / name, channels, settings.bit_depth, args.noise if name == MIC_TRACK else 0.0)
                    tracks.append(folder / name)
            container.mixer.mix(tracks, folder / "audio.m4a")
            for track in tracks:   # the recorder deletes the raw tracks once the mix succeeds
                track.unlink(missing_ok=True)
        seconds = len(mic) / 2 / SAMPLE_RATE
        start = datetime.strptime(mid, "%Y-%m-%d_%H-%M-%S")
        meta = {"id": mid, "started_at": start.isoformat(), "ended_at": (start + timedelta(seconds=seconds)).isoformat(timespec="seconds"),
                "pid": None, "title": None}
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{mid}: {seconds / 60:.1f} min of audio")


# --- process ------------------------------------------------------------------------------
def container_for(data: Path, cli_model: str | None = None) -> Any:
    from teams_recorder.config import load_settings
    from teams_recorder.container import build_container
    settings = dataclasses.replace(load_settings(PROJECT), data_dir=data)  # models stay in the real models dir
    if cli_model:
        settings = dataclasses.replace(settings, llm_cli_model=cli_model)
    return build_container(settings, headless=True)


def link_fillers(fillers: Path, data: Path) -> set[str]:
    """Distractor meetings enter a run as symlinks to their transcripts (no copies); the analysis
    then writes its own files next to the links."""
    from teams_recorder.domain.status import META, TRANSCRIPT_JSON, TRANSCRIPT_TXT
    ids = set()
    for src in sorted((fillers / "recordings").iterdir()):
        dst = data / "recordings" / src.name
        dst.mkdir(parents=True, exist_ok=True)
        for name in (META, TRANSCRIPT_JSON, TRANSCRIPT_TXT):
            if not (dst / name).exists():
                (dst / name).symlink_to(src / name)
        ids.add(src.name)
    return ids


def process(args: argparse.Namespace) -> None:
    from teams_recorder.domain.status import ANALYSIS, AUDIO, TRANSCRIPT_JSON
    c = container_for(args.data)
    fillers = link_fillers(args.fillers, args.data) if args.fillers else set()
    # Distractors are scenery: analyzing them with a cheaper model saves quota without touching
    # what is measured (the planted meetings use the project's own model).
    filler_c = container_for(args.data, cli_model=args.filler_model) if fillers else c
    meetings = sorted(c.repo.list_meetings(), key=lambda m: m.id)
    for meeting in meetings:   # whisper one at a time: it already uses half the cores
        t0 = time.monotonic()
        if TRANSCRIPT_JSON not in c.repo.files(meeting.id):
            disk_guard(args.data)
            transcript = c.transcribe_meeting().execute(meeting.id)
            print(f"{meeting.id}: transcribed, {len(transcript.segments)} segments ({time.monotonic() - t0:.0f} s)")
        if AUDIO in c.repo.files(meeting.id) and TRANSCRIPT_JSON in c.repo.files(meeting.id) and not args.keep_audio:
            c.repo.delete_file(meeting.id, AUDIO)   # never read again once transcribed
    if args.transcribe_only:
        return

    def analyze(meeting_id: str) -> str:
        t1 = time.monotonic()
        analysis = (filler_c if meeting_id in fillers else c).analyze_meeting().execute(meeting_id)
        return f"{meeting_id}: analyzed '{analysis.title}', {len(analysis.my_actions)} own actions ({time.monotonic() - t1:.0f} s)"

    todo = [m.id for m in meetings if ANALYSIS not in c.repo.files(m.id)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:   # one model call per meeting, independent
        for line in pool.map(analyze, todo):
            print(line)


# --- ask ----------------------------------------------------------------------------------
def claude_env() -> dict[str, str]:
    from teams_recorder.adapters.outbound.llm_transport import claude_code_env
    return claude_code_env()


def minutes_context(data: Path) -> str:
    parts = []
    for folder in sorted((data / "recordings").iterdir()):
        minutes = folder / "minutes.md"
        if minutes.exists():
            parts.append(f"## Reunião {folder.name}\n\n{minutes.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def ask_once(question: dict[str, Any], condition: str, data: Path, wiki: Path, settings: Any, neutral_cwd: Path) -> dict[str, Any]:
    base = ["claude", "-p", "--output-format", "json", "--no-session-persistence", "--model", settings.llm_cli_model,
            "--effort", str(settings.llm_effort)]
    if condition == "minutes":
        cmd = [*base, "--tools", "", "--system-prompt", MINUTES_SYSTEM]
        stdin = f"Pergunta: {question['text']}\n\n# Atas das reuniões\n\n{minutes_context(data)}"
        cwd = neutral_cwd
    else:
        system = (wiki / "CLAUDE.md").read_text(encoding="utf-8") + WIKI_SYSTEM_SUFFIX
        cmd = [*base, "--tools", WIKI_TOOLS, "--allowedTools", WIKI_TOOLS, "--system-prompt", system]
        stdin = f"Pergunta: {question['text']}"
        cwd = wiki
    t0 = time.monotonic()
    result = subprocess.run(cmd, input=stdin, capture_output=True, text=True, cwd=cwd, env=claude_env(), timeout=900, check=False)
    seconds = time.monotonic() - t0
    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError:
        envelope = {"is_error": True, "result": (result.stdout or result.stderr)[-500:]}
    usage = envelope.get("usage") or {}
    return {
        "question": question["id"], "condition": condition, "answer": str(envelope.get("result", "")),
        "error": bool(envelope.get("is_error")) or result.returncode != 0, "seconds": round(seconds, 1),
        "input_tokens": sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")),
        "output_tokens": int(usage.get("output_tokens") or 0), "cost_usd_equiv": envelope.get("total_cost_usd"),
        "turns": envelope.get("num_turns"),
    }


def ask(args: argparse.Namespace) -> None:
    from teams_recorder.config import load_settings
    settings = load_settings(PROJECT)
    wiki = args.wiki or args.data / "wiki"
    questions = load_questions(args.questions)
    if args.only:
        questions = [q for q in questions if q["id"] in set(args.only.split(","))]
    args.out.mkdir(parents=True, exist_ok=True)
    answers_path = args.out / "answers.jsonl"
    done = set()
    if answers_path.exists():
        for line in answers_path.read_text(encoding="utf-8").splitlines():
            a = json.loads(line)
            if not a["error"]:
                done.add((a["question"], a["condition"], a["run"]))
    jobs = [(q, cond, run) for run in range(1, args.runs + 1) for cond in args.conditions.split(",") for q in questions
            if (q["id"], cond, run) not in done]
    print(f"{len(jobs)} answers to produce ({len(done)} already done) → {answers_path}")
    lock = threading.Lock()
    with tempfile.TemporaryDirectory() as neutral, concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(ask_once, q, cond, args.data, wiki, settings, Path(neutral)): (q, cond, run) for q, cond, run in jobs}
        for future in concurrent.futures.as_completed(futures):
            q, cond, run = futures[future]
            row = {**future.result(), "run": run}
            with lock, answers_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"  {q['id']:<28} {cond:<8} run {run}: {'ERROR' if row['error'] else 'ok'} ({row['seconds']} s, {row['input_tokens']} in)")


# --- score --------------------------------------------------------------------------------
def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def code_checks(question: dict[str, Any], answer: str) -> tuple[bool, list[str], bool]:
    """(passed, failures, fabricated): fabricated = a must_not_include hit."""
    text = norm(answer)
    failures = [f"missing one of {alts}" for alts in question.get("must_include", []) if not any(norm(a) in text for a in alts)]
    hits = [s for s in question.get("must_not_include", []) if norm(s) in text]
    failures += [f"contains forbidden {s!r}" for s in hits]
    failures += [f"no citation of {alts}" for alts in question.get("must_cite", []) if not any(norm(a) in text for a in alts)]
    return not failures, failures, bool(hits)


def judge(question: dict[str, Any], answer: str, transport: Any) -> tuple[bool, str]:
    from pydantic import BaseModel

    class JudgeOut(BaseModel):
        critique: str
        verdict: Literal["PASS", "FAIL"]

    user = f"Question: {question['text']}\n\nRubric: {question['judge']}\n\nAnswer:\n{answer}"
    out = transport.complete(JUDGE_SYSTEM, user, JudgeOut, tag=f"wiki-eval-judge:{question['id']}")
    return out.verdict == "PASS", out.critique


def score(args: argparse.Namespace) -> None:
    questions = {q["id"]: q for q in load_questions(args.questions)}
    rows = [json.loads(line) for line in (args.run / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if not r["error"]]
    judged_path = args.run / "judged.jsonl"
    judged = {(r["question"], r["condition"], r["run"]): r for r in map(json.loads, judged_path.read_text(encoding="utf-8").splitlines())} \
        if judged_path.exists() else {}
    from teams_recorder.config import load_settings
    from teams_recorder.container import build_transport
    settings = dataclasses.replace(load_settings(PROJECT), data_dir=args.run)   # judge usage logged under the run
    transport = build_transport(settings)

    def grade(row: dict[str, Any]) -> dict[str, Any] | None:
        q = questions[row["question"]]
        ok, failures, fabricated = code_checks(q, row["answer"])
        verdict, critique = (True, "")
        if q.get("judge"):
            try:
                verdict, critique = judge(q, row["answer"], transport)
            except Exception as exc:  # noqa: BLE001 - e.g. the subscription's session limit: retried on the next `score`
                print(f"  judge failed for {row['question']} {row['condition']} run {row['run']}: {str(exc)[:120]}")
                return None
        return {**row, "code_ok": ok, "failures": failures, "fabricated": fabricated, "judge_ok": verdict,
                "critique": critique, "passed": ok and verdict}

    todo = [r for r in rows if (r["question"], r["condition"], r["run"]) not in judged]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for graded in pool.map(grade, todo):
            if graded is None:
                continue
            judged[(graded["question"], graded["condition"], graded["run"])] = graded
            with judged_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(graded, ensure_ascii=False) + "\n")
    write_report(args.run, questions, list(judged.values()))


def write_report(run: Path, questions: dict[str, dict[str, Any]], graded: list[dict[str, Any]]) -> None:
    conditions = sorted({g["condition"] for g in graded}, key=lambda c: CONDITIONS.index(c) if c in CONDITIONS else 9)
    categories = list(dict.fromkeys(q["category"] for q in questions.values()))
    by: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for g in graded:
        by.setdefault((g["question"], g["condition"]), []).append(g)
    lines = [f"# Wiki evaluation: {run.name}", "", f"Generated {datetime.now():%Y-%m-%d %H:%M}. pass^k = passed every run; pass@k = passed at least one run.", ""]
    lines += ["## By category", "", "| Category | " + " | ".join(f"{c} pass^k | {c} pass@k" for c in conditions) + " |",
              "|---|" + "---|---|" * len(conditions)]
    for cat in categories + ["all"]:
        ids = [qid for qid, q in questions.items() if cat == "all" or q["category"] == cat]
        cells = []
        for c in conditions:
            groups = [by[(qid, c)] for qid in ids if (qid, c) in by]
            all_k = sum(all(g["passed"] for g in grp) for grp in groups)
            any_k = sum(any(g["passed"] for g in grp) for grp in groups)
            cells.append(f"{all_k}/{len(groups)} | {any_k}/{len(groups)}")
        lines.append(f"| {cat} | " + " | ".join(cells) + " |")
    lines += ["", "## Cost per answer (median)", "", "| Condition | input tokens | output tokens | seconds | fabricated (must_not_include hits) |", "|---|---|---|---|---|"]
    for c in conditions:
        rows = [g for g in graded if g["condition"] == c]
        med = lambda key: sorted(r[key] for r in rows)[len(rows) // 2] if rows else 0  # noqa: E731
        lines.append(f"| {c} | {med('input_tokens')} | {med('output_tokens')} | {med('seconds')} | {sum(r['fabricated'] for r in rows)} |")
    lines += ["", "## Per question", "", "| Question | Category | " + " | ".join(conditions) + " |", "|---|---|" + "---|" * len(conditions)]
    for qid, q in questions.items():
        cells = []
        for c in conditions:
            grp = sorted(by.get((qid, c), []), key=lambda g: g["run"])
            cells.append("".join("✓" if g["passed"] else "✗" for g in grp) or "—")
        lines.append(f"| {qid} | {q['category']} | " + " | ".join(cells) + " |")
    lines += ["", "## Failures", ""]
    for g in sorted(graded, key=lambda g: (g["question"], g["condition"], g["run"])):
        if not g["passed"]:
            why = "; ".join(g["failures"] + ([f"judge: {g['critique']}"] if not g["judge_ok"] else []))
            lines.append(f"- **{g['question']}** · {g['condition']} · run {g['run']}: {why}")
    (run / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report: {run / 'report.md'}")


# --- fill (scale test distractors) --------------------------------------------------------
FILLER_PROJECTS = [  # fictional; near-duplicate names of the planted cast on purpose, to stress retrieval
    ("Portal do Fornecedor", "Metalúrgica Serra Azul", ["Bruna Lemes (compradora da Serra Azul)", "Carlos Medeiros (TI da Serra Azul)", "Ana Tavares (gerente de projetos da nossa empresa)"]),
    ("App de Inspeção de Redes", "Energia Vale Verde", ["José Ferreira (supervisor de campo da Vale Verde, chamado de Ferreira)", "Tânia Rocha (analista da Vale Verde)"]),
    ("Migração para a nuvem", "projeto interno", ["Ana Tavares (gerente de projetos)", "Diego Santos (infraestrutura)"]),
    ("Dashboard de Vendas", "Rede de Farmácias Bom Preço", ["Paulo Rezende (diretor comercial da Bom Preço)", "Lívia Nunes (analista de dados da Bom Preço)"]),
    ("Integração com o ERP", "Cooperativa Agro Sul", ["Rafaela Costa (controladora da Agro Sul)", "Marcos Teixeira (TI da Agro Sul)"]),
    ("Chatbot de Atendimento", "Seguradora Atlântica", ["Mariana Lopes (gerente de atendimento da Atlântica)", "Otávio Prado (TI da Atlântica)"]),
    ("Auditoria de segurança", "projeto interno", ["Diego Santos (infraestrutura e segurança)", "Ana Tavares (gerente de projetos)"]),
    ("Onboarding do novo desenvolvedor", "projeto interno", ["Lucas Prado (desenvolvedor recém-contratado)", "Ana Tavares (gerente de projetos)"]),
    ("Sistema de Ponto Eletrônico", "Construtora Horizonte", ["Fernanda Dias (RH da Construtora Horizonte)", "Gustavo Lima (engenheiro da obra)"]),
]
# Planted names and topics (tests/fixtures/wiki_corpus) a distractor must never mention: it would
# change the answer key. Matched on accent-free lowercase text.
FILLER_FORBIDDEN = [r"\bpampa\b", r"rota ?facil", r"santa clara", r"agenda ?clara", r"\bcarla\b", r"\bbruno\b", r"\bfontes\b",
                    r"\bze\b", r"\bpaula\b", r"\brafael\b", r"mapbox", r"google maps", r"whatsapp", r"quilometragem", r"\bfrota",
                    r"porto alegre", r"pelotas", r"meta business", r"cardiolog", r"lembretes? (de consulta|por sms|pelo sms)",
                    r"\bana\b.{0,60}\bferias|\bferias\b.{0,60}\bana\b"]   # Ana's vacation is a planted fact
FILLER_SLOTS = ("08:30:00", "10:30:00", "13:30:00", "15:30:00", "17:00:00")
WORDS_PER_SECOND = 2.6

FILL_ARC_SYSTEM = """You design the storyline of one fictional project for a test corpus of work meetings. The user, Felipe, is a developer and tech lead at a software company and is in every meeting. Return exactly the number of beats asked for, one per meeting, in order. Each beat says, in 3 to 5 sentences of Brazilian Portuguese, what that meeting discusses with concrete facts: decisions, actions with owner and due date, numbers, blockers. Across the beats include at least: one deadline that changes, one decision that is reversed later, one blocker that recurs and is eventually resolved, and one tentative statement confirmed later. Use only the people listed plus Felipe. Never mention anything in the forbidden list."""

FILL_TRANSCRIPT_SYSTEM = """You write the raw speech-to-text transcript of one work meeting in Brazilian Portuguese, as whisper.cpp outputs it for a Teams call: segments of 5 to 20 words, no speaker names or labels, no timestamps; natural speech with fillers (né, tipo, então, beleza), interruptions, a little small talk at the start and end, some repetition and a few recognition errors (an occasional misheard word, missing punctuation). People sometimes address each other by name, as in real calls. Length: 1,300 to 1,800 words in total. The content is exactly what the beat says, with realistic detail around it; add no decision, action or date beyond the beat. Never mention anything in the forbidden list."""


def filler_schedule(count: int) -> list[str]:
    """Meeting ids on working days from 2026-01-05, four or five a day, at times that never clash
    with the planted meetings."""
    days, day = [], datetime(2026, 1, 5)
    while len(days) * 4 < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    ids = [f"{d:%Y-%m-%d}_{slot.replace(':', '-')}" for d in days for slot in FILLER_SLOTS[:4]]
    extra = [f"{d:%Y-%m-%d}_{FILLER_SLOTS[4].replace(':', '-')}" for d in days]
    return sorted((ids + extra)[:count]) if count > len(ids) else sorted(ids[:count])


def forbidden_hits(text: str) -> list[str]:
    plain = norm(text)
    return [p for p in FILLER_FORBIDDEN if re.search(p, plain)]


def fill(args: argparse.Namespace) -> None:
    from pydantic import BaseModel

    from teams_recorder.adapters.outbound.llm_transport import ClaudeCodeTransport
    from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
    from teams_recorder.domain import Meeting, Segment, Transcript

    class ArcOut(BaseModel):
        beats: list[str]

    class TranscriptOut(BaseModel):
        segments: list[str]

    disk_guard(args.out)
    transport = ClaudeCodeTransport(model=args.model, effort="medium", usage_log=args.out / "log" / "llm_usage.jsonl")
    repo = FsMeetingRepository(args.out)
    ids = filler_schedule(args.count)
    plan: dict[str, tuple[int, int]] = {mid: (i % len(FILLER_PROJECTS), i // len(FILLER_PROJECTS)) for i, mid in enumerate(ids)}
    arcs_path = args.out / "arcs.json"
    arcs: dict[str, list[str]] = json.loads(arcs_path.read_text(encoding="utf-8")) if arcs_path.exists() else {}

    def arc(p: int) -> list[str]:
        name, client, cast = FILLER_PROJECTS[p]
        dates = [mid[:10] for mid, (pp, _) in plan.items() if pp == p]
        user = (f"Project: {name}. Client: {client}. People: {'; '.join(cast)}.\nNumber of beats: {len(dates)}; meeting dates in order: "
                f"{', '.join(dates)}.\nForbidden (never mention): {', '.join(FILLER_FORBIDDEN)} (regular expressions over lowercase text without accents).")
        for _ in range(3):
            out = transport.complete(FILL_ARC_SYSTEM, user, ArcOut, tag=f"wiki-fill-arc:{p}")
            if len(out.beats) == len(dates) and not forbidden_hits(" ".join(out.beats)):
                return out.beats
        raise SystemExit(f"could not generate a clean arc for {name}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        missing = [p for p in range(len(FILLER_PROJECTS)) if str(p) not in arcs and any(pp == p for pp, _ in plan.values())]
        for p, beats in zip(missing, pool.map(arc, missing)):
            arcs[str(p)] = beats
            arcs_path.write_text(json.dumps(arcs, ensure_ascii=False, indent=1), encoding="utf-8")

    def transcript(mid: str) -> str:
        p, k = plan[mid]
        name, client, cast = FILLER_PROJECTS[p]
        beats = arcs[str(p)]
        user = (f"Project: {name}. Client: {client}. People: {'; '.join(cast)}; Felipe.\nMeeting date: {mid[:10]}.\n"
                f"Earlier meetings of this project: {' | '.join(beats[:k]) or 'none'}\nTHIS meeting: {beats[k]}\n"
                f"Forbidden (never mention): {', '.join(FILLER_FORBIDDEN)} (regular expressions over lowercase text without accents).")
        feedback = ""
        for _ in range(4):
            out = transport.complete(FILL_TRANSCRIPT_SYSTEM, user + feedback, TranscriptOut, tag=f"wiki-fill:{mid}")
            words = sum(len(s.split()) for s in out.segments)
            hits = forbidden_hits(" ".join(out.segments))
            if words >= 900 and not hits:
                break
            feedback = (f"\n\nYour previous attempt was rejected: {words} words"
                        + (f"; it matched the forbidden patterns {hits}" if hits else "") + ". Write it again without that.")
        else:
            return f"{mid}: FAILED ({words} words, forbidden {hits}); run `fill` again to retry"
        t, segments = 0.0, []
        for text in (s.strip() for s in out.segments if s.strip()):
            length = max(1.0, len(text.split()) / WORDS_PER_SECOND)
            segments.append(Segment(round(t, 2), round(t + length, 2), text))
            t += length + 0.3
        start = datetime.strptime(mid, "%Y-%m-%d_%H-%M-%S")
        if not repo.exists(mid):
            repo.create(Meeting(id=mid, started_at=start, ended_at=start + timedelta(seconds=t)))
        repo.save_transcript(mid, Transcript(segments=segments))
        return f"{mid}: {name}, {words} words"

    todo = [mid for mid in ids if not (args.out / "recordings" / mid / "transcript.json").exists()]
    print(f"{len(todo)} distractor transcripts to generate ({len(ids) - len(todo)} already there) → {args.out}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for line in pool.map(transcript, todo):
            print(" ", line)


# --- ingest -------------------------------------------------------------------------------
def ingest(args: argparse.Namespace) -> None:
    """One fresh Claude Code process per meeting, oldest first, inside the wiki folder (so it
    loads the wiki's CLAUDE.md), with file tools only; the script commits after each one."""
    from teams_recorder.config import load_settings
    from teams_recorder.domain.status import ANALYSIS
    settings = load_settings(PROJECT)
    wiki = args.wiki or args.data / "wiki"
    recordings = args.data / "recordings"
    done_path = wiki / INGESTED_FILE
    done = set(done_path.read_text(encoding="utf-8").split()) if done_path.exists() else set()
    todo = [d.name for d in sorted(recordings.iterdir()) if (d / ANALYSIS).exists() and d.name not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} meetings to ingest ({len(done)} already in the wiki)")
    log_path = args.data / "ingest.jsonl"
    # Distractors are scenery: a cheaper model and effort for them (user decision, 2026-10-10:
    # the agent-loop ingest cost US$ 1.59 per meeting on Opus); planted meetings keep the
    # project's own model, which is what the evaluation measures.
    fillers = {d.name for d in (args.fillers / "recordings").iterdir()} if args.fillers else set()
    for mid in todo:
        model, effort = ((args.filler_model, args.filler_effort) if mid in fillers
                         else (args.model or settings.llm_cli_model, args.effort or str(settings.llm_effort)))
        disk_guard(args.data)
        prompt = (f"Ingest the meeting {mid} into this wiki, following CLAUDE.md exactly (read it first). Its sources are "
                  f"../recordings/{mid}/analysis.json and ../recordings/{mid}/transcript.txt. Use only that meeting's sources and the "
                  f"current wiki pages; never open another meeting's sources. Never modify anything under ../recordings. Do not run git. "
                  f"When done, reply with one line listing the pages created and updated.")
        cmd = ["claude", "-p", "--output-format", "json", "--no-session-persistence", "--model", model,
               "--effort", effort, "--tools", INGEST_TOOLS, "--allowedTools", INGEST_TOOLS,
               "--permission-mode", "acceptEdits", "--add-dir", str(recordings)]
        t0 = time.monotonic()
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=wiki, env=claude_env(), timeout=1800, check=False)
        try:
            envelope = json.loads(result.stdout)
        except json.JSONDecodeError:
            envelope = {"is_error": True, "result": (result.stdout or result.stderr)[-500:]}
        usage = envelope.get("usage") or {}
        row = {"meeting": mid, "model": model, "effort": effort, "seconds": round(time.monotonic() - t0), "error": bool(envelope.get("is_error")) or result.returncode != 0,
               "turns": envelope.get("num_turns"), "cost_usd_equiv": envelope.get("total_cost_usd"),
               "input_tokens": sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")),
               "result": str(envelope.get("result", ""))[:300]}
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        if row["error"]:
            raise SystemExit(f"{mid}: ingest failed ({row['result'][:200]}); fix it and run again to resume")
        subprocess.run(["git", "-C", str(wiki), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(wiki), "commit", "-q", "--allow-empty", "-m", f"ingest {mid}"], check=True)
        with done_path.open("a", encoding="utf-8") as fh:
            fh.write(mid + "\n")
        print(f"{mid}: ingested with {model} in {row['seconds']} s, {row['turns']} turns, US$ {row['cost_usd_equiv'] or 0:.2f} eq. — {row['result'][:100]}")


# --- clean --------------------------------------------------------------------------------
def clean(args: argparse.Namespace) -> None:
    """Free a data dir's recordings, temporary files and logs; the wiki and runs/ stay."""
    for name in ("recordings", ".tmp", "log"):
        target = args.data / name
        if target.exists():
            size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file() and not f.is_symlink())
            shutil.rmtree(target)
            print(f"removed {target} ({size / 1e6:.1f} MB)")


# --- autorun (unattended scale test) -----------------------------------------------------
RESET_PATTERN = r"resets (\d{1,2})(?::(\d{2}))?\s*(am|pm)"


def wait_for_reset(message: str) -> bool:
    """Sleep until the subscription window named in `message` reopens (plus two minutes).
    False when the message is not a session-limit error."""
    m = re.search(RESET_PATTERN, message)
    if "limit" not in message or not m:
        return False
    hour, minute, half = int(m.group(1)) % 12, int(m.group(2) or 0), m.group(3)
    now = datetime.now()
    at = now.replace(hour=hour + (12 if half == "pm" else 0), minute=minute, second=0, microsecond=0) + timedelta(minutes=2)
    if at <= now:
        at += timedelta(days=1)
    print(f"[{now:%H:%M}] session limit reached; waiting until {at:%H:%M}", flush=True)
    time.sleep((at - now).total_seconds())
    return True


def autorun(args: argparse.Namespace) -> None:
    """ingest → ask → score, resuming each step after the subscription's five-hour window
    resets. Any other failure stops the run (rerun `autorun` to resume)."""
    me = [sys.executable, "-u", str(Path(__file__).resolve())]
    data = ["--data", str(args.data)]
    run = args.data / "runs" / args.run_name
    while True:   # ingest
        result = subprocess.run([*me, "ingest", *data, *(["--fillers", str(args.fillers)] if args.fillers else [])],
                                capture_output=True, text=True, check=False)
        print(result.stdout[-2000:], result.stderr[-1000:], flush=True)
        if result.returncode == 0:
            break
        if not wait_for_reset(result.stdout + result.stderr):
            raise SystemExit("ingest stopped for a reason other than the session limit; see above")
    for step in ("ask", "score"):
        while True:
            cmd = [*me, "ask", *data, "--runs", str(args.runs), "--jobs", str(args.jobs), "--out", str(run)] if step == "ask" \
                else [*me, "score", "--run", str(run), "--jobs", str(args.jobs)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            print(result.stdout[-2000:], result.stderr[-1000:], flush=True)
            errors = [json.loads(line) for line in (run / "answers.jsonl").read_text(encoding="utf-8").splitlines()] if step == "ask" else []
            done = {(e["question"], e["condition"], e["run"]) for e in errors if not e["error"]}
            pending = [e for e in errors if e["error"] and (e["question"], e["condition"], e["run"]) not in done]
            if step == "score":
                judged = run / "judged.jsonl"
                total = sum(1 for e in map(json.loads, (run / "answers.jsonl").read_text(encoding="utf-8").splitlines()) if not e["error"])
                missing = total - (sum(1 for _ in judged.open(encoding="utf-8")) if judged.exists() else 0)
                if missing <= 0 and result.returncode == 0:
                    break
                if not wait_for_reset(result.stdout + result.stderr):
                    raise SystemExit("score stopped for a reason other than the session limit; see above")
                continue
            if result.returncode == 0 and not pending:
                break
            if not wait_for_reset(" ".join(e["answer"] for e in pending[-3:]) + result.stdout + result.stderr):
                raise SystemExit("ask stopped for a reason other than the session limit; see above")
    print(f"done: {run / 'report.md'}", flush=True)


# --- CLI ----------------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("render")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--noise", type=float, default=0.004, help="pink room-noise amplitude on the microphone track (0 = none)")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("process")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--transcribe-only", action="store_true", help="local whisper only, no model calls")
    p.add_argument("--keep-audio", action="store_true", help="keep audio.m4a after transcription (default: delete it)")
    p.add_argument("--fillers", type=Path, help="distractor meetings made by `fill`, linked into <data>")
    p.add_argument("--filler-model", default="sonnet", help="Claude Code model for analyzing the distractors")
    p.add_argument("--jobs", type=int, default=4)
    p = sub.add_parser("fill")
    p.add_argument("--out", type=Path, required=True, help="e.g. data/wiki-eval/corpus-fillers (ignored by Git)")
    p.add_argument("--count", type=int, default=81)
    p.add_argument("--model", default="sonnet")
    p.add_argument("--jobs", type=int, default=4)
    p = sub.add_parser("ingest")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--wiki", type=Path, help="default: <data>/wiki")
    p.add_argument("--model", help="default: llm.cli_model from config.toml")
    p.add_argument("--effort", help="default: llm.effort from config.toml")
    p.add_argument("--limit", type=int, help="ingest at most this many meetings")
    p.add_argument("--fillers", type=Path, help="distractor meetings (from `fill`): ingested with --filler-model")
    p.add_argument("--filler-model", default="sonnet")
    p.add_argument("--filler-effort", default="medium")
    p = sub.add_parser("clean")
    p.add_argument("--data", type=Path, required=True)
    p = sub.add_parser("autorun", help="ingest, ask and score unattended, waiting out the subscription's session limit")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--fillers", type=Path)
    p.add_argument("--run-name", default="scale-r1")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--jobs", type=int, default=4)
    p = sub.add_parser("ask")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--wiki", type=Path, help="default: <data>/wiki")
    p.add_argument("--questions", type=Path, default=CORPUS / "questions.toml")
    p.add_argument("--conditions", default=",".join(CONDITIONS))
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--only", help="comma-separated question ids")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("score")
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--questions", type=Path, default=CORPUS / "questions.toml")
    p.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    for name in ("data", "out", "run", "wiki", "fillers"):
        if getattr(args, name, None) is not None:
            setattr(args, name, getattr(args, name).expanduser().resolve())
    {"render": render, "process": process, "ask": ask, "score": score, "fill": fill, "ingest": ingest,
     "clean": clean, "autorun": autorun}[args.command](args)


if __name__ == "__main__":
    main()
