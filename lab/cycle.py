"""One AutoContext Lab cycle. Builds on evals/improve.py (propose one card edit per failing dataset, apply_edit =
re-run failing + control cases, keep or revert) and adds what makes it safe to run unattended: an environment guard,
a budget, failure diagnosis, a static check of the edit, a versioned quality gate and an append-only log."""
import json
import re
import time
from pathlib import Path

from django.conf import settings

import llm as llm_mod
from catalog.models import Dataset
from ctx.models import ContextEdit
from evals import improve
from evals.agent import MAX_STEPS
from evals.models import EvalRun
from tools.odsql import ODSQLRejected, validate

from . import log

POLICY = json.loads((Path(__file__).parent / "policy.json").read_text())
INJECTION = re.compile(r"(ignore (all|previous)|system prompt|you are now|https?://|<script|api[_ ]?key)", re.I)


class LabRefused(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


def guard():
    """The lab writes candidate cards and runs evals: only in preprod (own database and ES alias)."""
    if settings.CTXC_ENV != "preprod":
        raise LabRefused(f"AutoContext Lab runs only with CTXC_ENV=preprod (now: {settings.CTXC_ENV})")
    return f"preprod:{settings.DATABASES['default']['NAME']}:{settings.ES_INDEX}"


def diagnose(result):
    """EvalResult -> one category. Deterministic, from the transcript and the golden case."""
    case, msgs = result.case, result.transcript or []
    tool_out = " ".join(m.get("content") or "" for m in msgs if m.get("role") == "tool").lower()
    if "forbidden" in tool_out or "api refused access" in tool_out:
        return "permission_error"
    if case.expected_datasets and result.found_dataset and result.found_dataset not in case.expected_datasets:
        return "wrong_asset"
    if "unknown field" in tool_out or "odsqlerror" in tool_out or "query rejected" in tool_out:
        return "schema_mismatch"
    if result.steps >= MAX_STEPS and not result.answer:
        return "latency"
    if not result.found_dataset:
        return "wrong_asset" if case.expected_datasets else "no_answer"
    if '"total_count": 0' in tool_out:
        return "wrong_filter"
    from optimizer.evidence import check  # numbers in the answer that no query returned
    queries = [{"dataset_id": result.found_dataset, "ok": True, "result": _result_of(m)}
               for m in msgs if m.get("role") == "tool" and '"total_count"' in (m.get("content") or "")]
    if check(case.question, result.answer, queries)["status"] == "blocked":
        return "hallucinated_value"
    return "wrong_filter"


def _result_of(msg):
    try:
        return json.loads(msg["content"])
    except (json.JSONDecodeError, TypeError):
        return {}


def static_check(edit, cases):
    """Reject an edit before spending any eval on it. -> list of problems ([] = passes)."""
    problems, text = [], edit.after
    if edit.kind not in POLICY["editable_artifacts"]:
        problems.append(f"kind {edit.kind} is not an editable artifact")
    if INJECTION.search(text):
        problems.append("looks like an instruction or a link, not a fact about the data")
    if edit.kind == "query_template":
        params = dict(p.split("=", 1) for p in text.split("&") if "=" in p)
        try:
            validate(edit.dataset.fields.values_list("name", flat=True), params)
        except ODSQLRejected as e:
            problems.append(f"query template does not validate: {e}")
    for c in cases:  # no answer leakage: an edit may not carry a golden expected value
        v = c.expected_value
        if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) >= 10 and re.search(rf"\b{int(v)}\b", text):
            problems.append(f"contains the expected answer of {c.slug}")
        elif isinstance(v, str) and len(v) > 3 and v.lower() in text.lower() and v.lower() not in edit.before.lower():
            problems.append(f"contains the expected answer of {c.slug}")
    return problems


def gate(edit, base_run):
    """Versioned policy, decided before the run. -> (keep: bool, reasons)"""
    g, after = POLICY["gate"], EvalRun.objects.get(id=edit.eval_after["run"])
    reasons = []
    fixed, broken = edit.eval_after.get("fixed", []), edit.eval_after.get("broken", [])
    if len(fixed) < g["min_fixed"]:
        reasons.append(f"fixed {len(fixed)} < {g['min_fixed']}")
    if len(broken) > g["max_broken_control"]:
        reasons.append(f"broke control cases: {', '.join(broken)}")
    before_pc, after_pc = base_run.metrics["per_case"], after.metrics["per_case"]
    new_wrong = [s for s, v in after_pc.items() if not v["answer_ok"] and not v.get("abstained")
                 and (before_pc.get(s, {}).get("answer_ok") or before_pc.get(s, {}).get("abstained"))]
    if len(new_wrong) > g["max_new_wrong_confident"]:
        reasons.append(f"new confident wrong answers: {', '.join(new_wrong)}")
    t_before = sum(before_pc[s].get("tokens", 0) for s in after_pc if s in before_pc)
    t_after = sum(v.get("tokens", 0) for v in after_pc.values())
    if t_before and 100 * (t_after - t_before) / t_before > g["max_tokens_increase_pct"]:
        reasons.append(f"tokens +{round(100 * (t_after - t_before) / t_before)} %")
    return not reasons, reasons or ["all gate rules passed"]


