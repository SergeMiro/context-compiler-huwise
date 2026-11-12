"""Evidence contract: what backs an answer. Four checks, kept apart on purpose:
schema_valid (the query passed the field whitelist), executed (the API answered), consistent (every number or name
in the answer comes from a returned result), and semantic correctness, which is NOT checked here: only the golden
evaluation can say whether the right question was asked of the data."""
import json

from evals.runner import norm, numbers

NO_DATA = ("pas de donnees", "aucune donnee", "pas disponible", "n'existe pas", "no data")


def _values(result):
    """Numbers and strings an answer may legitimately quote from one query result."""
    nums, texts = set(), set()
    if isinstance(result.get("total_count"), (int, float)):
        nums.add(float(result["total_count"]))
    for row in result.get("results") or []:
        for v in row.values():
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, (int, float)):
                nums.add(float(v))
            elif isinstance(v, str):
                try:
                    nums.add(float(v.replace(",", ".")))
                except ValueError:
                    if len(v) > 1:
                        texts.add(norm(v))
    return nums, texts


def _close(n, values):
    return any(abs(n - v) <= max(abs(v) * 0.005, 0.05) or round(v) == n or round(v, 1) == n for v in values)


def check(question, answer, queries):
    """queries: [{"dataset_id", "params", "ok", "result"}] in call order. -> evidence dict."""
    done = [q for q in queries if q.get("ok")]
    nums, texts = set(), set()
    for q in done:
        n, t = _values(q.get("result") or {})
        nums |= n
        texts |= t
    asked = set(numbers(question))
    said = [n for n in numbers(answer) if n not in asked]
    a = norm(answer)
    reasons = []
    if any(m in a for m in NO_DATA):
        status = "unverified"
        reasons.append("abstention: nothing to verify against the API")
    elif not done:
        status = "blocked" if said else "unverified"
        reasons.append("no successful query backs this answer")
    elif said and all(_close(n, nums) for n in said):
        status = "verified"
        reasons.append("every number in the answer equals a value returned by the API")
    elif said:
        status = "blocked"
        bad = [n for n in said if not _close(n, nums)]
        reasons.append(f"number(s) not returned by any query: {', '.join(f'{x:g}' for x in bad[:3])}")
    elif any(t in a for t in texts):
        status = "verified"
        reasons.append("the answer quotes a value returned by the API")
    else:
        status = "partially_verified"
        reasons.append("query succeeded, but the answer quotes no returned value")
    last = done[-1] if done else None
    zero = [q for q in done if (q.get("result") or {}).get("total_count") == 0]
    if zero and status == "verified":
        status = "partially_verified"
        reasons.append("a query returned 0 rows: a filter value may be written differently in the data")
    return {"status": status, "reasons": reasons,
            "checks": {"schema_valid": bool(done), "executed": bool(done), "result_consistent": status == "verified",
                       "semantic_correctness": "not checked at runtime (golden eval only)"},
            "dataset_id": last["dataset_id"] if last else None,
            "query": last.get("params") if last else None}


def contract(domain, question, answer, queries, ds_meta=None):
    """Full evidence record for one answer (no API key, no prompt)."""
    ev = check(question, answer, queries)
    ds = ev["dataset_id"]
    return ev | {"source_portal": domain, "source_url": f"https://{domain}/explore/dataset/{ds}/" if ds else None,
                 "schema_version": (ds_meta or {}).get("schema_version"),
                 "data_version": (ds_meta or {}).get("data_version"),
                 "api_result": _short((queries[-1] if queries else {}).get("result"))}


def _short(result):
    if not result:
        return None
    return json.loads(json.dumps({"total_count": result.get("total_count"), "results": (result.get("results") or [])[:3]},
                                 default=str))


def _demo():  # self-check, runs in tests
    q = [{"dataset_id": "d", "params": {}, "ok": True, "result": {"total_count": 23, "results": []}}]
    assert check("Combien de collèges à Dijon ?", "Il y a 23 collèges.", q)["status"] == "verified"
    assert check("Combien de collèges à Dijon ?", "Il y a 25 collèges.", q)["status"] == "blocked"
    assert check("Combien ?", "Il y a 12.", [])["status"] == "blocked"
