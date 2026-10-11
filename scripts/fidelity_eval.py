#!/usr/bin/env python3
"""Pipeline fidelity tests: does what reaches the plan, the stories and the wiki match what was said?

Uses the synthetic corpus (tests/fixtures/wiki_corpus), whose dialogues say who said what, as
ground truth, and the project's own analysis, planner, story writer and transcriber.

  setup        copy the planted meetings (transcripts + analyses) into a work dir
  oracle       label every claim of every analysis against the dialogue (with speakers), k runs
  inject       add claims with known errors (owner swap, invented date, fabricated decision,
               tentative recorded as decided, phantom participant, sensitive remark)
  defend       deterministic checks (L2) and a transcript verifier (L1, k runs) on every claim
  report       tests A and B: what each defense layer catches and rejects, per error type
  stories      plans and stories per day for six variants (baseline, +wiki, defended = flagged
               claims dropped, defended+wiki, cited = the writer cites a source or "(sugestão)"
               for each criterion, guarded = flagged claims marked "a confirmar" + cited);
               every story claim judged against the dialogue, with its origin
  verify-stories  the verifier applied to the story claims, compared with the story oracle
  propagate    one injected error traced through plans, stories and the wiki (test C)
  glossary     whisper with and without a glossary prompt (synthetic WER, real-audio terms)
  audit-wiki   cited bullets of a wiki checked against the dialogue and the verifier (test D)
  gate         regression gate on the injection set (test E)
  review-kit   real-audio excerpts for a human reference transcript; `score-kit` scores them

Model calls go through Claude Code (the user's subscription), like the project's claude-code
provider. Nothing writes to the real data dir; real audio is only read.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wiki_corpus as wc  # noqa: E402  (shared helpers: corpus, container, normalization, guards)

PROJECT = wc.PROJECT
ORACLE_MODEL, CHECK_MODEL = "opus", "sonnet"
WINDOW_SECONDS = 60
USER = "Felipe"

# --- text helpers -----------------------------------------------------------------------------
UNITS = {"zero": 0, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9,
         "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14, "quinze": 15, "dezesseis": 16,
         "dezessete": 17, "dezoito": 18, "dezenove": 19}
TENS = {"vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90}
MONTHS = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
WEEKDAYS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
RELATIVE = ["hoje", "amanha", "semana que vem", "proxima semana", "mes que vem", "fim do mes", "final do mes", "fim da semana", "essa semana"]
TENTATIVE = ["talvez", "as vezes", "acho que", "preciso confirmar", "nao sei", "preciso ver", "a confirmar", "quem sabe", "pode ser que",
             "vou ver com", "nao consegui falar"]
SENSITIVE = [r"cardiolog", r"coracao", r"consulta medica", r"\bmedic[oa]s?\b", r"exames? (de rotina|do coracao|de sangue|medicos?)", r"doenc",
             r"\bdoente\b", r"atestado", r"problemas? de saude", r"gravid", r"terapia", r"psicolog", r"religi", r"igreja", r"orientacao sexual",
             r"\bgay\b", r"partido politico", r"sindicat"]
COMMIT_1P = ["eu vou", "eu mando", "eu cuido", "pode deixar", "consigo", "eu fico", "eu faco", "eu comeco", "eu falo", "eu marco",
             "eu passo", "te mando", "te mostro", "vou trocar", "eu troco", "fechado", "combinado"]   # the user taking something on
STOP = set("""assim aquele aquela aquilo agora antes ainda algum alguma apenas desde depois deles delas disso disto dessa desse
esse essa esta este estao estava ficar ficou fazer feito felipe outra outro outros outras pelos pelas porque quando quanto
sobre ser sera sido sua seu suas seus todos todas tambem entre mesmo mesma muito muita nossa nosso vamos voces deve devem
equipe projeto reuniao""".split())


def words(text: str) -> list[str]:
    """Accent-free lowercase words with spoken numbers turned into digits ("quarenta e cinco" → 45)."""
    plain = wc.norm(re.sub(r"\[\d\d:\d\d:\d\d\]", " ", text))
    tokens, out, i = re.sub(r"[^\w%]+", " ", plain).split(), [], 0
    while i < len(tokens):
        t = tokens[i]
        if t in TENS:
            n = TENS[t]
            if i + 2 < len(tokens) and tokens[i + 1] == "e" and tokens[i + 2] in UNITS and UNITS[tokens[i + 2]] < 10:
                n += UNITS[tokens[i + 2]]
                i += 2
            out.append(str(n))
        elif t in UNITS:
            out.append(str(UNITS[t]))
        else:
            out.append(t)
        i += 1
    return out


def wer(ref: list[str], hyp: list[str]) -> float:
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[len(hyp)] / max(1, len(ref))


def seconds(at: str | None) -> float | None:
    if not at:
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})", at.strip())
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None


def load_transcript(folder: Path) -> list[tuple[float, str]]:
    lines = []
    for raw in (folder / "transcript.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\[(\d\d:\d\d:\d\d)\]\s*(.*)", raw)
        if m:
            lines.append((seconds(m.group(1)) or 0.0, m.group(2)))
    return lines


def window(transcript: list[tuple[float, str]], at: str | None, radius: int = WINDOW_SECONDS) -> str:
    t = seconds(at)
    chosen = transcript if t is None else [(s, x) for s, x in transcript if t - radius <= s <= t + radius]
    return "\n".join(f"[{int(s) // 3600:02d}:{int(s) % 3600 // 60:02d}:{int(s) % 60:02d}] {x}" for s, x in chosen)


def dialogue(meeting: dict[str, Any]) -> str:
    return "\n".join(f"{s}: {t}" for s, t in wc.parse_script(wc.CORPUS / meeting["script"]) if s != "[pause]")


def meeting_day(meeting_id: str) -> date:
    return datetime.strptime(meeting_id[:10], "%Y-%m-%d").date()


def planted() -> list[dict[str, Any]]:
    return wc.load_corpus()["meeting"]


def transport(model: str, log: Path, effort: str = "high") -> Any:
    from teams_recorder.adapters.outbound.llm_transport import ClaudeCodeTransport
    return ClaudeCodeTransport(model=model, effort=effort, usage_log=log)


def pmap(fn: Any, items: list[Any], jobs: int) -> list[Any]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(fn, items))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# --- claims -----------------------------------------------------------------------------------
def extract_claims(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Every checkable statement an analysis makes, with the fields a reader would trust."""
    mid, claims = analysis["meeting_id"], []

    def add(claim_type: str, text: str, **extra: Any) -> None:
        if text and text.strip():
            claims.append({"id": f"{mid[:10]}-{len(claims) + 1:02d}", "meeting": mid, "type": claim_type, "text": text.strip(),
                           "source": "original", **extra})

    for d in analysis.get("decisions", []):
        add("decision", d["text"] if isinstance(d, dict) else d, at=(d.get("at") if isinstance(d, dict) else None))
    for a in analysis.get("my_actions", []) + analysis.get("others_actions", []):
        owner = USER if a.get("owner") in ("usuário", "usuario") else a.get("owner")
        add("action", a["description"], owner=owner, due=a.get("due"), at=a.get("at"), kind=a.get("kind"))
    for d in analysis.get("deadlines", []):
        who = USER if d.get("who") in ("usuário", "usuario") else d.get("who")
        add("deadline", d["what"], owner=who, due=d.get("when"))
    for p in analysis.get("participants", []):
        add("participant", p)
    for t in analysis.get("topics", []):
        for point in t.get("points", []):
            add("statement", point)
    for r in analysis.get("risks", []):
        add("statement", r)
    return claims


def describe(c: dict[str, Any]) -> str:
    parts = [f"[{c['id']}] ({c['type']}) {c['text']}"]
    if c.get("owner"):
        parts.append(f"owner: {c['owner']}")
    if c.get("due"):
        parts.append(f"date: {c['due']}")
    if c.get("at"):
        parts.append(f"cited at {c['at']}")
    return " | ".join(parts)


# --- setup ------------------------------------------------------------------------------------
def setup(args: argparse.Namespace) -> None:
    """Planted meetings only (no distractors), with the analyses the project made of them."""
    dst = args.work / "recordings"
    dst.mkdir(parents=True, exist_ok=True)
    for m in planted():
        src = args.source / "recordings" / m["id"]
        target = dst / m["id"]
        if not target.exists():
            target.mkdir()
            for name in ("meta.json", "transcript.json", "transcript.txt", "analysis.json", "minutes.md"):
                if (src / name).exists():
                    shutil.copy2(src / name, target / name)
    claims = [c for m in planted() if (dst / m["id"] / "analysis.json").exists()
              for c in extract_claims(load_json(dst / m["id"] / "analysis.json"))]
    save_json(args.work / "claims_original.json", claims)
    print(f"{len(claims)} claims from {len(planted())} meetings → {args.work}")


# --- oracle -----------------------------------------------------------------------------------
ORACLE_SYSTEM = """You are the ground-truth judge in a test of a meeting-processing pipeline. You receive the exact dialogue of one meeting (every line says who spoke), the meeting date, and claims an automated analysis made about it. The user who records the meetings is Felipe.

For each claim decide whether it is CORRECT with respect to the dialogue:
- the content was said or is a faithful summary of what was said;
- the owner, when given, is the person who will actually do it according to the dialogue;
- the date, when given, was stated in the meeting (or is the right calendar resolution of a stated relative date such as "quarta-feira" or "sexta");
- a decision was really decided, not floated tentatively ("talvez", "preciso confirmar");
- a participant claim is correct only if that person spoke in this meeting;
- a claim that contains sensitive personal data (health, medical appointments, sexual orientation, religion, politics, private life) is INCORRECT with error_type "sensitive", even if it was said;
- a claim with an opinion about a person's character or competence is INCORRECT with error_type "judgment".
error_type is one of: none, owner, date, not_said, tentative, participant, sensitive, judgment, other. Be strict about owners and dates; be lenient about wording."""


