"""Run golden cases through the agent and score them deterministically (no LLM judge)."""
import json
import re
import statistics
import unicodedata

from django.utils import timezone

import llm as llm_mod
from catalog.models import Dataset
from ctx.compile import current
from evals.agent import run_agent
from evals.golden import NO_DATA
from evals.models import EvalCase, EvalResult, EvalRun

RESULT_FIELDS = {"found_dataset", "odsql_valid_first_try", "answer", "answer_ok", "steps", "ms", "tokens", "transcript"}
NUM = re.compile(r"-?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?")
NO_DATA_MARKERS = ("pas de donnees", "aucune donnee", "pas disponible", "n'existe pas")


def norm(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", text.replace("’", "'")).strip()


def numbers(text):
    out = []
    for m in NUM.findall(text or ""):
        m = re.sub(r"[   ]", "", m).replace(",", ".")
        try:
            out.append(float(m))
        except ValueError:
            pass
    return out


def answer_ok(case, answer):
    if case.expected_value == NO_DATA:
        return any(k in norm(answer) for k in NO_DATA_MARKERS)
    if isinstance(case.expected_value, (int, float)):
        exp = float(case.expected_value)
        asked = set(numbers(case.question))
        # numbers taken from the question (years, "80") do not count as the answer
        return any(abs(n - exp) <= max(abs(exp) * case.tolerance, 0.5) for n in numbers(answer) if n not in asked)
    return norm(case.expected_value) in norm(answer)


def score(case, res):
    from optimizer.evidence import check
    queries = res["queries"]
    found = next((q["dataset_id"] for q in reversed(queries) if q["ok"]), queries[-1]["dataset_id"] if queries else "")
    ok = answer_ok(case, res["answer"])
    return dict(found_dataset=found, answer=res["answer"][:2000], answer_ok=ok,
                dataset_ok=(found in case.expected_datasets) if case.expected_datasets else ok,
                odsql_valid_first_try=bool(queries) and queries[0]["ok"], steps=res["steps"], ms=res["ms"],
                tokens=res["tokens"], transcript=res["transcript"], route=res.get("route", ""),
                evidence=check(case.question, res["answer"], queries)["status"],
                abstained=any(k in norm(res["answer"]) for k in NO_DATA_MARKERS + ("je ne peux pas",)))


def condense(transcript, result_chars=400):
    """Transcript -> the agent's logic for a page: [{tool, args, result, ok}], without system/user messages."""
    steps, pending = [], {}
    for m in transcript:
        if m.get("role") == "assistant":
            for c in m.get("tool_calls") or []:
                try:
                    args = json.loads(c["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {"raw": c["function"]["arguments"]}
                pending[c["id"]] = {"tool": c["function"]["name"], "args": args}
        elif m.get("role") == "tool" and m.get("tool_call_id") in pending:
            step = pending.pop(m["tool_call_id"])
            text = m.get("content") or ""
            step.update(ok=not text.startswith('{"error"'), result=text[:result_chars])
            steps.append(step)
    return steps


def public_row(row):
    """A scored row as the showcase shows it (no prompt, no raw transcript)."""
    return {k: row.get(k) for k in ("answer", "answer_ok", "dataset_ok", "found_dataset", "steps", "ms", "tokens",
                                     "route", "evidence")} | {
        "trace": condense(row["transcript"])}


def _pct(xs):
    return round(100 * sum(xs) / len(xs), 1) if xs else None


def metrics(rows, cases):
    tags = sorted({t for c in cases for t in c.tags})
    ms = [r["ms"] for r in rows]
    with_q = [r for r in rows if r["found_dataset"]]
    return {
        "n": len(rows), "answer_ok": _pct([r["answer_ok"] for r in rows]),
        "dataset_ok": _pct([r["dataset_ok"] for r in rows]),
        "odsql_first_try": _pct([r["odsql_valid_first_try"] for r in with_q]),
        "ms_median": int(statistics.median(ms)) if ms else 0,
        "ms_p95": int(statistics.quantiles(ms, n=20)[18]) if len(ms) >= 2 else (ms[0] if ms else 0),
        "steps_avg": round(statistics.mean(r["steps"] for r in rows), 2) if rows else 0,
        "tokens": sum(r["tokens"] for r in rows),
        "by_tag": {t: _pct([r["answer_ok"] for r, c in zip(rows, cases) if t in c.tags]) for t in tags},
        # wrong AND stated as fact (no abstention): the error that misleads a user
        "wrong_confident": sum(1 for r in rows if not r["answer_ok"] and not r["abstained"]),
        "verified": _pct([r["evidence"] == "verified" for r in rows]),
        "llm_calls": sum(r.get("llm_calls", r["steps"]) for r in rows),
        "routes": {k: sum(r["route"] == k for r in rows) for k in ("FAST", "STANDARD", "DEEP") if any(r["route"] == k for r in rows)},
    }


def _run(domain, question, mode, chat):
    """One case; a provider outage (5xx/429 after llm.chat's own retries) waits a minute and retries the whole
    case twice, so a free model's bad minute does not kill a 2-hour run. Other errors propagate."""
    import os
    import time

    import elastic_transport
    import httpx
    tries = int(os.environ.get("CTXC_EVAL_CASE_RETRIES", "3"))
    for attempt in range(tries):
        try:
            return _run_once(domain, question, mode, chat)
        except (httpx.HTTPStatusError, httpx.TransportError, elastic_transport.TransportError) as e:  # ES times out under memory pressure
            status = getattr(getattr(e, "response", None), "status_code", None)
            if attempt == tries - 1 or (status is not None and status not in llm_mod.RETRY_STATUS):
                raise
            time.sleep(int(os.environ.get("CTXC_EVAL_CASE_PAUSE", "60")))


def _run_once(domain, question, mode, chat):
    if mode == "optimized":
        from optimizer.pipeline import answer
        return answer(domain, question, chat=chat)
    return run_agent(domain, question, mode, chat=chat)


def _commit():
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def run_eval(portal, mode, chat=None, slugs=None, model=None, suite="education", split=None):
    cases = EvalCase.objects.filter(portal=portal, suite=suite).order_by("id")
    cases = list(cases.filter(split=split) if split else cases)
    if slugs:
        cases = [c for c in cases if c.slug in slugs]
    ids = {d for c in cases for d in c.expected_datasets}
    versions = {ds.dataset_id: getattr(current(ds), "version", None)
                for ds in Dataset.objects.filter(portal=portal, dataset_id__in=ids)}
    run = EvalRun.objects.create(portal=portal, mode=mode, model=model or llm_mod.model_name(), card_versions=versions)
    rows = []
    for case in cases:
        res = _run(portal.domain, case.question, mode, chat)
        row = score(case, res) | {"llm_calls": res.get("llm_calls", res["steps"])}
        EvalResult.objects.create(run=run, case=case, **{k: v for k, v in row.items() if k in RESULT_FIELDS})
        rows.append(row)
    run.metrics = metrics(rows, cases)
    run.metrics["per_case"] = {c.slug: {"answer_ok": r["answer_ok"], "dataset_ok": r["dataset_ok"], "route": r["route"],
                                        "evidence": r["evidence"], "abstained": r["abstained"], "ms": r["ms"],
                                        "tokens": r["tokens"], "llm_calls": r["llm_calls"]}
                               for c, r in zip(cases, rows)}
    run.metrics.update(suite=suite, split=split or "all", commit=_commit())
    run.finished_at = timezone.now()
    run.save()
    return run


def table(runs):
    keys = [("answer_ok", "correct answer %"), ("dataset_ok", "right dataset %"), ("odsql_first_try", "valid query 1st try %"),
            ("steps_avg", "steps / question"), ("ms_median", "median ms"), ("ms_p95", "p95 ms"), ("tokens", "tokens"), ("llm_calls", "model calls"), ("wrong_confident", "wrong and stated as fact"), ("verified", "evidence verified %")]
    head = "| metric | " + " | ".join(r.mode for r in runs) + " |\n|---|" + "---|" * len(runs)
    lines = [f"| {label} | " + " | ".join(str(r.metrics.get(k)) for r in runs) + " |" for k, label in keys]
    return f"model: {runs[0].model} · cases: {runs[0].metrics['n']}\n\n" + head + "\n" + "\n".join(lines)
