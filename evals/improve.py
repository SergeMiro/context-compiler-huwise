"""autoresearch-style loop over context: propose one edit per failing dataset, re-run the failing cases plus a
control sample of passing ones, keep the edit only if answers improved and nothing regressed; otherwise revert."""
import json
import random
import re

from django.utils import timezone

import llm as llm_mod
from catalog.models import Dataset
from ctx.compile import compile_dataset, current
from ctx.models import ContextEdit
from evals.models import EvalCase, EvalRun
from evals.runner import run_eval
from projections.es import upsert_es

CONTROL = 10
KINDS = {k for k, _ in ContextEdit.KINDS}
PROMPT = """You maintain the context card that AI agents read before querying a dataset of the portal {domain}.
Agents failed these questions while using this card. Propose ONE edit to the card that would have prevented the
failures, using only facts visible in the card and the transcripts (field names, value formats, errors returned).

Card:
{card}

Failures:
{failures}

Edit kinds: "synonyms" (comma-separated words people use for this dataset), "description" (replaces the
description, <= 400 chars), "query_template" (one ODSQL example: select=...&where=...), "note" (one rule, <= 200
chars, e.g. a value format or a field to use).
Reply with JSON only: {{"kind": "...", "after": "...", "rationale": "..."}}"""


def _failures(results):
    out = []
    for r in results:
        calls = [m for m in r.transcript if m.get("role") in ("assistant", "tool")][-6:]
        steps = "\n".join(f"  {m['role']}: {json.dumps(m.get('tool_calls') or m.get('content'), ensure_ascii=False)[:400]}"
                          for m in calls)
        out.append(f"- Q: {r.case.question}\n  expected: {r.case.expected_value!r}\n  agent answered: {r.answer[:200]!r}\n{steps}")
    return "\n".join(out)


def _parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(m.group()) if m else None
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("kind") not in KINDS or not str(data.get("after", "")).strip():
        return None
    return data


def llm_calls_today(portal):
    start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return ContextEdit.objects.filter(dataset__portal=portal, source="llm", created_at__gte=start).count()


def propose(portal, run, chat=None, max_edits=10):
    chat = chat or llm_mod.chat
    # holdout cases never reach the proposer: neither their questions nor their transcripts
    failed = [r for r in run.results.select_related("case")
              if not r.answer_ok and r.case.expected_datasets and r.case.split != "holdout"]
    groups = {}
    for r in failed:
        groups.setdefault(r.case.expected_datasets[0], []).append(r)
    edits = []
    for dataset_id, results in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:max_edits]:
        if llm_calls_today(portal) >= portal.llm_budget_per_day:
            break
        ds = Dataset.objects.get(portal=portal, dataset_id=dataset_id)
        card = current(ds)
        reply = chat([{"role": "user", "content": PROMPT.format(domain=portal.domain, card=card.full,
                                                                failures=_failures(results))}])
        data = _parse(reply["message"]["content"])
        if data is None:  # invalid JSON or kind: skip, still counts against the budget via a rejected edit
            ContextEdit.objects.create(dataset=ds, kind="note", after="(invalid proposal)", source="llm",
                                       status="rejected", rationale=(reply["message"]["content"] or "")[:1000])
            continue
        edits.append(ContextEdit.objects.create(
            dataset=ds, kind=data["kind"], before=card.full, after=str(data["after"]).strip()[:1000], source="llm",
            rationale=str(data.get("rationale", ""))[:1000],
            eval_before={"run": run.id, "failed": [r.case.slug for r in results]}))
    return edits


def apply_edit(edit, chat=None):
    """Try the edit; keep it only if more failing cases pass and no control case regresses. Preprod only: it writes
    a candidate card and re-projects it into the search index."""
    from lab.cycle import guard
    guard()
    portal, ds = edit.dataset.portal, edit.dataset
    baseline = EvalRun.objects.get(id=edit.eval_before["run"])
    per_case = baseline.metrics["per_case"]
    failed = edit.eval_before["failed"]
    holdout = set(EvalCase.objects.filter(portal=portal, split="holdout").values_list("slug", flat=True))
    passing = sorted(s for s, v in per_case.items() if v["answer_ok"] and s not in holdout)
    control = random.Random(edit.id).sample(passing, min(CONTROL, len(passing)))
    edit.status = "kept"  # tentatively, so compile includes it
    edit.save(update_fields=["status"])
    compile_dataset(ds)
    upsert_es(ds)
    after = run_eval(portal, baseline.mode, chat=chat, slugs=set(failed) | set(control),
                     suite=baseline.metrics.get("suite", "education"))
    now = {s: v["answer_ok"] for s, v in after.metrics["per_case"].items()}
    fixed = [s for s in failed if now.get(s)]
    broken = [s for s in control if not now.get(s)]
    edit.status = "kept" if fixed and not broken else "reverted"
    edit.eval_after = {"run": after.id, "fixed": fixed, "broken": broken, "control": control}
    edit.decided_at = timezone.now()
    edit.save(update_fields=["status", "eval_after", "decided_at"])
    if edit.status == "reverted":
        compile_dataset(ds)  # card content goes back to the version without the edit
        upsert_es(ds)
    return edit


def improve(portal, mode="propose", run=None, proposer=None, agent=None, max_edits=10):
    run = run or EvalRun.objects.filter(portal=portal, mode="compiled", finished_at__isnull=False).latest("id")
    edits = propose(portal, run, chat=proposer, max_edits=max_edits)
    if mode == "auto":
        for e in edits:
            apply_edit(e, chat=agent)
    kept = [e for e in edits if e.status == "kept"]
    base_ok = sum(v["answer_ok"] for v in run.metrics["per_case"].values())
    return {"proposed": len(edits), "kept": len(kept), "reverted": sum(e.status == "reverted" for e in edits),
            "correct_before": base_ok, "correct_after": base_ok + sum(len(e.eval_after.get("fixed", [])) for e in kept),
            "of": run.metrics["n"], "edits": [e.id for e in edits]}