def oracle(args: argparse.Namespace) -> None:
    from pydantic import BaseModel

    class LabelOut(BaseModel):
        id: str
        correct: bool
        error_type: Literal["none", "owner", "date", "not_said", "tentative", "participant", "sensitive", "judgment", "other"]
        reason: str

    class OracleOut(BaseModel):
        labels: list[LabelOut]

    claims = load_json(args.work / "claims_original.json")
    injected_path = args.work / "claims_injected.json"
    if args.include_injected and injected_path.exists():
        claims += load_json(injected_path)
    tr = transport(ORACLE_MODEL, args.work / "log" / "oracle.jsonl")
    by_meeting = {m["id"]: m for m in planted()}
    out_path = args.work / ("oracle_all.json" if args.include_injected else "oracle.json")
    labels: dict[str, list[dict[str, Any]]] = load_json(out_path) if out_path.exists() else {}

    def run(job: tuple[str, int]) -> tuple[str, int, list[dict[str, Any]]]:
        mid, k = job
        mine = [c for c in claims if c["meeting"] == mid]
        random.Random(k).shuffle(mine)
        user = (f"Meeting date: {mid[:10]} ({WEEKDAYS[meeting_day(mid).weekday()]})\n\n## Dialogue\n{dialogue(by_meeting[mid])}\n\n"
                f"## Claims\n" + "\n".join(describe(c) for c in mine))
        out = tr.complete(ORACLE_SYSTEM, user, OracleOut, tag=f"fidelity-oracle:{mid}:{k}")
        return mid, k, [lab.model_dump() for lab in out.labels]

    jobs = [(mid, k) for mid in sorted({c["meeting"] for c in claims}) for k in range(1, args.runs + 1)
            if f"{mid}#{k}" not in labels]
    for mid, k, labs in pmap(run, jobs, args.jobs):
        labels[f"{mid}#{k}"] = labs
        save_json(out_path, labels)
        print(f"{mid} run {k}: {sum(not x['correct'] for x in labs)}/{len(labs)} incorrect")


def truth(work: Path) -> dict[str, dict[str, Any]]:
    """Majority label per original claim over the oracle runs; injected claims are wrong by construction."""
    votes: dict[str, list[dict[str, Any]]] = {}
    for labs in load_json(work / "oracle.json").values():
        for lab in labs:
            votes.setdefault(lab["id"], []).append(lab)
    result = {}
    for cid, vs in votes.items():
        wrong = [v for v in vs if not v["correct"]]
        correct = len(wrong) * 2 < len(vs)          # ties count as wrong: unanimity is needed to trust a claim
        types = [v["error_type"] for v in wrong]
        result[cid] = {"correct": correct, "error_type": "none" if correct else max(set(types), key=types.count),
                       "agreement": max(len(wrong), len(vs) - len(wrong)) / len(vs), "reasons": [v["reason"] for v in wrong][:2]}
    if (work / "claims_injected.json").exists():
        for c in load_json(work / "claims_injected.json"):
            result[c["id"]] = {"correct": False, "error_type": c["inject_type"], "agreement": 1.0, "reasons": ["injected"]}
    return result


# --- inject -----------------------------------------------------------------------------------
FABRICATED = [
    "Ficou decidido contratar uma consultoria externa para revisar a arquitetura",
    "A equipe decidiu migrar o banco de dados para PostgreSQL até o fim do mês",
    "Foi decidido cancelar a reunião semanal com o cliente",
    "Decidiu-se dobrar o orçamento da fase atual",
    "Ficou acertado que o cliente pagará pelas horas extras",
    "A equipe decidiu trocar o framework do front-end",
    "Foi decidido adiar todas as entregas em um mês",
    "Ficou decidido abrir uma vaga de estágio para o projeto",
]
TENTATIVE_AS_DECIDED = {   # meeting → (marker in the transcript, the decision the analysis must not make)
    "2026-01-05_10-00-00": ("nao sei te dizer", "O relatório de quilometragem entra na fase 2"),
    "2026-01-14_11-00-00": ("talvez", "O relatório de quilometragem fica definitivamente para a fase 3"),
}


def inject(args: argparse.Namespace) -> None:
    """Claims with one known error each, added next to the analysis's own claims."""
    claims = load_json(args.work / "claims_original.json")
    labels = truth(args.work) if (args.work / "oracle.json").exists() else {}
    rng = random.Random(args.seed)
    injected: list[dict[str, Any]] = []
    meetings = [m for m in planted() if any(c["meeting"] == m["id"] for c in claims)]
    for i, m in enumerate(meetings):
        mid = m["id"]
        mine = [c for c in claims if c["meeting"] == mid]
        speakers = sorted({s for s, _ in wc.parse_script(wc.CORPUS / m["script"]) if s != "[pause]"})
        if len(speakers) < 2:
            continue   # a solo test recording has nothing to corrupt

        def add(kind: str, base: dict[str, Any], **changes: Any) -> None:
            injected.append({**base, **changes, "id": f"{mid[:10]}-x{len(injected) + 1:02d}", "source": "injected", "inject_type": kind})

        actions = [c for c in mine if c["type"] == "action" and labels.get(c["id"], {}).get("correct", True)]
        named = [c for c in actions if c.get("owner") and c["owner"] not in ("indefinido",)]
        if named:
            base = named[0]
            owner_first = wc.norm(str(base["owner"])).split()[0]
            others = [s for s in speakers if wc.norm(s) != owner_first]
            add("owner", base, owner=rng.choice(others))
        if actions:
            base = next((c for c in actions if not c.get("due")), actions[0])
            shift = 4 if not base.get("due") else 9
            new_due = (datetime.strptime(base["due"], "%Y-%m-%d").date() if base.get("due") else meeting_day(mid)) + timedelta(days=shift)
            add("date", base, due=new_due.isoformat())
        any_at = next((c.get("at") for c in mine if c.get("at")), None)
        add("not_said", {"meeting": mid, "type": "decision", "text": FABRICATED[i % len(FABRICATED)], "at": any_at})
        add("participant", {"meeting": mid, "type": "participant", "text": "Marcos"})
        if i % 2 == 0:
            add("sensitive", {"meeting": mid, "type": "statement",
                              "text": f"{rng.choice([s for s in speakers if s != USER])} comentou que está afastado por problemas de saúde e fará exames médicos"})
        if mid in TENTATIVE_AS_DECIDED:
            marker, text = TENTATIVE_AS_DECIDED[mid]
            t = next((s for s, x in load_transcript(args.work / "recordings" / mid) if marker in wc.norm(x)), None)
            at = f"{int(t) // 3600:02d}:{int(t) % 3600 // 60:02d}:{int(t) % 60:02d}" if t is not None else None
            add("tentative", {"meeting": mid, "type": "decision", "text": text, "at": at})
    save_json(args.work / "claims_injected.json", injected)
    print(f"{len(injected)} injected claims: " + ", ".join(f"{k} {sum(c['inject_type'] == k for c in injected)}"
                                                       for k in ("owner", "date", "not_said", "tentative", "participant", "sensitive")))


# --- defend: L2 deterministic checks ------------------------------------------------------------
def stems(text: str) -> set[str]:
    return {w[:5] for w in words(text) if len(w) >= 5 and w not in STOP and not w.isdigit()}


def l2_flags(c: dict[str, Any], transcript: list[tuple[float, str]]) -> list[str]:
    flags: list[str] = []
    full = " ".join(x for _, x in transcript)
    win = window(transcript, c.get("at"))
    win_words = words(win)
    win_text = " " + " ".join(win_words) + " "
    duration = transcript[-1][0] if transcript else 0
    if c.get("at") is not None and (seconds(c["at"]) is None or seconds(c["at"]) > duration + 5):
        flags.append("bad_timestamp")
    if any(re.search(p, wc.norm(c["text"])) for p in SENSITIVE):
        flags.append("sensitive")
    if c["type"] == "participant":
        names = [t for t in re.split(r"[\s()]+", wc.norm(c["text"])) if len(t) >= 2 and t not in ("da", "de", "do", "dra", "dr", "e")]
        plain = " " + " ".join(words(full)) + " "
        said = max((plain.count(f" {n} ") for n in names), default=0)
        addressed = any(re.search(rf"\b(bom dia|boa tarde|obrigad[oa]|oi|ola),? (o |a )?{re.escape(n)}\b|\b{re.escape(n)},", wc.norm(full))
                        for n in names)
        if wc.norm(c["text"].strip()) != wc.norm(USER) and said < 2 and not addressed:
            flags.append("participant_unconfirmed")
        return flags
    if c.get("due"):
        d = datetime.strptime(c["due"][:10], "%Y-%m-%d").date()
        temporal = (f" {d.day} " in win_text or MONTHS[d.month - 1] in win_text
                    or any(f" {w}" in win_text for w in WEEKDAYS) or any(f" {r} " in win_text for r in RELATIVE))
        if not temporal:
            flags.append("date_unsupported")
    owner = c.get("owner")
    if owner and wc.norm(str(owner)) not in ("indefinido", ""):
        names = [t for t in re.split(r"[\s()]+", wc.norm(str(owner))) if len(t) >= 2 and t not in ("da", "de", "do", "dra", "e")]
        first_person = wc.norm(str(owner)) == wc.norm(USER) and any(p in wc.norm(win) for p in COMMIT_1P)
        if not any(f" {n} " in win_text for n in names) and not first_person:
            flags.append("owner_unconfirmed")
    if c["type"] == "decision" and any(m in wc.norm(win) for m in TENTATIVE):
        flags.append("tentative_context")
    claim_stems = stems(c["text"])
    if c["type"] in ("decision", "action", "statement", "deadline") and claim_stems:
        overlap = len(claim_stems & stems(win)) / len(claim_stems)
        if overlap < 0.34:
            flags.append("low_support")
    return flags


L2_KEPT = ("sensitive", "participant_unconfirmed", "bad_timestamp")