class Budget:
    def __init__(self, chat, max_calls, max_seconds):
        self.chat, self.max_calls, self.calls = chat, max_calls, 0
        self.deadline = time.monotonic() + max_seconds

    def __call__(self, *a, **kw):
        return self.wrap(self.chat)(*a, **kw)

    def wrap(self, fn):
        """Same counter for every model the cycle uses (proposer and agent)."""
        def call(*a, **kw):
            if self.calls >= self.max_calls or time.monotonic() > self.deadline:
                raise BudgetExceeded(f"budget used: {self.calls} model calls")
            self.calls += 1
            return fn(*a, **kw)
        return call


def run_cycle(portal, base_run=None, chat=None, agent=None, max_proposals=None, max_calls=None):
    """-> list of log rows. Proposer sees only dev failures; holdout cases are never loaded here.
    chat = proposer model, agent = model of the eval agent (default: the same); one budget for both."""
    fork = guard()
    b = POLICY["budget"]
    budget = Budget(chat or llm_mod.chat, max_calls or b["max_llm_calls"], b["max_seconds"])
    agent_chat = budget.wrap(agent or chat or llm_mod.chat)
    base_run = base_run or EvalRun.objects.filter(portal=portal, mode__in=("compiled", "optimized"),
                                                  finished_at__isnull=False).latest("id")
    results = [r for r in base_run.results.select_related("case") if r.case.split in ("", "dev")]
    failures = [r for r in results if not r.answer_ok and r.case.expected_datasets]
    diagnosis = {r.case.slug: diagnose(r) for r in failures}
    rows = [log.append({"step": "collect+diagnose", "fork": fork, "policy": POLICY["version"], "base_run": base_run.id,
                        "model": base_run.model, "failures": diagnosis})]
    cases = [r.case for r in results]
    try:
        edits = improve.propose(portal, base_run, chat=budget, max_edits=max_proposals or b["max_proposals"])
    except BudgetExceeded as e:
        return rows + [log.append({"step": "stopped", "reason": str(e)})]
    for edit in edits:
        problems = static_check(edit, cases)
        entry = {"step": "experiment", "edit": edit.id, "dataset": edit.dataset.dataset_id, "kind": edit.kind,
                 "diff": {"before": "(card v%s)" % _card_version(edit.dataset), "after": edit.after},
                 "rationale": edit.rationale[:500], "static_check": problems or "ok"}
        if problems:
            edit.status = "rejected"
            edit.save(update_fields=["status"])
            rows.append(log.append(entry | {"decision": "rejected"}))
            continue
        try:
            improve.apply_edit(edit, chat=agent_chat)
        except BudgetExceeded as e:
            edit.status = "proposed"
            edit.save(update_fields=["status"])
            rows.append(log.append(entry | {"decision": "stopped", "reason": str(e)}))
            break
        keep, reasons = gate(edit, base_run)
        if edit.status == "kept" and not keep:  # improve kept it on fixed/broken; the stricter gate says no
            _revert(edit)
        edit.eval_after = edit.eval_after | {"gate": {"policy": POLICY["version"], "keep": keep, "reasons": reasons}}
        edit.save(update_fields=["eval_after"])
        rows.append(log.append(entry | {"decision": edit.status, "gate": reasons, "eval_run": edit.eval_after["run"],
                                        "fixed": edit.eval_after.get("fixed"), "broken": edit.eval_after.get("broken")}))
    rows.append(log.append({"step": "done", "model_calls": budget.calls}))
    return rows


def _card_version(ds):
    c = ds.cards.order_by("-version").first()
    return c.version if c else 0


def _revert(edit):
    from django.utils import timezone

    from ctx.compile import compile_dataset
    from projections.es import upsert_es
    edit.status = "reverted"
    edit.decided_at = timezone.now()
    edit.save(update_fields=["status", "decided_at"])
    compile_dataset(edit.dataset)
    upsert_es(edit.dataset)
