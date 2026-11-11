"""Minimal tool-calling loop, no framework. Same model, same prompt, two toolsets:
`compiled` (our cards) vs `naked` (generic catalog access, named like Huwise's MCP tools)."""
import json
import time

import llm as llm_mod
import tools

SYSTEM = ("Tu réponds à des questions sur les données du portail {domain}, uniquement à partir des résultats des "
          "outils. Étapes : trouver le jeu de données, lire sa description, puis interroger les enregistrements. "
          "Termine par une phrase courte avec le nombre ou le nom exact. Si le portail n'a pas ces données, "
          "réponds exactement « pas de données ».")
MAX_STEPS, MAX_RESULT_CHARS = 6, 6000

_QUERY_PARAMS = {"type": "object", "properties": {
    "dataset_id": {"type": "string"},
    "select": {"type": "string", "description": "ODSQL select, e.g. count(*) as n"},
    "where": {"type": "string", "description": "ODSQL where"},
    "group_by": {"type": "string"}, "order_by": {"type": "string"},
    "limit": {"type": "integer", "description": "max 100"}}, "required": ["dataset_id"]}


def _fn(name, description, params):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}


def _q(question):
    return {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}


_ID = {"type": "object", "properties": {"dataset_id": {"type": "string"}}, "required": ["dataset_id"]}

TOOLSETS = {
    "compiled": {
        "find_dataset": (_fn("find_dataset", "Find datasets that can answer the question (short cards, best first).",
                             _q("question")), lambda d, a: tools.find_dataset(d, a["question"])),
        "explain_dataset": (_fn("explain_dataset", "Full card: fields, types, value formats, query hints, joins.", _ID),
                            lambda d, a: tools.explain_dataset(d, a["dataset_id"])),
        "query": (_fn("query", "ODSQL query on a dataset's records (read-only, limit <= 100).", _QUERY_PARAMS),
                  lambda d, a: tools.query(d, a["dataset_id"], _params(a))),
    },
    "naked": {
        "search_assets": (_fn("search_assets", "Search the catalog of datasets.", _q("question")),
                          lambda d, a: tools.naked_search(d, a["question"])),
        "get_asset": (_fn("get_asset", "Metadata, schema and example records of a dataset.", _ID),
                      lambda d, a: tools.naked_get(d, a["dataset_id"])),
        "search_asset_records": (_fn("search_asset_records", "ODSQL query on a dataset's records.", _QUERY_PARAMS),
                                 lambda d, a: tools.naked_query(d, a["dataset_id"], _params(a))),
    },
}
TOOLSETS["optimized"] = dict(TOOLSETS["compiled"])  # same tools, the query is grounded (cache + value hints)
TOOLSETS["optimized"]["query"] = (TOOLSETS["compiled"]["query"][0],
                                  lambda d, a: _grounded()(d, a["dataset_id"], _params(a)))
QUERY_TOOLS = {"query", "search_asset_records"}


def _grounded():
    from optimizer.pipeline import grounded_query  # optimizer imports evals: import late
    return grounded_query


def _params(args):
    return {k: v for k, v in args.items() if k != "dataset_id" and v not in (None, "")}


def run_agent(domain, question, mode, chat=None, max_steps=MAX_STEPS):
    chat = chat or llm_mod.chat
    toolset = TOOLSETS[mode]
    messages = [{"role": "system", "content": SYSTEM.format(domain=domain)}, {"role": "user", "content": question}]
    out = {"answer": "", "steps": 0, "tokens": 0, "queries": [], "spans": []}
    t0 = time.monotonic()
    specs = [spec for spec, _ in toolset.values()]
    for step in range(max_steps):
        # last step without tools: the agent must answer with what it has (eval showed answers lost on step 6)
        t_llm = time.monotonic()
        r = chat(messages, tools=specs if step < max_steps - 1 else None)
        out["spans"].append({"name": "llm", "ms": int((time.monotonic() - t_llm) * 1000), "tokens": r["tokens"]})
        out["steps"] += 1
        out["tokens"] += r["tokens"]
        msg = r["message"]
        messages.append({k: v for k, v in msg.items() if v or k == "content"})
        if not msg["tool_calls"]:
            out["answer"] = msg["content"] or ""
            break
        for call in msg["tool_calls"]:
            name = call["function"]["name"]
            t_tool = time.monotonic()
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
                result = toolset[name][1](domain, args) if name in toolset else {"error": f"unknown tool {name}"}
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                args, result = {}, {"error": f"bad arguments: {e}"}
            ok = isinstance(result, dict) and "error" not in result
            out["spans"].append({"name": name, "ms": int((time.monotonic() - t_tool) * 1000), "ok": ok})
            if name in QUERY_TOOLS:
                out["queries"].append({"dataset_id": args.get("dataset_id", ""), "ok": ok, "params": _params(args),
                                       "result": {"total_count": result.get("total_count"),
                                                  "results": (result.get("results") or [])[:20]} if ok else None})
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": json.dumps(result, ensure_ascii=False, default=str)[:MAX_RESULT_CHARS]})
    out["ms"] = int((time.monotonic() - t0) * 1000)
    out["transcript"] = messages
    return out