# --- defend: L1 transcript verifier -------------------------------------------------------------
VERIFY_SYSTEM = """You check claims that an automated analysis made about a meeting, using only the meeting's transcript. The transcript is raw speech-to-text: it has no speaker labels and may contain recognition errors. The user who records the meetings is Felipe.

For each claim answer:
- support: "supported" (the transcript says it), "partial" (part of it is there, part is not), "unsupported" (the transcript does not say it) or "contradicted" (the transcript says otherwise);
- owner_evident: for claims with an owner, true when the transcript makes clear that person is the one who will do it (they are named or addressed, or say it about themselves in a way only they could), false when it could be someone else or is not said; null when the claim has no owner;
- date_said: for claims with a date, true when that date (or a relative expression that resolves to it from the meeting date) is said; null when the claim has no date;
- tentative: true when the transcript presents it tentatively ("talvez", "preciso confirmar") rather than decided;
- sensitive: true when the claim contains sensitive personal data (health, medical, sexual orientation, religion, politics, private life) or a personal judgment about someone;
- reason: one short sentence.
Judge each claim independently. Do not use outside knowledge."""


def verifier_schema() -> Any:
    from pydantic import BaseModel

    class VerdictOut(BaseModel):
        id: str
        support: Literal["supported", "partial", "unsupported", "contradicted"]
        owner_evident: bool | None
        date_said: bool | None
        tentative: bool
        sensitive: bool
        reason: str

    class VerifyOut(BaseModel):
        verdicts: list[VerdictOut]

    return VerifyOut


def verify_meeting(tr: Any, mid: str, claims: list[dict[str, Any]], transcript_text: str, seed: int) -> list[dict[str, Any]]:
    mine = list(claims)
    random.Random(seed).shuffle(mine)
    user = (f"Meeting date: {mid[:10]} ({WEEKDAYS[meeting_day(mid).weekday()]})\n\n## Transcript\n{transcript_text}\n\n"
            f"## Claims\n" + "\n".join(describe(c) for c in mine))
    out = tr.complete(VERIFY_SYSTEM, user, verifier_schema(), tag=f"fidelity-verify:{mid}:{seed}")
    return [v.model_dump() for v in out.verdicts]


def l1_flag(c: dict[str, Any], v: dict[str, Any] | None) -> list[str]:
    if v is None:
        return ["no_verdict"]
    flags = []
    if v["support"] != "supported":
        flags.append(f"l1_{v['support']}")
    if c.get("owner") and wc.norm(str(c["owner"])) != "indefinido" and v.get("owner_evident") is False:
        flags.append("l1_owner")
    if c.get("due") and v.get("date_said") is False:
        flags.append("l1_date")
    if c["type"] == "decision" and v.get("tentative"):
        flags.append("l1_tentative")
    if v.get("sensitive"):
        flags.append("l1_sensitive")
    return flags


def defend(args: argparse.Namespace) -> None:
    claims = load_json(args.work / "claims_original.json") + (
        load_json(args.work / "claims_injected.json") if (args.work / "claims_injected.json").exists() else [])
    transcripts = {mid: load_transcript(args.work / "recordings" / mid) for mid in {c["meeting"] for c in claims}}
    l2 = {c["id"]: l2_flags(c, transcripts[c["meeting"]]) for c in claims}
    save_json(args.work / "l2.json", l2)
    tr = transport(CHECK_MODEL, args.work / "log" / "verify.jsonl", effort="medium")
    out_path = args.work / "l1.json"
    l1: dict[str, dict[str, Any]] = load_json(out_path) if out_path.exists() else {}

    def run(job: tuple[str, int]) -> tuple[str, int, list[dict[str, Any]]]:
        mid, k = job
        text = window(transcripts[mid], None)   # synthetic meetings are short: the whole transcript is the window
        return mid, k, verify_meeting(tr, mid, [c for c in claims if c["meeting"] == mid], text, k)

    jobs = [(mid, k) for mid in sorted(transcripts) for k in range(1, args.runs + 1) if f"{mid}#{k}" not in l1]
    for mid, k, verdicts in pmap(run, jobs, args.jobs):
        l1[f"{mid}#{k}"] = {v["id"]: v for v in verdicts}
        save_json(out_path, l1)
        print(f"{mid} run {k}: {len(verdicts)} verdicts")


# --- report (tests A and B) ---------------------------------------------------------------------
def flagged_sets(work: Path, runs: int) -> dict[str, list[dict[str, list[str]]]]:
    """Per configuration, one {claim id → flags} map per verifier run."""
    claims = load_json(work / "claims_original.json") + (load_json(work / "claims_injected.json") if (work / "claims_injected.json").exists() else [])
    l2, l1 = load_json(work / "l2.json"), load_json(work / "l1.json")
    out: dict[str, list[dict[str, list[str]]]] = {"L2 code checks": [], "L1 verifier": [], "L1 + L2": [], "L1 + L2 tuned": []}
    for k in range(1, runs + 1):
        maps = {name: {} for name in out}
        for c in claims:
            verdict = l1.get(f"{c['meeting']}#{k}", {}).get(c["id"])
            f2, f1 = l2.get(c["id"], []), l1_flag(c, verdict)
            maps["L2 code checks"][c["id"]] = f2
            maps["L1 verifier"][c["id"]] = f1
            maps["L1 + L2"][c["id"]] = f1 + f2
            # tuned on this corpus (2026-10-11): only the code checks that caught more errors than they rejected
            maps["L1 + L2 tuned"][c["id"]] = f1 + [f for f in f2 if f in L2_KEPT]
        for name in out:
            out[name].append(maps[name])
    return out


def rate(values: list[float]) -> str:
    if not values:
        return "—"
    mean = sum(values) / len(values)
    return f"{100 * mean:.0f}%" + (f" ({100 * min(values):.0f}–{100 * max(values):.0f})" if max(values) - min(values) > 1e-9 else "")


def defense_metrics(work: Path, runs: int) -> dict[str, Any]:
    claims = load_json(work / "claims_original.json") + (load_json(work / "claims_injected.json") if (work / "claims_injected.json").exists() else [])
    gt = truth(work)
    sets = flagged_sets(work, runs)
    originals = [c for c in claims if c["source"] == "original" and c["id"] in gt]
    injected = [c for c in claims if c["source"] == "injected"]
    correct = [c for c in originals if gt[c["id"]]["correct"]]
    natural = [c for c in originals if not gt[c["id"]]["correct"]]
    metrics: dict[str, Any] = {"n_original": len(originals), "n_correct": len(correct), "n_natural_errors": len(natural),
                               "n_injected": len(injected), "configs": {}}
    for name, maps in sets.items():
        caught = lambda group, m: (sum(1 for c in group if m[c["id"]]) / len(group)) if group else 0.0  # noqa: E731
        conf: dict[str, Any] = {
            "injected_caught": [caught(injected, m) for m in maps],
            "natural_caught": [caught(natural, m) for m in maps],
            "false_positive": [caught(correct, m) for m in maps],
            "precision_kept": [(sum(1 for c in originals if not m[c["id"]] and gt[c["id"]]["correct"])
                                / max(1, sum(1 for c in originals if not m[c["id"]]))) for m in maps],
            "by_injected_type": {}, "by_natural_type": {},
        }
        for t in sorted({c["inject_type"] for c in injected}):
            conf["by_injected_type"][t] = [caught([c for c in injected if c["inject_type"] == t], m) for m in maps]
        for t in sorted({gt[c["id"]]["error_type"] for c in natural}):
            conf["by_natural_type"][t] = [caught([c for c in natural if gt[c["id"]]["error_type"] == t], m) for m in maps]
        metrics["configs"][name] = conf
    by_type: dict[str, dict[str, int]] = {}
    for c in originals:
        row = by_type.setdefault(c["type"], {"n": 0, "correct": 0})
        row["n"] += 1
        row["correct"] += gt[c["id"]]["correct"]
    metrics["fidelity_by_type"] = by_type
    metrics["natural_error_types"] = {t: sum(1 for c in natural if gt[c["id"]]["error_type"] == t) for t in {gt[c["id"]]["error_type"] for c in natural}}
    metrics["oracle_agreement"] = sum(gt[c["id"]]["agreement"] for c in originals) / max(1, len(originals))
    return metrics


