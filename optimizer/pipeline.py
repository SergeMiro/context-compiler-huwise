"""Configuration C: Context Compiler + Context Optimizer. route -> (FAST recipe | STANDARD/DEEP agent with grounded
query) -> evidence check -> answer. Every step is a span (name, ms, attributes), never with the API key or prompt."""
import re
import time

from catalog.models import Dataset
from tools import ToolError, query as tool_query

from . import cache, evidence, router
from .values import candidates, literal, norm

DEEP_STEPS, STANDARD_STEPS = 8, 6
EQ = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'([^']*)'")


def _ds(domain, dataset_id):
    return Dataset.objects.filter(portal__domain=domain, dataset_id=dataset_id).first()


def _hints(domain, ds, where):
    """0 rows with an equality filter: say how the value is really written (case, accents, leading zeros)."""
    out = []
    samples = {f.name: f.sample_values for f in ds.fields.all()}
    for field, value in EQ.findall(where or ""):
        if field not in samples:
            continue
        lens = {len(str(s)) for s in samples[field] if str(s).isdigit()}
        if value.isdigit() and lens and max(lens) > len(value):
            out.append(f"{field}: codes are written with leading zeros, try {literal(value.zfill(max(lens)))}")
            continue
        try:
            found = [v for v, _ in candidates(domain, ds.dataset_id, field, value)]
        except Exception:  # hint is best effort: the query result itself is already correct
            found = []
        same = [v for v in found if norm(v) == norm(value) and v != value]
        if value in found:
            continue  # this filter value exists: the empty result comes from another condition
        if same:
            out.append(f"{field}: {literal(value)} is stored as {literal(same[0])}")
        elif found:
            out.append(f"{field}: no row has {literal(value)}; stored values close to it: "
                       + ", ".join(literal(v) for v in found[:3]))
    return out


def grounded_query(domain, dataset_id, params, api_key=None, recipe=""):
    """tools.query + cache + value hints on an empty result. Same validation, same tool log."""
    ds = _ds(domain, dataset_id)
    k = cache.key(domain, cache.scope_of(api_key), ds, params, recipe) if ds else None
    if k and (hit := cache.CACHE.get(k)) is not None:
        return hit | {"cache": "hit"}
    res = tool_query(domain, dataset_id, params, api_key=api_key)
    if "error" in res:
        return res
    if ds and res.get("total_count") == 0 and params.get("where"):
        hints = _hints(domain, ds, params["where"])
        if hints:
            res["hint"] = hints
    if k:
        cache.CACHE.put(k, res)
    return res | {"cache": "miss"}


def _fast(domain, question, plan, api_key):
    t = time.monotonic()
    res = grounded_query(domain, plan["dataset_id"], plan["params"], api_key=api_key, recipe=plan["recipe"])
    span = {"name": "query", "ms": int((time.monotonic() - t) * 1000), "ok": "error" not in res,
            "cache": res.get("cache")}
    if "error" in res:
        raise ToolError("recipe_failed", res["error"])
    n = res["total_count"]
    filters = ", ".join(f"{k} = {v}" for k, v in plan["slots"].items())
    answer = f"{n} établissement{'s' if n != 1 else ''} ({filters}) — source : {plan['dataset_id']}."
    q = {"dataset_id": plan["dataset_id"], "params": plan["params"], "ok": True,
         "result": {"total_count": n, "results": []}}
    return answer, [q], [span]


def answer(domain, question, api_key=None, chat=None):
    """-> {answer, route, reasons, evidence, spans, steps, tokens, ms, llm_calls}"""
    from evals.agent import run_agent
    t0 = time.monotonic()
    t = time.monotonic()
    r = router.route(domain, question)
    spans = [{"name": "route", "ms": int((time.monotonic() - t) * 1000), "route": r["route"],
              "policy": r["policy"], "value_lookups": len((r.get("plan") or {}).get("calls", r.get("calls", [])))}]
    steps = tokens = llm_calls = 0
    transcript = []
    if r["route"] == "FAST":
        try:
            text, queries, s = _fast(domain, question, r["plan"], api_key)
            spans += s
        except ToolError as e:  # recipe broke at run time: fall back to the agent, never answer unbacked
            r = r | {"route": "STANDARD", "reasons": r["reasons"] + [f"recipe failed: {e}"]}
    if r["route"] != "FAST":
        res = run_agent(domain, question, "optimized", chat=chat,
                        max_steps=DEEP_STEPS if r["route"] == "DEEP" else STANDARD_STEPS)
        text, queries, transcript = res["answer"], res["queries"], res["transcript"]
        spans += res["spans"]
        steps, tokens, llm_calls = res["steps"], res["tokens"], sum(s["name"] == "llm" for s in res["spans"])
    t = time.monotonic()
    ds = _ds(domain, queries[-1]["dataset_id"]) if queries else None
    meta = {"schema_version": cache.schema_version(ds), "data_version": cache.data_version(ds)} if ds else None
    ev = evidence.contract(domain, question, text, queries, meta)
    if ev["status"] == "blocked":  # a number nothing returned: do not state it
        text = ("Je ne peux pas donner de réponse vérifiée : " + "; ".join(ev["reasons"]) + ".")
    spans.append({"name": "verify", "ms": int((time.monotonic() - t) * 1000), "status": ev["status"]})
    return {"answer": text, "route": r["route"], "reasons": r["reasons"], "evidence": ev, "spans": spans,
            "steps": steps, "tokens": tokens, "llm_calls": llm_calls, "queries": queries,
            "transcript": transcript, "ms": int((time.monotonic() - t0) * 1000)}
