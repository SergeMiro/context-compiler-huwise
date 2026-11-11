"""Adaptive router, deterministic rules (RouteLLM idea: pick the cheapest path that is safe for this question;
here the paths differ in tool calls and model calls, not in which model). Low confidence always goes up a level."""
import re

from . import recipes
from .values import norm

POLICY_VERSION = "route-2026-11-11.1"
DEEP_SIGNS = [
    (r"\b(compar\w*|par rapport|versus|vs|difference|evolution|entre .+ et .+|plus que|moins que)\b",
     "comparison or evolution"),
    (r"\b(et|and)\b.*\?$", "several things asked"),
]


def route(domain, question):
    """-> {"route": FAST|STANDARD|DEEP, "reasons": [...], "plan": recipe plan or None, "policy": version}"""
    q = norm(question) + ("?" if question.strip().endswith("?") else "")
    deep = [why for rx, why in DEEP_SIGNS if re.search(rx, q)]
    if deep:
        return {"route": "DEEP", "reasons": deep, "plan": None, "policy": POLICY_VERSION}
    try:
        p = recipes.plan(domain, question)
    except Exception as e:  # value lookup failed (timeout, 5xx): the agent path still works, a guess never runs
        p = {"reject": f"value lookup failed ({type(e).__name__})"}
    if "reject" in p:
        return {"route": "STANDARD", "reasons": [f"no verified recipe: {p['reject']}"], "plan": None,
                "calls": p.get("calls", []), "policy": POLICY_VERSION}
    return {"route": "FAST", "reasons": [f"verified recipe {p['recipe']}, schema {p['schema_hash']} unchanged, "
                                         f"every slot resolved to a stored value"], "plan": p,
            "policy": POLICY_VERSION}