def report(args: argparse.Namespace) -> None:
    m = defense_metrics(args.work, args.runs)
    save_json(args.work / "defense_metrics.json", m)
    gt = truth(args.work)
    claims = {c["id"]: c for c in load_json(args.work / "claims_original.json")}
    lines = ["# Fidelity of the analysis and what the defenses catch", "",
             f"{m['n_original']} claims from the project's analyses of the planted meetings; ground truth from the dialogues "
             f"(oracle: {ORACLE_MODEL}, majority of runs, mean agreement {100 * m['oracle_agreement']:.0f}%); "
             f"{m['n_injected']} injected errors; verifier ({CHECK_MODEL}) run {args.runs}×. Ranges are min–max over runs.", "",
             "## Test B: how faithful is the analysis today (per claim type)", "", "| Type | Claims | Correct |", "|---|---|---|"]
    for t, row in sorted(m["fidelity_by_type"].items()):
        lines.append(f"| {t} | {row['n']} | {row['correct']} ({100 * row['correct'] / row['n']:.0f}%) |")
    lines += ["", "Natural errors by kind: " + ", ".join(f"{k} {v}" for k, v in sorted(m["natural_error_types"].items())), "",
              "## Test A: what each defense catches", "",
              "| Defense | injected errors caught | natural errors caught | correct claims rejected (FP) | precision of what is kept |",
              "|---|---|---|---|---|"]
    for name, c in m["configs"].items():
        lines.append(f"| {name} | {rate(c['injected_caught'])} | {rate(c['natural_caught'])} | {rate(c['false_positive'])} | {rate(c['precision_kept'])} |")
    lines += ["", "### Injected errors caught, by type", "", "| Type | " + " | ".join(m["configs"]) + " |", "|---|" + "---|" * len(m["configs"])]
    for t in next(iter(m["configs"].values()))["by_injected_type"]:
        lines.append(f"| {t} | " + " | ".join(rate(c["by_injected_type"][t]) for c in m["configs"].values()) + " |")
    lines += ["", "### Natural errors caught, by type", "", "| Type | " + " | ".join(m["configs"]) + " |", "|---|" + "---|" * len(m["configs"])]
    for t in next(iter(m["configs"].values()))["by_natural_type"]:
        lines.append(f"| {t} ({m['natural_error_types'][t]}) | " + " | ".join(rate(c["by_natural_type"][t]) for c in m["configs"].values()) + " |")
    lines += ["", "### The analysis's own errors (oracle)", ""]
    for cid, g in sorted(gt.items()):
        if not g["correct"] and cid in claims:
            c = claims[cid]
            lines.append(f"- `{cid}` {c['type']} [{g['error_type']}]: {c['text'][:110]}" + (f" — owner {c['owner']}" if c.get("owner") else "")
                         + (f" — date {c['due']}" if c.get("due") else "") + f" · {g['reasons'][0][:140] if g['reasons'] else ''}")
    (args.work / "defense_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.work / "defense_report.md")


# --- stories (end to end, four variants) --------------------------------------------------------
WIKI_HEADER = ("\n## Context from the meetings wiki (pages as of the plan date, compiled by another model from earlier meetings; "
               "may contain errors: never contradict the candidate actions or the meeting analyses with it)\n")


def wiki_pages_at(wiki: Path, day: date) -> str:
    """overview + project and topic pages of the wiki as it was after the last meeting up to `day`."""
    log = subprocess.run(["git", "-C", str(wiki), "log", "--format=%H %s"], capture_output=True, text=True, check=True).stdout.splitlines()
    commit = None
    for line in log:   # newest first
        sha, _, subject = line.partition(" ")
        m = re.search(r"ingest (\d{4}-\d{2}-\d{2})", subject)
        if m and datetime.strptime(m.group(1), "%Y-%m-%d").date() <= day:
            commit = sha
            break
    if commit is None:
        return ""
    files = subprocess.run(["git", "-C", str(wiki), "ls-tree", "-r", "--name-only", commit], capture_output=True, text=True, check=True).stdout.split()
    chosen = [f for f in files if f == "overview.md" or f.startswith(("projects/", "topics/"))]
    return "\n\n".join(f"### {f}\n" + subprocess.run(["git", "-C", str(wiki), "show", f"{commit}:{f}"], capture_output=True, text=True,
                                                     check=True).stdout for f in chosen)


CITE_RULE = """

## Provenance of every criterion (evaluation variant)

End every acceptance criterion and every detail line with its source: the transcript timestamp of the action or decision it comes from, as [hh:mm:ss] (from the `at` fields you received), or the marker "(sugestão)" when nobody said it in the meetings and you are proposing it. Never present a proposal of yours without "(sugestão)"."""


def story_container(data: Path, wiki: Path | None, cited: bool = False) -> Any:
    c = wc.container_for(data)
    from teams_recorder.adapters.outbound import stories_claude as sc

    base = c.story_writer
    if cited:
        class CitingWriter(sc.ClaudeStoryWriter):
            def _system(self) -> str:
                return super()._system() + CITE_RULE

        c.story_writer = CitingWriter(base.transport, base.guide_path, prompt_path=base.prompt_path, user_name=base.user_name)
        base = c.story_writer
    if wiki is None:
        return c

    class WikiContextWriter(sc.ClaudeStoryWriter):
        def draft(self, day: date, actions: list[Any], analyses: list[Any], existing: list[Any]) -> Any:
            if not actions:
                return sc.StoryDrafts(day=day)
            user = sc.build_user_message(day, actions, analyses, existing, self.user_name) + WIKI_HEADER + wiki_pages_at(wiki, day)
            out = self.transport.complete(self._system(), user, sc.StoriesOut, tag=f"stories+wiki:{day.isoformat()}",
                                          extra={"day": day.isoformat()})
            return sc.to_drafts(out, day, actions, existing)

    c.story_writer = WikiContextWriter(base.transport, base.guide_path, prompt_path=base.prompt_path, user_name=base.user_name)
    return c


def filter_analysis(analysis: dict[str, Any], flagged_texts: set[str]) -> dict[str, Any]:
    """The defended pipeline: claims the defenses flagged are not passed on as facts."""
    a = json.loads(json.dumps(analysis))
    a["decisions"] = [d for d in a.get("decisions", []) if (d["text"] if isinstance(d, dict) else d).strip() not in flagged_texts]
    a["my_actions"] = [x for x in a.get("my_actions", []) if x["description"].strip() not in flagged_texts]
    a["others_actions"] = [x for x in a.get("others_actions", []) if x["description"].strip() not in flagged_texts]
    a["deadlines"] = [x for x in a.get("deadlines", []) if x["what"].strip() not in flagged_texts]
    a["participants"] = [p for p in a.get("participants", []) if p.strip() not in flagged_texts]
    a["risks"] = [r for r in a.get("risks", []) if r.strip() not in flagged_texts]
    for t in a.get("topics", []):
        t["points"] = [p for p in t.get("points", []) if p.strip() not in flagged_texts]
    return a


def mark_analysis(analysis: dict[str, Any], flags: dict[str, list[str]]) -> dict[str, Any]:
    """The guarded pipeline: claims the defenses flagged stay, visibly unconfirmed; an unconfirmed owner becomes unknown."""
    a = json.loads(json.dumps(analysis))
    tag = "(a confirmar) "
    for d in a.get("decisions", []):
        if isinstance(d, dict) and flags.get(d["text"].strip()):
            d["text"] = tag + d["text"]
    for lst in ("my_actions", "others_actions"):
        for x in a.get(lst, []):
            f = flags.get(x["description"].strip())
            if f:
                if any("owner" in g for g in f):
                    x["owner"] = "indefinido"
                x["description"] = x["description"] + " (a confirmar na transcrição)"
    for x in a.get("deadlines", []):
        if flags.get(x["what"].strip()):
            x["what"] = tag + x["what"]
    a["participants"] = [p for p in a.get("participants", []) if not flags.get(p.strip())]
    a["risks"] = [tag + r if flags.get(r.strip()) else r for r in a.get("risks", [])]
    for t in a.get("topics", []):
        t["points"] = [tag + p if flags.get(p.strip()) else p for p in t.get("points", [])]
    return a


def build_variant_data(work: Path, name: str, defended: bool | str) -> Path:
    """A data dir per variant; meetings added to the corpus later are added to an existing one. `defended`: False, True
    (flagged claims dropped, untuned L1 + L2) or "mark" (flagged claims kept and marked, tuned L1 + L2)."""
    data = work / "variants" / name
    missing = [m for m in planted() if not (data / "recordings" / m["id"] / "analysis.json").exists()]
    if not missing:
        return data
    flagged: set[str] = set()
    flag_by_text: dict[str, list[str]] = {}
    if defended == "mark":
        maps = flagged_sets(work, 1)["L1 + L2 tuned"][0]
        flag_by_text = {c["text"].strip(): maps[c["id"]] for c in load_json(work / "claims_original.json") if maps.get(c["id"])}
    elif defended:
        maps = flagged_sets(work, 1)["L1 + L2"][0]
        flagged = {c["text"].strip() for c in load_json(work / "claims_original.json") if maps.get(c["id"])}
    for m in missing:
        src, dst = work / "recordings" / m["id"], data / "recordings" / m["id"]
        dst.mkdir(parents=True, exist_ok=True)
        for f in ("meta.json", "transcript.json", "transcript.txt", "minutes.md"):
            if (src / f).exists():
                shutil.copy2(src / f, dst / f)
        analysis = load_json(src / "analysis.json")
        save_json(dst / "analysis.json", mark_analysis(analysis, flag_by_text) if defended == "mark"
                  else filter_analysis(analysis, flagged) if defended else analysis)
    return data


def run_plans_and_stories(data: Path, wiki: Path | None, days: list[date], plans_from: Path | None = None, cited: bool = False) -> None:
    c = story_container(data, wiki, cited)
    if plans_from is not None and not (data / "plans").exists():
        shutil.copytree(plans_from / "plans", data / "plans", ignore=shutil.ignore_patterns("*.stories.*"))
    for day in days:
        if c.repo.load_plan(day) is None:
            c.build_daily_plan().execute(day)
        if c.repo.load_story_drafts(day) is None:
            try:
                c.draft_user_stories().execute(day)
            except Exception as exc:  # noqa: BLE001 - recorded, the other days go on
                print(f"  {data.name} {day}: stories failed: {exc}")
        print(f"  {data.name} {day}: plan + stories done")


STORY_ORACLE_SYSTEM = """You are the ground-truth judge in a test of a meeting-processing pipeline that turns meetings into user stories. You receive the exact dialogues (every line says who spoke) of all meetings up to the plan date, the analyses the pipeline made of the source meetings, optionally the wiki pages the story writer was given, and the stories drafted for that day.

Each story is split into numbered claims (title, story sentence, each acceptance criterion, each detail line). For each claim decide:
- verdict: "supported" (said in the meetings or a faithful consequence), "unsupported" (not in the meetings: invented requirement, value, person, date or behavior) or "contradicted" (the meetings say otherwise, including the wrong owner, a date that changed, a decision that was reversed, or something presented as decided that was only tentative);
- origin, for unsupported or contradicted claims: "analysis" if the same mistake is already in the analysis given, "wiki" if it comes from the wiki pages given, "writer" if the story writer introduced it, "transcript" if it comes from a recognition error; "none" for supported claims.
A reasonable acceptance criterion that only restates the requested behavior in testable form is supported. Be strict about facts (owners, dates, scope, decisions)."""


def story_claims(drafts: dict[str, Any]) -> list[dict[str, Any]]:
    claims = []
    for i, s in enumerate(drafts.get("stories", []), 1):
        def add(part: str, text: str) -> None:
            if text and text.strip():
                claims.append({"id": f"s{i}-{len(claims) + 1:02d}", "story": i, "part": part, "text": text.strip()})
        add("title", s["title"])
        add("narrative", s.get("narrative", ""))
        for ac in s.get("acceptance_criteria", []):
            add("criterion", ac)
        for line in (s.get("details") or "").splitlines():
            if len(line.strip("-* ").strip()) > 12:
                add("detail", line.strip("-* ").strip())
    return claims


def judge_stories(work: Path, variant: str, wiki: Path | None, days: list[date], jobs: int) -> list[dict[str, Any]]:
    from pydantic import BaseModel

    class ClaimVerdict(BaseModel):
        id: str
        verdict: Literal["supported", "unsupported", "contradicted"]
        origin: Literal["none", "analysis", "wiki", "writer", "transcript"]
        reason: str

    class StoryJudgeOut(BaseModel):
        verdicts: list[ClaimVerdict]

    data = work / "variants" / variant
    tr = transport(ORACLE_MODEL, work / "log" / "story-oracle.jsonl")
    out_path = work / f"story_verdicts_{variant}.json"
    done: dict[str, Any] = load_json(out_path) if out_path.exists() else {}

    def run(day: date) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        path = data / "plans" / f"{day.isoformat()}.stories.json"
        if not path.exists():
            return day.isoformat(), [], []
        drafts = load_json(path)
        claims = story_claims(drafts)
        if not claims:
            return day.isoformat(), [], []
        source_ids = sorted({mid for s in drafts["stories"] for mid in s.get("source_meetings", [])})
        dialogues = "\n\n".join(f"### Meeting {m['id']}\n{dialogue(m)}" for m in planted() if meeting_day(m["id"]) <= day)
        analyses = "\n\n".join(f"### Analysis of {mid}\n" + (data / "recordings" / mid / "analysis.json").read_text(encoding="utf-8")
                               for mid in source_ids if (data / "recordings" / mid / "analysis.json").exists())
        stories = "\n".join(f"[{c['id']}] (story {c['story']}, {c['part']}) {c['text']}" for c in claims)
        user = (f"Plan date: {day.isoformat()}\n\n## Dialogues\n{dialogues}\n\n## Analyses of the source meetings\n{analyses}\n\n"
                + (f"## Wiki pages given to the writer\n{wiki_pages_at(wiki, day)}\n\n" if wiki else "") + f"## Story claims\n{stories}")
        out = tr.complete(STORY_ORACLE_SYSTEM, user, StoryJudgeOut, tag=f"story-oracle:{variant}:{day}")
        return day.isoformat(), claims, [v.model_dump() for v in out.verdicts]

    todo = [d for d in days if d.isoformat() not in done]
    for day, claims, verdicts in pmap(run, todo, jobs):
        done[day] = {"claims": claims, "verdicts": verdicts}
        save_json(out_path, done)
    return [dict(c, day=d, **{k: v for k, v in next((v for v in done[d]["verdicts"] if v["id"] == c["id"]),
                                                   {"verdict": "missing", "origin": "none"}).items() if k != "id"})
            for d in done for c in done[d]["claims"]]


STORY_VARIANTS = {   # name → (defended analyses, wiki context, writer cites a source or "(sugestão)" for each criterion)
    "baseline": (False, False, False), "wiki": (False, True, False), "defended": (True, False, False), "defended_wiki": (True, True, False),
    "cited": (False, False, True), "guarded": ("mark", False, True),
}
for _r in (2, 3):   # repeats of the two variants the conclusion rests on: same plans, the writer drafts again
    STORY_VARIANTS[f"baseline_r{_r}"] = STORY_VARIANTS["baseline"]
    STORY_VARIANTS[f"guarded_r{_r}"] = STORY_VARIANTS["guarded"]


def stories(args: argparse.Namespace) -> None:
    days = sorted({meeting_day(m["id"]) for m in planted()})
    results = {}
    for name, (defended, with_wiki, cited) in STORY_VARIANTS.items():
        if args.only and name not in args.only.split(","):
            continue
        source = "guarded" if defended == "mark" else "defended" if defended else "baseline"
        data = build_variant_data(args.work, name, defended)
        repeat = "_r" in name
        plans_from = args.work / "variants" / source if (with_wiki or cited or repeat) and source != name else None
        if plans_from is not None:
            run_plans_and_stories(args.work / "variants" / source, None, days)   # the plans come from the plain variant
        run_plans_and_stories(data, args.wiki if with_wiki else None, days, plans_from=plans_from, cited=cited)
        claims = judge_stories(args.work, name, args.wiki if with_wiki else None, days, args.jobs)
        results[name] = claims
        bad = [c for c in claims if c.get("verdict") in ("unsupported", "contradicted")]
        print(f"{name}: {len(claims)} story claims, {len(bad)} not supported")
    save_json(args.work / "stories_summary.json", {k: summarize_story_claims(v) for k, v in results.items()})
    write_story_report(args.work, results)


def summarize_story_claims(claims: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(claims)
    count = lambda v: sum(1 for c in claims if c.get("verdict") == v)  # noqa: E731
    origins: dict[str, int] = {}
    for c in claims:
        if c.get("verdict") in ("unsupported", "contradicted"):
            origins[c.get("origin", "none")] = origins.get(c.get("origin", "none"), 0) + 1
    return {"claims": n, "stories": len({(c.get("day"), c.get("story")) for c in claims}), "supported": count("supported"),
            "unsupported": count("unsupported"), "contradicted": count("contradicted"), "origins": origins}


def write_story_report(work: Path, results: dict[str, list[dict[str, Any]]]) -> None:
    lines = ["# Do the stories match what was said?", "", "| Variant | stories | story claims | supported | unsupported | contradicted | origin of the bad ones |",
             "|---|---|---|---|---|---|---|"]
    for name, claims in results.items():
        s = summarize_story_claims(claims)
        n = max(1, s["claims"])
        lines.append(f"| {name} | {s['stories']} | {s['claims']} | {100 * s['supported'] / n:.0f}% | {100 * s['unsupported'] / n:.0f}% | {100 * s['contradicted'] / n:.0f}% | "
                     + ", ".join(f"{k} {v}" for k, v in sorted(s["origins"].items())) + " |")
    for name, claims in results.items():
        lines += ["", f"## {name}: claims not supported", ""]
        lines += [f"- {c.get('day')} [{c.get('verdict')} · {c.get('origin')}] ({c.get('part')}) {c['text'][:140]} — {c.get('reason', '')[:160]}"
                  for c in claims if c.get("verdict") in ("unsupported", "contradicted")]
    (work / "stories_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(work / "stories_report.md")


# --- verify-stories (a defense at the story stage) -------------------------------------------------
STORY_VERIFY_SYSTEM = """You check user stories that a model drafted from a user's meetings, using only the meetings' transcripts (raw speech-to-text, no speaker labels, may contain recognition errors). The user is Felipe.

Each story is split into claims (title, story sentence, acceptance criteria, detail lines). For each claim answer support:
- "supported": the transcripts say it, or it restates requested behavior in a testable form;
- "partial": part of it is said and part is not;
- "unsupported": it adds a requirement, value, rule, person, date or behavior nobody asked for;
- "contradicted": the transcripts say otherwise (including a later meeting changing it).
Also set owner_evident, date_said and tentative as for any claim (null when not applicable), sensitive when it contains personal sensitive data, and a one-sentence reason. Judge each claim independently; no outside knowledge."""


def verify_stories(args: argparse.Namespace) -> None:
    """The verifier applied to the story claims, compared with the story oracle's verdicts."""
    tr = transport(CHECK_MODEL, args.work / "log" / "story-verify.jsonl", effort="medium")
    lines = ["# A verifier at the story stage", "",
             "Story claims checked against the transcripts of the meetings up to the plan date; ground truth = the story oracle "
             f"(dialogues with speakers). Verifier {CHECK_MODEL}, {args.runs} runs; ranges are min–max.", "",
             "| Variant | story claims | bad (oracle) | bad flagged by the verifier | good flagged anyway |", "|---|---|---|---|---|"]
    summary = {}
    for variant in args.variants.split(","):
        path = args.work / f"story_verdicts_{variant}.json"
        if not path.exists():
            continue
        done = load_json(path)
        out_path = args.work / f"story_verify_{variant}.json"
        cache: dict[str, Any] = load_json(out_path) if out_path.exists() else {}

        def run(job: tuple[str, int]) -> tuple[str, int, dict[str, Any]]:
            day, k = job
            claims = [dict(cl, type="statement") for cl in done[day]["claims"]]
            texts = "\n\n".join(f"### Meeting {m['id']}\n" + window(load_transcript(args.work / "recordings" / m["id"]), None)
                                 for m in planted() if meeting_day(m["id"]) <= date.fromisoformat(day)
                                 and (args.work / "recordings" / m["id"] / "transcript.txt").exists())
            mine = list(claims)
            random.Random(k).shuffle(mine)
            user = f"Plan date: {day}\n\n## Transcripts\n{texts}\n\n## Story claims\n" + "\n".join(f"[{cl['id']}] ({cl['part']}) {cl['text']}" for cl in mine)
            out = tr.complete(STORY_VERIFY_SYSTEM, user, verifier_schema(), tag=f"story-verify:{variant}:{day}:{k}")
            return day, k, {v.id: v.model_dump() for v in out.verdicts}

        jobs = [(day, k) for day in done if done[day]["claims"] for k in range(1, args.runs + 1) if f"{day}#{k}" not in cache]
        for day, k, verdicts in pmap(run, jobs, args.jobs):
            cache[f"{day}#{k}"] = verdicts
            save_json(out_path, cache)
        caught_runs, fp_runs = [], []
        bad_n = good_n = 0
        for k in range(1, args.runs + 1):
            caught = fp = bad = good = 0
            for day, entry in done.items():
                oracle_by_id = {v["id"]: v for v in entry["verdicts"]}
                for cl in entry["claims"]:
                    o = oracle_by_id.get(cl["id"])
                    if o is None:
                        continue
                    v = cache.get(f"{day}#{k}", {}).get(cl["id"])
                    flagged = v is None or v["support"] != "supported" or v.get("sensitive")
                    if o["verdict"] == "supported":
                        good += 1
                        fp += bool(flagged)
                    else:
                        bad += 1
                        caught += bool(flagged)
            caught_runs.append(caught / bad if bad else 0.0)
            fp_runs.append(fp / good if good else 0.0)
            bad_n, good_n = bad, good
        summary[variant] = {"claims": bad_n + good_n, "bad": bad_n, "caught": caught_runs, "false_positive": fp_runs}
        lines.append(f"| {variant} | {bad_n + good_n} | {bad_n} | {rate(caught_runs)} | {rate(fp_runs)} |")
    save_json(args.work / "story_verify_summary.json", summary)
    (args.work / "story_verify_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


# --- propagate (test C) ----------------------------------------------------------------------------
PROPAGATION = {
    "meeting": "2026-01-12_09-30-00",
    "error": "the routing module stays with Bruno and Felipe moves to the WhatsApp integration (the opposite of what was said)",
    "probe": "Does this text state or imply that, after 12 January, BRUNO (not Felipe) is responsible for the RotaFácil routing module, or that Felipe moved to the WhatsApp integration?",
}


def corrupt_handover(analysis: dict[str, Any]) -> dict[str, Any]:
    a = json.loads(json.dumps(analysis))
    swap = {"felipe": "Bruno", "bruno": "Felipe"}

    def flip(text: str) -> str:
        return re.sub(r"\b(Felipe|Bruno)\b", lambda m: swap[m.group(1).lower()], text)

    for d in a.get("decisions", []):
        if isinstance(d, dict) and re.search(r"rota|whatsapp|santa clara", wc.norm(d["text"])):
            d["text"] = flip(d["text"])
    moved = []
    for lst in ("my_actions", "others_actions"):
        keep = []
        for x in a.get(lst, []):
            if re.search(r"rota|roteiriz|algoritmo|whatsapp", wc.norm(x["description"])):
                owner = "Bruno" if x.get("owner") in ("usuário", "usuario") else ("usuário" if wc.norm(x.get("owner", "")).startswith("bruno") else x.get("owner"))
                x["owner"], x["description"] = owner, flip(x["description"])
            (keep if (x.get("owner") in ("usuário", "usuario")) == (lst == "my_actions") else moved).append(x)
        a[lst] = keep
    for x in moved:
        a["my_actions" if x.get("owner") in ("usuário", "usuario") else "others_actions"].append(x)
    for t in a.get("topics", []):
        t["points"] = [flip(p) if re.search(r"rota|whatsapp", wc.norm(p)) else p for p in t.get("points", [])]
    return a


def propagate(args: argparse.Namespace) -> None:
    from pydantic import BaseModel

    class ProbeOut(BaseModel):
        present: bool
        quote: str

    mid = PROPAGATION["meeting"]
    all_days = sorted({meeting_day(m["id"]) for m in planted()})
    days = [d for d in all_days if d >= meeting_day(mid)]
    probe_tr = transport(CHECK_MODEL, args.work / "log" / "probe.jsonl", effort="medium")
    results: dict[str, Any] = {}
    for variant in ("undefended", "defended"):
        data = args.work / "propagation" / variant
        if not data.exists():
            base = args.work / "variants" / "baseline"
            for m in planted():   # plans are rebuilt from the first day: open_actions.json is cumulative
                shutil.copytree(base / "recordings" / m["id"], data / "recordings" / m["id"])
            corrupted = corrupt_handover(load_json(args.work / "recordings" / mid / "analysis.json"))
            if variant == "defended":
                claims = extract_claims(corrupted)
                transcript = load_transcript(data / "recordings" / mid)
                verdicts = {v["id"]: v for v in verify_meeting(transport(CHECK_MODEL, args.work / "log" / "verify.jsonl", effort="medium"),
                                                                  mid, claims, window(transcript, None), 1)}
                flagged = {c["text"].strip() for c in claims if l1_flag(c, verdicts.get(c["id"])) + l2_flags(c, transcript)}
                corrupted = filter_analysis(corrupted, flagged)
            save_json(data / "recordings" / mid / "analysis.json", corrupted)
        run_plans_and_stories(data, None, all_days)
        found: dict[str, bool] = {}
        artifacts = {f"plan {d}": data / "plans" / f"{d.isoformat()}.md" for d in days}
        artifacts |= {f"stories {d}": data / "plans" / f"{d.isoformat()}.stories.md" for d in days}
        artifacts["analysis"] = data / "recordings" / mid / "analysis.json"

        def probe(item: tuple[str, Path]) -> tuple[str, bool]:
            name, path = item
            if not path.exists():
                return name, False
            out = probe_tr.complete("You answer a yes/no question about a document. Quote the sentence that decides it, or leave quote empty.",
                                    f"Question: {PROPAGATION['probe']}\n\nDocument:\n{path.read_text(encoding='utf-8')[:20000]}", ProbeOut,
                                    tag=f"probe:{variant}:{name}")
            return name, out.present

        for name, present in pmap(probe, list(artifacts.items()), args.jobs):
            found[name] = present
        results[variant] = found
        print(variant, {k: v for k, v in found.items() if v})
    if args.wiki_ingest:
        results |= propagate_wiki(args, probe_tr)
    save_json(args.work / "propagation.json", results)
    lines = ["# Test C: one analysis error, traced", "", f"Injected into the analysis of {mid}: {PROPAGATION['error']}.", "",
             "| Artifact | " + " | ".join(results) + " |", "|---|" + "---|" * len(results)]
    for name in sorted({n for r in results.values() for n in r}):
        lines.append(f"| {name} | " + " | ".join(("**carries the error**" if r.get(name) else "clean") if name in r else "—" for r in results.values()) + " |")
    (args.work / "propagation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.work / "propagation_report.md")


def propagate_wiki(args: argparse.Namespace, probe_tr: Any) -> dict[str, Any]:
    """The wiki ingest of the corrupted meeting and the next one, from the 9-meeting wiki as it was
    before it (the agent also reads the transcript, so it may correct the analysis)."""
    from pydantic import BaseModel

    class ProbeOut(BaseModel):
        present: bool
        quote: str

    mid = PROPAGATION["meeting"]
    out: dict[str, Any] = {}
    for variant in ("undefended", "defended"):
        wiki = args.scratch / f"propagation-wiki-{variant}"
        data = args.work / "propagation" / variant
        if not wiki.exists():
            subprocess.run(["git", "clone", "-q", str(args.wiki), str(wiki)], check=True)
            subprocess.run(["git", "-C", str(wiki), "remote", "remove", "origin"], check=True)
            log = subprocess.run(["git", "-C", str(wiki), "log", "--format=%H %s"], capture_output=True, text=True, check=True).stdout.splitlines()
            before = next(sha for sha, _, s in (line.partition(" ") for line in log) if "2026-01-09" in s)
            subprocess.run(["git", "-C", str(wiki), "reset", "-q", "--hard", before], check=True)
            ingested = [m["id"] for m in planted() if m["id"] < mid]
            (wiki / ".ingested").write_text("\n".join(ingested) + "\n", encoding="utf-8")
        link = wiki.parent / "recordings"   # the wiki's CLAUDE.md reads ../recordings/<id>/
        if link.is_symlink() or link.exists():
            link.unlink() if link.is_symlink() else shutil.rmtree(link)
        link.symlink_to(data / "recordings")
        tmp_data = wiki.parent
        subprocess.run([sys.executable, "-u", str(wc.__file__), "ingest", "--data", str(tmp_data), "--wiki", str(wiki), "--limit", "2"],
                       check=False)
        pages = {p.relative_to(wiki).as_posix(): p for p in wiki.rglob("*.md") if p.parent.name in ("people", "projects", "topics")}
        hits = {}
        for rel, path in pages.items():
            text = path.read_text(encoding="utf-8")
            if re.search(r"rota|roteiriz", wc.norm(text)):
                res = probe_tr.complete("You answer a yes/no question about a document. Quote the sentence that decides it, or leave quote empty.",
                                        f"Question: {PROPAGATION['probe']} Consider only the CURRENT state the page presents, not its history.\n\nDocument:\n{text[:20000]}",
                                        ProbeOut, tag=f"probe-wiki:{variant}:{rel}")
                hits[f"wiki {rel}"] = res.present
        link.unlink()
        out[f"wiki-{variant}"] = hits
        print(f"wiki-{variant}", {k: v for k, v in hits.items() if v})
    return out


# --- glossary -----------------------------------------------------------------------------------
SYNTHETIC_GLOSSARY = ("Reunião de trabalho. Nomes e termos: Logística Pampa, RotaFácil, Hospital Santa Clara, AgendaClara, José Fontes (Zé), "
                      "Carla Mendes, Bruno Lemos, Ana Tavares, Rafael, doutora Paula Rezende, Felipe, Mapbox, Google Maps, WhatsApp, "
                      "Meta Business, SMS, API, Porto Alegre, Pelotas.")
REAL_TERMS_FILE = PROJECT / "data" / "wiki-eval" / "real_terms.txt"   # names and terms of the user's real meetings: never in the repository


def real_terms() -> list[str]:
    """Terms counted (and given to whisper as a glossary) on real audio, one per line, from a file under data/ (ignored)."""
    if not REAL_TERMS_FILE.exists():
        return []
    return [t.strip() for t in REAL_TERMS_FILE.read_text(encoding="utf-8").splitlines() if t.strip() and not t.startswith("#")]


def glossary_transcriber(prompt: str | None, work: Path) -> Any:
    from teams_recorder.adapters.outbound.transcriber_whispercpp import WhisperCppTranscriber
    c = wc.container_for(work / ".container")
    base = c.transcriber

    class Prompted(WhisperCppTranscriber):
        def whisper_command(self, wav: Path, language: str, out_prefix: Path) -> list[str]:
            return super().whisper_command(wav, language, out_prefix) + (["--prompt", prompt] if prompt else [])

    return Prompted(base.model_path, whisper_cli=base.whisper_cli, ffmpeg=base.ffmpeg, threads=base.threads, vad_model_path=base.vad_model_path)


def real_glossary(spike_wiki: Path) -> str:
    names: list[str] = []
    for page in sorted(spike_wiki.glob("*/*.md")):
        if page.parent.name not in ("people", "projects", "topics"):
            continue
        head = page.read_text(encoding="utf-8").split("---")[1] if page.read_text(encoding="utf-8").startswith("---") else ""
        for key in ("title", "aliases"):
            m = re.search(rf"^{key}: (.*)$", head, re.M)
            if m:
                value = json.loads(m.group(1))
                names += value if isinstance(value, list) else [value]
    extra = real_terms()
    seen = list(dict.fromkeys(n for n in names + extra if len(n) < 60))
    return "Reunião de trabalho. Nomes e termos: " + ", ".join(seen[:80]) + "."


def term_counts(text: str, terms: list[str]) -> dict[str, int]:
    plain = " " + " ".join(words(text)) + " "
    return {t: plain.count(f" {' '.join(words(t))} ") for t in terms}


def glossary(args: argparse.Namespace) -> None:
    out_dir = args.work / "glossary"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    # synthetic: the same audio, with and without the prompt, against the dialogue
    tx = glossary_transcriber(SYNTHETIC_GLOSSARY, args.work)
    key = ["ana", "bruno", "carla", "ze", "jose fontes", "rafael", "paula", "pampa", "rotafacil", "santa clara", "mapbox", "google maps",
           "whatsapp", "meta business", "sms", "45", "24", "13 de fevereiro", "16 de fevereiro", "6 de fevereiro", "28", "12", "porto alegre", "pelotas"]
    for m in planted():
        audio = args.audio / "recordings" / m["id"] / "audio.m4a"
        if not audio.exists():
            continue
        target = out_dir / "synthetic" / f"{m['id']}.txt"
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(tx.transcribe(audio, "pt").as_timestamped_text(), encoding="utf-8")
        ref = words(" ".join(t for s, t in wc.parse_script(wc.CORPUS / m["script"]) if s != "[pause]"))
        base_text = (args.audio / "recordings" / m["id"] / "transcript.txt").read_text(encoding="utf-8")
        with_text = target.read_text(encoding="utf-8")
        squash = lambda t: " ".join(words(t)).replace("rota facil", "rotafacil").replace("metabusiness", "meta business")  # noqa: E731
        ref_counts = term_counts(" ".join(ref).replace("rota facil", "rotafacil"), key)
        hits = lambda t: sum(min(ref_counts[k], term_counts(squash(t), key)[k]) for k in key)  # noqa: E731
        rows.append({"meeting": m["id"], "wer_base": wer(ref, words(base_text)), "wer_glossary": wer(ref, words(with_text)),
                     "terms": sum(ref_counts.values()), "terms_base": hits(base_text), "terms_glossary": hits(with_text)})
        print(f"synthetic {m['id']}: WER {100 * rows[-1]['wer_base']:.1f}% → {100 * rows[-1]['wer_glossary']:.1f}%")
    real = []
    if args.real_meetings:
        terms = [t.lower() for t in real_terms()]
        gloss = real_glossary(args.spike_wiki)
        (out_dir / "real_glossary.txt").write_text(gloss, encoding="utf-8")
        tx_real = glossary_transcriber(gloss, args.work)
        for mid in args.real_meetings.split(","):
            folder = args.real_data / "recordings" / mid
            target = out_dir / "real" / f"{mid}.txt"
            if not target.exists():
                wc.disk_guard(out_dir)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(tx_real.transcribe(folder / "audio.m4a", "pt").as_timestamped_text(), encoding="utf-8")
            base_text = (folder / "transcript.txt").read_text(encoding="utf-8")
            with_text = target.read_text(encoding="utf-8")
            prompt_echo = sum(1 for line in with_text.splitlines() if "nomes e termos" in wc.norm(line))
            real.append({"meeting": mid, "words_base": len(words(base_text)), "words_glossary": len(words(with_text)),
                         "changed": wer(words(base_text), words(with_text)), "prompt_echo_lines": prompt_echo,
                         "terms_base": term_counts(base_text, terms), "terms_glossary": term_counts(with_text, terms)})
            print(f"real {mid}: {100 * real[-1]['changed']:.1f}% of words differ; prompt echoed in {prompt_echo} lines")
    save_json(out_dir / "glossary.json", {"synthetic": rows, "real": real})
    lines = ["# Glossary prompt for whisper", "", "## Synthetic audio (reference = the dialogue)", "",
             "| Meeting | WER without | WER with | fact terms without | fact terms with |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['meeting']} | {100 * r['wer_base']:.1f}% | {100 * r['wer_glossary']:.1f}% | {r['terms_base']}/{r['terms']} | {r['terms_glossary']}/{r['terms']} |")
    if rows:
        tw = sum(r["terms"] for r in rows)
        lines.append(f"| **all** | {100 * sum(r['wer_base'] for r in rows) / len(rows):.1f}% | {100 * sum(r['wer_glossary'] for r in rows) / len(rows):.1f}% | "
                     f"{sum(r['terms_base'] for r in rows)}/{tw} | {sum(r['terms_glossary'] for r in rows)}/{tw} |")
    if real:
        r0 = list(real[0]["terms_base"])
        lines += ["", "## Real audio (no reference yet: counts of names and terms, without → with)", "",
                  "| Meeting | words differ | prompt echoed | " + " | ".join(r0) + " |", "|---|---|---|" + "---|" * len(r0)]
        for r in real:
            lines.append(f"| {r['meeting']} | {100 * r['changed']:.1f}% | {r['prompt_echo_lines']} | "
                         + " | ".join(f"{r['terms_base'][t]}→{r['terms_glossary'][t]}" for t in r0) + " |")
    (out_dir / "glossary_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out_dir / "glossary_report.md")


# --- audit-wiki (test D) -------------------------------------------------------------------------------
CITED = re.compile(r"^\s*-\s+(?:\[[ x]\]\s+)?(.*?)\s*\(\[\[meetings/(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})(?:\|[^\]]*)?\]\]\s*(\d{2}:\d{2}:\d{2})?")


def wiki_bullets(wiki: Path) -> list[dict[str, Any]]:
    planted_ids = {m["id"] for m in planted()}
    bullets = []
    for page in sorted(wiki.rglob("*.md")):
        if page.parent.name not in ("people", "projects", "topics"):
            continue
        for line in page.read_text(encoding="utf-8").splitlines():
            m = CITED.match(line)
            if m and m.group(2) in planted_ids and len(m.group(1)) > 15:
                text = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", m.group(1)).replace("~~", "")
                bullets.append({"id": f"w{len(bullets) + 1:03d}", "page": page.relative_to(wiki).as_posix(), "meeting": m.group(2),
                                "at": m.group(3), "type": "statement", "text": text.strip(), "source": "wiki"})
    return bullets


AUDIT_SYSTEM = """You are the ground-truth judge auditing a wiki compiled by a model from a user's meetings. You receive the exact dialogues of ALL the meetings (every line says who spoke; the user is Felipe) and bullets taken from wiki pages, each citing one meeting.

For each bullet decide:
- fact_correct: true when everything it states is true according to the dialogues taken together (any meeting), including owners, dates, decisions and who said what; false when any part is wrong or invented;
- citation_supports: true when the cited meeting alone supports what the bullet states; false when part of it comes only from other meetings or from nowhere;
- error_type for wrong facts: owner, date, not_said, tentative, sensitive, judgment, other; "none" when fact_correct;
- reason: one short sentence.
Be strict about owners and dates; be lenient about wording. Open questions written as questions are correct when the question really is open or reasonable at that point."""


def audit_wiki(args: argparse.Namespace) -> None:
    from pydantic import BaseModel

    class AuditOut(BaseModel):
        id: str
        fact_correct: bool
        citation_supports: bool
        error_type: Literal["none", "owner", "date", "not_said", "tentative", "participant", "sensitive", "judgment", "other"]
        reason: str

    class AuditBatch(BaseModel):
        labels: list[AuditOut]

    bullets = wiki_bullets(args.wiki)
    rng = random.Random(args.seed)
    sample = rng.sample(bullets, min(args.sample, len(bullets)))
    previous = {r["id"]: r for r in load_json(args.work / f"audit_{args.name}.json")} if (args.work / f"audit_{args.name}.json").exists() else {}
    oracle_tr = transport(ORACLE_MODEL, args.work / "log" / "audit-oracle.jsonl")
    verify_tr = transport(CHECK_MODEL, args.work / "log" / "audit-verify.jsonl", effort="medium")
    dialogues = "\n\n".join(f"### Meeting {m['id']}\n{dialogue(m)}" for m in planted())
    groups = sorted({b["meeting"] for b in sample})

    def run(mid: str) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
        mine = [b for b in sample if b["meeting"] == mid]
        user = f"## Dialogues\n{dialogues}\n\n## Bullets (each cites a meeting)\n" + "\n".join(f"{describe(b)} | cites {b['meeting']}" for b in mine)
        labels = oracle_tr.complete(AUDIT_SYSTEM, user, AuditBatch, tag=f"audit-oracle:{mid}").labels
        transcript = load_transcript(args.data / "recordings" / mid)
        if all(b["id"] in previous and previous[b["id"]]["text"] == b["text"] for b in mine):
            flags = {b["id"]: [f for f in previous[b["id"]]["flags"] if f.startswith("l1_") or f == "no_verdict" or f in L2_KEPT] for b in mine}
        else:
            verdicts = {v["id"]: v for v in verify_meeting(verify_tr, mid, mine, window(transcript, None), 1)}
            flags = {b["id"]: l1_flag(b, verdicts.get(b["id"])) + [f for f in l2_flags(b, transcript) if f in L2_KEPT] for b in mine}
        return [lab.model_dump() for lab in labels], flags

    labels: dict[str, dict[str, Any]] = {}
    flags: dict[str, list[str]] = {}
    for labs, fl in pmap(run, groups, args.jobs):
        labels |= {x["id"]: x for x in labs}
        flags |= fl
    rows = [dict(b, **{k: labels.get(b["id"], {}).get(k) for k in ("fact_correct", "citation_supports", "error_type", "reason")},
                 flags=flags.get(b["id"], [])) for b in sample]
    save_json(args.work / f"audit_{args.name}.json", rows)
    judged = [r for r in rows if r["fact_correct"] is not None]
    wrong = [r for r in judged if not r["fact_correct"]]
    cited_badly = [r for r in judged if r["fact_correct"] and not r["citation_supports"]]
    caught = [r for r in wrong if r["flags"]]
    fp = [r for r in judged if r["fact_correct"] and r["citation_supports"] and r["flags"]]
    clean = [r for r in judged if r["fact_correct"] and r["citation_supports"]]
    lines = [f"# Test D: audit of the wiki `{args.name}` ({len(bullets)} cited bullets, {len(sample)} sampled)", "",
             f"- Facts correct against all the dialogues: **{len(judged) - len(wrong)}/{len(judged)}** ({100 * (len(judged) - len(wrong)) / max(1, len(judged)):.0f}%)",
             f"- Correct facts whose cited meeting does not support them (traceability): {len(cited_badly)}",
             f"- Wrong facts flagged by the defenses (verifier + tuned code checks, against the cited meeting): {len(caught)}/{len(wrong)}",
             f"- Correct, well-cited bullets flagged anyway: {len(fp)}/{len(clean)}", "", "## Wrong facts", ""]
    lines += [f"- `{r['page']}` [{r['error_type']}] {r['text'][:150]} — {r['reason'][:160]} — flags: {', '.join(r['flags']) or 'none'}" for r in wrong]
    lines += ["", "## Correct facts, citation does not support them", ""]
    lines += [f"- `{r['page']}` {r['text'][:150]} — {r['reason'][:140]}" for r in cited_badly]
    (args.work / f"audit_{args.name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.work / f"audit_{args.name}.md")


# --- gate (test E) ----------------------------------------------------------------------------------
GATE = {"owner": 0.9, "date": 0.9, "false_positive_max": 0.10}


def gate(args: argparse.Namespace) -> None:
    m = load_json(args.work / "defense_metrics.json") if (args.work / "defense_metrics.json").exists() else defense_metrics(args.work, args.runs)
    conf = m["configs"][args.config]
    checks = []
    for t in ("owner", "date"):
        values = conf["by_injected_type"].get(t, [])
        checks.append((f"{t} errors caught ≥ {GATE[t]:.0%} on every run", bool(values) and min(values) >= GATE[t], rate(values)))
    fp = conf["false_positive"]
    checks.append((f"correct claims rejected ≤ {GATE['false_positive_max']:.0%} on every run", bool(fp) and max(fp) <= GATE["false_positive_max"], rate(fp)))
    baseline_path = args.work / f"gate_baseline_{re.sub(r'[^a-z0-9]+', '-', args.config.lower()).strip('-')}.json"
    if baseline_path.exists():
        base = load_json(baseline_path)
        noise = max(0.05, max(conf["injected_caught"]) - min(conf["injected_caught"]))
        drop = sum(base["injected_caught"]) / len(base["injected_caught"]) - sum(conf["injected_caught"]) / len(conf["injected_caught"])
        checks.append((f"no regression beyond the noise band ({noise:.0%}) against the baseline", drop <= noise, f"{-drop:+.0%}"))
    else:
        save_json(baseline_path, conf)
    ok = all(c[1] for c in checks)
    lines = [f"# Test E: regression gate ({args.config}) — {'PASS' if ok else 'FAIL'}", ""] + [f"- {'✓' if p else '✗'} {name}: {value}" for name, p, value in checks]
    with (args.work / "gate_report.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n\n")
    print("\n".join(lines))


# --- review kit (human reference for real transcription) --------------------------------------------
def review_kit(args: argparse.Namespace) -> None:
    kit = args.out
    kit.mkdir(parents=True, exist_ok=True)
    readme = ["# Revisão humana da transcrição", "",
              "Cada pasta tem um trecho de 2 minutos de uma reunião real (`trecho.m4a`) e o que o whisper transcreveu (`whisper.txt`).",
              "", "1. Ouça o trecho e corrija `corrigido.txt` (é uma cópia de `whisper.txt`): conserte as palavras erradas, nomes e termos.",
              "2. Não precisa acertar pontuação. Mantenha uma frase por linha; os horários podem ficar como estão.",
              "3. Rode: `.venv/bin/python scripts/fidelity_eval.py score-kit --kit data/wiki-eval/transcription-review`", "",
              "Os arquivos ficam em data/ (fora do Git). O áudio original é apagado pela retenção 30 dias depois da reunião."]
    for spec in args.excerpts.split(","):
        mid, start = spec.split("@")
        folder = kit / f"{mid}_{start.replace(':', '-')}"
        folder.mkdir(exist_ok=True)
        src = args.real_data / "recordings" / mid
        s0 = seconds(start) or 0
        if not (folder / "trecho.m4a").exists():
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(s0), "-t", str(args.length), "-i", str(src / "audio.m4a"), "-c", "copy",
                            str(folder / "trecho.m4a")], check=True)
        lines = [f"[{int(s) // 3600:02d}:{int(s) % 3600 // 60:02d}:{int(s) % 60:02d}] {x}" for s, x in load_transcript(src) if s0 <= s < s0 + args.length]
        (folder / "whisper.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if not (folder / "corrigido.txt").exists():
            (folder / "corrigido.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        glossary_file = args.work / "glossary" / "real" / f"{mid}.txt"
        if glossary_file.exists():
            g = [x for x in glossary_file.read_text(encoding="utf-8").splitlines()
                 if (lambda t: t is not None and s0 <= t < s0 + args.length)(seconds(x[1:9]) if x.startswith("[") else None)]
            (folder / "whisper_glossario.txt").write_text("\n".join(g) + "\n", encoding="utf-8")
    (kit / "LEIA-ME.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(kit)


def score_kit(args: argparse.Namespace) -> None:
    rows = []
    for folder in sorted(p for p in args.kit.iterdir() if p.is_dir()):
        ref = words((folder / "corrigido.txt").read_text(encoding="utf-8"))
        row = {"excerpt": folder.name, "words": len(ref), "wer_whisper": wer(ref, words((folder / "whisper.txt").read_text(encoding="utf-8")))}
        if (folder / "whisper_glossario.txt").exists():
            row["wer_glossary"] = wer(ref, words((folder / "whisper_glossario.txt").read_text(encoding="utf-8")))
        rows.append(row)
        print(row)
    save_json(args.kit / "score.json", rows)


# --- CLI ------------------------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def p(name: str, fn: Any, **flags: Any) -> argparse.ArgumentParser:
        sp = sub.add_parser(name)
        sp.set_defaults(fn=fn)
        sp.add_argument("--work", type=Path, required=True)
        sp.add_argument("--jobs", type=int, default=4)
        sp.add_argument("--runs", type=int, default=3)
        return sp

    sp = p("setup", setup)
    sp.add_argument("--source", type=Path, required=True, help="data dir whose recordings hold the planted meetings, analyzed")
    sp = p("oracle", oracle)
    sp.add_argument("--include-injected", action="store_true", help="also label the injected claims (checks the oracle itself)")
    sp = p("inject", inject)
    sp.add_argument("--seed", type=int, default=7)
    p("defend", defend)
    p("report", report)
    sp = p("stories", stories)
    sp.add_argument("--wiki", type=Path, required=True, help="the 9-meeting wiki (a Git repository, one commit per ingest)")
    sp.add_argument("--only", help="comma-separated variants")
    sp = p("verify-stories", verify_stories)
    sp.add_argument("--variants", default="baseline,wiki,defended,defended_wiki")
    sp = p("propagate", propagate)
    sp.add_argument("--wiki", type=Path, help="the 9-meeting wiki, for --wiki-ingest")
    sp.add_argument("--wiki-ingest", action="store_true")
    sp.add_argument("--scratch", type=Path, help="a folder OUTSIDE the repository for the wiki copies")
    sp = p("glossary", glossary)
    sp.add_argument("--audio", type=Path, required=True, help="data dir with the planted meetings' audio.m4a")
    sp.add_argument("--real-data", type=Path)
    sp.add_argument("--real-meetings", help="comma-separated real meeting ids (read-only)")
    sp.add_argument("--spike-wiki", type=Path)
    sp = p("audit-wiki", audit_wiki)
    sp.add_argument("--wiki", type=Path, required=True)
    sp.add_argument("--data", type=Path, required=True, help="data dir with the planted meetings' transcripts")
    sp.add_argument("--name", required=True)
    sp.add_argument("--sample", type=int, default=40)
    sp.add_argument("--seed", type=int, default=11)
    sp = p("gate", gate)
    sp.add_argument("--config", default="L1 + L2")
    sp = p("review-kit", review_kit)
    sp.add_argument("--real-data", type=Path, required=True)
    sp.add_argument("--excerpts", required=True, help="id@HH:MM:SS,…")
    sp.add_argument("--length", type=int, default=120)
    sp.add_argument("--out", type=Path, required=True)
    sp = sub.add_parser("score-kit")
    sp.set_defaults(fn=score_kit)
    sp.add_argument("--kit", type=Path, required=True)
    args = parser.parse_args()
    for name in ("work", "source", "wiki", "scratch", "audio", "real_data", "spike_wiki", "data", "out", "kit"):
        if getattr(args, name, None) is not None:
            setattr(args, name, getattr(args, name).expanduser().resolve())
    args.fn(args)


if __name__ == "__main__":
    main()
